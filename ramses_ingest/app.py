# -*- coding: utf-8 -*-
"""Main application — wires together scanning, matching, probing, publishing, and preview.

The ``IngestEngine`` class sequences the full pipeline:

    scan_directory → match_clips → probe → build_plans → (user review) → execute_plans
"""

from __future__ import annotations

import os
import time
import concurrent.futures
from pathlib import Path
from typing import Callable

from ramses_ingest.scanner import scan_directory, Clip
from ramses_ingest.matcher import match_clips, NamingRule, MatchResult
from ramses_ingest.prober import probe_file, MediaInfo
from ramses_ingest.publisher import (
    build_plans, execute_plan, resolve_paths, resolve_paths_from_daemon,
    register_ramses_objects, IngestPlan, IngestResult,
)
from ramses_ingest.config import load_rules


class IngestEngine:
    """Orchestrates the full ingest pipeline."""

    def __init__(self) -> None:
        self._project_id: str = ""
        self._project_name: str = ""
        self._project_path: str = ""
        self._step_id: str = "PLATE"
        self._connected: bool = False

        self._existing_sequences: list[str] = []
        self._existing_shots: list[str] = []
        self._shot_objects: dict[str, object] = {}
        self._steps: list[str] = []

        self._rules, self.studio_name = load_rules()

        # OCIO Defaults
        self.ocio_config: str | None = os.getenv("OCIO")
        self.ocio_in: str = "Linear"
        self.ocio_out: str = "sRGB"

    # -- Properties ----------------------------------------------------------

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def project_name(self) -> str:
        return self._project_name

    @property
    def project_path(self) -> str:
        return self._project_path

    @property
    def step_id(self) -> str:
        return self._step_id

    @step_id.setter
    def step_id(self, value: str) -> None:
        self._step_id = value

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def existing_sequences(self) -> list[str]:
        return list(self._existing_sequences)

    @property
    def existing_shots(self) -> list[str]:
        return list(self._existing_shots)

    @property
    def steps(self) -> list[str]:
        return list(self._steps)

    @property
    def rules(self) -> list[NamingRule]:
        return list(self._rules)

    @rules.setter
    def rules(self, value: list[NamingRule]) -> None:
        self._rules = list(value)

    # -- Daemon connection ---------------------------------------------------

    def connect_ramses(self) -> bool:
        """Attempt to connect to the Ramses daemon and cache project info.

        Returns True if the daemon is online and a project is loaded.
        """
        self._connected = False
        try:
            from ramses import Ramses
            ram = Ramses.instance()
            if not ram.online():
                return False

            project = ram.project()
            if project is None:
                return False

            self._project_id = project.shortName()
            self._project_name = project.name()
            self._project_path = project.folderPath()

            # Cache sequences
            self._existing_sequences = []
            for seq in project.sequences():
                sn = seq.shortName()
                self._existing_sequences.append(sn)

            # Cache shots
            self._existing_shots = []
            self._shot_objects = {}
            for shot in project.shots():
                sn = shot.shortName()
                self._existing_shots.append(sn)
                self._shot_objects[sn.upper()] = shot

            # Cache step short names
            self._steps = []
            try:
                from ramses.ram_step import RamStep, StepType
                for step in project.steps(StepType.SHOT_PRODUCTION):
                    self._steps.append(step.shortName())
            except Exception:
                pass
            if not self._steps:
                self._steps = ["PLATE"]

            self._connected = True
            return True

        except Exception:
            return False

    # -- Pipeline stages -----------------------------------------------------

    def load_delivery(
        self,
        paths: str | Path | list[str | Path],
        rules: list[NamingRule] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[IngestPlan]:
        """Scan one or more delivery paths and return plans for user review.

        Steps: scan → match → probe → build_plans → resolve_paths.
        """
        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        if not isinstance(paths, list):
            paths = [paths]

        all_clips: list[Clip] = []
        seen_seq_keys: set[tuple[str, str, str]] = set() # (dir, base, ext)

        for p in paths:
            _log(f"Scanning {p}...")
            if os.path.isfile(p):
                # Specific file selection
                from ramses_ingest.scanner import RE_FRAME_PADDING
                name = os.path.basename(p)
                m = RE_FRAME_PADDING.match(name)
                if m:
                    # It's part of a sequence, find the whole sequence in parent
                    parent = os.path.dirname(p)
                    base = m.group("base")
                    ext = m.group("ext").lower()
                    key = (parent, base, ext)
                    if key in seen_seq_keys:
                        continue
                    
                    clips = scan_directory(parent)
                    # Filter to only the sequence this file belongs to
                    seq_clips = [c for c in clips if c.base_name == base and c.extension == ext]
                    all_clips.extend(seq_clips)
                    seen_seq_keys.add(key)
                else:
                    # Single movie or image
                    all_clips.append(Clip(
                        base_name=os.path.splitext(name)[0],
                        extension=os.path.splitext(name)[1].lstrip(".").lower(),
                        directory=Path(os.path.dirname(p)),
                        first_file=str(p)
                    ))
            else:
                # Directory scan
                new_clips = scan_directory(p)
                for c in new_clips:
                    if c.is_sequence:
                        key = (str(c.directory), c.base_name, c.extension.lower())
                        if key in seen_seq_keys:
                            continue
                        seen_seq_keys.add(key)
                    all_clips.append(c)

        _log(f"  Found {len(all_clips)} clip(s).")

        effective_rules = rules if rules is not None else (self._rules or None)
        _log("Matching clips to naming rules...")
        matches = match_clips(all_clips, effective_rules)

        _log("Probing media info (Parallel)...")
        media_infos: dict[str, MediaInfo] = {}
        
        def _probe_one(clip: Clip) -> tuple[str, MediaInfo]:
            try:
                return clip.first_file, probe_file(clip.first_file)
            except Exception:
                return clip.first_file, MediaInfo()

        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            future_to_clip = {executor.submit(_probe_one, c): c for c in all_clips}
            for future in concurrent.futures.as_completed(future_to_clip):
                file_path, info = future.result()
                media_infos[file_path] = info

        _log("Building ingest plans...")
        plans = build_plans(
            matches,
            media_infos,
            project_id=self._project_id or "PROJ",
            project_name=self._project_name or self._project_id or "Project",
            step_id=self._step_id,
            existing_sequences=self._existing_sequences,
            existing_shots=self._existing_shots,
        )

        # Resolve target paths
        if self._connected and self._shot_objects:
            resolve_paths_from_daemon(plans, self._shot_objects)
        if self._project_path:
            # Fill in any plans that the daemon didn't resolve
            resolve_paths(
                [p for p in plans if not p.target_publish_dir],
                self._project_path,
            )

        matched = sum(1 for p in plans if p.match.matched)
        _log(f"Ready: {matched} matched, {len(plans) - matched} unmatched.")
        return plans

    def execute(
        self,
        plans: list[IngestPlan],
        generate_thumbnails: bool = True,
        generate_proxies: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        update_status: bool = False,
    ) -> list[IngestResult]:
        """Execute all approved (can_execute) plans.

        Returns one ``IngestResult`` per plan.
        """
        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        if not self._connected:
            _log("ERROR: Not connected to Ramses. Ingest aborted.")
            return [IngestResult(plan=p, error="No Ramses connection") for p in plans]

        executable = [p for p in plans if p.can_execute]
        total = len(executable)
        _log(f"Starting ingest for {total} clips...")

        # Pre-fetch caches for speed
        _log("Fetching project metadata...")
        from ramses.daemon_interface import RamDaemonInterface
        daemon = RamDaemonInterface.instance()
        seq_cache = {s.shortName().upper(): s.uuid() for s in daemon.getObjects("RamSequence")}
        shot_cache = self._shot_objects # Already cached in connect_ramses

        # Phase 1: Register Ramses Objects (Sequential, Thread-Safe)
        _log("Phase 1: Registering shots in Ramses database...")
        for i, plan in enumerate(executable, 1):
            try:
                register_ramses_objects(plan, lambda _: None, sequence_cache=seq_cache)
            except Exception as exc:
                _log(f"  Warning: Failed to register {plan.shot_id}: {exc}")

        # Phase 2: Parallel Execution (Copy + FFmpeg)
        _log("Phase 2: Processing files (Parallel)...")
        results: list[IngestResult] = []
        
        # Initialize results with failed entries for non-executable plans
        # so they show up in the report as skipped/failed.
        executed_plans = set()

        # Helper for thread pool
        def _run_one(plan: IngestPlan) -> IngestResult:
            return execute_plan(
                plan,
                generate_thumbnail=generate_thumbnails,
                generate_proxy=generate_proxies,
                progress_callback=None,
                ocio_config=self.ocio_config,
                ocio_in=self.ocio_in,
                ocio_out=self.ocio_out,
                skip_ramses_registration=True,
            )

        if executable:
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                future_to_plan = {executor.submit(_run_one, p): p for p in executable}
                
                for i, future in enumerate(concurrent.futures.as_completed(future_to_plan), 1):
                    plan = future_to_plan[future]
                    executed_plans.add(id(plan))
                    try:
                        res = future.result()
                        results.append(res)
                        prefix = "OK" if res.success else "FAILED"
                        _log(f"[{i}/{total}] {res.plan.shot_id}: {prefix}")
                        if not res.success:
                            _log(f"  Error: {res.error}")
                    except Exception as exc:
                        _log(f"[{i}/{total}] CRITICAL ERROR processing {plan.shot_id}: {exc}")
                        results.append(IngestResult(plan=plan, error=str(exc)))

        # Add skipped plans to results for the report
        for p in plans:
            if id(p) not in executed_plans:
                results.append(IngestResult(plan=p, error=p.error or "Skipped or not executable"))

        # Phase 3: Update Lifecycle Status (Feature 5)
        if update_status:
            _log("Phase 3: Finalizing production statuses in Ramses...")
            from ramses_ingest.publisher import update_ramses_status
            for res in results:
                if res.success:
                    try:
                        update_ramses_status(res.plan, "OK", shot_cache=shot_cache)
                    except Exception:
                        pass

        # Phase 4: Generate Report (Feature 4)
        _log(f"Phase 4: Generating ingest manifest for {len(results)} items...")
        from ramses_ingest.reporting import generate_html_report
        report_name = f"Ingest_Report_{self.project_id}_{int(time.time())}.html"
        report_path = os.path.join(self.project_path, "_ingest_reports", report_name) if self.project_path else report_name
        
        if generate_html_report(results, report_path, studio_name=self.studio_name):
            _log(f"  Manifest created: {report_path}")
        else:
            _log(f"  ERROR: Failed to write manifest to {report_path}")

        succeeded = sum(1 for r in results if r.success)
        _log(f"Done: {succeeded}/{len(plans)} succeeded.")
        return results


def main():
    """CLI / GUI entry point."""
    from ramses_ingest.gui import launch_gui
    launch_gui()

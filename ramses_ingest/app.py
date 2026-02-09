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

from ramses_ingest.scanner import scan_directory, Clip, RE_FRAME_PADDING
from ramses_ingest.matcher import match_clips, NamingRule, MatchResult
from ramses_ingest.prober import probe_file, MediaInfo, flush_cache
from ramses_ingest.publisher import (
    build_plans, execute_plan, resolve_paths, resolve_paths_from_daemon,
    register_ramses_objects, IngestPlan, IngestResult, check_for_duplicates,
    update_ramses_status
)


def _optimal_io_workers() -> int:
    """Calculate optimal thread count for I/O-bound operations.

    For I/O-bound work (file copying, network, ffprobe), use more threads
    than CPU cores. Common pattern: min(32, cpu_count + 4).

    Returns:
        Optimal number of worker threads (typically 8-32).
    """
    return min(32, (os.cpu_count() or 1) + 4)
from ramses_ingest.config import load_rules
from ramses_ingest.reporting import generate_html_report, generate_json_audit_trail
from ramses_ingest.path_utils import normalize_path, validate_path_within_root


class IngestEngine:
    """Orchestrates the full ingest pipeline."""

    def __init__(self, debug_mode: bool = False) -> None:
        self._project_id: str = ""
        self._project_name: str = ""
        self._project_path: str = ""
        self._step_id: str = "PLATE"
        self._connected: bool = False
        self._debug_mode: bool = debug_mode

        # Project Standards (loaded from Ramses - no defaults!)
        self._project_fps: float | None = None
        self._project_width: int | None = None
        self._project_height: int | None = None
        
        # Sequence Overrides: {SEQ_NAME: (fps, width, height)}
        self._sequence_settings: dict[str, tuple[float, int, int]] = {}

        self._existing_sequences: list[str] = []
        self._existing_shots: list[str] = []
        self._shot_objects: dict[str, object] = {}
        self._sequence_uuids: dict[str, str] = {}  # Cache sequence UUIDs for execute phase
        self._steps: list[str] = []
        self._operator_name: str = "Unknown"

        self._rules, self.studio_name = load_rules()
        self.last_report_path: str | None = None

        # OCIO Defaults
        self.ocio_config: str | None = os.getenv("OCIO")
        self.ocio_in: str = "sRGB"

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

    @property
    def debug_mode(self) -> bool:
        return self._debug_mode

    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        self._debug_mode = value

    # -- Daemon connection ---------------------------------------------------

    def connect_ramses(self) -> bool:
        """Attempt to connect to the Ramses daemon and cache project info.

        Returns True if the daemon is online and a project is loaded.
        """
        self._connected = False
        try:
            from ramses import Ramses
            from ramses.constants import LogLevel
            ram = Ramses.instance()

            # Configure logging based on debug mode setting
            if self._debug_mode:
                ram.settings().debugMode = True
                ram.settings().logLevel = LogLevel.Debug
            else:
                ram.settings().debugMode = False
                ram.settings().logLevel = LogLevel.Info

            # If the singleton was already created but is offline, explicitly try to connect
            if not ram.online():
                ram.connect()

            if not ram.online():
                return False

            project = ram.project()
            if project is None:
                return False

            self._project_id = project.shortName()
            self._project_name = project.name()
            self._project_path = project.folderPath()

            # Naming Validation: Ensure the project ID is compatible with Ramses API regex (10-char limit)
            from ramses.file_info import RamFileInfo
            test_info = RamFileInfo()
            test_info.project = self._project_id
            test_info.ramType = "S"
            test_info.shortName = "SHOT"
            if not test_info.setFileName(test_info.fileName()):
                old_id = self._project_id
                self._project_id = old_id[:10]
                from ramses.logger import log
                from ramses.constants import LogLevel
                log(f"Project Short Name '{old_id}' is too long for Ramses (max 10 chars). Truncating to '{self._project_id}'.", LogLevel.Warning)
            
            # Retrieve Project Standards
            self._project_fps = project.framerate()
            self._project_width = project.width()
            self._project_height = project.height()

            # Cache User/Operator
            self._operator_name = "Unknown"
            user = ram.user()
            if user:
                self._operator_name = user.name()

            # Relational Batching: Fetch only what's needed for this project
            # to stay below the 64KB socket limit.
            from ramses.daemon_interface import RamDaemonInterface
            daemon = RamDaemonInterface.instance()
            project_uuid = project.uuid()

            # Cache sequences with UUIDs and Standards
            self._existing_sequences = []
            self._sequence_uuids = {}
            self._sequence_settings = {}
            all_seqs = daemon.getObjects("RamSequence")
            for seq in all_seqs:
                if seq.get("project") == project_uuid:
                    sn = seq.shortName()
                    self._existing_sequences.append(sn)
                    self._sequence_uuids[sn.upper()] = seq.uuid()
                    # Store sequence-specific overrides
                    self._sequence_settings[sn.upper()] = (
                        seq.framerate(), seq.width(), seq.height()
                    )

            # Cache shots
            self._existing_shots = []
            self._shot_objects = {}
            all_shots = daemon.getObjects("RamShot")
            for shot in all_shots:
                if shot.get("project") == project_uuid:
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
            
            if self._steps:
                # If we were on default "PLATE" but it's not in the list, 
                # switch to the first valid project step.
                if self._step_id == "PLATE" and "PLATE" not in self._steps:
                    self._step_id = self._steps[0]
            else:
                self._steps = ["PLATE"]

            self._connected = True
            return True

        except Exception:
            # Connection failed - ensure no defaults are used
            self._project_fps = None
            self._project_width = None
            self._project_height = None
            return False

    def _require_connection(self) -> None:
        """Raise an error if not connected to Ramses daemon.

        Call this at the start of any operation that requires Ramses.
        """
        if not self._connected:
            raise RuntimeError(
                "Not connected to Ramses daemon. "
                "Ensure the Ramses application is running and a project is loaded."
            )
        if self._project_fps is None or self._project_width is None:
            raise RuntimeError(
                "Project settings not loaded from Ramses. "
                "Connection may have failed or project is not properly configured."
            )

    # -- Pipeline stages -----------------------------------------------------

    def load_delivery(
        self,
        paths: str | Path | list[str | Path],
        rules: list[NamingRule] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[IngestPlan]:
        """Scan one or more delivery paths and return plans for user review.

        Steps: scan → match → probe → build_plans → resolve_paths.

        Raises:
            RuntimeError: If not connected to Ramses daemon.
        """
        self._require_connection()

        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        if not isinstance(paths, list):
            paths = [paths]

        # Normalize all paths to forward slashes for consistency
        paths = [normalize_path(p) for p in paths]

        all_clips: list[Clip] = []
        seen_seq_keys: set[tuple[str, str, str]] = set() # (dir, base, ext)

        # UX Magic: If user selects multiple files from same sequence, consolidate them instantly
        # rather than performing N full-directory rescans.
        file_paths = [p for p in paths if os.path.isfile(p)]
        dir_paths = [p for p in paths if os.path.isdir(p)]

        # 1. Process files with grouping
        if file_paths:
            if progress_callback: progress_callback(f"Consolidating {len(file_paths)} files...")
            from ramses_ingest.scanner import RE_FRAME_PADDING, MOVIE_EXTENSIONS
            
            temp_buckets: dict[tuple[str, str, str], list[tuple[int, str, int]]] = {}
            standalone: list[Clip] = []

            for p in file_paths:
                name = os.path.basename(p)
                ext = os.path.splitext(name)[1].lstrip(".").lower()
                m = RE_FRAME_PADDING.match(name)
                
                # Logic: Only group if it matches the padding regex AND is not a movie
                if m and ext not in MOVIE_EXTENSIONS:
                    base = m.group("base")
                    frame_str = m.group("frame")
                    key = (os.path.dirname(p), base, ext)
                    temp_buckets.setdefault(key, []).append((int(frame_str), p, len(frame_str)))
                else:
                    standalone.append(Clip(
                        base_name=os.path.splitext(name)[0],
                        extension=ext,
                        directory=Path(os.path.dirname(p)),
                        first_file=str(p)
                    ))
            
            # Convert buckets to sequence Clips
            for (dir_path, base, ext), frames in temp_buckets.items():
                frames.sort()
                all_clips.append(Clip(
                    base_name=base,
                    extension=ext,
                    directory=Path(dir_path),
                    is_sequence=True,
                    frames=[f[0] for f in frames],
                    first_file=frames[0][1],
                    _padding=frames[0][2]
                ))
                seen_seq_keys.add((dir_path, base, ext))
            all_clips.extend(standalone)

        # 2. Process directories
        for p in dir_paths:
            if progress_callback: progress_callback(f"Scanning directory: {os.path.basename(p)}...")
            new_clips = scan_directory(p)
            for c in new_clips:
                if c.is_sequence:
                    key = (str(c.directory), c.base_name, c.extension.lower())
                    if key in seen_seq_keys: continue
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=_optimal_io_workers()) as executor:
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

        # Enhancement #9: Check for duplicate versions
        _log("Checking for duplicate versions...")
        from ramses_ingest.publisher import check_for_duplicates, check_for_path_collisions
        check_for_duplicates(plans)
        
        # New: Check for collisions within the current batch
        check_for_path_collisions(plans)

        matched = sum(1 for p in plans if p.match.matched)
        duplicates = sum(1 for p in plans if p.is_duplicate)
        if duplicates > 0:
            _log(f"Ready: {matched} matched, {len(plans) - matched} unmatched, {duplicates} duplicates detected.")
        else:
            _log(f"Ready: {matched} matched, {len(plans) - matched} unmatched.")
        return plans

    def execute(
        self,
        plans: list[IngestPlan],
        generate_thumbnails: bool = True,
        generate_proxies: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        update_status: bool = False,
        export_json_audit: bool = False,
        dry_run: bool = False,
        fast_verify: bool = False,
    ) -> list[IngestResult]:
        """Execute all approved (can_execute) plans.

        Args:
            plans: List of IngestPlan objects to execute
            generate_thumbnails: Generate JPEG previews
            generate_proxies: Generate MP4 proxies
            progress_callback: Optional callback for progress updates
            update_status: Update Ramses production status to "OK" on success
            export_json_audit: Generate machine-readable JSON audit trail
            dry_run: Preview operations without actually copying files (Enhancement #8)
            fast_verify: If True, only verify MD5 for first/middle/last frames.

        Returns one ``IngestResult`` per plan.
        """
        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        try:
            self._require_connection()
        except RuntimeError as e:
            _log(f"ERROR: {e}")
            return [IngestResult(plan=p, error=str(e)) for p in plans]

        executable = [p for p in plans if p.can_execute]
        
        # 0. State Assignment: Set state based on user choice before path resolution
        target_state = "OK" if update_status else "WIP"
        for p in executable:
            # HERO HIERARCHY: Only 'No Resource' clips update the shot status
            if not p.resource:
                p.state = target_state
            else:
                # Resources stay in the current state or default to WIP 
                # but we don't push a status change for them in Phase 1
                p.state = "WIP" 
            
            # Clear previous resolution to force fresh path building with new state
            p.target_publish_dir = ""
            p.target_preview_dir = ""
            
        # Re-resolve paths to include the correct state in the folder name
        if self._connected and self._shot_objects:
            resolve_paths_from_daemon(executable, self._shot_objects)
        if self._project_path:
            resolve_paths(
                [p for p in executable if not p.target_publish_dir],
                self._project_path,
            )

        total = len(executable)
        _log(f"Starting ingest for {total} clips...")

        # Enhancement: Disk Space Guard
        if not dry_run and executable:
            total_required = sum(p.match.clip.frame_count * 1024 * 1024 if p.match.clip.is_sequence else 10 * 1024 * 1024 for p in executable) # Rough estimate if media info missing
            # More accurate if we have media info
            total_required = 0
            for p in executable:
                if p.match.clip.is_sequence:
                    # Estimate based on first file size * frame count
                    try:
                        sz = os.path.getsize(p.match.clip.first_file)
                        total_required += sz * p.match.clip.frame_count
                    except Exception:
                        total_required += 10 * 1024 * 1024 * p.match.clip.frame_count # 10MB fallback
                else:
                    try:
                        total_required += os.path.getsize(p.match.clip.first_file)
                    except Exception:
                        total_required += 500 * 1024 * 1024 # 500MB fallback

            from ramses_ingest.publisher import check_disk_space
            ok, err = check_disk_space(self.project_path or ".", total_required)
            if not ok:
                _log(f"CRITICAL: {err}")
                return [IngestResult(plan=p, error=err) for p in plans]

        # Reuse cached metadata from connect_ramses (no redundant daemon queries)
        seq_cache = self._sequence_uuids  # Already fetched in connect phase
        shot_cache = self._shot_objects   # Already cached in connect_ramses

        # Phase 1: Register Ramses Objects (Sequential, Thread-Safe)
        if not dry_run:
            _log("Phase 1: Registering shots in Ramses database...")
            for i, plan in enumerate(executable, 1):
                try:
                    # HERO HIERARCHY: Only 'No Resource' clips are allowed to update the shot status.
                    # If a resource exists, we register the file but skip the status/state change.
                    skip_status = bool(plan.resource)
                    if skip_status:
                        _log(f"  Registering auxiliary resource: {plan.resource} for {plan.shot_id} (Skipping status update)")
                    
                    from ramses_ingest.publisher import register_ramses_objects
                    register_ramses_objects(
                        plan, 
                        lambda _: None, 
                        sequence_cache=seq_cache,
                        skip_status_update=skip_status
                    )
                except Exception as exc:
                    _log(f"  Warning: Failed to register {plan.shot_id}: {exc}")
        else:
            _log("Dry-run mode: Skipping Ramses registration...")

        # Phase 2: Parallel Execution (Copy + FFmpeg)
        action_msg = "Simulating" if dry_run else "Processing"
        _log(f"Phase 2: {action_msg} files (Parallel)...")
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
                ocio_out="sRGB",
                skip_ramses_registration=True,
                dry_run=dry_run,  # Enhancement #8: Dry-run mode
                fast_verify=fast_verify,
            )

        if executable:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_optimal_io_workers()) as executor:
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

        # Phase 4: Generate Reports (HTML + JSON Audit Trail)
        _log(f"Phase 4: Generating ingest manifest for {len(results)} items...")
        from ramses_ingest.reporting import generate_html_report, generate_json_audit_trail

        timestamp = int(time.time())
        report_dir = os.path.join(self.project_path, "_ingest_reports") if self.project_path else "."

        # Generate client-facing HTML report
        html_name = f"Ingest_Report_{self.project_id}_{timestamp}.html"
        html_path = os.path.join(report_dir, html_name)
        self.last_report_path = html_path

        if generate_html_report(results, html_path, studio_name=self.studio_name, operator=self._operator_name):
            _log(f"  HTML manifest created: {html_path}")
        else:
            _log(f"  ERROR: Failed to write HTML manifest to {html_path}")

        # Generate machine-readable JSON audit trail (optional, for database integration)
        if export_json_audit:
            json_name = f"Ingest_Audit_{self.project_id}_{timestamp}.json"
            json_path = os.path.join(report_dir, json_name)

            if generate_json_audit_trail(results, json_path, project_id=self.project_id, operator=self._operator_name):
                _log(f"  JSON audit trail created: {json_path}")
            else:
                _log(f"  WARNING: Failed to write JSON audit trail to {json_path}")

        succeeded = sum(1 for r in results if r.success)
        _log(f"Done: {succeeded}/{len(plans)} succeeded.")

        # Flush metadata cache to disk (batched write for performance)
        flush_cache()

        return results


def main():
    """CLI / GUI entry point."""
    from ramses_ingest.gui import launch_gui
    launch_gui()

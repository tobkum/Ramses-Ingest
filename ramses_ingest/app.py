# -*- coding: utf-8 -*-
"""Main application — wires together scanning, matching, probing, publishing, and preview.

The ``IngestEngine`` class sequences the full pipeline:

    scan_directory → match_clips → probe → build_plans → (user review) → execute_plans
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ramses_ingest.scanner import scan_directory, Clip
from ramses_ingest.matcher import match_clips, NamingRule, MatchResult
from ramses_ingest.prober import probe_file, MediaInfo
from ramses_ingest.publisher import (
    build_plans, execute_plan, resolve_paths, resolve_paths_from_daemon,
    IngestPlan, IngestResult,
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

        self._rules: list[NamingRule] = load_rules()

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
        path: str | Path,
        rules: list[NamingRule] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[IngestPlan]:
        """Scan a delivery folder and return plans for user review.

        Steps: scan → match → probe → build_plans → resolve_paths.
        """
        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        _log(f"Scanning {path}...")
        clips = scan_directory(path)
        _log(f"  Found {len(clips)} clip(s).")

        effective_rules = rules if rules is not None else (self._rules or None)
        _log("Matching clips to naming rules...")
        matches = match_clips(clips, effective_rules)

        _log("Probing media info...")
        media_infos: dict[str, MediaInfo] = {}
        for clip in clips:
            try:
                media_infos[clip.first_file] = probe_file(clip.first_file)
            except Exception:
                media_infos[clip.first_file] = MediaInfo()

        _log("Building ingest plans...")
        plans = build_plans(
            matches,
            media_infos,
            project_id=self._project_id or "PROJ",
            step_id=self._step_id,
            existing_sequences=self._existing_sequences,
            existing_shots=self._existing_shots,
        )

        # Resolve target paths
        if self._connected and self._shot_objects:
            resolve_paths_from_daemon(plans, self._shot_objects)
        if self._project_path:
            # Fill in any plans that the daemon didn't resolve
            for plan in plans:
                if plan.can_execute and not plan.target_publish_dir:
                    resolve_paths(
                        [plan],
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
    ) -> list[IngestResult]:
        """Execute all approved (can_execute) plans.

        Returns one ``IngestResult`` per plan.
        """
        def _log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        results: list[IngestResult] = []
        executable = [p for p in plans if p.can_execute]
        total = len(executable)

        for i, plan in enumerate(executable, 1):
            _log(f"[{i}/{total}] {plan.sequence_id}/{plan.shot_id}...")
            result = execute_plan(
                plan,
                generate_thumbnail=generate_thumbnails,
                generate_proxy=generate_proxies,
                progress_callback=_log,
            )
            results.append(result)
            if result.success:
                _log(f"  OK — {result.frames_copied} file(s) copied.")
            else:
                _log(f"  FAILED: {result.error}")

        succeeded = sum(1 for r in results if r.success)
        _log(f"Done: {succeeded}/{total} succeeded.")
        return results


def main():
    """CLI / GUI entry point."""
    from ramses_ingest.gui import launch_gui
    launch_gui()

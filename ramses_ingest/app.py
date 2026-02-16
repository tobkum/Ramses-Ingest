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
from typing import Callable, List, Dict, Optional, Any
from collections import Counter

from ramses_ingest.scanner import scan_directory, Clip, RE_FRAME_PADDING, group_files
from ramses_ingest.matcher import match_clips, NamingRule, MatchResult
from ramses_ingest.prober import probe_file, MediaInfo, flush_cache
from ramses_ingest.publisher import (
    build_plans, execute_plan, resolve_paths, resolve_paths_from_daemon,
    register_ramses_objects, IngestPlan, IngestResult, check_for_duplicates,
    update_ramses_status, check_disk_space, check_for_path_collisions
)
from ramses_ingest.config import load_rules
from ramses_ingest.reporting import generate_html_report, generate_json_audit_trail
from ramses_ingest.path_utils import normalize_path, validate_path_within_root


def _optimal_io_workers() -> int:
    """Calculate optimal thread count for I/O-bound operations."""
    return min(32, (os.cpu_count() or 1) + 4)


def _generate_one_thumbnail(job_data):
    """Worker function for parallel thumbnail generation."""
    try:
        from ramses_ingest.preview import generate_thumbnail
        clip, path = job_data['clip'], job_data['path']
        ok = generate_thumbnail(clip, path, ocio_config=job_data['ocio_config'], ocio_in=job_data['ocio_in'])
        return (path if ok else None, ok)
    except Exception:
        return (None, False)


class IngestEngine:
    """Orchestrates the full ingest pipeline."""

    def __init__(self, debug_mode: bool = False) -> None:
        self._project_id = ""; self._project_name = ""; self._project_path = ""
        self._step_id = "PLATE"; self._connected = False; self._debug_mode = debug_mode
        self._project_fps = None; self._project_width = None; self._project_height = None; self._project_par = 1.0
        self._sequence_settings = {}; self._existing_sequences = []; self._existing_shots = []
        self._shot_objects = {}; self._sequence_uuids = {}; self._operator_name = "Unknown"
        self._rules, self.studio_name, self.studio_logo = load_rules()
        self.last_report_path = None
        self.ocio_config = os.getenv("OCIO"); self.ocio_in = "sRGB"

    # -- Properties ----------------------------------------------------------

    @property
    def project_id(self) -> str: return self._project_id
    @property
    def project_name(self) -> str: return self._project_name
    @property
    def project_path(self) -> str: return self._project_path
    @property
    def step_id(self) -> str: return self._step_id
    @step_id.setter
    def step_id(self, value: str) -> None: self._step_id = value
    @property
    def connected(self) -> bool: return self._connected
    @property
    def existing_sequences(self) -> list[str]: return list(self._existing_sequences)
    @property
    def existing_shots(self) -> list[str]: return list(self._existing_shots)
    @property
    def steps(self) -> list[str]: return list(self._steps)
    @property
    def rules(self) -> list[NamingRule]: return list(self._rules)
    @rules.setter
    def rules(self, value: list[NamingRule]) -> None: self._rules = list(value)
    @property
    def debug_mode(self) -> bool: return self._debug_mode
    @debug_mode.setter
    def debug_mode(self, value: bool) -> None: self._debug_mode = value

    # -- Daemon connection ---------------------------------------------------

    def connect_ramses(self) -> bool:
        """Attempt to connect to the Ramses daemon and cache project info."""
        self._connected = False
        try:
            from ramses import Ramses
            from ramses.constants import LogLevel
            ram = Ramses.instance()
            ram.settings().debugMode = self._debug_mode
            ram.settings().logLevel = LogLevel.Debug if self._debug_mode else LogLevel.Info
            if not ram.online(): ram.connect()
            if not ram.online(): return False
            project = ram.project()
            if project is None: return False

            self._project_id, self._project_name, self._project_path = project.shortName(), project.name(), project.folderPath()
            self._project_fps, self._project_width, self._project_height, self._project_par = project.framerate(), project.width(), project.height(), project.pixelAspectRatio()
            
            user = ram.user()
            if user: self._operator_name = user.name()

            self._existing_sequences, self._sequence_uuids, self._sequence_settings = [], {}, {}
            for seq in project.sequences():
                sn = seq.shortName()
                if not sn or not seq.uuid(): continue
                self._existing_sequences.append(sn); self._sequence_uuids[sn.upper()] = seq.uuid()
                self._sequence_settings[sn.upper()] = (seq.framerate(), seq.width(), seq.height(), seq.pixelAspectRatio())

            self._existing_shots, self._shot_objects = [], {}
            for shot in project.shots(lazyLoading=False):
                sn = shot.shortName()
                if not sn: continue
                self._existing_shots.append(sn); self._shot_objects[sn.upper()] = shot

            self._steps = []
            try:
                from ramses.ram_step import StepType
                for step in project.steps(StepType.SHOT_PRODUCTION): self._steps.append(step.shortName())
            except Exception: pass
            if self._steps:
                if self._step_id == "PLATE" and "PLATE" not in self._steps: self._step_id = self._steps[0]
            else: self._steps = ["PLATE"]

            self._connected = True; return True
        except Exception:
            self._project_fps = None; self._project_width = None; self._project_height = None; return False

    def _require_connection(self) -> None:
        if not self._connected or self._project_fps is None:
            raise RuntimeError("Not connected to Ramses or project settings not loaded.")

    # -- Pipeline stages -----------------------------------------------------

    def load_delivery(self, paths: str | Path | list[str | Path], rules: list[NamingRule] | None = None, progress_callback: Callable[[str], None] | None = None) -> list[IngestPlan]:
        self._require_connection()
        _log = lambda m: progress_callback(m) if progress_callback else None
        if not isinstance(paths, list): paths = [paths]
        paths = [normalize_path(p) for p in paths]
        
        all_candidate_files = []
        for p in paths:
            if os.path.isfile(p): all_candidate_files.append(p)
            elif os.path.isdir(p):
                for root, _, filenames in os.walk(p):
                    for f in filenames: all_candidate_files.append(os.path.join(root, f))

        all_clips = group_files(all_candidate_files); _log(f"  Found {len(all_clips)} clip(s).")
        matches = match_clips(all_clips, rules if rules is not None else self._rules)

        _log("Probing media info...")
        media_infos = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=_optimal_io_workers()) as executor:
            fut = {executor.submit(lambda c: (c.first_file, probe_file(c.first_file)), cl): cl for cl in all_clips}
            for f in concurrent.futures.as_completed(fut):
                fp, info = f.result(); media_infos[fp] = info

        plans = build_plans(matches, media_infos, project_id=self._project_id or "PROJ", project_name=self._project_name or "Project", step_id=self._step_id, existing_sequences=self._existing_sequences, existing_shots=self._existing_shots)
        if self._connected and self._shot_objects: resolve_paths_from_daemon(plans, self._shot_objects)
        if self._project_path: resolve_paths([p for p in plans if not p.target_publish_dir], self._project_path)
        
        check_for_duplicates(plans); check_for_path_collisions(plans)
        return plans

    def execute(self, plans: list[IngestPlan], generate_thumbnails: bool = True, generate_proxies: bool = False, progress_callback: Callable[[str], None] | None = None, update_status: bool = False, export_json_audit: bool = False, dry_run: bool = False, fast_verify: bool = True) -> list[IngestResult]:
        _log = lambda m: progress_callback(m) if progress_callback else None
        try: self._require_connection()
        except RuntimeError as e: return [IngestResult(plan=p, error=str(e)) for p in plans]

        executable = [p for p in plans if p.can_execute]
        target_state = "OK" if update_status else "WIP"
        
        to_resolve = []
        for p in executable:
            if not p.resource and p.state != target_state:
                p.state = target_state; p.target_publish_dir = ""; p.target_preview_dir = ""; to_resolve.append(p)
        
        if to_resolve:
            if self._connected and self._shot_objects: resolve_paths_from_daemon(to_resolve, self._shot_objects)
            if self._project_path: resolve_paths([p for p in to_resolve if not p.target_publish_dir], self._project_path)

        if not dry_run and executable:
            total_req = 0
            for p in executable:
                try:
                    fp = p.match.clip.first_file
                    if fp: total_req += os.path.getsize(fp) * (p.match.clip.frame_count if p.match.clip.is_sequence else 1)
                    else: total_req += 500 * 1024 * 1024
                except Exception: total_req += 500 * 1024 * 1024
            ok, err = check_disk_space(self.project_path or ".", total_req)
            if not ok: return [IngestResult(plan=p, error=err) for p in plans]

        if not dry_run:
            _log("Phase 1: Database Registration...")
            registered = set()
            for plan in executable:
                rk = (plan.shot_id.upper(), plan.sequence_id.upper())
                if rk not in registered:
                    try:
                        register_ramses_objects(plan, lambda _: None, sequence_cache=self._sequence_uuids, shot_cache=self._shot_objects, skip_status_update=bool(plan.resource))
                        registered.add(rk)
                    except Exception as e: _log(f"  Warning: DB Fail {plan.shot_id}: {e}")
                elif not plan.resource: update_ramses_status(plan, plan.state, shot_cache=self._shot_objects)

        _log("Phase 2: Data Transfer...")
        results, executed_ids = [], set()
        if executable:
            max_w = _optimal_io_workers()
            copy_w_per_plan = max(1, 32 // min(len(executable), max_w))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as executor:
                fut_to_p = {executor.submit(execute_plan, p, generate_thumbnail=generate_thumbnails, generate_proxy=generate_proxies, ocio_config=self.ocio_config, ocio_in=p.colorspace_override or self.ocio_in, skip_ramses_registration=True, dry_run=dry_run, fast_verify=fast_verify, copy_max_workers=copy_w_per_plan): p for p in executable}
                for i, f in enumerate(concurrent.futures.as_completed(fut_to_p), 1):
                    res = f.result(); results.append(res); executed_ids.add(id(res.plan))
                    _log(f"[{i}/{len(executable)}] {res.plan.shot_id}: {'OK' if res.success else 'FAILED'}")

        for p in plans:
            if id(p) not in executed_ids: results.append(IngestResult(plan=p, error=p.error or "Skipped"))

        jobs = [(r, r._thumbnail_job) for r in results if hasattr(r, '_thumbnail_job') and r._thumbnail_job]
        if jobs and generate_thumbnails:
            _log(f"Phase 2.5: Thumbnails...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                f_to_r = {executor.submit(_generate_one_thumbnail, j): r for r, j in jobs}
                for f in concurrent.futures.as_completed(f_to_r):
                    path, ok = f.result()
                    if ok: f_to_r[f].preview_path = path

        if update_status:
            for res in results:
                if res.success and not res.plan.resource: update_ramses_status(res.plan, "OK", shot_cache=self._shot_objects)

        _log("Phase 4: Reports...")
        ts, report_dir = int(time.time()), (os.path.join(self.project_path, "_ingest_reports") if self.project_path else ".")
        h_path = os.path.join(report_dir, f"Ingest_Report_{self.project_id}_{ts}.html")
        if generate_html_report(results, h_path, studio_name=self.studio_name, studio_logo_path=self.studio_logo, operator=self._operator_name):
            self.last_report_path = h_path; _log(f"  Report: {h_path}")
        
        if export_json_audit:
            j_path = os.path.join(report_dir, f"Ingest_Audit_{self.project_id}_{ts}.json")
            generate_json_audit_trail(results, j_path, project_id=self.project_id, operator=self._operator_name)

        flush_cache(); return results


def main():
    from ramses_ingest.gui import launch_gui
    launch_gui()

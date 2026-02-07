# -*- coding: utf-8 -*-
"""Ramses pipeline publishing — create shots/sequences and ingest footage.

Responsibilities:
    - Create RamSequence / RamShot objects in Ramses via the Daemon API.
    - Copy (or hardlink) source frames into the Ramses folder tree with
      correct naming: ``{PROJECT}_S_{SHOT}_{STEP}.{padding}.{ext}``
    - Write ``_ramses_data.json`` metadata for each published version.
    - Update shot status in Ramses.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from ramses_ingest.scanner import Clip
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo

from ramses.file_info import RamFileInfo
from ramses.constants import ItemType

# Thread-safe cache lock for Ramses object registration
_RAMSES_CACHE_LOCK = threading.Lock()


@dataclass
class IngestPlan:
    """A fully resolved plan for ingesting one clip into the Ramses tree."""

    match: MatchResult
    media_info: MediaInfo

    sequence_id: str = ""
    shot_id: str = ""
    project_id: str = ""
    project_name: str = "" # Added long name support
    step_id: str = "PLATE"

    is_new_sequence: bool = False
    is_new_shot: bool = False
    version: int = 1

    target_publish_dir: str = ""
    """Resolved path: ``{Shot}/{Step}/_published/v{NNN}/``."""

    target_preview_dir: str = ""
    """Resolved path: ``{Shot}/{Step}/_preview/``."""

    error: str = ""
    """Non-empty if this plan cannot be executed."""

    # Enhancement #9: Duplicate detection
    is_duplicate: bool = False
    """True if this clip appears to be a duplicate of an existing version."""
    duplicate_version: int = 0
    """Version number of the duplicate, if found."""
    duplicate_path: str = ""
    """Path to the duplicate version, if found."""

    @property
    def can_execute(self) -> bool:
        return self.error == "" and self.match.matched and not self.is_duplicate


@dataclass
class IngestResult:
    """Outcome of executing a single ``IngestPlan``."""

    plan: IngestPlan
    success: bool = False
    published_path: str = ""
    preview_path: str = ""
    frames_copied: int = 0
    bytes_copied: int = 0 # Exact byte count
    checksum: str = "" # MD5 of the first frame/file
    missing_frames: list[int] = field(default_factory=list) # Frame gaps in sequences
    error: str = ""


def build_plans(
    matches: list[MatchResult],
    media_infos: dict[str, MediaInfo],
    project_id: str,
    step_id: str = "PLATE",
    existing_sequences: list[str] | None = None,
    existing_shots: list[str] | None = None,
    project_name: str = "",
) -> list[IngestPlan]:
    """Build an ``IngestPlan`` for each matched clip."""
    if existing_sequences is None:
        existing_sequences = []
    if existing_shots is None:
        existing_shots = []

    seen_seqs = set(s.upper() for s in existing_sequences)
    seen_shots = set(s.upper() for s in existing_shots)

    plans: list[IngestPlan] = []

    for match in matches:
        info = media_infos.get(match.clip.first_file, MediaInfo())
        plan = IngestPlan(
            match=match,
            media_info=info,
            sequence_id=match.sequence_id,
            shot_id=match.shot_id,
            project_id=project_id,
            project_name=project_name or project_id,
            step_id=step_id,
        )

        if not match.matched:
            plan.error = "Could not match clip to a shot identity."
            plans.append(plan)
            continue

        plan.is_new_sequence = match.sequence_id.upper() not in seen_seqs
        plan.is_new_shot = match.shot_id.upper() not in seen_shots

        # Track for subsequent clips in the same batch
        if match.sequence_id:
            seen_seqs.add(match.sequence_id.upper())
        seen_shots.add(match.shot_id.upper())

        plans.append(plan)

    return plans


import concurrent.futures
import hashlib

def _calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file in chunks."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def copy_frames(
    clip: Clip,
    dest_dir: str,
    project_id: str,
    shot_id: str,
    step_id: str,
    progress_callback: Callable[[str], None] | None = None,
    dry_run: bool = False
) -> tuple[int, str, int, str]:
    """Copy clip frames into *dest_dir* and verify bit-for-bit using MD5.

    Args:
        clip: Source clip to copy
        dest_dir: Destination directory
        project_id: Project short name
        shot_id: Shot identifier
        step_id: Step identifier
        progress_callback: Optional callback for progress updates (Enhancement #5)
        dry_run: If True, simulate copy without actually writing files (Enhancement #8)

    Returns (number of files copied, MD5 checksum of the first file, total bytes moved, first filename).
    Raises OSError if verification or checksum fails.
    """
    if not dry_run:
        os.makedirs(dest_dir, exist_ok=True)
    copied = 0
    total_bytes = 0
    first_checksum = ""
    first_filename = ""

    def _copy_and_verify(src: str, dst: str) -> tuple[str, int]:
        if dry_run:
            # Dry-run: only get source size and checksum, don't copy
            sz = os.path.getsize(src)
            src_md5 = _calculate_md5(src)
            return src_md5, sz

        shutil.copy2(src, dst)
        sz = os.path.getsize(src)
        # 1. Quick size check
        if sz != os.path.getsize(dst):
            raise OSError(f"Size mismatch: {dst}")

        # 2. Bit-for-bit MD5 check
        src_md5 = _calculate_md5(src)
        if src_md5 != _calculate_md5(dst):
            raise OSError(f"Checksum mismatch: {dst}")
        return src_md5, sz

    if clip.is_sequence:
        padding = clip.padding
        total_count = len(clip.frames)

        # Copy and verify ALL frames with MD5 checksums for data integrity
        for i, frame in enumerate(clip.frames):
            src = os.path.join(
                str(clip.directory),
                f"{clip.base_name}.{str(frame).zfill(padding)}.{clip.extension}",
            )
            dst_name = f"{project_id}_S_{shot_id}_{step_id}.{str(frame).zfill(padding)}.{clip.extension}"
            dst = os.path.join(dest_dir, dst_name)

            # Full MD5 verification for every frame (VFX data integrity requirement)
            checksum, sz = _copy_and_verify(src, dst)

            # Store first frame info for reporting
            if i == 0:
                first_checksum = checksum
                first_filename = dst_name

            total_bytes += sz
            copied += 1

            # Progress reporting every 10 frames (or every frame for small sequences)
            if progress_callback and (i % 10 == 0 or i == total_count - 1):
                progress_callback(f"    Verifying frame {i+1}/{total_count}...")

    else:
        src = clip.first_file
        dst_name = f"{project_id}_S_{shot_id}_{step_id}.{clip.extension}"
        dst = os.path.join(dest_dir, dst_name)
        first_checksum, sz = _copy_and_verify(src, dst)
        first_filename = dst_name
        total_bytes += sz
        copied = 1

    return copied, first_checksum, total_bytes, first_filename


def _get_next_version(publish_root: str) -> int:
    """Find the next available version number by scanning vNNN folders."""
    if not os.path.isdir(publish_root):
        return 1
    
    max_v = 0
    try:
        for item in os.listdir(publish_root):
            if item.startswith("v") and len(item) == 4 and item[1:].isdigit():
                v = int(item[1:])
                if v > max_v:
                    max_v = v
    except Exception:
        pass
    return max_v + 1


def generate_thumbnail_for_result(
    result: IngestResult,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
) -> bool:
    """Generate thumbnail on-demand for a previously ingested result (Enhancement #20).

    This allows lazy thumbnail generation - skip during ingest, generate when needed.

    Args:
        result: IngestResult from a previous ingest
        ocio_config: Optional OCIO config file path
        ocio_in: Source colorspace

    Returns:
        True if thumbnail generated successfully
    """
    if not result.success or not result.plan.target_preview_dir:
        return False

    try:
        from ramses_ingest.preview import generate_thumbnail as gen_thumb
        os.makedirs(result.plan.target_preview_dir, exist_ok=True)

        thumb_name = f"{result.plan.project_id}_S_{result.plan.shot_id}_{result.plan.step_id}.jpg"
        thumb_path = os.path.join(result.plan.target_preview_dir, thumb_name)

        ok = gen_thumb(
            result.plan.match.clip,
            thumb_path,
            ocio_config=ocio_config,
            ocio_in=ocio_in,
        )

        if ok:
            result.preview_path = thumb_path

        return ok
    except Exception:
        return False


def check_for_duplicates(plans: list[IngestPlan]) -> None:
    """Check all plans for duplicate versions and mark them (Enhancement #9).

    Updates the IngestPlan objects in-place with duplicate information.

    Args:
        plans: List of IngestPlan objects to check
    """
    from ramses_ingest.validator import check_for_duplicate_version

    for plan in plans:
        if not plan.match.matched or not plan.target_publish_dir:
            continue

        # Get the parent directory containing published versions
        existing_versions_dir = os.path.dirname(plan.target_publish_dir)

        is_dup, dup_path, dup_version = check_for_duplicate_version(
            plan.match.clip,
            existing_versions_dir
        )

        if is_dup:
            plan.is_duplicate = True
            plan.duplicate_version = dup_version
            plan.duplicate_path = dup_path
            plan.error = f"Duplicate of v{dup_version:03d}"


def resolve_paths(
    plans: list[IngestPlan],
    project_root: str,
    shots_folder: str = "05-SHOTS",
) -> None:
    """Fill in ``target_publish_dir`` and ``target_preview_dir`` on each plan.

    Uses the Ramses folder convention::

        {project_root}/{shots_folder}/[{SEQUENCE}]/{SHOT}/{Project}_S_{Shot}_{Step}/_published/v{NNN}/

    This is the offline fallback matching the Ramses API behavior.
    """
    for plan in plans:
        if not plan.can_execute:
            continue

        if plan.sequence_id:
            shot_root = os.path.join(
                project_root, shots_folder, plan.sequence_id, plan.shot_id,
            )
        else:
            shot_root = os.path.join(
                project_root, shots_folder, plan.shot_id,
            )

        # Build step folder name using API convention: PROJ_S_SH010_PLATE
        nm = RamFileInfo()
        nm.project = plan.project_id
        nm.ramType = ItemType.SHOT
        nm.shortName = plan.shot_id
        nm.step = plan.step_id
        step_folder_name = nm.fileName()

        step_folder = os.path.join(shot_root, step_folder_name)
        
        # VERSION-UP LOGIC
        publish_root = os.path.join(step_folder, "_published")
        plan.version = _get_next_version(publish_root)
        
        version_str = f"v{plan.version:03d}"

        plan.target_publish_dir = os.path.join(
            publish_root, version_str,
        )
        plan.target_preview_dir = os.path.join(
            step_folder, "_preview",
        )


def resolve_paths_from_daemon(
    plans: list[IngestPlan],
    shot_objects: dict[str, object],
) -> None:
    """Calculate target paths for the UI without creating folders on disk (Dry Resolve)."""
    from ramses.daemon_interface import RamDaemonInterface
    daemon = RamDaemonInterface.instance()

    for plan in plans:
        if not plan.can_execute:
            continue
        shot_obj = shot_objects.get(plan.shot_id.upper())
        if shot_obj is None:
            continue
        
        try:
            # We bypass high-level API methods to avoid os.makedirs side-effects.
            # Get the raw path from daemon without triggering the API's internal folder creation.
            base_path = daemon.getPath(shot_obj.uuid(), "RamShot").replace("\\", "/")
            if not base_path:
                continue

            # Build step folder name using API convention
            nm = RamFileInfo()
            nm.project = plan.project_id
            nm.ramType = ItemType.SHOT
            nm.shortName = plan.shot_id
            nm.step = plan.step_id
            step_folder_name = nm.fileName()

            # Construct paths manually (Dry)
            step_root = f"{base_path}/{step_folder_name}"
            
            # Find next version (Dry scan of existing folders)
            publish_root = f"{step_root}/_published"
            plan.version = _get_next_version(publish_root)
            
            version_str = f"v{plan.version:03d}"
            plan.target_publish_dir = f"{publish_root}/{version_str}"
            plan.target_preview_dir = f"{step_root}/_preview"

        except Exception:
            pass


def _write_ramses_metadata(
    folder: str,
    filename: str,
    version: int,
    comment: str = "",
    timecode: str = "",
) -> None:
    """Write a ``_ramses_data.json`` sidecar file for the published version."""
    meta_path = os.path.join(folder, "_ramses_data.json")

    data = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}

    entry = {
        "version": version,
        "comment": comment,
        "state": "wip",
        "date": int(time.time()),
    }
    if timecode:
        entry["timecode"] = timecode
    
    data[filename] = entry

    os.makedirs(folder, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def execute_plan(
    plan: IngestPlan,
    generate_thumbnail: bool = True,
    generate_proxy: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
    ocio_out: str = "sRGB", # Hardcoded for safety
    skip_ramses_registration: bool = False,
    dry_run: bool = False,
) -> IngestResult:
    """Execute a single ``IngestPlan``: create Ramses objects, copy frames, generate previews.

    Args:
        plan: The plan to execute.
        generate_thumbnail: Whether to generate a JPEG thumbnail.
        generate_proxy: Whether to generate an MP4 video proxy.
        progress_callback: Optional callable for progress messages.
        ocio_config: Path to an OCIO config file.
        ocio_in: Source colorspace.
        ocio_out: Target colorspace.
        skip_ramses_registration: If True, skips the DB creation step (useful for parallel execution).
        dry_run: If True, preview operations without actually copying files (Enhancement #8).

    Returns:
        An ``IngestResult`` describing the outcome.
    """
    def _log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    result = IngestResult(plan=plan, missing_frames=plan.match.clip.missing_frames)

    if not plan.can_execute:
        result.error = plan.error or "Plan cannot be executed."
        return result

    if not plan.target_publish_dir:
        result.error = "No target publish directory resolved."
        return result

    clip = plan.match.clip

    # --- Create Ramses objects if daemon is available ---
    if not skip_ramses_registration and not dry_run:
        try:
            register_ramses_objects(plan, _log)
        except Exception as exc:
            _log(f"  Ramses API (non-fatal): {exc}")

    # --- Copy frames ---
    try:
        action_verb = "Simulating" if dry_run else "Copying"
        _log(f"  {action_verb} {clip.frame_count or 1} file(s)...")
        copied_count, checksum, total_bytes, first_filename = copy_frames(
            clip, plan.target_publish_dir,
            plan.project_id, plan.shot_id, plan.step_id,
            progress_callback=progress_callback,  # Enhancement #5: MD5 progress reporting
            dry_run=dry_run,  # Enhancement #8: Dry-run mode
        )
        # Use technical frame count for movies, or files copied for sequences
        if not clip.is_sequence and plan.media_info.frame_count > 0:
            result.frames_copied = plan.media_info.frame_count
        else:
            result.frames_copied = copied_count

        result.checksum = checksum
        result.bytes_copied = total_bytes
        result.published_path = plan.target_publish_dir
    except Exception as exc:
        result.error = f"Copy failed: {exc}"
        return result

    # --- Write metadata ---
    if not dry_run:
        try:
            # Use tracked filename instead of expensive listdir() call
            _write_ramses_metadata(
                plan.target_publish_dir,
                first_filename,
                plan.version,
                comment="Ingested via Ramses-Ingest",
                timecode=plan.media_info.start_timecode,
            )
        except Exception as exc:
            _log(f"  Metadata write (non-fatal): {exc}")

    # --- Generate thumbnail ---
    if generate_thumbnail and plan.target_preview_dir and not dry_run:
        try:
            from ramses_ingest.preview import generate_thumbnail as gen_thumb
            os.makedirs(plan.target_preview_dir, exist_ok=True)
            thumb_name = f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.jpg"
            thumb_path = os.path.join(plan.target_preview_dir, thumb_name)
            _log("  Generating thumbnail...")
            ok = gen_thumb(
                clip, thumb_path,
                ocio_config=ocio_config,
                ocio_in=ocio_in,
            )
            if ok:
                result.preview_path = thumb_path
        except Exception as exc:
            _log(f"  Thumbnail (non-fatal): {exc}")

    # --- Generate video proxy ---
    if generate_proxy and plan.target_preview_dir and not dry_run:
        try:
            from ramses_ingest.preview import generate_proxy as gen_proxy
            proxy_name = f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.mp4"
            proxy_path = os.path.join(plan.target_preview_dir, proxy_name)
            _log("  Generating video proxy...")
            gen_proxy(
                clip, proxy_path,
                ocio_config=ocio_config,
                ocio_in=ocio_in,
            )
        except Exception as exc:
            _log(f"  Proxy (non-fatal): {exc}")

    result.success = True
    return result


def register_ramses_objects(
    plan: IngestPlan, 
    log: Callable[[str], None], 
    sequence_cache: dict[str, str] | None = None,
    shot_cache: dict[str, object] | None = None
) -> None:
    """Create or HEAL RamSequence / RamShot via the Daemon API."""
    try:
        from ramses import Ramses
        ram = Ramses.instance()
        if not ram.online():
            return
    except Exception:
        return

    from ramses.ram_sequence import RamSequence
    from ramses.ram_shot import RamShot
    from ramses.daemon_interface import RamDaemonInterface

    info = plan.media_info
    daemon = RamDaemonInterface.instance()
    project = ram.project()
    if not project:
        return
    
    project_uuid = project.uuid()

    # 1. Handle Sequence
    seq_obj = None
    if plan.sequence_id:
        seq_upper = plan.sequence_id.upper()
        
        # Use cache if available, otherwise fetch
        if sequence_cache and seq_upper in sequence_cache:
            seq_obj = RamSequence(sequence_cache[seq_upper])
        else:
            for s in daemon.getObjects("RamSequence"):
                if s.shortName().upper() == seq_upper:
                    seq_obj = s
                    break
        
        seq_folder = os.path.join(project.folderPath(), "05-SHOTS", plan.sequence_id).replace("\\", "/")
        seq_data = {
            "shortName": plan.sequence_id,
            "name": plan.sequence_id,
            "folderPath": seq_folder,
            "project": project_uuid,
            "overrideResolution": True,
            "width": info.width or 1920,
            "height": info.height or 1080,
            "overrideFramerate": True,
            "framerate": info.fps or 24.0,
        }

        if not seq_obj:
            log(f"  Creating sequence {plan.sequence_id}...")
            try:
                seq_obj = RamSequence(data=seq_data, create=True)
                if sequence_cache is not None:
                    with _RAMSES_CACHE_LOCK:
                        sequence_cache[seq_upper] = seq_obj.uuid()
            except Exception as exc:
                log(f"  Sequence creation failed: {exc}")
        else:
            # HEAL only if needed
            current_data = seq_obj.data()
            if current_data.get("folderPath") != seq_folder or current_data.get("project") != project_uuid:
                log(f"  Healing sequence {plan.sequence_id} metadata...")
                seq_obj.setData(seq_data)

    # 2. Handle Shot
    if plan.shot_id:
        shot_upper = plan.shot_id.upper()
        shot_obj = None
        
        # Use provided shot_cache (passed from app.py)
        if shot_cache and shot_upper in shot_cache:
            shot_obj = shot_cache[shot_upper]
        else:
            # Fallback to direct lookup (avoid getObjects in loop)
            for s in project.shots():
                if s.shortName().upper() == shot_upper:
                    shot_obj = s
                    break

        # Derive folder path
        if plan.sequence_id:
            shot_folder = os.path.join(project.folderPath(), "05-SHOTS", plan.sequence_id, plan.shot_id).replace("\\", "/")
        else:
            shot_folder = os.path.join(project.folderPath(), "05-SHOTS", plan.shot_id).replace("\\", "/")

        duration = 5.0
        if info.fps and info.fps > 0:
            fc = info.frame_count or (plan.match.clip.frame_count if plan.match.clip.is_sequence else 0)
            if fc > 0:
                duration = fc / info.fps

        shot_data = {
            "shortName": plan.shot_id,
            "name": plan.shot_id,
            "folderPath": shot_folder,
            "project": project_uuid,
            "duration": duration,
        }
        if seq_obj:
            shot_data["sequence"] = seq_obj.uuid()

        if not shot_obj:
            log(f"  Creating shot {plan.shot_id}...")
            try:
                shot_obj = RamShot(data=shot_data, create=True)
                if shot_cache is not None:
                    with _RAMSES_CACHE_LOCK:
                        shot_cache[shot_upper] = shot_obj
            except Exception as exc:
                log(f"  Shot creation failed: {exc}")
        else:
            # HEAL only if needed
            current_data = shot_obj.data()
            if current_data.get("folderPath") != shot_folder or current_data.get("project") != project_uuid:
                log(f"  Healing shot {plan.shot_id} metadata...")
                shot_obj.setData(shot_data)


# Track daemon feature support globally to prevent log flooding
_USER_ASSIGNMENT_SUPPORTED = True


def update_ramses_status(
    plan: IngestPlan, 
    status_name: str = "OK",
    shot_cache: dict[str, object] | None = None,
) -> bool:
    """Update the status of the target step in Ramses and assign current user."""
    global _USER_ASSIGNMENT_SUPPORTED
    try:
        from ramses import Ramses
        ram = Ramses.instance()
        if not ram.online():
            return False
        
        project = ram.project()
        if not project:
            return False

        # Find the shot object
        target_shot = None
        if shot_cache and plan.shot_id.upper() in shot_cache:
            target_shot = shot_cache[plan.shot_id.upper()]
        else:
            for shot in project.shots():
                if shot.shortName().upper() == plan.shot_id.upper():
                    target_shot = shot
                    break
        
        if not target_shot:
            return False

        # Find the step object
        from ramses.ram_step import RamStep, StepType
        target_step = None
        for step in project.steps(StepType.SHOT_PRODUCTION):
            if step.shortName().upper() == plan.step_id.upper():
                target_step = step
                break
        
        if not target_step:
            return False

        # Update status
        status = target_shot.currentStatus(target_step)
        if status:
            # Find the state (OK, TODO, etc)
            target_state = None
            for state in ram.states():
                if state.shortName().upper() == status_name.upper():
                    target_state = state
                    break
            
            if target_state:
                try:
                    status.setState(target_state)
                    status.setCompletionRatio(100 if status_name.upper() == "OK" else 0)
                    
                    # setUser calls setStatusModifiedBy which fails on some Daemon versions
                    if _USER_ASSIGNMENT_SUPPORTED:
                        try:
                            status.setUser() 
                        except Exception as exc:
                            # If we see "Unknown query", stop trying for this session
                            # The API might log this to stdout before we catch it,
                            # but this flag prevents subsequent attempts.
                            err_msg = str(exc).lower()
                            if "unknown query" in err_msg or "not reply" in err_msg:
                                _USER_ASSIGNMENT_SUPPORTED = False
                        
                    return True
                except Exception:
                    return False
                
        return False
    except Exception:
        return False
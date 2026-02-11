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

import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from ramses_ingest.scanner import Clip
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.path_utils import normalize_path, join_normalized

from ramses.file_info import RamFileInfo
from ramses.constants import FolderNames
from ramses.constants import ItemType


def check_disk_space(dest_path: str, required_bytes: int) -> tuple[bool, str]:
    """Verify if the destination volume has enough free space.

    Args:
        dest_path: Target directory or file path.
        required_bytes: Number of bytes needed.

    Returns:
        (bool success, str error_message)
    """
    try:
        # Get the root of the destination path (even if it doesn't exist yet)
        target = os.path.abspath(dest_path)
        while not os.path.exists(target):
            parent = os.path.dirname(target)
            if parent == target:
                break  # Root reached
            target = parent

        usage = shutil.disk_usage(target)
        # Keep 500MB as safety margin for OS/logs
        if usage.free < (required_bytes + 524288000):
            free_gb = usage.free / (1024**3)
            req_gb = required_bytes / (1024**3)
            return (
                False,
                f"Insufficient disk space on {target}. Need {req_gb:.2f} GB, but only {free_gb:.2f} GB free (plus safety margin).",
            )
        return True, ""
    except Exception as exc:
        return True, ""  # Don't block on errors (e.g. permission issues on parent)


# Thread-safe cache lock for Ramses object registration
_RAMSES_CACHE_LOCK = threading.Lock()

# Thread-safe lock for version number generation to prevent race conditions
_VERSION_LOCK = threading.Lock()

# Thread-safe lock for metadata writes to prevent read-modify-write race conditions
_METADATA_WRITE_LOCK = threading.Lock()


@dataclass
class IngestPlan:
    """A fully resolved plan for ingesting one clip into the Ramses tree."""

    match: MatchResult
    media_info: MediaInfo

    sequence_id: str = ""
    shot_id: str = ""
    project_id: str = ""
    project_name: str = ""  # Added long name support
    step_id: str = "PLATE"
    resource: str = ""
    state: str = "WIP"

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

    enabled: bool = True
    """User-controlled toggle for inclusion in ingest."""

    @property
    def can_execute(self) -> bool:
        return (
            self.enabled
            and self.error == ""
            and self.match.matched
            and not self.is_duplicate
        )


@dataclass
class IngestResult:
    """Outcome of executing a single ``IngestPlan``."""

    plan: IngestPlan
    success: bool = False
    published_path: str = ""
    preview_path: str = ""
    frames_copied: int = 0
    bytes_copied: int = 0  # Exact byte count
    checksum: str = ""  # MD5 of the first frame/file
    missing_frames: list[int] = field(default_factory=list)  # Frame gaps in sequences
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
            step_id=match.step_id or step_id,
            resource=match.resource,
            version=match.version or 1,
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


def _calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file in large chunks (1MB) for performance."""
    hash_md5 = hashlib.md5()
    # Let OSError propagate so copy failures are not silent
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):  # 1MB chunks
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def copy_frames(
    clip: Clip,
    dest_dir: str,
    project_id: str,
    shot_id: str,
    step_id: str,
    resource: str = "",
    progress_callback: Callable[[str], None] | None = None,
    dry_run: bool = False,
    fast_verify: bool = False,
    max_workers: int | None = None,
) -> tuple[int, str, int, str]:
    """Copy clip frames into *dest_dir* with parallel processing and verification.

    Args:
        clip: Source clip to copy
        dest_dir: Destination directory
        project_id: Project short name
        shot_id: Shot identifier
        step_id: Step identifier
        progress_callback: Optional callback for progress updates
        dry_run: If True, simulate copy without actually writing files
        fast_verify: If True, only MD5 verify first, middle and last frames.
        max_workers: Number of parallel copy threads. If None, auto-calculated for I/O.

    Returns (number of files copied, MD5 checksum of the first file, total bytes moved, first filename).
    """
    if max_workers is None:
        # I/O-bound operation: use more threads than CPU cores
        max_workers = min(32, (os.cpu_count() or 1) + 4)
    if not dry_run:
        os.makedirs(dest_dir, exist_ok=True)

    total_bytes = 0
    first_checksum = ""
    first_filename = ""

    # Enforce case-consistency for destination filenames
    # Project casing is preserved, but Shot/Step are standardized to Upper
    shot_id = shot_id.upper()
    step_id = step_id

    # Build base part of Ramses filename
    # e.g. PROJ_S_SH010_PLATE or PROJ_S_SH010_PLATE_BG
    base_parts = [project_id, "S", shot_id, step_id]
    if resource:
        base_parts.append(resource)
    ramses_base = "_".join(base_parts)

    frames_to_copy = []
    if clip.is_sequence:
        padding = clip.padding
        separator = clip.separator  # Use detected separator from scanner
        for i, frame in enumerate(clip.frames):
            src = os.path.join(
                str(clip.directory),
                f"{clip.base_name}{separator}{str(frame).zfill(padding)}.{clip.extension}",
            )
            # Validate source file exists before adding to copy list
            if not os.path.isfile(src):
                raise FileNotFoundError(f"Source frame missing: {src}")

            dst_name = f"{ramses_base}.{str(frame).zfill(padding)}.{clip.extension}"
            dst = os.path.join(dest_dir, dst_name)

            # Determine if this frame needs full MD5 verification
            needs_md5 = True
            if fast_verify:
                # Only verify first, middle, and last
                mid = len(clip.frames) // 2
                if i != 0 and i != mid and i != (len(clip.frames) - 1):
                    needs_md5 = False

            frames_to_copy.append((src, dst, dst_name, needs_md5, i == 0))
    else:
        src = clip.first_file
        # Validate source file exists
        if not os.path.isfile(src):
            raise FileNotFoundError(f"Source file missing: {src}")

        dst_name = f"{ramses_base}.{clip.extension}"
        dst = os.path.join(dest_dir, dst_name)
        frames_to_copy.append((src, dst, dst_name, True, True))

    def _process_one(args):
        src, dst, dst_name, needs_md5, is_first = args

        if dry_run:
            sz = os.path.getsize(src)
            checksum = _calculate_md5(src) if needs_md5 else "skipped"
            return checksum, sz, dst_name, is_first

        src_sz = os.path.getsize(src)  # Read source size before copy
        shutil.copy2(src, dst)
        dst_sz = os.path.getsize(dst)  # Read destination size for verification

        # Force sync on Windows network drives to prevent buffered write issues
        # On SMB/CIFS shares, copy2 can return success while data is still buffered
        if sys.platform == "win32":
            handle = -1
            try:
                import ctypes

                # Open file handle with write access
                handle = ctypes.windll.kernel32.CreateFileW(
                    dst,
                    0x40000000,  # GENERIC_WRITE
                    0,  # No sharing
                    None,
                    3,  # OPEN_EXISTING
                    0,
                    None,
                )
                if handle != -1:
                    # Force flush buffers to disk
                    ctypes.windll.kernel32.FlushFileBuffers(handle)
            except Exception:
                # If flush fails, proceed anyway - size/MD5 checks will catch issues
                pass
            finally:
                # Always close handle if it was opened successfully
                if handle != -1:
                    try:
                        import ctypes

                        ctypes.windll.kernel32.CloseHandle(handle)
                    except Exception:
                        pass

        # 1. Size check (always) - compare source vs destination
        if src_sz != dst_sz:
            raise OSError(
                f"Size mismatch: {dst} (source: {src_sz} bytes, dest: {dst_sz} bytes)"
            )

        # 2. MD5 check (conditional)
        checksum = ""
        if needs_md5:
            try:
                src_md5 = _calculate_md5(src)
                dst_md5 = _calculate_md5(dst)
                if src_md5 != dst_md5:
                    raise OSError(f"Checksum mismatch: {dst}")
                checksum = src_md5
            except OSError as e:
                # Preserve original OS error (permission denied, disk full, etc.)
                raise OSError(f"MD5 verification failed for {dst}: {e}") from e

        return checksum, dst_sz, dst_name, is_first

    copied_count = 0
    total_frames = len(frames_to_copy)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_one, f) for f in frames_to_copy]

        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            checksum, sz, dst_name, is_first = future.result()
            total_bytes += sz
            copied_count += 1

            if is_first:
                first_checksum = checksum
                first_filename = dst_name

            if progress_callback and (i % 10 == 0 or i == total_frames - 1):
                mode = "Verifying" if not fast_verify else "Copying"
                progress_callback(f"    {mode} frame {i + 1}/{total_frames}...")

    return copied_count, first_checksum, total_bytes, first_filename


def _get_next_version(publish_root: str) -> int:
    """Find the next available version number by scanning API-compliant folders.

    Ramses API Spec: [RESOURCE]_[VERSION]_[STATE] or [VERSION]_[STATE]

    Thread-safe: Uses _VERSION_LOCK to prevent race conditions in parallel execution.
    Callers are responsible for creating the version directory after obtaining the number.
    """
    with _VERSION_LOCK:
        publish_root = normalize_path(publish_root)
        if not os.path.isdir(publish_root):
            return 1

        max_v = 0
        # Regex to match API-compliant version folders:
        # 1. (?:(?P<res>.*)_)?  -> Optional resource block
        # 2. (?P<ver>\d{3})     -> Mandatory 3-digit version
        # 3. (?:_(?P<state>.*))? -> Optional state block
        version_re = re.compile(
            r"^(?:(?P<res>[^_]+)_)?(?P<ver>\d{3})(?:_(?P<state>.*))?$"
        )

        try:
            for item in os.listdir(publish_root):
                match = version_re.match(item)
                if match:
                    v_path = os.path.join(publish_root, item)
                    is_valid_version = False

                    # Check for completion marker (permanent)
                    if os.path.exists(os.path.join(v_path, ".ramses_complete")):
                        is_valid_version = True
                    # Fallback: Check mtime (for backwards compatibility with old versions)
                    else:
                        try:
                            mtime = os.path.getmtime(v_path)
                            if (time.time() - mtime) < 3600:
                                is_valid_version = True
                        except (OSError, PermissionError):
                            pass

                    if is_valid_version:
                        v = int(match.group("ver"))
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
            plan.match.clip, existing_versions_dir, resource=plan.resource
        )

        if is_dup:
            plan.is_duplicate = True
            plan.duplicate_version = dup_version
            plan.duplicate_path = dup_path
            plan.error = f"Duplicate of v{dup_version:03d}"


def check_for_path_collisions(plans: list[IngestPlan]) -> None:
    """Identify plans that resolve to the same destination path within the current batch.

    Updates the IngestPlan.error field if a collision is detected.
    """
    from collections import defaultdict

    path_to_plans = defaultdict(list)

    for plan in plans:
        # Only check matched plans that have a target path
        if not plan.match.matched or not plan.target_publish_dir:
            continue

        # Normalize path for comparison
        path_key = os.path.normpath(plan.target_publish_dir).lower()
        path_to_plans[path_key].append(plan)

    for path, colliding in path_to_plans.items():
        if len(colliding) > 1:
            for plan in colliding:
                # Only append if not already showing a more specific error
                collision_msg = (
                    f"COLLISION: {len(colliding)} clips resolving to same path"
                )
                if not plan.error:
                    plan.error = collision_msg
                elif "COLLISION" not in plan.error:
                    plan.error += f" | {collision_msg}"


def resolve_paths(
    plans: list[IngestPlan],
    project_root: str,
    shots_folder: str = FolderNames.shots,
) -> None:
    """Fill in ``target_publish_dir`` and ``target_preview_dir`` on each plan.

    Uses the Ramses folder convention::

        {project_root}/{shots_folder}/{Project}_S_{Shot}/{Project}_S_{Shot}_{Step}/_published/v{NNN}/

    This matches the standard Ramses API behavior (no sequence nesting on disk).
    """
    version_cache: dict[str, int] = {}  # Cache next version by publish_root path

    for plan in plans:
        if not plan.can_execute:
            continue

        # Preserve project casing (Ramses is case-sensitive for projects)
        # but enforce uppercase for Shot as per standard convention
        proj_id = plan.project_id
        shot_id = plan.shot_id.upper()
        step_id = plan.step_id

        # Sanitize IDs to prevent path traversal
        if "/" in proj_id or "\\" in proj_id or ".." in proj_id:
            plan.error = f"Invalid project ID contains path separators: {proj_id}"
            continue
        if "/" in shot_id or "\\" in shot_id or ".." in shot_id:
            plan.error = f"Invalid shot ID contains path separators: {shot_id}"
            continue
        if "/" in step_id or "\\" in step_id or ".." in step_id:
            plan.error = f"Invalid step ID contains path separators: {step_id}"
            continue

        # Build standard Shot Root folder name: PROJ_S_SH010
        snm = RamFileInfo()
        snm.project = proj_id
        snm.ramType = ItemType.SHOT
        snm.shortName = shot_id
        shot_root_name = snm.fileName()

        shot_root = os.path.join(project_root, shots_folder, shot_root_name)

        # Build step folder name using API convention: PROJ_S_SH010_PLATE
        nm = RamFileInfo()
        nm.project = proj_id
        nm.ramType = ItemType.SHOT
        nm.shortName = shot_id
        nm.step = step_id
        step_folder_name = nm.fileName()

        step_folder = os.path.join(shot_root, step_folder_name)

        # VERSION-UP LOGIC (Optimized with local cache)
        publish_root = os.path.join(step_folder, "_published")
        if publish_root not in version_cache:
            version_cache[publish_root] = _get_next_version(publish_root)

        plan.version = version_cache[publish_root]

        # Validate version number and state
        if plan.version <= 0 or plan.version > 999:
            plan.error = f"Invalid version number: {plan.version}"
            continue
        if "/" in plan.state or "\\" in plan.state:
            plan.error = f"Invalid state contains path separators: {plan.state}"
            continue

        # API COMPLIANT NAMING: [RESOURCE]_[VERSION]_[STATE] or [VERSION]_[STATE]
        if plan.resource:
            version_str = f"{plan.resource}_{plan.version:03d}_{plan.state}"
        else:
            version_str = f"{plan.version:03d}_{plan.state}"

        plan.target_publish_dir = os.path.join(
            publish_root,
            version_str,
        )
        plan.target_preview_dir = os.path.join(
            step_folder,
            "_preview",
        )


def resolve_paths_from_daemon(
    plans: list[IngestPlan],
    shot_objects: dict[str, object],
) -> None:
    """Calculate target paths for the UI without creating folders on disk (Dry Resolve)."""
    from ramses.daemon_interface import RamDaemonInterface

    daemon = RamDaemonInterface.instance()
    version_cache: dict[str, int] = {}  # Cache next version by publish_root path

    for plan in plans:
        if not plan.can_execute:
            continue
        shot_obj = shot_objects.get(plan.shot_id.upper())
        if shot_obj is None:
            continue

        try:
            # We bypass high-level API methods to avoid os.makedirs side-effects.
            # Get the raw path from daemon without triggering the API's internal folder creation.
            base_path = normalize_path(daemon.getPath(shot_obj.uuid(), "RamShot"))
            if not base_path:
                continue

            # Preserve project casing
            proj_id = plan.project_id
            shot_id = plan.shot_id.upper()
            step_id = plan.step_id

            # Build step folder name using API convention
            nm = RamFileInfo()
            nm.project = proj_id
            nm.ramType = ItemType.SHOT
            nm.shortName = shot_id
            nm.step = step_id
            step_folder_name = nm.fileName()

            # Construct paths manually (Dry)
            step_root = f"{base_path}/{step_folder_name}"

            # Find next version (Dry scan of existing folders) with optimization
            publish_root = f"{step_root}/_published"
            if publish_root not in version_cache:
                version_cache[publish_root] = _get_next_version(publish_root)

            plan.version = version_cache[publish_root]

            # API STRICT NAMING: [RESOURCE]_[VERSION]_[STATE] or [VERSION]_[STATE]
            if plan.resource:
                version_str = f"{plan.resource}_{plan.version:03d}_{plan.state}"
            else:
                version_str = f"{plan.version:03d}_{plan.state}"

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
    """Write a ``_ramses_data.json`` sidecar file for the published version.

    Uses atomic write pattern (temp file + rename) + thread-safe lock to prevent corruption.
    """
    # Protect entire read-modify-write sequence with lock to prevent race conditions
    with _METADATA_WRITE_LOCK:
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

        # Atomic write: write to temp file, then rename
        import tempfile

        temp_fd, temp_path = tempfile.mkstemp(
            dir=folder, prefix=".ramses_data_", suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            # Atomic rename (POSIX) or best-effort on Windows
            os.replace(temp_path, meta_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.remove(temp_path)
            except Exception:
                pass
            raise


def execute_plan(
    plan: IngestPlan,
    generate_thumbnail: bool = True,
    generate_proxy: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
    ocio_out: str = "sRGB",  # Hardcoded for safety
    skip_ramses_registration: bool = False,
    dry_run: bool = False,
    fast_verify: bool = False,
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
        fast_verify: If True, only verify MD5 for first/middle/last frames.

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
            # Non-fatal: Log and continue (don't re-raise)
            _log(f"  Ramses API (non-fatal): {exc}")

    # --- Transactional Execution (Copy + Metadata) ---
    try:
        # 1. Copy frames
        action_verb = "Simulating" if dry_run else "Copying"
        _log(f"  {action_verb} {clip.frame_count or 1} file(s)...")
        copied_count, checksum, total_bytes, first_filename = copy_frames(
            clip,
            plan.target_publish_dir,
            plan.project_id,
            plan.shot_id,
            plan.step_id,
            resource=plan.resource,
            progress_callback=progress_callback,
            dry_run=dry_run,
            fast_verify=fast_verify,
        )

        # Update result stats
        if not clip.is_sequence and plan.media_info.frame_count > 0:
            result.frames_copied = plan.media_info.frame_count
        else:
            result.frames_copied = copied_count

        result.checksum = checksum
        result.bytes_copied = total_bytes
        result.published_path = plan.target_publish_dir

        # 2. Write metadata (Critical Step - Failure triggers rollback)
        if not dry_run:
            _write_ramses_metadata(
                plan.target_publish_dir,
                first_filename,
                plan.version,
                comment="Ingested via Ramses-Ingest",
                timecode=plan.media_info.start_timecode,
            )

    except Exception as exc:
        error_msg = str(exc)
        # Rollback: Delete the partially created version folder
        if (
            not dry_run
            and plan.target_publish_dir
            and os.path.exists(plan.target_publish_dir)
        ):
            try:
                _log(f"  CRITICAL ERROR: {error_msg}. Rolling back...")
                shutil.rmtree(plan.target_publish_dir)
                _log("  Rollback successful: Cleaned up partial files.")
            except Exception as rollback_exc:
                _log(
                    f"  WARNING: Rollback failed - {plan.target_publish_dir}: {rollback_exc}"
                )
                result.error = f"Ingest failed AND rollback failed: {error_msg} | Rollback error: {rollback_exc}"
                return result

        result.error = f"Ingest failed (Rolled back): {error_msg}"
        return result

    # --- Generate thumbnail (moved to batch processing for parallelization) ---
    # Store thumbnail job info for later batch processing
    result._thumbnail_job = None
    if generate_thumbnail and not dry_run:
        # HERO VS AUXILIARY: Determine target storage
        if not plan.resource:
            # Hero: permanent preview folder
            os.makedirs(plan.target_preview_dir, exist_ok=True)
            thumb_name = f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.jpg"
            thumb_path = os.path.join(plan.target_preview_dir, thumb_name)
        else:
            # Sanitize resource string to prevent path traversal
            safe_resource = re.sub(r'[/\\:*?"<>|]', "_", plan.resource)
            if ".." in safe_resource or safe_resource.startswith("."):
                safe_resource = safe_resource.replace("..", "_").lstrip(".")

            # Auxiliary: temporary storage for report embedding only
            import tempfile

            t_dir = tempfile.gettempdir()
            # Unique name to avoid collisions in system temp
            t_name = f"ram_tmp_{plan.project_id}_{plan.shot_id}_{safe_resource}_{int(time.time())}.jpg"
            thumb_path = os.path.join(t_dir, t_name)

        # Store job for batch processing (avoids sequential FFmpeg calls)
        result._thumbnail_job = {
            "clip": clip,
            "path": thumb_path,
            "ocio_config": ocio_config,
            "ocio_in": ocio_in,
            "is_resource": bool(plan.resource),
        }

    # --- Generate video proxy (HERO ONLY) ---
    if generate_proxy and plan.target_preview_dir and not dry_run and not plan.resource:
        try:
            from ramses_ingest.preview import generate_proxy as gen_proxy

            proxy_name = f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.mp4"

            proxy_path = os.path.join(plan.target_preview_dir, proxy_name)
            _log("  Generating video proxy...")
            gen_proxy(
                clip,
                proxy_path,
                ocio_config=ocio_config,
                ocio_in=ocio_in,
            )
        except Exception as exc:
            # Non-fatal: Log and continue (don't re-raise)
            _log(f"  Proxy (non-fatal): {exc}")

    # Mark version as complete (prevents zombie detection on next ingest)
    if not dry_run and plan.target_publish_dir:
        try:
            marker_path = os.path.join(plan.target_publish_dir, ".ramses_complete")
            with open(marker_path, "w") as f:
                f.write(f"{time.time()}\n")
        except Exception:
            pass  # Non-fatal

    result.success = True
    return result


def register_ramses_objects(
    plan: IngestPlan,
    log: Callable[[str], None],
    sequence_cache: dict[str, str] | None = None,
    shot_cache: dict[str, object] | None = None,
    skip_status_update: bool = False,
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

    # ... (Sequence and Shot creation logic remains same) ...

    # 1. Handle Sequence
    seq_obj = None
    if plan.sequence_id:
        seq_upper = plan.sequence_id.upper()

        # Use cache if available, otherwise fetch
        if sequence_cache and seq_upper in sequence_cache:
            seq_obj = RamSequence(sequence_cache[seq_upper])
        else:
            # Fallback to project-level lookup (lazyLoading=False for bulk fetch)
            for s in project.sequences():
                if s.shortName().upper() == seq_upper:
                    seq_obj = s
                    break

        seq_folder = join_normalized(project.folderPath(), "05-SHOTS", plan.sequence_id)
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
            "overridePixelAspectRatio": True,
            "pixelAspectRatio": info.pixel_aspect_ratio,
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
            # METADATA MINIMIZATION: Only update if changed
            current_data = seq_obj.data()
            needs_update = False
            for key, val in seq_data.items():
                if current_data.get(key) != val:
                    needs_update = True
                    break

            if needs_update:
                log(f"  Updating sequence {plan.sequence_id} metadata...")
                seq_obj.setData(seq_data)

    # 2. Handle Shot
    if plan.shot_id:
        # ... (shot resolution logic remains same) ...
        shot_upper = plan.shot_id.upper()
        shot_obj = None

        # Use provided shot_cache (passed from app.py)
        if shot_cache and shot_upper in shot_cache:
            shot_obj = shot_cache[shot_upper]
        else:
            # Fallback to direct lookup (lazyLoading=False fetches full data in bulk)
            for s in project.shots(lazyLoading=False):
                if s.shortName().upper() == shot_upper:
                    shot_obj = s
                    break

        # Derive folder path using standard naming: PROJ_S_SH010
        shot_nm = RamFileInfo()
        shot_nm.project = plan.project_id
        shot_nm.ramType = ItemType.SHOT
        shot_nm.shortName = plan.shot_id
        shot_folder_name = shot_nm.fileName()
        shot_folder = join_normalized(
            project.folderPath(), "05-SHOTS", shot_folder_name
        )

        duration = 5.0
        if info.fps and info.fps > 0:
            fc = info.frame_count or (
                plan.match.clip.frame_count if plan.match.clip.is_sequence else 0
            )
            if fc > 0:
                duration = fc / info.fps

        shot_data = {
            "shortName": plan.shot_id,
            "name": plan.shot_id,
            "folderPath": shot_folder,
            "project": project_uuid,
            "duration": duration,
        }

        # HERO SOVEREIGNTY: Only 'No Resource' clips define the source media identity
        if not plan.resource:
            shot_data["sourceMedia"] = plan.match.clip.base_name
        elif shot_obj:
            # For auxiliary, preserve existing sourceMedia if it exists
            existing = shot_obj.get("sourceMedia")
            if existing:
                shot_data["sourceMedia"] = existing

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
            # METADATA MINIMIZATION: Only update if changed
            current_data = shot_obj.data()
            needs_update = False
            for key, val in shot_data.items():
                if current_data.get(key) != val:
                    needs_update = True
                    break

            if needs_update:
                log(f"  Updating shot {plan.shot_id} metadata...")
                shot_obj.setData(shot_data)

    # 3. Handle Status Update (HERO ONLY)
    if not skip_status_update:
        update_ramses_status(plan, plan.state, shot_cache=shot_cache)


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
            for shot in project.shots(lazyLoading=False):
                if shot.shortName().upper() == plan.shot_id.upper():
                    target_shot = shot
                    break

        if not target_shot:
            return False

        # Find the step object
        from ramses.ram_step import RamStep, StepType

        target_step = None
        for step in project.steps(StepType.SHOT_PRODUCTION):
            if step.shortName() == plan.step_id:
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

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
import contextlib
import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)


def check_disk_space(dest_path: str, required_bytes: int) -> tuple[bool, str]:
    """Verify if the destination volume has enough free space."""
    try:
        target = os.path.abspath(dest_path)
        while not os.path.exists(target):
            parent = os.path.dirname(target)
            if parent == target: break
            target = parent

        usage = shutil.disk_usage(target)
        if usage.free < (required_bytes + 524288000):
            free_gb = usage.free / (1024**3)
            req_gb = required_bytes / (1024**3)
            return (False, f"Insufficient disk space on {target}. Need {req_gb:.2f} GB, but only {free_gb:.2f} GB free.")
        return True, ""
    except Exception:
        return True, ""


_RAMSES_CACHE_LOCK = threading.Lock()
_VERSION_LOCK = threading.Lock()

# Thread-local lock for in-process serialisation (still needed so multiple
# threads in the same process don't race on the file-lock acquisition).
_METADATA_WRITE_LOCK = threading.Lock()


@contextlib.contextmanager
def _folder_lock(folder: str, timeout: float = 10.0):
    """Cross-process advisory lock using an exclusive lock file.

    Uses O_CREAT | O_EXCL (atomic on POSIX and Windows NTFS) so two
    processes can never both believe they hold the lock.  Stale locks
    (left by a crashed process) are removed after ``timeout`` seconds.
    """
    lock_path = os.path.join(folder, ".ram_write.lock")
    deadline = time.monotonic() + timeout
    acquired = False
    while not acquired:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            acquired = True
        except FileExistsError:
            if time.monotonic() >= deadline:
                # Assume the lock is stale and forcibly remove it.
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
                # One final attempt; if it still fails, propagate.
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                acquired = True
            else:
                time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass


@dataclass
class IngestPlan:
    """A fully resolved plan for ingesting one clip into the Ramses tree."""
    match: MatchResult
    media_info: MediaInfo
    sequence_id: str = ""
    shot_id: str = ""
    project_id: str = ""
    project_name: str = ""
    step_id: str = "PLATE"
    resource: str = ""
    state: str = "WIP"
    colorspace_override: str = ""
    is_new_sequence: bool = False
    is_new_shot: bool = False
    version: int = 1
    target_publish_dir: str = ""
    target_preview_dir: str = ""
    error: str = ""
    is_duplicate: bool = False
    duplicate_version: int = 0
    duplicate_path: str = ""
    enabled: bool = True

    @property
    def can_execute(self) -> bool:
        return self.enabled and self.error == "" and self.match.matched and not self.is_duplicate


@dataclass
class IngestResult:
    """Outcome of executing a single ``IngestPlan``."""
    plan: IngestPlan
    success: bool = False
    published_path: str = ""
    preview_path: str = ""
    frames_copied: int = 0
    bytes_copied: int = 0
    checksum: str = ""
    checksums: dict[str, str] = field(default_factory=dict)
    missing_frames: list[int] = field(default_factory=list)
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
    seen_seqs = set(s.upper() for s in (existing_sequences or []))
    seen_shots = set(s.upper() for s in (existing_shots or []))
    plans: list[IngestPlan] = []

    for match in matches:
        info = media_infos.get(match.clip.first_file, MediaInfo())
        plan = IngestPlan(
            match=match, media_info=info, sequence_id=match.sequence_id, shot_id=match.shot_id,
            project_id=project_id, project_name=project_name or project_id,
            step_id=match.step_id or step_id, resource=match.resource, version=match.version or 1,
        )
        if not match.matched:
            plan.error = "Could not match clip to a shot identity."; plans.append(plan); continue

        plan.is_new_sequence = match.sequence_id.upper() not in seen_seqs
        plan.is_new_shot = match.shot_id.upper() not in seen_shots
        if match.sequence_id: seen_seqs.add(match.sequence_id.upper())
        seen_shots.add(match.shot_id.upper())
        plans.append(plan)
    return plans


def _calculate_md5(file_path: str, sampled: bool = False) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    chunk_size = 1048576
    with open(file_path, "rb") as f:
        if sampled:
            f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
            if size > (chunk_size * 3):
                hash_md5.update(f.read(chunk_size))
                f.seek(size // 2); hash_md5.update(f.read(chunk_size))
                f.seek(max(0, size - chunk_size)); hash_md5.update(f.read(chunk_size))
                return hash_md5.hexdigest()
            else: f.seek(0)
        for chunk in iter(lambda: f.read(chunk_size), b""): hash_md5.update(chunk)
    return hash_md5.hexdigest()


def copy_frames(
    clip: Clip, dest_dir: str, project_id: str, shot_id: str, step_id: str,
    resource: str = "", progress_callback: Callable[[str], None] | None = None,
    dry_run: bool = False, fast_verify: bool = True, max_workers: int | None = None,
) -> tuple[int, dict[str, str], int, str]:
    """Copy clip frames into *dest_dir* with parallel processing and verification."""
    max_workers = max_workers or min(32, (os.cpu_count() or 1) + 4)
    if not dry_run: os.makedirs(dest_dir, exist_ok=True)

    total_bytes, all_checksums, first_filename = 0, {}, ""
    shot_id = shot_id.upper()
    base_parts = [project_id, "S", shot_id, step_id]
    if resource: base_parts.append(resource)
    ramses_base = "_".join(base_parts)

    frames_to_copy = []
    if clip.is_sequence:
        for i, frame in enumerate(clip.frames):
            src = os.path.join(str(clip.directory), f"{clip.base_name}{clip.separator}{str(frame).zfill(clip.padding)}.{clip.extension}")
            if not os.path.isfile(src): raise FileNotFoundError(f"Source frame missing: {src}")
            dst_name = f"{ramses_base}.{str(frame).zfill(clip.padding)}.{clip.extension}"
            needs_md5 = not fast_verify or i in (0, len(clip.frames)//2, len(clip.frames)-1)
            frames_to_copy.append((src, os.path.join(dest_dir, dst_name), dst_name, needs_md5, i == 0, False))
    else:
        if not os.path.isfile(clip.first_file): raise FileNotFoundError(f"Source file missing: {clip.first_file}")
        dst_name = f"{ramses_base}.{clip.extension}"
        frames_to_copy.append((clip.first_file, os.path.join(dest_dir, dst_name), dst_name, True, True, fast_verify))

    def _process_one(args):
        src, dst, dst_name, needs_md5, is_first, use_sampling = args
        if dry_run: return ("dry_run_skipped" if needs_md5 else "skipped"), os.path.getsize(src), dst_name, is_first
        src_sz = os.path.getsize(src)
        try: shutil.copy2(src, dst)
        except OSError as e:
            if e.errno == 28: raise OSError(f"Disk full while copying {dst_name}") from e
            raise
        dst_sz = os.path.getsize(dst)
        if sys.platform == "win32":
            handle = -1
            try:
                import ctypes
                handle = ctypes.windll.kernel32.CreateFileW(dst, 0x40000000, 0, None, 3, 0, None)
                if handle != -1:
                    import threading
                    done = threading.Event()
                    def _f():
                        try: ctypes.windll.kernel32.FlushFileBuffers(handle)
                        except Exception: pass
                        finally: done.set()
                    t = threading.Thread(target=_f, daemon=True); t.start()
                    if not done.wait(timeout=15): logger.warning(f"FlushFileBuffers timed out for {dst_name}")
            except Exception: pass
            finally:
                if handle != -1: ctypes.windll.kernel32.CloseHandle(handle)
        if src_sz != dst_sz: raise OSError(f"Size mismatch after copy: {dst_name}")
        checksum = ""
        if needs_md5:
            src_md5, dst_md5 = _calculate_md5(src, sampled=use_sampling), _calculate_md5(dst, sampled=use_sampling)
            if src_md5 != dst_md5: raise OSError(f"Checksum mismatch: {dst}")
            checksum = src_md5
        return checksum, dst_sz, dst_name, is_first

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_one, f) for f in frames_to_copy]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            checksum, sz, dst_name, is_first = future.result()
            total_bytes += sz; first_filename = dst_name if is_first else first_filename
            if checksum: all_checksums[dst_name] = checksum
            if progress_callback and (i % 10 == 0 or i == len(frames_to_copy)-1):
                progress_callback(f"    {'Verifying' if not fast_verify else 'Copying'} frame {i+1}/{len(frames_to_copy)}...")
    return len(frames_to_copy), all_checksums, total_bytes, first_filename


def _get_next_version(publish_root: str) -> int:
    """Find next available version number.

    Protected by two layers of locking:
    1. ``_VERSION_LOCK`` (threading.Lock) — serialises threads within this process.
    2. ``_folder_lock`` (O_CREAT | O_EXCL file lock) — prevents two separate ingest
       processes from both reading version N and both trying to publish as N+1.

    Lock-target selection (no directories are ever created here):
    - If ``publish_root`` already exists: lock inside it directly.
    - Otherwise: lock inside its parent (the step folder, which exists for any
      real Ramses shot) and re-check ``publish_root`` inside the lock to close
      the TOCTOU window.
    - If neither directory exists: return 1 immediately (brand-new shot).
    """
    publish_root = normalize_path(publish_root)

    if os.path.isdir(publish_root):
        lock_dir = publish_root
    else:
        lock_dir = os.path.dirname(publish_root)
        if not os.path.isdir(lock_dir):
            return 1  # Neither _published nor its parent exist yet — version 1.

    with _VERSION_LOCK, _folder_lock(lock_dir):
        if not os.path.isdir(publish_root):
            return 1  # Still absent inside the lock — no prior versions.
        max_v = 0
        version_re = re.compile(r"^(?:(?P<res>[^_]+)_)?(?P<ver>\d{3})(?:_(?P<state>.*))?$")
        try:
            for item in os.listdir(publish_root):
                match = version_re.match(item)
                if match:
                    v_path = os.path.join(publish_root, item)
                    if os.path.exists(os.path.join(v_path, ".ramses_complete")):
                        v = int(match.group("ver"))
                        if v > max_v: max_v = v
        except Exception: pass
        return max_v + 1


def generate_thumbnail_for_result(result: IngestResult, ocio_config: str | None = None, ocio_in: str = "sRGB") -> bool:
    if not result.success or not result.plan.target_preview_dir: return False
    try:
        from ramses_ingest.preview import generate_thumbnail as gen_thumb
        os.makedirs(result.plan.target_preview_dir, exist_ok=True)
        thumb_path = os.path.join(result.plan.target_preview_dir, f"{result.plan.project_id}_S_{result.plan.shot_id}_{result.plan.step_id}.jpg")
        if gen_thumb(result.plan.match.clip, thumb_path, ocio_config=ocio_config, ocio_in=ocio_in):
            result.preview_path = thumb_path; return True
        return False
    except Exception: return False


def check_for_duplicates(plans: list[IngestPlan]) -> None:
    from ramses_ingest.validator import check_for_duplicate_version
    for plan in plans:
        if not plan.match.matched or not plan.target_publish_dir: continue
        is_dup, dup_path, dup_version = check_for_duplicate_version(plan.match.clip, os.path.dirname(plan.target_publish_dir), resource=plan.resource)
        if is_dup:
            plan.is_duplicate, plan.duplicate_version, plan.duplicate_path = True, dup_version, dup_path
            plan.error = f"Duplicate of v{dup_version:03d}"


def check_for_path_collisions(plans: list[IngestPlan]) -> None:
    from collections import defaultdict
    path_to_plans = defaultdict(list)
    for plan in plans:
        if not plan.match.matched or not plan.target_publish_dir: continue
        path_to_plans[os.path.normpath(plan.target_publish_dir).lower()].append(plan)
    for colliding in path_to_plans.values():
        if len(colliding) > 1:
            for p in colliding:
                msg = f"COLLISION: {len(colliding)} clips resolving to same path"
                p.error = f"{p.error} | {msg}" if p.error and "COLLISION" not in p.error else msg


def resolve_paths(plans: list[IngestPlan], project_root: str, shots_folder: str = FolderNames.shots) -> None:
    version_cache: dict[str, int] = {}
    for plan in plans:
        if not plan.can_execute: continue
        proj_id, shot_id, step_id = plan.project_id, plan.shot_id.upper(), plan.step_id
        if any(c in proj_id + shot_id + step_id for c in "/\\") or ".." in proj_id + shot_id + step_id:
            plan.error = "Invalid IDs contain path separators"; continue
        
        snm = RamFileInfo(); snm.project, snm.ramType, snm.shortName = proj_id, ItemType.SHOT, shot_id
        shot_root = os.path.join(project_root, shots_folder, snm.fileName())
        nm = RamFileInfo(); nm.project, nm.ramType, nm.shortName, nm.step = proj_id, ItemType.SHOT, shot_id, step_id
        step_folder = os.path.join(shot_root, nm.fileName())
        publish_root = os.path.join(step_folder, "_published")
        if publish_root not in version_cache: version_cache[publish_root] = _get_next_version(publish_root)
        plan.version = version_cache[publish_root]
        if plan.version <= 0 or plan.version > 999: plan.error = f"Invalid version: {plan.version}"; continue
        version_str = f"{plan.resource}_{plan.version:03d}_{plan.state}" if plan.resource else f"{plan.version:03d}_{plan.state}"
        plan.target_publish_dir, plan.target_preview_dir = os.path.join(publish_root, version_str), os.path.join(step_folder, "_preview")


def resolve_paths_from_daemon(plans: list[IngestPlan], shot_objects: dict[str, object]) -> None:
    from ramses.daemon_interface import RamDaemonInterface
    daemon, version_cache = RamDaemonInterface.instance(), {}
    for plan in plans:
        if not plan.can_execute: continue
        shot_obj = shot_objects.get(plan.shot_id.upper())
        if not shot_obj: continue
        try:
            base_path = normalize_path(daemon.getPath(shot_obj.uuid(), "RamShot"))
            if not base_path: continue
            nm = RamFileInfo(); nm.project, nm.ramType, nm.shortName, nm.step = plan.project_id, ItemType.SHOT, plan.shot_id.upper(), plan.step_id
            step_root = f"{base_path}/{nm.fileName()}"
            publish_root = f"{step_root}/_published"
            if publish_root not in version_cache: version_cache[publish_root] = _get_next_version(publish_root)
            plan.version = version_cache[publish_root]
            version_str = f"{plan.resource}_{plan.version:03d}_{plan.state}" if plan.resource else f"{plan.version:03d}_{plan.state}"
            plan.target_publish_dir, plan.target_preview_dir = f"{publish_root}/{version_str}", f"{step_root}/_preview"
        except Exception: pass


def _write_ramses_metadata(folder: str, version: int, comment: str = "", timecode: str = "", checksums: dict[str, str] | None = None) -> None:
    """Write metadata and completion marker atomically.

    Uses two layers of locking:
    1. ``_METADATA_WRITE_LOCK`` (threading.Lock) — serialises threads within
       the same process.
    2. ``_folder_lock`` (O_CREAT | O_EXCL file lock) — prevents concurrent
       writes from separate ingest processes running against the same folder.
    """
    with _METADATA_WRITE_LOCK, _folder_lock(folder):
        meta_path = os.path.join(folder, "_ramses_data.json")
        data = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f: data = json.load(f)
            except Exception: pass
        
        timestamp = int(time.time())
        filenames = list(checksums.keys()) if checksums else [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and not f.startswith("._") and f not in {".DS_Store", "Thumbs.db", "_ramses_data.json", ".ramses_complete"}]
        for fname in filenames:
            entry = {"version": version, "comment": comment, "state": "wip", "date": timestamp}
            if timecode: entry["timecode"] = timecode
            if checksums and fname in checksums: entry["md5"] = checksums[fname]
            data[fname] = entry

        import tempfile
        fd, t_path = tempfile.mkstemp(dir=folder, prefix=".ram_meta_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
            os.replace(t_path, meta_path)
            # Write completion marker INSIDE lock
            with open(os.path.join(folder, ".ramses_complete"), "w") as f: f.write(str(timestamp))
        except Exception:
            if os.path.exists(t_path): os.remove(t_path)
            raise


def execute_plan(
    plan: IngestPlan, generate_thumbnail: bool = True, generate_proxy: bool = False,
    progress_callback: Callable[[str], None] | None = None, ocio_config: str | None = None,
    ocio_in: str = "sRGB", ocio_out: str = "sRGB", skip_ramses_registration: bool = False,
    dry_run: bool = False, fast_verify: bool = True, copy_max_workers: int | None = None,
) -> IngestResult:
    _log = lambda m: progress_callback(m) if progress_callback else None
    result = IngestResult(plan=plan, missing_frames=plan.match.clip.missing_frames)
    if not plan.can_execute:
        result.error = plan.error or "Cannot execute plan"
        return result
    if not plan.target_publish_dir:
        result.error = "No target publish directory resolved."
        return result

    try:
        _log(f"  {'Simulating' if dry_run else 'Copying'} files...")
        count, sums, bts, first = copy_frames(plan.match.clip, plan.target_publish_dir, plan.project_id, plan.shot_id, plan.step_id, resource=plan.resource, progress_callback=progress_callback, dry_run=dry_run, fast_verify=fast_verify, max_workers=copy_max_workers)
        result.frames_copied = plan.media_info.frame_count if not plan.match.clip.is_sequence and plan.media_info.frame_count > 0 else count
        result.checksums, result.bytes_copied, result.published_path = sums, bts, plan.target_publish_dir
        if first in sums: result.checksum = sums[first]
        if not dry_run: _write_ramses_metadata(plan.target_publish_dir, plan.version, comment="Ingested via Ramses-Ingest", timecode=plan.media_info.start_timecode, checksums=sums)
    except Exception as exc:
        error_msg = str(exc)
        if not dry_run and os.path.exists(plan.target_publish_dir):
            try:
                shutil.rmtree(plan.target_publish_dir)
                _log("  Rollback successful.")
                result.error = f"Ingest failed (Rolled back): {error_msg}"
                return result
            except Exception as rollback_err:
                _log(f"  Rollback failed: {rollback_err}")
                result.error = f"Ingest failed AND rollback failed: {error_msg}"
                return result
        result.error = f"Ingest failed: {error_msg}"
        return result

    # Register in the Ramses DB only after files are confirmed on disk.
    # Registering before copy_frames would leave orphaned shots/sequences if
    # the copy fails and is rolled back (zombie DB entries).
    if not skip_ramses_registration and not dry_run:
        try: register_ramses_objects(plan, _log)
        except Exception as e: _log(f"  Ramses DB (non-fatal): {e}")

    result._thumbnail_job = None
    if generate_thumbnail and not dry_run:
        if not plan.resource:
            os.makedirs(plan.target_preview_dir, exist_ok=True)
            t_path = os.path.join(plan.target_preview_dir, f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.jpg")
        else:
            import tempfile
            t_path = os.path.join(tempfile.gettempdir(), f"ram_tmp_{plan.project_id}_{plan.shot_id}_{re.sub(r'[/\\:*?\"<>|]', '_', plan.resource)}_{int(time.time())}.jpg")
        result._thumbnail_job = {"clip": plan.match.clip, "path": t_path, "ocio_config": ocio_config, "ocio_in": ocio_in, "is_resource": bool(plan.resource)}

    if generate_proxy and plan.target_preview_dir and not dry_run and not plan.resource:
        try:
            from ramses_ingest.preview import generate_proxy as gen_proxy
            gen_proxy(plan.match.clip, os.path.join(plan.target_preview_dir, f"{plan.project_id}_S_{plan.shot_id}_{plan.step_id}.mp4"), ocio_config=ocio_config, ocio_in=ocio_in)
        except Exception as e: _log(f"  Proxy failed: {e}")

    result.success = True
    return result


def register_ramses_objects(plan: IngestPlan, log: Callable[[str], None], sequence_cache: dict[str, str] | None = None, shot_cache: dict[str, object] | None = None, skip_status_update: bool = False) -> None:
    try:
        from ramses import Ramses
        ram = Ramses.instance()
        if not ram.online(): return
    except Exception: return
    from ramses.ram_sequence import RamSequence
    from ramses.ram_shot import RamShot
    from ramses.daemon_interface import RamDaemonInterface
    info, daemon, project = plan.media_info, RamDaemonInterface.instance(), ram.project()
    if not project: return
    project_uuid = project.uuid()

    seq_obj = None
    if plan.sequence_id:
        seq_up = plan.sequence_id.upper()
        if sequence_cache and seq_up in sequence_cache: seq_obj = RamSequence(sequence_cache[seq_up])
        else:
            for s in project.sequences():
                if s.shortName().upper() == seq_up: seq_obj = s; break
        seq_data = {"shortName": plan.sequence_id, "name": plan.sequence_id, "folderPath": join_normalized(project.folderPath(), FolderNames.shots, plan.sequence_id), "project": project_uuid, "overrideResolution": True, "width": info.width or 1920, "height": info.height or 1080, "overrideFramerate": True, "framerate": info.fps or 24.0, "overridePixelAspectRatio": True, "pixelAspectRatio": info.pixel_aspect_ratio}
        if not seq_obj:
            log(f"  Creating sequence {plan.sequence_id}..."); seq_obj = RamSequence(data=seq_data, create=True)
            if sequence_cache is not None:
                with _RAMSES_CACHE_LOCK: sequence_cache[seq_up] = seq_obj.uuid()
        else:
            if any(seq_obj.data().get(k) != v for k, v in seq_data.items()): seq_obj.setData(seq_data)

    if plan.shot_id:
        shot_up = plan.shot_id.upper()
        shot_obj = shot_cache.get(shot_up) if shot_cache else None
        if not shot_obj:
            for s in project.shots(lazyLoading=False):
                if s.shortName().upper() == shot_up: shot_obj = s; break
        shot_nm = RamFileInfo(); shot_nm.project, shot_nm.ramType, shot_nm.shortName = plan.project_id, ItemType.SHOT, plan.shot_id
        shot_data = {"shortName": plan.shot_id, "name": plan.shot_id, "folderPath": join_normalized(project.folderPath(), FolderNames.shots, shot_nm.fileName()), "project": project_uuid}
        if not plan.resource:
            # Primary clip: update duration and source media from the ingested clip
            duration = (info.frame_count or plan.match.clip.frame_count) / info.fps if info.fps and info.fps > 0 else 5.0
            shot_data["duration"] = duration
            shot_data["sourceMedia"] = plan.match.clip.base_name
        else:
            # Resource clip: preserve existing duration and source media so a short
            # reference/resource never overwrites the hero plate's metadata
            if shot_obj and shot_obj.get("duration"): shot_data["duration"] = shot_obj.get("duration")
            if shot_obj and shot_obj.get("sourceMedia"): shot_data["sourceMedia"] = shot_obj.get("sourceMedia")
        if seq_obj: shot_data["sequence"] = seq_obj.uuid()
        if not shot_obj:
            log(f"  Creating shot {plan.shot_id}..."); shot_obj = RamShot(data=shot_data, create=True)
            if shot_cache is not None:
                with _RAMSES_CACHE_LOCK: shot_cache[shot_up] = shot_obj
        else:
            if any(shot_obj.data().get(k) != v for k, v in shot_data.items()): shot_obj.setData(shot_data)
    if not skip_status_update: update_ramses_status(plan, plan.state, shot_cache=shot_cache)


_USER_ASSIGNMENT_SUPPORTED = True

def update_ramses_status(plan: IngestPlan, status_name: str = "OK", shot_cache: dict[str, object] | None = None) -> bool:
    global _USER_ASSIGNMENT_SUPPORTED
    try:
        from ramses import Ramses
        ram = Ramses.instance()
        if not ram.online(): return False
        project = ram.project()
        if not project: return False
        target_shot = shot_cache.get(plan.shot_id.upper()) if shot_cache else next((s for s in project.shots(lazyLoading=False) if s.shortName().upper() == plan.shot_id.upper()), None)
        if not target_shot: return False
        from ramses.ram_step import StepType
        target_step = next((s for s in project.steps(StepType.SHOT_PRODUCTION) if s.shortName() == plan.step_id), None)
        if not target_step: return False
        status = target_shot.currentStatus(target_step)
        if status:
            state = next((s for s in ram.states() if s.shortName().upper() == status_name.upper()), None)
            if state:
                status.setState(state); status.setCompletionRatio(100 if status_name.upper() == "OK" else 0)
                if _USER_ASSIGNMENT_SUPPORTED:
                    try: status.setUser()
                    except Exception as e:
                        if "unknown query" in str(e).lower(): _USER_ASSIGNMENT_SUPPORTED = False
                return True
        return False
    except Exception: return False

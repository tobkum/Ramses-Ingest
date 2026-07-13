# -*- coding: utf-8 -*-
"""Whole-project ingest report, built from the pipeline's on-disk state.

Sessions record what *happened* (attempts, including failures and later
reverts); this module reports what *is*: every published version that carries
an Ingest sidecar (``_ramses_data.json``), across any number of ingest
sessions. A reverted or deleted version simply is not on disk anymore, so the
report needs no reconciliation logic to stay clean — which is exactly what a
client-facing document requires.

Each version found is synthesized into the same ``IngestResult`` shape the
per-session report consumes, so both reports share one HTML template and one
JSON schema.
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Callable, Optional

from ramses_ingest.scanner import Clip
from ramses_ingest.prober import probe_file, MediaInfo
from ramses_ingest.matcher import MatchResult
from ramses_ingest.publisher import IngestPlan, IngestResult
from ramses_ingest.preview import generate_thumbnail
from ramses_ingest.reporting import generate_html_report, generate_json_audit_trail
from ramses_ingest.path_utils import normalize_path

logger = logging.getLogger(__name__)

# Published sequence frames are normalized to dot separators:
# {PROJ}_S_{SHOT}_{STEP}[_{RESOURCE}].{frame}.{ext}
_PUBLISHED_FRAME_RE = re.compile(r"\.(\d+)\.[A-Za-z0-9]+$")

_SIDECAR = "_ramses_data.json"
_SKIP_FILES = {_SIDECAR, "Thumbs.db", ".DS_Store"}


def _parse_version_folder(name: str) -> tuple[str, int, str]:
    """Splits ``[RESOURCE_]NNN[_STATE]`` into (resource, version, state)."""
    blocks = name.split("_")
    for i, block in enumerate(blocks):
        if block.isdigit():
            resource = "_".join(blocks[:i])
            state = "_".join(blocks[i + 1:])
            return resource, int(block), state
    return "", 0, ""


def _parse_step_folder(name: str) -> tuple[str, str, str]:
    """Splits ``{PROJ}_S_{SHOT}_{STEP}`` into (project, shot, step)."""
    parts = name.rsplit("_S_", 1)
    if len(parts) != 2 or "_" not in parts[1]:
        return "", "", ""
    shot, step = parts[1].rsplit("_", 1)
    return parts[0], shot, step


def _read_sidecar(folder: str) -> dict:
    try:
        with open(os.path.join(folder, _SIDECAR), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable sidecar in %s: %s", folder, exc)
        return {}


def _footage_files(folder: str) -> list[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(
        n for n in names
        if not n.startswith(".") and n not in _SKIP_FILES
        and os.path.isfile(os.path.join(folder, n))
    )


def _synthesize_result(version_dir: str, fallback_project_id: str) -> Optional[IngestResult]:
    """Builds an IngestResult for one published version folder on disk."""
    sidecar = _read_sidecar(version_dir)
    if not sidecar:
        return None
    files = _footage_files(version_dir)
    if not files:
        return None

    step_dir = os.path.dirname(os.path.dirname(version_dir))  # …/step/_published/version
    step_dir_name = os.path.basename(step_dir)
    proj_id, shot_id, step_id = _parse_step_folder(step_dir_name)
    resource, version, state = _parse_version_folder(os.path.basename(version_dir))

    # Sidecar entry of the first footage file (they share the version fields)
    meta = sidecar.get(files[0]) or next(iter(sidecar.values()), {})
    if not isinstance(meta, dict):
        meta = {}
    version = version or int(meta.get("version") or 0)
    state = state or str(meta.get("state", "")).upper()

    # Frame analysis from the actual files on disk
    frames = []
    for n in files:
        m = _PUBLISHED_FRAME_RE.search(n)
        if m:
            frames.append(int(m.group(1)))
    frames.sort()
    is_sequence = len(frames) >= 2
    first_file = os.path.join(version_dir, files[0])
    extension = os.path.splitext(files[0])[1].lstrip(".").lower()

    # Files recorded at ingest time but no longer on disk = integrity warning
    recorded = [n for n in sidecar.keys() if isinstance(sidecar.get(n), dict)]
    lost = sorted(set(recorded) - set(files))

    try:
        media_info = probe_file(first_file)
    except Exception as exc:
        logger.debug("Probe failed for %s: %s", first_file, exc)
        media_info = MediaInfo()

    # Effective technical values recorded at ingest time win over a re-probe:
    # sequences carry no framerate, and operator overrides (fps, colorspace)
    # exist only in the sidecar.
    sidecar_fps = meta.get("fps")
    if isinstance(sidecar_fps, (int, float)) and sidecar_fps > 0:
        media_info.fps = float(sidecar_fps)

    clip = Clip(
        base_name=str(meta.get("sourceMedia") or step_dir_name),
        extension=extension,
        directory=Path(version_dir),
        is_sequence=is_sequence,
        frames=frames,
        first_file=first_file,
    )
    plan = IngestPlan(
        match=MatchResult(clip=clip, shot_id=shot_id, matched=True),
        media_info=media_info,
        shot_id=shot_id,
        project_id=proj_id or fallback_project_id,
        step_id=step_id,
        resource=resource,
        state=state or "WIP",
        version=version,
    )
    # Operator-set values are marked "manual" in the report, so the client
    # can flag wrong assumptions
    if meta.get("fpsManual"):
        plan.fps_is_manual = True
    if meta.get("colorspaceManual") and meta.get("colorspace"):
        plan.colorspace_override = str(meta["colorspace"])
    if lost:
        plan.warnings.append(
            f"{len(lost)} file(s) recorded at ingest are missing on disk"
        )
    if not os.path.isfile(os.path.join(version_dir, ".ramses_complete")):
        plan.warnings.append("No completion marker — the ingest may have been interrupted")

    # Extra context for the report row / JSON (dynamic attrs, template uses getattr)
    date_val = meta.get("date")
    plan.ingest_date_ts = float(date_val) if isinstance(date_val, (int, float)) else 0.0
    if plan.ingest_date_ts > 0:
        plan.ingested_on = time.strftime("%Y-%m-%d %H:%M", time.localtime(date_val))
    plan.ingest_source = str(meta.get("source", ""))
    plan.ingest_operator = str(meta.get("operator", ""))
    plan.ingest_verification = str(meta.get("verification", ""))
    plan.ingest_colorspace = str(meta.get("colorspace", ""))

    checksums = {
        n: str(entry.get("md5"))
        for n, entry in sidecar.items()
        if isinstance(entry, dict) and entry.get("md5")
    }
    try:
        total_bytes = sum(os.path.getsize(os.path.join(version_dir, n)) for n in files)
    except OSError:
        total_bytes = 0

    result = IngestResult(
        plan=plan,
        success=True,
        published_path=normalize_path(version_dir),
        frames_copied=len(files) if is_sequence else max(1, media_info.frame_count if getattr(media_info, "frame_count", 0) else 1),
        bytes_copied=total_bytes,
        checksum=checksums.get(files[0], ""),
        checksums=checksums,
        missing_frames=clip.missing_frames,
    )

    # Thumbnail written by Ingest next to the step folder
    thumb = os.path.join(step_dir, "_preview", f"{step_dir_name}.jpg")
    if os.path.isfile(thumb):
        result.preview_path = thumb
    return result


def collect_ingested_versions(
    project_path: str,
    progress_callback: Callable[[str], None] | None = None,
    fallback_project_id: str = "",
) -> list[IngestResult]:
    """Finds every Ingest-written published version under the project's shots.

    Only version folders carrying the Ingest sidecar are included — versions
    published by other tools (e.g. Fusion comp backups) are not footage
    deliveries and stay out of the client report.
    """
    _log = progress_callback or (lambda m: None)

    try:
        from ramses.constants import FolderNames
        shots_root = os.path.join(project_path, FolderNames.shots)
    except ImportError:
        shots_root = project_path

    if not os.path.isdir(shots_root):
        shots_root = project_path

    results: list[IngestResult] = []
    for dirpath, dirnames, filenames in os.walk(shots_root):
        if os.path.basename(dirpath) != "_published":
            continue
        dirnames.sort()
        for version_name in list(dirnames):
            version_dir = os.path.join(dirpath, version_name)
            if not os.path.isfile(os.path.join(version_dir, _SIDECAR)):
                continue
            res = _synthesize_result(version_dir, fallback_project_id)
            if res:
                results.append(res)
                _log(f"  found {res.plan.shot_id} v{res.plan.version:03d}")
        # Never descend into version folders themselves
        dirnames.clear()

    results.sort(key=lambda r: (r.plan.shot_id, r.plan.step_id, r.plan.resource, r.plan.version))
    return results


def _ensure_version_thumbnails(
    results: list[IngestResult],
    tmp_dir: str,
    ocio_config: Optional[str] = None,
    ocio_in_default: str = "sRGB",
    log: Callable[[str], None] = lambda m: None,
) -> None:
    """Gives every report row a thumbnail of ITS OWN frames.

    The permanent `_preview` thumbnail belongs to the shot's latest hero
    version — resource versions (whose ingest-time thumbnails are transient
    by design) and superseded hero versions would silently inherit it,
    showing the wrong image in the report. Those rows get a transient
    thumbnail rendered from their own first frames instead (embedded as
    base64 during report generation; *tmp_dir* is deleted afterwards).
    """
    latest_hero: dict[tuple, int] = {}
    for r in results:
        p = r.plan
        if not p.resource:
            key = (p.shot_id, p.step_id)
            latest_hero[key] = max(latest_hero.get(key, 0), p.version)

    for r in results:
        p = r.plan
        is_latest_hero = (
            not p.resource
            and latest_hero.get((p.shot_id, p.step_id)) == p.version
        )
        if is_latest_hero and r.preview_path:
            continue  # the permanent thumbnail IS this version's image

        out = os.path.join(
            tmp_dir,
            f"{p.shot_id}_{p.step_id}_{p.resource or 'HERO'}_{p.version:03d}.jpg",
        )
        try:
            ocio_in = getattr(p, "ingest_colorspace", "") or ocio_in_default
            if generate_thumbnail(
                p.match.clip, out, ocio_config=ocio_config, ocio_in=ocio_in
            ) and os.path.isfile(out):
                r.preview_path = out
            else:
                r.preview_path = ""
        except Exception as exc:
            log(f"  Thumbnail failed for {p.shot_id} v{p.version:03d}: {exc}")
            r.preview_path = ""


_REPORT_NAME_RE = re.compile(r"^Project_Ingest_Report_.+_(\d{8}-\d{6})\.html$")


def find_last_report_time(output_dir: str) -> Optional[float]:
    """Timestamp of the most recent project report in *output_dir*, or None.

    Parsed from the report filenames, so 'new since the last report' works
    across machines and sessions without any extra state file.
    """
    latest = None
    try:
        names = os.listdir(output_dir)
    except OSError:
        return None
    for name in names:
        m = _REPORT_NAME_RE.match(name)
        if not m:
            continue
        try:
            ts = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
        except ValueError:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def generate_project_report(
    project_path: str,
    output_dir: str,
    project_id: str = "",
    studio_name: str = "Ramses Studio",
    studio_logo: str = "",
    operator: str = "Unknown",
    progress_callback: Callable[[str], None] | None = None,
    since: Optional[float] = None,
    ocio_config: Optional[str] = None,
    ocio_in_default: str = "sRGB",
) -> tuple[Optional[str], Optional[str]]:
    """Renders the whole-project HTML report and its JSON manifest.

    Args:
        since: When given, only versions ingested after this timestamp are
            included ("delta report" for later deliveries — the client gets
            just the newly ingested files). The full report is the default.
        ocio_config: OCIO config used when rendering transient thumbnails
            for versions without a matching permanent one (resources,
            superseded hero versions).

    Returns:
        (html_path, json_path) — either may be None on failure/empty result.
    """
    _log = progress_callback or (lambda m: None)
    _log("Scanning published versions...")
    results = collect_ingested_versions(project_path, progress_callback, fallback_project_id=project_id)

    title = "Project Ingest Report"
    if since is not None:
        since_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(since))
        results = [r for r in results if getattr(r.plan, "ingest_date_ts", 0.0) > since]
        title = f"Ingest Report — new since {since_str}"
        _log(f"Filtering to versions ingested after {since_str}...")

    if not results:
        _log("No ingested versions found.")
        return None, None
    _log(f"Found {len(results)} ingested version(s). Rendering report...")

    # Honest verification badge: only claim a mode if every version agrees
    modes = {getattr(r.plan, "ingest_verification", "") for r in results}
    verification = modes.pop() if len(modes) == 1 else ""

    ts = time.strftime("%Y%m%d-%H%M%S")
    tag = project_id or "PROJECT"
    html_path = os.path.join(output_dir, f"Project_Ingest_Report_{tag}_{ts}.html")
    json_path = os.path.join(output_dir, f"Project_Ingest_Manifest_{tag}_{ts}.json")

    # Transient per-version thumbnails (deleted after base64 embedding)
    import shutil
    import tempfile
    thumb_tmp = tempfile.mkdtemp(prefix="ramses_report_thumbs_")
    try:
        _log("Rendering per-version thumbnails...")
        _ensure_version_thumbnails(
            results, thumb_tmp,
            ocio_config=ocio_config, ocio_in_default=ocio_in_default, log=_log,
        )
        ok = generate_html_report(
            results,
            html_path,
            studio_name=studio_name,
            studio_logo_path=studio_logo,
            operator=operator,
            verification=verification,
            title=title,
            id_label="Report ID",
        )
    finally:
        shutil.rmtree(thumb_tmp, ignore_errors=True)

    # Client-facing manifest: no internal filesystem paths
    json_ok = generate_json_audit_trail(
        results, json_path, project_id=tag, operator=operator, include_paths=False
    )
    return (html_path if ok else None), (json_path if json_ok else None)

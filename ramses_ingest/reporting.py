# -*- coding: utf-8 -*-
"""Ingest report generation (HTML/JSON)."""

from __future__ import annotations

import os
import time
import base64
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ramses_ingest.publisher import IngestResult


def _get_base64_image(path: str) -> str:
    """Encode an image file to a Base64 data URI."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def generate_json_audit_trail(results: list[IngestResult], output_path: str, project_id: str = "PROJ", operator: str = "Unknown") -> bool:
    """Generate machine-readable JSON audit trail for database integration.

    Exports comprehensive ingest metadata including checksums, colorspace info,
    frame continuity, and error details for VFX pipeline tracking systems.
    """
    import json
    import time

    audit_data = {
        "version": "1.0",
        "schema": "ramses-ingest-audit",
        "project": project_id,
        "operator": operator,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "total_clips": len(results),
            "succeeded": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "total_frames": sum(r.frames_copied for r in results if r.success),
            "total_bytes": sum(r.bytes_copied for r in results if r.success),
        },
        "clips": []
    }

    for res in results:
        if not res or not res.plan:
            continue

        mi = res.plan.media_info
        clip_data = {
            "shot_id": res.plan.shot_id,
            "sequence_id": res.plan.sequence_id or None,
            "version": res.plan.version,
            "step": res.plan.step_id,
            "status": "success" if res.success else "failed",
            "error": res.error or None,
            "frames": {
                "count": res.frames_copied,
                "missing": res.missing_frames if res.missing_frames else None,
                "has_gaps": len(res.missing_frames) > 0,
            },
            "technical": {
                "resolution": {"width": mi.width, "height": mi.height} if mi.width else None,
                "framerate": mi.fps if mi.fps else None,
                "codec": mi.codec or None,
                "pixel_format": mi.pix_fmt or None,
                "duration_seconds": mi.duration_seconds if mi.duration_seconds else None,
            },
            "colorspace": {
                "primaries": mi.color_primaries or None,
                "transfer": mi.color_transfer or None,
                "space": mi.color_space or None,
            },
            "editorial": {
                "start_timecode": mi.start_timecode or None,
            },
            "integrity": {
                "md5_checksum": res.checksum or None,
                "bytes_verified": res.bytes_copied,
            },
            "paths": {
                "published": res.published_path or None,
                "preview": res.preview_path or None,
            },
        }
        audit_data["clips"].append(clip_data)

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def generate_html_report(results: list[IngestResult], output_path: str, studio_name: str = "Ramses Studio", operator: str = "Unknown") -> bool:
    """Generate a clean, professional HTML manifest with exact analytics and technical flagging."""
    
    css = """
    :root {
        --bg: #f8f9fa;
        --card-bg: #ffffff;
        --border: #e0e0e0;
        --border-light: #f0f0f0;
        --text-main: #1a1a1a;
        --text-muted: #6c757d;
        --accent: #0056b3;
        --accent-hover: #004494;
        --success: #28a745;
        --warning: #ffc107;
        --error: #dc3545;
        --table-header: #f8f9fa;
        --table-row-hover: rgba(0, 86, 179, 0.04);
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
        --shadow-lg: 0 10px 30px rgba(0,0,0,0.12);
    }

    [data-theme="dark"] {
        --bg: #0d1117;
        --card-bg: #161b22;
        --border: #30363d;
        --border-light: #21262d;
        --text-main: #e6edf3;
        --text-muted: #8b949e;
        --accent: #58a6ff;
        --accent-hover: #79c0ff;
        --success: #3fb950;
        --warning: #d29922;
        --error: #f85149;
        --table-header: #0d1117;
        --table-row-hover: rgba(88, 166, 255, 0.06);
        --shadow-sm: 0 0 0 1px rgba(0,0,0,0.1);
        --shadow-md: 0 0 0 1px rgba(0,0,0,0.1);
        --shadow-lg: 0 0 0 1px rgba(0,0,0,0.1);
    }

    * { box-sizing: border-box; }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif;
        background-color: var(--bg);
        color: var(--text-main);
        padding: 20px;
        margin: 0;
        line-height: 1.6;
        -webkit-font-smoothing: antialiased;
        transition: background-color 0.2s ease, color 0.2s ease;
    }

    .report {
        max-width: 100%;
        margin: 0 auto;
        background: var(--card-bg);
        padding: 32px;
        border: 1px solid var(--border);
        border-radius: 8px;
        box-shadow: var(--shadow-lg);
    }

    header {
        border-bottom: 3px solid var(--accent);
        padding-bottom: 24px;
        margin-bottom: 32px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }

    .studio-header {
        font-size: 11px;
        font-weight: 700;
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: 2.5px;
        margin-bottom: 8px;
    }

    h1 {
        margin: 0;
        font-size: 32px;
        font-weight: 700;
        color: var(--text-main);
        letter-spacing: -0.5px;
    }

    /* Theme Toggle */
    .theme-toggle {
        background: var(--table-header);
        border: 1px solid var(--border);
        color: var(--text-main);
        padding: 8px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: all 0.2s ease;
    }
    .theme-toggle:hover {
        background: var(--border-light);
        transform: translateY(-1px);
        box-shadow: var(--shadow-sm);
    }

    /* Executive Health Dashboard */
    .health-dashboard {
        display: flex;
        gap: 16px;
        margin-bottom: 32px;
    }

    .health-badge {
        flex: 0 0 150px;
        padding: 16px;
        border-radius: 8px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        border: 2px solid;
        box-shadow: var(--shadow-md);
        transition: transform 0.2s ease;
    }

    .health-badge:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-lg);
    }

    .health-score {
        font-size: 26px;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 8px;
        letter-spacing: -0.5px;
    }

    .health-label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        opacity: 0.95;
    }

    .health-green { background-color: var(--success); color: #fff; border-color: var(--success); }
    .health-yellow { background-color: var(--warning); color: #000; border-color: var(--warning); }
    .health-red { background-color: var(--error); color: #fff; border-color: var(--error); }

    [data-theme="dark"] .health-yellow { color: #000; }

    .meta-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 1px;
        background: var(--border);
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
        flex-grow: 1;
    }

    .meta-item {
        flex: 1;
        background: var(--card-bg);
        padding: 12px 14px;
        min-width: 110px;
    }

    .meta-label {
        font-size: 11px;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
        display: block;
    }

    .meta-value {
        font-size: 14px;
        color: var(--text-main);
        font-weight: 600;
        display: block;
    }

    .meta-value-project {
        font-size: 16px;
        color: var(--text-main);
        font-weight: 700;
        display: block;
    }

    /* Alert Boxes */
    .attention-box {
        background: #fff3cd;
        border: 2px solid #ffc107;
        border-left-width: 4px;
        color: #000;
        padding: 14px 20px;
        border-radius: 6px;
        margin-bottom: 16px;
        font-size: 13px;
        font-weight: 500;
        line-height: 1.5;
    }

    [data-theme="dark"] .attention-box {
        background: rgba(255, 193, 7, 0.08);
        border-color: var(--warning);
        color: var(--warning);
    }

    .error-summary {
        background: rgba(220, 53, 69, 0.06);
        border: 2px solid var(--error);
        border-left-width: 4px;
        border-radius: 8px;
        padding: 24px;
        margin-bottom: 32px;
    }

    .error-summary-title {
        font-size: 16px;
        font-weight: 700;
        color: var(--error);
        margin-bottom: 16px;
        letter-spacing: -0.2px;
    }

    .error-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
    }

    .error-list li {
        padding: 10px 14px;
        background: var(--card-bg);
        border-radius: 4px;
        border-left: 3px solid var(--error);
        font-size: 12px;
        line-height: 1.5;
        box-shadow: var(--shadow-sm);
    }

    /* Table Styling */
    table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin-top: 24px;
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: var(--shadow-sm);
    }

    thead th {
        background: var(--table-header);
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        padding: 16px 12px;
        text-align: left;
        border-bottom: 2px solid var(--border);
        position: sticky;
        top: 0;
        z-index: 10;
        white-space: nowrap;
    }

    thead th:nth-child(1) { width: 50px; text-align: center; } /* Row # */
    thead th:nth-child(2) { width: 160px; } /* Thumbnail - fixed */
    thead th:nth-child(3) { min-width: 140px; } /* Shot ID */
    thead th:nth-child(4) { text-align: center; } /* Version */
    thead th:nth-child(5) { text-align: center; } /* Verification */
    thead th:nth-child(6) { text-align: right; white-space: nowrap; } /* # Frames */
    thead th:nth-child(7) { text-align: center; } /* Frame Continuity */
    thead th:nth-child(9) { text-align: center; white-space: nowrap; } /* Timecode */
    thead th:nth-child(10) { font-family: 'Consolas', monospace; font-size: 11px; } /* MD5 */

    .row-num {
        text-align: center;
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
    }

    tbody tr {
        transition: background-color 0.15s ease;
    }

    tbody tr:nth-child(even) {
        background: rgba(0, 0, 0, 0.035);
    }

    [data-theme="dark"] tbody tr:nth-child(even) {
        background: rgba(255, 255, 255, 0.02);
    }

    tbody tr:hover {
        background: var(--table-row-hover) !important;
    }

    tbody tr:last-child td {
        border-bottom: none;
    }

    tfoot {
        position: sticky;
        bottom: 0;
        background: var(--table-header);
        border-top: 2px solid var(--border);
        font-weight: 600;
        z-index: 5;
    }

    tfoot td {
        padding: 16px 12px;
        font-size: 12px;
        color: var(--text-main);
        border-bottom: none;
    }

    td {
        padding: 16px 12px;
        border-bottom: 1px solid var(--border-light);
        font-size: 13px;
        vertical-align: middle;
    }

    td:nth-child(4) { text-align: center; } /* Version */
    td:nth-child(5) { text-align: center; } /* Verification */
    td:nth-child(6) { text-align: right; font-variant-numeric: tabular-nums; } /* # Frames */
    td:nth-child(7) { text-align: center; } /* Frame Continuity */
    td:nth-child(9) { text-align: center; } /* Timecode */

    .thumb {
        width: 140px;
        height: 78px;
        background: #000;
        border-radius: 6px;
        object-fit: cover;
        display: block;
        border: 1px solid var(--border);
        box-shadow: var(--shadow-sm);
    }
    
    /* Status Indicators */
    .status-ok {
        color: var(--success);
        font-weight: 700;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .status-fail {
        color: var(--error);
        font-weight: 700;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .status-warn {
        color: var(--warning);
        font-weight: 700;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Shot ID Column */
    .xray-wrap {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .xray-target {
        color: var(--text-main);
        font-weight: 700;
        font-size: 17px;
        line-height: 1.4;
        white-space: nowrap;
        letter-spacing: -0.2px;
    }

    .xray-source {
        color: var(--text-muted);
        font-size: 12px;
        font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
        line-height: 1.5;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .xray-arrow {
        color: var(--accent);
        margin: 0 4px 0 0;
        font-size: 12px;
        opacity: 0.7;
    }

    /* Technical Data Styling */
    .deviation {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffc107;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 11px;
        font-weight: 600;
        display: inline-block;
    }

    [data-theme="dark"] .deviation {
        background-color: rgba(210, 153, 34, 0.15);
        color: #d29922;
        border-color: #d29922;
    }

    .code {
        font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
        background: var(--table-header);
        border: 1px solid var(--border-light);
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 12px;
        color: var(--text-main);
        font-weight: 500;
        display: inline-block;
    }

    .tech {
        color: var(--text-muted);
        font-size: 12px;
        line-height: 1.6;
    }

    .tech b {
        color: var(--text-main);
        font-weight: 600;
    }

    .color-audit {
        color: var(--accent);
        font-weight: 600;
        font-size: 11px;
        margin-top: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .color-audit span {
        cursor: help;
        border-bottom: 1px dotted currentColor;
    }

    .missing-frames {
        color: var(--error);
        font-weight: 700;
        font-size: 11px;
        background: rgba(220, 53, 69, 0.1);
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid var(--error);
        display: inline-block;
    }

    .resource-badge {
        display: inline-block;
        font-size: 10px;
        font-weight: 800;
        background: var(--border);
        color: var(--text-muted);
        padding: 2px 8px;
        border-radius: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-left: 8px;
        vertical-align: middle;
        border: 1px solid var(--border-light);
    }

    [data-theme="dark"] .resource-badge {
        background: #21262d;
        color: #8b949e;
        border-color: #30363d;
    }

    /* Footer */
    .footer {
        margin-top: 60px;
        padding-top: 24px;
        border-top: 2px solid var(--border-light);
        font-size: 11px;
        color: var(--text-muted);
        text-align: center;
        font-weight: 500;
    }

    /* Print Styles */
    @media print {
        body { background: white; padding: 0; }
        .report { box-shadow: none; border: none; padding: 20px; }
        .theme-toggle { display: none; }
        thead th { position: static; }
        tbody tr:hover { background: transparent; }
    }

    /* Responsive */
    @media (max-width: 1200px) {
        body { padding: 12px; }
        .report { padding: 24px; }
        .health-badge { flex: 0 0 130px; padding: 12px; }
        .meta-item { padding: 10px 12px; min-width: 100px; }
        table { font-size: 12px; }
        td { padding: 12px 10px; }
        .thumb { width: 120px; height: 67px; }
    }
    """

    # 1. Analyze Batch for Deviations and Totals
    resolutions = []
    framerates = []
    codecs = []
    total_frames = 0
    total_size_bytes = 0
    succeeded = 0
    failed = 0
    step_id = "—"
    sequences_with_gaps = 0
    total_missing_frames = 0

    # Error categorization for executive summary
    from collections import Counter
    error_categories = Counter()

    # Colorspace validation (Enhancement #3)
    from ramses_ingest.validator import validate_batch_colorspace
    colorspace_issues = validate_batch_colorspace([r.plan for r in results if r.plan])

    for res in results:
        if not res or not res.plan: continue
        step_id = res.plan.step_id

        # Track missing frames (critical for VFX deliveries)
        if res.missing_frames:
            sequences_with_gaps += 1
            total_missing_frames += len(res.missing_frames)

        if res.success:
            succeeded += 1
            total_frames += res.frames_copied
            total_size_bytes += res.bytes_copied # Exact count from verified copy loop

            # HERO SPEC BASELINE: Only use primary clips to determine the common project specs
            if not res.plan.resource:
                mi = res.plan.media_info
                if mi.width: resolutions.append(f"{mi.width}x{mi.height}")
                if mi.fps: framerates.append(mi.fps)
                if mi.codec: codecs.append(mi.codec.lower())
        elif res.error:
            failed += 1
            # Categorize errors for summary
            error_msg = res.error.lower()
            if "match" in error_msg or "naming" in error_msg:
                error_categories["Naming/Matching Issues"] += 1
            elif "md5" in error_msg or "checksum" in error_msg or "verification" in error_msg:
                error_categories["Data Integrity Failures"] += 1
            elif "resolution" in error_msg or "mismatch" in error_msg:
                error_categories["Technical Spec Mismatches"] += 1
            elif "copy" in error_msg or "permission" in error_msg:
                error_categories["File System Errors"] += 1
            else:
                error_categories["Other Errors"] += 1

    # Find "Common" values (Modes)
    def get_mode(data):
        if not data: return None
        return Counter(data).most_common(1)[0][0]

    common_res = get_mode(resolutions)
    common_fps = get_mode(framerates)
    common_codec = get_mode(codecs)

    # 2. Tiered Sorting: Hero first, then Auxiliary (Sequence -> Shot)
    sorted_results = sorted(
        results,
        key=lambda r: (
            1 if r and r.plan and r.plan.resource else 0, # Tier 0: Hero, Tier 1: Aux
            r.plan.sequence_id or "" if r and r.plan else "",
            r.plan.shot_id or "" if r and r.plan else ""
        )
    )

    # 3. Build Rows & Track Deviations
    rows = []
    has_deviations = False
    row_number = 0
    current_tier = 0 # 0=Hero, 1=Aux

    for res in sorted_results:
        if not res or not res.plan: continue
        
        # Check for Tier transition to add a divider
        new_tier = 1 if res.plan.resource else 0
        if row_number > 0 and new_tier != current_tier:
            # Add a sub-header row for Auxiliary data
            rows.append(f"""
            <tr style="background: var(--table-header) !important;">
                <td colspan="10" style="padding: 12px 20px; font-size: 11px; font-weight: 800; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px;">
                    Supporting & Auxiliary Data
                </td>
            </tr>
            """)
        current_tier = new_tier
        
        mi = res.plan.media_info
        status_cls = "status-ok" if res.success else "status-fail"
        
        if res.success:
            if res.plan.resource:
                status_text = "AUXILIARY DATA"
                status_cls = "status-ok" # Keep green but use the new text
            else:
                status_text = "PASSED"
        elif "skipped" in (res.error or "").lower():
            status_text = "SKIPPED"
            status_cls = "status-warn"
        else:
            status_text = "FAILED"
        
        # Deviation Detection - HERO ONLY
        # Resources (Auxiliary) skip the visual deviation highlighting
        res_val = f"{mi.width}x{mi.height}" if mi.width else "—"
        res_dev = (not res.plan.resource and res_val != common_res and common_res)
        res_display = f'<span class="deviation" title="Deviation">{res_val}</span>' if res_dev else res_val
        
        fps_val = mi.fps if mi.fps else 0
        fps_dev = (not res.plan.resource and common_fps and abs(fps_val - common_fps) > 0.001)
        fps_display = f'<span class="deviation">{fps_val:.3f}</span>' if fps_dev else f"{fps_val:.3f}"
        
        codec_val = mi.codec.upper() if mi.codec else "—"
        codec_dev = (not res.plan.resource and mi.codec and mi.codec.lower() != common_codec and common_codec)
        codec_display = f'<span class="deviation">{codec_val}</span>' if codec_dev else codec_val
        
        if res_dev or fps_dev or codec_dev:
            has_deviations = True

        # Format Color VUI with helpful tooltips
        def _colorspace_tooltip(value: str) -> str:
            """Add human-readable tooltips for common colorspace values."""
            tooltips = {
                # Color Primaries
                "bt709": "Rec. 709 (Standard HD television color gamut)",
                "bt2020": "Rec. 2020 (Wide color gamut for UHD/HDR)",
                "smpte170m": "SMPTE 170M (NTSC standard definition)",
                "smpte240m": "SMPTE 240M (Legacy HD standard)",
                "film": "Film primaries (DCI-P3 cinema)",
                "bt470bg": "PAL/SECAM standard definition",
                # Transfer Functions
                "iec61966-2-1": "sRGB transfer (standard web/display gamma)",
                "linear": "Linear light (no gamma encoding)",
                "smpte2084": "PQ (Perceptual Quantizer for HDR10)",
                "arib-std-b67": "HLG (Hybrid Log-Gamma for broadcast HDR)",
                "gamma22": "Gamma 2.2 (PC display standard)",
                "gamma28": "Gamma 2.8 (legacy Mac display)",
                # Color Spaces
                "ycbcr": "YCbCr (standard video color space)",
                "rgb": "RGB (full range color)",
                "ycocg": "YCoCg (luma + chroma color difference)",
            }
            return tooltips.get(value.lower(), value)

        # Check for colorspace issues from validator
        plan_idx = results.index(res)
        cs_issue = colorspace_issues.get(plan_idx)

        color_parts = []
        has_critical_cs_issue = cs_issue and cs_issue.severity == "critical"

        if mi.color_primaries:
            tooltip = _colorspace_tooltip(mi.color_primaries)
            # Highlight if this clip has a colorspace issue
            if has_critical_cs_issue:
                color_parts.append(f'<span class="deviation" title="{cs_issue.message}">{mi.color_primaries}</span>')
            else:
                color_parts.append(f'<span title="{tooltip}">{mi.color_primaries}</span>')
        if mi.color_transfer:
            tooltip = _colorspace_tooltip(mi.color_transfer)
            if has_critical_cs_issue:
                color_parts.append(f'<span class="deviation" title="{cs_issue.message}">{mi.color_transfer}</span>')
            else:
                color_parts.append(f'<span title="{tooltip}">{mi.color_transfer}</span>')
        if mi.color_space:
            tooltip = _colorspace_tooltip(mi.color_space)
            if has_critical_cs_issue:
                color_parts.append(f'<span class="deviation" title="{cs_issue.message}">{mi.color_space}</span>')
            else:
                color_parts.append(f'<span title="{tooltip}">{mi.color_space}</span>')
        color_str = " / ".join(color_parts) if color_parts else '<span title="No color metadata embedded in file">No VUI Tags</span>'

        # Add colorspace warning indicator if present
        if cs_issue:
            color_str += f' <span style="color:#f39c12; font-weight:bold;" title="{cs_issue.message}">⚠</span>'
        
        # Format missing frames for display
        if res.missing_frames:
            if len(res.missing_frames) <= 5:
                missing_display = f'<span class="missing-frames frame-gap-warn">⚠ Missing: {", ".join(map(str, res.missing_frames))}</span>'
            else:
                missing_display = f'<span class="missing-frames frame-gap-warn">⚠ {len(res.missing_frames)} frames missing</span>'
        else:
            missing_display = '<span style="color:#27ae60;">Complete</span>'

        b64_img = _get_base64_image(res.preview_path)
        img_tag = f'<img src="{b64_img}" class="thumb">' if b64_img else '<div class="thumb"></div>'

        # Resource Badge logic
        resource_tag = ""
        if res.plan.resource:
            resource_tag = f'<span class="resource-badge">{res.plan.resource}</span>'

        row_number += 1
        row_html = f"""
        <tr>
            <td class="row-num">{row_number}</td>
            <td>{img_tag}</td>
            <td>
                <div class="xray-wrap">
                    <div class="xray-target">{res.plan.shot_id}{resource_tag}</div>
                    <div class="xray-source" style="margin-top:2px;">{res.plan.sequence_id or ""}</div>
                    <div class="xray-source"><span class="xray-arrow">←</span> {res.plan.match.clip.base_name}.{res.plan.match.clip.extension}</div>
                </div>
            </td>
            <td><span class="code">v{res.plan.version:03d}</span></td>
            <td class="{status_cls}">{status_text}</td>
            <td><b>{res.frames_copied}</b></td>
            <td>{missing_display}</td>
            <td class="tech">
                <b>{res_display}</b> @ {fps_display} fps<br>{codec_display} / {mi.pix_fmt}<br>
                <div class="color-audit">{color_str}</div>
            </td>
            <td><span class="code">{mi.start_timecode or "—"}</span></td>
            <td><span class="code" style="font-size:13px;">{res.checksum or "—"}</span></td>
        </tr>
        """
        rows.append(row_html)

    if not rows:
        rows.append("<tr><td colspan='10' style='text-align:center; padding:40px; color:var(--text-muted);'>No clips processed in this session.</td></tr>")

    # Analytics Header Formatting
    if total_size_bytes >= (1024**3):
        size_display = f"{total_size_bytes / (1024**3):.2f} GB"
    else:
        size_display = f"{total_size_bytes / (1024**2):.1f} MB"

    # 3. Calculate Executive Health Score (Idea #1)
    critical_colorspace_issues = [idx for idx, issue in colorspace_issues.items() if issue.severity == "critical"]
    
    health_cls = "health-green"
    health_score = "HEALTHY"
    health_label = "Verified & Ready"

    if failed > 0:
        health_cls = "health-red"
        health_score = "CRITICAL"
        health_label = f"{failed} Clips Failed"
    elif sequences_with_gaps > 0 or critical_colorspace_issues or has_deviations:
        health_cls = "health-yellow"
        health_score = "WARNING"
        health_label = "Gaps / Deviations"

    # Build error summary section
    error_summary_html = ""
    if failed > 0:
        error_items = []
        for category, count in error_categories.most_common():
            error_items.append(f'<li><span style="font-weight:800; color:var(--error);">{count}</span> clip(s): {category}</li>')

        error_summary_html = f"""
        <div class="error-summary">
            <div class="error-summary-title">Batch Failures</div>
            <ul class="error-list">
                {"".join(error_items)}
            </ul>
        </div>
        """

    # Build combined attention box for all issues
    attention_box = ""
    attention_items = []
    if has_deviations:
        attention_items.append('⚠ <strong>Technical Deviation:</strong> Inconsistent resolution or framerate detected')
    if sequences_with_gaps > 0:
        attention_items.append(f'⚠ <strong>Frame Gaps:</strong> {sequences_with_gaps} sequence(s) missing {total_missing_frames} frames from expected range')
    if critical_colorspace_issues:
        attention_items.append('⚠ <strong>Colorspace Conflict:</strong> Incompatible gamut profiles detected (see color audit below)')

    if attention_items:
        items_html = "<br>".join(attention_items)
        attention_box = f'<div class="attention-box"><strong>Attention Required</strong><br>{items_html}</div>'

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    project = getattr(results[0].plan, 'project_name', "") or results[0].plan.project_id if results and results[0].plan else "Unknown"

    html_parts = [
        "<!DOCTYPE html>",
        '<html data-theme="dark">',
        "<head>",
        '    <meta charset="utf-8">',
        f"    <title>Ingest Manifest - {project}</title>",
        f"    <style>{css}</style>",
        "    <script>",
        "        function toggleTheme() {",
        "            const html = document.documentElement;",
        "            const current = html.getAttribute('data-theme');",
        "            const next = current === 'dark' ? 'light' : 'dark';",
        "            html.setAttribute('data-theme', next);",
        "            document.getElementById('theme-label').textContent = next === 'dark' ? 'LIGHT MODE' : 'DARK MODE';",
        "        }",
        "    </script>",
        "</head>",
        "<body>",
        '    <div class="report">',
        '        <header>',
        '            <div>',
        f'                <div class="studio-header">{studio_name}</div>',
        "                <h1>Ingest Manifest</h1>",
        '            </div>',
        '            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 10px;">',
        '                <button class="theme-toggle" onclick="toggleTheme()">',
        '                    <span id="theme-label">LIGHT MODE</span>',
        '                </button>',
        f'                <div style="font-size: 13px; color: var(--text-muted); text-align: right; font-weight: 600;">Batch ID: {int(time.time())}<br>{timestamp}</div>',
        '            </div>',
        '        </header>',
        '        <div class="health-dashboard">',
        f'            <div class="health-badge {health_cls}">',
        f'                <div class="health-score">{health_score}</div>',
        f'                <div class="health-label">{health_label}</div>',
        '            </div>',
        '            <div class="meta-grid">',
        '                <div class="meta-item"><span class="meta-label">Project</span><span class="meta-value-project">' + project + '</span></div>',
        '                <div class="meta-item"><span class="meta-label">Operator</span><span class="meta-value">' + operator + '</span></div>',
        '                <div class="meta-item"><span class="meta-label">Step</span><span class="meta-value">' + step_id + '</span></div>',
        '                <div class="meta-item"><span class="meta-label">Total Volume</span><span class="meta-value">' + size_display + '</span></div>',
        '                <div class="meta-item"><span class="meta-label">Clips</span><span class="meta-value">' + f'{succeeded} of {len(results)} ok' + '</span></div>',
        '                <div class="meta-item"><span class="meta-label">Frames</span><span class="meta-value">' + str(total_frames) + '</span></div>',
        '            </div>',
        '        </div>',
        error_summary_html,
        attention_box,
        "        <table>",
        "            <thead>",
        "                <tr>",
        "                    <th>#</th>",
        "                    <th>Thumbnail</th>",
        "                    <th>Shot ID</th>",
        "                    <th>Version</th>",
        "                    <th>Verification</th>",
        "                    <th># Frames</th>",
        "                    <th>Frame Continuity</th>",
        "                    <th>Technical Specs</th>",
        "                    <th>Timecode</th>",
        "                    <th>MD5 Checksum</th>",
        "                </tr>",
        "            </thead>",
        "            <tbody>",
        "".join(rows),
        "            </tbody>",
        "            <tfoot>",
        "                <tr>",
        "                    <td colspan='10' style='text-align: left;'>",
        f"                        <strong>Summary:</strong> {len(results)} clips · {succeeded} succeeded · {len(results) - succeeded} failed · {total_frames} frames · {size_display}",
        "                    </td>",
        "                </tr>",
        "            </tfoot>",
        "        </table>",
        '        <div class="footer">',
        f"            With &epsilon;&gt; from {studio_name}",
        "        </div>",
        "    </div>",
        "</body>",
        "</html>"
    ]
    
    html = "\n".join(html_parts)

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return True
    except Exception:
        return False
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
        --bg: #f5f5f5;
        --card-bg: #ffffff;
        --border: #ddd;
        --text-main: #333;
        --text-muted: #666;
        --accent: #005a9e;
        --success: #27ae60;
        --warning: #f39c12;
        --error: #c53030;
        --table-header: #f9f9f9;
    }

    [data-theme="dark"] {
        --bg: #121212;
        --card-bg: #1e1e1e;
        --border: #333;
        --text-main: #e0e0e0;
        --text-muted: #888;
        --accent: #00bff3;
        --success: #27ae60;
        --warning: #f39c12;
        --error: #f44747;
        --table-header: #252526;
    }

    body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: var(--bg); color: var(--text-main); padding: 30px; margin: 0; transition: background-color 0.3s, color 0.3s; }
    .report { max-width: 1400px; margin: 0 auto; background: var(--card-bg); padding: 40px; border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    
    header { border-bottom: 2px solid var(--accent); padding-bottom: 20px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: flex-end; }
    .studio-header { font-size: 12px; font-weight: bold; color: var(--accent); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 5px; }
    h1 { margin: 0; font-size: 28px; color: var(--text-main); }
    
    /* Theme Toggle */
    .theme-toggle { background: var(--border); border: none; color: var(--text-main); padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; display: flex; align-items: center; gap: 8px; }
    .theme-toggle:hover { opacity: 0.8; }

    /* Executive Health Dashboard */
    .health-dashboard { display: flex; gap: 24px; margin-bottom: 35px; }
    .health-badge { flex: 0 0 180px; padding: 16px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .health-score { font-size: 28px; font-weight: 800; line-height: 1; margin-bottom: 8px; letter-spacing: -0.5px; }
    .health-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.9; }
    
    .health-green { background-color: var(--success); color: #fff; border-color: var(--success); }
    .health-yellow { background-color: var(--warning); color: #fff; border-color: var(--warning); }
    .health-red { background-color: var(--error); color: #fff; border-color: var(--error); }

    [data-theme="dark"] .health-green { color: #fff; }
    [data-theme="dark"] .health-yellow { color: #000; }
    [data-theme="dark"] .health-red { color: #fff; }

    .meta-grid { display: flex; flex-wrap: wrap; gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-grow: 1; }
    .meta-item { flex: 1; background: var(--card-bg); padding: 15px; min-width: 120px; }
    .meta-label { font-size: 10px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 5px; display: block; }
    .meta-value { font-size: 13px; color: var(--text-main); font-weight: 600; display: block; }

    .attention-box { background: rgba(243, 156, 18, 0.1); border: 1px solid var(--warning); color: var(--warning); padding: 12px 20px; border-radius: 4px; margin-bottom: 10px; font-size: 13px; }

    .error-summary { background: rgba(244, 71, 71, 0.05); border: 1px solid var(--error); border-radius: 4px; padding: 20px; margin-bottom: 30px; }
    .error-summary-title { font-size: 15px; font-weight: bold; color: var(--error); margin-bottom: 12px; }
    .error-list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .error-list li { padding: 8px 12px; background: rgba(0,0,0,0.02); border-radius: 3px; border-left: 3px solid var(--error); font-size: 12px; }

    table { width: 100%; border-collapse: collapse; margin-top: 20px; background: rgba(0,0,0,0.02); border-radius: 6px; overflow: hidden; }
    thead th { background: var(--table-header); color: var(--text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; padding: 15px 10px; text-align: left; border-bottom: 1px solid var(--border); }
    thead th:nth-child(2) { min-width: 180px; } /* Shot ID column */
    td { padding: 15px 10px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
    td:nth-child(2) { min-width: 180px; } /* Shot ID column */
    tr:hover td { background: rgba(0,0,0,0.02); }
    
    .thumb { width: 140px; height: 78px; background: #000; border-radius: 4px; object-fit: cover; display: block; border: 1px solid var(--border); }
    
    .status-ok { color: var(--success); font-weight: bold; }
    .status-fail { color: var(--error); font-weight: bold; }
    .status-warn { color: var(--warning); font-weight: bold; }
    
    .xray-wrap { display: flex; flex-direction: column; gap: 6px; }
    .xray-target { color: var(--text-main); font-weight: bold; font-size: 14px; line-height: 1.4; }
    .xray-source { color: var(--text-muted); font-size: 10px; font-family: 'Consolas', monospace; line-height: 1.5; }
    .xray-arrow { color: var(--accent); margin: 0 4px; font-size: 10px; }

    .deviation { background-color: rgba(243, 156, 18, 0.1); color: var(--warning); border: 1px solid var(--warning); border-radius: 3px; padding: 1px 4px; font-size: 11px; }
    .code { font-family: 'Consolas', monospace; background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 3px; font-size: 11px; color: var(--accent); }
    .tech { color: var(--text-muted); font-size: 11px; line-height: 1.5; }
    .color-audit { color: var(--accent); font-weight: 600; font-size: 9px; margin-top: 6px; text-transform: uppercase; opacity: 0.8; }
    
    .missing-frames { color: var(--error); font-weight: bold; font-size: 11px; background: rgba(244, 71, 71, 0.05); padding: 2px 6px; border-radius: 2px; }

    .footer { margin-top: 50px; font-size: 11px; color: var(--text-muted); text-align: center; border-top: 1px solid var(--border); padding-top: 20px; }
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

    # 2. Build Rows & Track Deviations
    rows = []
    has_deviations = False
    
    for res in results:
        if not res or not res.plan: continue
        
        mi = res.plan.media_info
        status_cls = "status-ok" if res.success else "status-fail"
        if res.success:
            status_text = "PASSED"
        elif "skipped" in (res.error or "").lower():
            status_text = "SKIPPED"
            status_cls = "status-warn"
        else:
            status_text = "FAILED"
        
        # Deviation Detection
        res_val = f"{mi.width}x{mi.height}" if mi.width else "—"
        res_dev = (res_val != common_res and common_res)
        res_display = f'<span class="deviation" title="Deviation">{res_val}</span>' if res_dev else res_val
        
        fps_val = mi.fps if mi.fps else 0
        fps_dev = (fps_val != common_fps and common_fps)
        fps_display = f'<span class="deviation">{fps_val:.3f}</span>' if fps_dev else f"{fps_val:.3f}"
        
        codec_val = mi.codec.upper() if mi.codec else "—"
        codec_dev = (mi.codec and mi.codec.lower() != common_codec and common_codec)
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
        if mi.color_primaries:
            tooltip = _colorspace_tooltip(mi.color_primaries)
            # Highlight if this clip has a colorspace issue
            if cs_issue and cs_issue.severity == "critical":
                color_parts.append(f'<span class="deviation" title="{cs_issue.message}">{mi.color_primaries}</span>')
            else:
                color_parts.append(f'<span title="{tooltip}">{mi.color_primaries}</span>')
        if mi.color_transfer:
            tooltip = _colorspace_tooltip(mi.color_transfer)
            color_parts.append(f'<span title="{tooltip}">{mi.color_transfer}</span>')
        if mi.color_space:
            tooltip = _colorspace_tooltip(mi.color_space)
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

        row_html = f"""
        <tr>
            <td>{img_tag}</td>
            <td class="xray-wrap">
                <div class="xray-target">{res.plan.shot_id}</div>
                <div class="xray-source"><span class="xray-arrow">←</span> {res.plan.match.clip.base_name}.{res.plan.match.clip.extension}</div>
                <div class="xray-source" style="margin-top:2px;">{res.plan.sequence_id or ""}</div>
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
            <td><span class="code" style="font-size:12px;">{res.checksum or "—"}</span></td>
        </tr>
        """
        rows.append(row_html)

    if not rows:
        rows.append("<tr><td colspan='9' style='text-align:center; padding:40px; color:var(--text-muted);'>No clips processed in this session.</td></tr>")

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

    # Build attention boxes for deviations and missing frames
    attention_box = ""
    attention_items = []
    if has_deviations:
        attention_items.append('<div class="attention-box">⚠ Technical Attention Required: Inconsistent resolution or framerate detected in this batch.</div>')
    if sequences_with_gaps > 0:
        attention_items.append(f'<div class="attention-box">⚠ Frame Gaps: {sequences_with_gaps} sequence(s) are short {total_missing_frames} frames from their detected range.</div>')
    if critical_colorspace_issues:
        attention_items.append('<div class="attention-box">⚠ Colorspace Conflict: Incompatible gamut profiles detected. Refer to color audit below.</div>')
    
    attention_box = "\n".join(attention_items)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    project = getattr(results[0].plan, 'project_name', "") or results[0].plan.project_id if results and results[0].plan else "Unknown"

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
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
        '                    <span id="theme-label">DARK MODE</span>',
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
        '                <div class="meta-item"><span class="meta-label">Project</span><span class="meta-value">' + project + '</span></div>',
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
        "                    <th>Thumbnail</th>",
        "                    <th>Shot ID</th>",
        "                    <th>Version</th>",
        "                    <th>Verification</th>",
        "                    <th># Frames</th>",
        "                    <th>Frame Continuity</th>",
        "                    <th>Technical Details & Color Audit</th>",
        "                    <th>Timecode</th>",
        "                    <th>MD5 Checksum</th>",
        "                </tr>",
        "            </thead>",
        "            <tbody>",
        "".join(rows),
        "            </tbody>",
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
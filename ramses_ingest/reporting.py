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
    body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f5f5f5; color: #333; padding: 30px; margin: 0; }
    .report { max-width: 1400px; margin: 0 auto; background: white; padding: 40px; border: 1px solid #ddd; border-radius: 4px; }
    
    header { border-bottom: 2px solid #005a9e; padding-bottom: 20px; margin-bottom: 25px; }
    .studio-header { font-size: 12px; font-weight: bold; color: #005a9e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    h1 { margin: 0; font-size: 26px; color: #222; }
    
    .meta-grid { display: flex; gap: 2px; background: #eee; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; margin-bottom: 30px; }
    .meta-item { flex: 1; background: white; padding: 15px; border-right: 1px solid #eee; min-width: 0; }
    .meta-item:last-child { border-right: none; }
    .meta-label { font-size: 10px; font-weight: bold; color: #888; text-transform: uppercase; margin-bottom: 5px; display: block; white-space: nowrap; }
    .meta-value { font-size: 13px; color: #222; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }

    .attention-box { background: #fffaf0; border: 1px solid #fbd38d; color: #9c4221; padding: 15px 20px; border-radius: 4px; margin-bottom: 30px; font-size: 14px; font-weight: 600; display: flex; align-items: center; }
    .attention-box:before { content: "⚠️"; margin-right: 12px; font-size: 18px; }

    .error-summary { background: #fff5f5; border: 1px solid #fc8181; border-radius: 4px; padding: 20px; margin-bottom: 30px; }
    .error-summary-title { font-size: 16px; font-weight: bold; color: #c53030; margin-bottom: 15px; display: flex; align-items: center; }
    .error-summary-title:before { content: "🔴"; margin-right: 10px; font-size: 20px; }
    .error-list { list-style: none; padding: 0; margin: 0; }
    .error-list li { padding: 8px 12px; background: white; margin-bottom: 6px; border-radius: 3px; border-left: 3px solid #fc8181; font-size: 13px; }
    .error-count { font-weight: bold; color: #c53030; }

    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    thead th { position: sticky; top: 0; background: #f9f9f9; z-index: 10; box-shadow: inset 0 -1px 0 #eee; }
    th { text-align: left; padding: 12px 10px; border-bottom: 2px solid #eee; color: #666; font-size: 12px; text-transform: uppercase; }
    td { padding: 12px 10px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: middle; }
    
    .thumb { width: 120px; height: 68px; background: #eee; border-radius: 2px; object-fit: cover; display: block; border: 1px solid #ccc; }
    
    .status-ok { color: #27ae60; font-weight: bold; }
    .status-fail { color: #c0392b; font-weight: bold; }
    .status-warn { color: #f39c12; font-weight: bold; }
    
    .deviation { background-color: #fffaf0 !important; color: #9c4221 !important; border: 1px solid #fbd38d; border-radius: 3px; padding: 2px 4px; font-weight: bold; display: inline-block; }
    .code { font-family: 'Consolas', 'Courier New', monospace; background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-size: 12px; color: #444; }
    .tech { color: #777; font-size: 11px; line-height: 1.4; }
    .color-audit { color: #005a9e; font-weight: 600; font-size: 10px; margin-top: 4px; text-transform: uppercase; }
    .missing-frames { color: #c0392b; font-weight: bold; font-size: 11px; }
    .frame-gap-warn { background-color: #ffebee; border-left: 3px solid #c0392b; padding: 2px 6px; border-radius: 2px; }

    .footer { margin-top: 50px; font-size: 11px; color: #bbb; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
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
        fps_display = f'<span class="deviation">{fps_val}</span>' if fps_dev else str(fps_val)
        
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
            <td><strong>{res.plan.shot_id}</strong><br><small style="color:#888">{res.plan.sequence_id or ""}</small></td>
            <td><span class="code">v{res.plan.version:03d}</span></td>
            <td class="{status_cls}">{status_text}</td>
            <td>{res.frames_copied}</td>
            <td>{missing_display}</td>
            <td class="tech">
                <b>{res_display}</b> @ {fps_display} fps<br>{codec_display} / {mi.pix_fmt}<br>
                <div class="color-audit">{color_str}</div>
            </td>
            <td><span class="code">{mi.start_timecode or "—"}</span></td>
            <td><span class="code" style="font-size:10px;">{res.checksum or "—"}</span></td>
        </tr>
        """
        rows.append(row_html)

    if not rows:
        rows.append("<tr><td colspan='9' style='text-align:center; padding:40px; color:#999;'>No clips processed in this session.</td></tr>")

    # Analytics Header Formatting
    if total_size_bytes >= (1024**3):
        size_display = f"{total_size_bytes / (1024**3):.2f} GB"
    else:
        size_display = f"{total_size_bytes / (1024**2):.1f} MB"

    # Build error summary section
    error_summary_html = ""
    if failed > 0:
        error_items = []
        for category, count in error_categories.most_common():
            error_items.append(f'<li><span class="error-count">{count}</span> clip(s): {category}</li>')

        error_summary_html = f"""
        <div class="error-summary">
            <div class="error-summary-title">Ingest Failures: {failed} of {len(results)} clips failed</div>
            <ul class="error-list">
                {"".join(error_items)}
            </ul>
        </div>
        """

    # Build attention boxes for deviations and missing frames
    attention_boxes = []
    if has_deviations:
        attention_boxes.append('<div class="attention-box">Technical Attention Required: Inconsistent technical specs detected in this batch. Review highlighted values below.</div>')
    if sequences_with_gaps > 0:
        attention_boxes.append(f'<div class="attention-box">Frame Gaps Detected: {sequences_with_gaps} sequence(s) have missing frames ({total_missing_frames} total). Incomplete deliveries flagged below.</div>')

    # Colorspace consistency warning (Enhancement #3)
    critical_colorspace_issues = [idx for idx, issue in colorspace_issues.items() if issue.severity == "critical"]
    if critical_colorspace_issues:
        issue_count = len(critical_colorspace_issues)
        attention_boxes.append(
            f'<div class="attention-box">Colorspace Warning: {issue_count} clip(s) have colorspace '
            f'inconsistencies that may cause rendering issues. Review clips marked with ⚠ below.</div>'
        )

    attention_box = "\n".join(attention_boxes)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    project = getattr(results[0].plan, 'project_name', "") or results[0].plan.project_id if results and results[0].plan else "Unknown"

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '    <meta charset="utf-8">',
        f"    <title>Ingest Manifest - {project}</title>",
        f"    <style>{css}</style>",
        "</head>",
        "<body>",
        '    <div class="report">',
        '        <header>',
        f'            <div class="studio-header">{studio_name}</div>',
        "            <h1>Ingest Manifest</h1>",
        '        </header>',
        '        <div class="meta-grid">',
        '            <div class="meta-item"><span class="meta-label">Project</span><span class="meta-value">' + project + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Operator</span><span class="meta-value">' + operator + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Step</span><span class="meta-value">' + step_id + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Timestamp</span><span class="meta-value">' + timestamp + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Clips</span><span class="meta-value">' + f'{succeeded} succeeded / {len(results)} total' + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Ingested Size</span><span class="meta-value">' + size_display + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Verified Frames</span><span class="meta-value">' + str(total_frames) + '</span></div>',
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
# -*- coding: utf-8 -*-
"""Ingest report generation (HTML/JSON)."""

from __future__ import annotations

import os
import time
import base64
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


def generate_html_report(results: list[IngestResult], output_path: str, studio_name: str = "Ramses Studio", operator: str = "Unknown") -> bool:
    """Generate a clean, professional HTML manifest with color audit and sticky headers."""
    
    css = """
    body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f5f5f5; color: #333; padding: 30px; margin: 0; }
    .report { max-width: 1400px; margin: 0 auto; background: white; padding: 40px; border: 1px solid #ddd; border-radius: 4px; position: relative; }
    
    header { border-bottom: 2px solid #005a9e; padding-bottom: 20px; margin-bottom: 25px; }
    .studio-header { font-size: 12px; font-weight: bold; color: #005a9e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    h1 { margin: 0; font-size: 26px; color: #222; }
    
    .meta-grid { display: flex; gap: 2px; background: #eee; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; margin-bottom: 20px; }
    .meta-item { flex: 1; background: white; padding: 15px; border-right: 1px solid #eee; min-width: 0; }
    .meta-item:last-child { border-right: none; }
    .meta-label { font-size: 10px; font-weight: bold; color: #888; text-transform: uppercase; margin-bottom: 5px; display: block; }
    .meta-value { font-size: 13px; color: #222; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }

    .warning-banner { background: #fff5f5; border: 1px solid #feb2b2; color: #c53030; padding: 10px 15px; border-radius: 4px; margin-bottom: 20px; font-size: 13px; font-weight: 600; display: flex; align-items: center; }
    .warning-banner:before { content: "⚠️"; margin-right: 10px; font-size: 16px; }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    thead th { position: sticky; top: 0; background: #f9f9f9; z-index: 10; box-shadow: inset 0 -1px 0 #eee; }
    th { text-align: left; padding: 12px 10px; border-bottom: 2px solid #eee; color: #666; font-size: 12px; text-transform: uppercase; }
    td { padding: 12px 10px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: middle; }
    
    .thumb { width: 120px; height: 68px; background: #eee; border-radius: 2px; object-fit: cover; display: block; border: 1px solid #ccc; }
    
    .status-ok { color: #27ae60; font-weight: bold; }
    .status-fail { color: #c0392b; font-weight: bold; }
    .status-warn { color: #f39c12; font-weight: bold; }
    
    .code { font-family: 'Consolas', 'Courier New', monospace; background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-size: 11px; color: #444; }
    .tech { color: #666; font-size: 11px; line-height: 1.4; }
    .color-audit { color: #005a9e; font-weight: 600; font-size: 10px; margin-top: 4px; text-transform: uppercase; }

    .footer { margin-top: 50px; font-size: 11px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
    """

    # Calculate Totals and Codec Consistency
    total_frames = 0
    total_size_bytes = 0
    succeeded = 0
    found_codecs = set()
    
    rows = []
    step_id = "—"
    for res in results:
        if not res or not res.plan:
            continue
        
        step_id = res.plan.step_id
        if res.success:
            succeeded += 1
            total_frames += res.frames_copied
            found_codecs.add(res.plan.media_info.codec.lower())
            
            try:
                if res.plan.match.clip.first_file:
                    fsize = os.path.getsize(res.plan.match.clip.first_file)
                    total_size_bytes += (fsize * res.frames_copied)
            except Exception:
                pass

        status_cls = "status-ok" if res.success else "status-fail"
        if res.success:
            status_text = "PASSED"
        elif "skipped" in (res.error or "").lower():
            status_text = "SKIPPED"
            status_cls = "status-warn"
        else:
            status_text = "FAILED"
        
        # Tech Specs & Color Audit
        mi = res.plan.media_info
        res_str = f"{mi.width}x{mi.height}" if mi.width else "—"
        codec_str = mi.codec.upper() if mi.codec else "—"
        tc_str = mi.start_timecode or "—"
        version_str = f"v{res.plan.version:03d}"
        
        # Format Color VUI tags (Primaries / Transfer / Matrix)
        color_parts = []
        if mi.color_primaries: color_parts.append(mi.color_primaries)
        if mi.color_transfer: color_parts.append(mi.color_transfer)
        if mi.color_space: color_parts.append(mi.color_space)
        color_str = " / ".join(color_parts) if color_parts else "No VUI Tags"
        
        # Visuals
        b64_img = _get_base64_image(res.preview_path)
        img_tag = f'<img src="{b64_img}" class="thumb">' if b64_img else '<div class="thumb"></div>'
        
        row_html = f"""
        <tr>
            <td>{img_tag}</td>
            <td><strong>{res.plan.shot_id}</strong><br><small style="color:#888">{res.plan.sequence_id or ""}</small></td>
            <td><span class="code">{version_str}</span></td>
            <td class="{status_cls}">{status_text}</td>
            <td>{res.frames_copied}</td>
            <td class="tech">
                <b>{res_str}</b> @ {mi.fps} fps<br>{codec_str} / {mi.pix_fmt}<br>
                <div class="color-audit">{color_str}</div>
            </td>
            <td><span class="code">{tc_str}</span></td>
            <td><span class="code" style="font-size:10px;">{res.checksum or "—"}</span></td>
        </tr>
        """
        rows.append(row_html)

    # Analytics Header
    total_gb = total_size_bytes / (1024**3)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    project = getattr(results[0].plan, 'project_name', "") or results[0].plan.project_id if results and results[0].plan else "Unknown"

    # Mixed Codec Warning
    warning_banner = ""
    if len(found_codecs) > 1:
        warning_banner = f'<div class="warning-banner">Mixed Codecs Detected in Delivery: {", ".join(c.upper() for c in found_codecs)}</div>'

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
        '            <div class="meta-item"><span class="meta-label">Total Size</span><span class="meta-value">' + f"{total_gb:.2f} GB" + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Total Frames</span><span class="meta-value">' + str(total_frames) + '</span></div>',
        '        </div>',
        warning_banner,
        "        <table>",
        "            <thead>",
        "                <tr>",
        "                    <th>Thumbnail</th>",
        "                    <th>Shot ID</th>",
        "                    <th>Version</th>",
        "                    <th>Verification</th>",
        "                    <th># Frames</th>",
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
        f"            &copy; {time.strftime('%Y')} {studio_name} &bull; Ramses-Ingest Production Manifest",
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

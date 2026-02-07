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
    """Generate a clean, professional HTML manifest with MD5 integrity and technical specs."""
    
    css = """
    body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f5f5f5; color: #333; padding: 30px; margin: 0; }
    .report { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border: 1px solid #ddd; border-radius: 4px; }
    
    header { border-bottom: 2px solid #005a9e; padding-bottom: 20px; margin-bottom: 25px; }
    .studio-badge { display: inline-block; font-size: 11px; font-weight: bold; color: white; background: #005a9e; padding: 3px 10px; border-radius: 10px; margin-bottom: 10px; text-transform: uppercase; }
    h1 { margin: 0; font-size: 26px; color: #222; }
    
    .meta-grid { display: flex; gap: 2px; background: #eee; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; margin-bottom: 30px; }
    .meta-item { flex: 1; background: white; padding: 15px; border-right: 1px solid #eee; }
    .meta-item:last-child { border-right: none; }
    .meta-label { font-size: 11px; font-weight: bold; color: #888; text-transform: uppercase; margin-bottom: 5px; display: block; }
    .meta-value { font-size: 14px; color: #222; font-weight: 600; }

    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { text-align: left; background: #f9f9f9; padding: 12px 10px; border-bottom: 2px solid #eee; color: #666; font-size: 12px; text-transform: uppercase; }
    td { padding: 12px 10px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: middle; }
    
    .thumb { width: 120px; height: 68px; background: #eee; border-radius: 2px; object-fit: cover; display: block; border: 1px solid #ccc; }
    
    .status-ok { color: #27ae60; font-weight: bold; }
    .status-fail { color: #c0392b; font-weight: bold; }
    .status-warn { color: #f39c12; font-weight: bold; }
    
    .code { font-family: 'Consolas', 'Courier New', monospace; background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-size: 11px; color: #444; }
    .tech { color: #777; font-size: 12px; line-height: 1.4; }

    .footer { margin-top: 50px; font-size: 11px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
    """

    rows = []
    step_id = "—"
    for res in results:
        if not res or not res.plan:
            continue
        
        step_id = res.plan.step_id

        status_cls = "status-ok" if res.success else "status-fail"
        if res.success:
            status_text = "PASSED"
        elif "skipped" in (res.error or "").lower():
            status_text = "SKIPPED"
            status_cls = "status-warn"
        else:
            status_text = "FAILED"
        
        # Tech Specs
        mi = res.plan.media_info
        res_str = f"{mi.width}x{mi.height}" if mi.width else "—"
        codec_str = mi.codec.upper() if mi.codec else "—"
        tc_str = mi.start_timecode or "—"
        version_str = f"v{res.plan.version:03d}"
        md5_str = res.checksum or "—"
        
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
            <td class="tech"><b>{res_str}</b><br>{mi.fps} fps<br>{codec_str}</td>
            <td><span class="code">{tc_str}</span></td>
            <td><span class="code" style="font-size:10px;">{md5_str}</span></td>
        </tr>
        """
        rows.append(row_html)

    if not rows:
        rows.append("<tr><td colspan='8' style='text-align:center; padding:40px; color:#999;'>No clips processed in this session.</td></tr>")

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
        f'            <div class="studio-badge">{studio_name}</div>',
        "            <h1>Ingest Manifest</h1>",
        '        </header>',
        '        <div class="meta-grid">',
        '            <div class="meta-item"><span class="meta-label">Project</span><span class="meta-value">' + project + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Operator</span><span class="meta-value">' + operator + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Step</span><span class="meta-value">' + step_id + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Timestamp</span><span class="meta-value">' + timestamp + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Volume</span><span class="meta-value">' + str(len(results)) + ' Clips</span></div>',
        '        </div>',
        "        <table>",
        "            <thead>",
        "                <tr>",
        "                    <th>Thumbnail</th>",
        "                    <th>Shot ID</th>",
        "                    <th>Version</th>",
        "                    <th>Verification</th>",
        "                    <th># Frames</th>",
        "                    <th>Technical</th>",
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

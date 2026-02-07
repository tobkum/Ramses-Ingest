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


def generate_html_report(results: list[IngestResult], output_path: str, studio_name: str = "Ramses Studio", operator: str = "Unknown") -> bool:
    """Generate a clean, professional HTML manifest with accurate analytics and technical flagging."""
    
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

    .footer { margin-top: 50px; font-size: 11px; color: #bbb; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
    """

    # 1. Analyze Batch for Deviations and Totals
    resolutions = []
    framerates = []
    codecs = []
    total_frames = 0
    total_size_bytes = 0
    succeeded = 0
    step_id = "—"
    
    for res in results:
        if not res or not res.plan: continue
        step_id = res.plan.step_id
        clip = res.plan.match.clip
        
        if res.success:
            succeeded += 1
            total_frames += res.frames_copied
            mi = res.plan.media_info
            if mi.width: resolutions.append(f"{mi.width}x{mi.height}")
            if mi.fps: framerates.append(mi.fps)
            if mi.codec: codecs.append(mi.codec.lower())
            
            # Correct Size Calculation
            try:
                if clip.first_file:
                    fsize = os.path.getsize(clip.first_file)
                    if clip.is_sequence:
                        total_size_bytes += (fsize * res.frames_copied)
                    else:
                        # Single container (movie)
                        total_size_bytes += fsize
            except Exception: pass

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

        # Format Color VUI
        color_parts = []
        if mi.color_primaries: color_parts.append(mi.color_primaries)
        if mi.color_transfer: color_parts.append(mi.color_transfer)
        if mi.color_space: color_parts.append(mi.color_space)
        color_str = " / ".join(color_parts) if color_parts else "No VUI Tags"
        
        b64_img = _get_base64_image(res.preview_path)
        img_tag = f'<img src="{b64_img}" class="thumb">' if b64_img else '<div class="thumb"></div>'
        
        row_html = f"""
        <tr>
            <td>{img_tag}</td>
            <td><strong>{res.plan.shot_id}</strong><br><small style="color:#888">{res.plan.sequence_id or ""}</small></td>
            <td><span class="code">v{res.plan.version:03d}</span></td>
            <td class="{status_cls}">{status_text}</td>
            <td>{res.frames_copied}</td>
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
        rows.append("<tr><td colspan='8' style='text-align:center; padding:40px; color:#999;'>No clips processed in this session.</td></tr>")

    # Analytics Header Formatting
    if total_size_bytes >= (1024**3):
        size_display = f"{total_size_bytes / (1024**3):.2f} GB"
    else:
        size_display = f"{total_size_bytes / (1024**2):.1f} MB"

    attention_box = ""
    if has_deviations:
        attention_box = '<div class="attention-box">Technical Attention Required: Inconsistent technical specs detected in this batch. Review highlighted values below.</div>'

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
        '            <div class="meta-item"><span class="meta-label">Clips</span><span class="meta-value">' + str(len(results)) + ' total</span></div>',
        '            <div class="meta-item"><span class="meta-label">Total Size</span><span class="meta-value">' + size_display + '</span></div>',
        '            <div class="meta-item"><span class="meta-label">Total Frames</span><span class="meta-value">' + str(total_frames) + '</span></div>',
        '        </div>',
        attention_box,
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
        f"            &copy; {time.strftime('%Y')} {studio_name}",
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

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
    """Generate a professional HTML manifest with embedded visuals and tech specs."""
    
    css = """
    body { font-family: 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; padding: 20px; }
    .report { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
    h1 { color: #1a365d; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-top: 0; font-size: 24px; }
    .studio-header { font-size: 11px; font-weight: 800; color: #3182ce; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    table { width: 100%; border-collapse: collapse; margin-top: 25px; }
    th { text-align: left; background: #edf2f7; padding: 12px 10px; border-bottom: 2px solid #cbd5e0; color: #4a5568; font-size: 12px; text-transform: uppercase; }
    td { padding: 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; vertical-align: middle; }
    .thumb { width: 120px; height: 68px; background: #eee; border-radius: 4px; object-fit: cover; display: block; border: 1px solid #ddd; }
    .status-ok { color: #2f855a; font-weight: bold; }
    .status-fail { color: #c53030; font-weight: bold; }
    .status-warn { color: #c05621; font-weight: bold; }
    .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; padding: 15px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0; }
    .meta-item { font-size: 12px; color: #64748b; }
    .meta-item strong { color: #1e293b; display: block; font-size: 14px; }
    .code { font-family: 'Consolas', monospace; background: #f1f5f9; padding: 2px 4px; border-radius: 3px; font-size: 12px; color: #475569; }
    .footer { margin-top: 40px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 20px; }
    """

    rows = []
    for res in results:
        if not res or not res.plan:
            continue

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
        fps_str = f"{mi.fps}" if mi.fps else "—"
        codec_str = mi.codec.upper() if mi.codec else "—"
        tc_str = mi.start_timecode or "—"
        
        # Visuals
        b64_img = _get_base64_image(res.preview_path)
        img_tag = f'<img src="{b64_img}" class="thumb">' if b64_img else '<div class="thumb"></div>'
        
        row_html = f"""
        <tr>
            <td>{img_tag}</td>
            <td><strong>{res.plan.shot_id}</strong><br><small style="color:#94a3b8">{res.plan.sequence_id or ""}</small></td>
            <td>{res.plan.step_id}</td>
            <td class="{status_cls}">{status_text}</td>
            <td>{res.frames_copied}</td>
            <td><small>{res_str}<br>{fps_str} fps<br>{codec_str}</small></td>
            <td class="code">{tc_str}</td>
            <td><span class="code">{res.published_path or res.error or "N/A"}</span></td>
        </tr>
        """
        rows.append(row_html)

    if not rows:
        rows.append("<tr><td colspan='8' style='text-align:center; padding:40px; color:#94a3b8;'>No clips processed in this session.</td></tr>")

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
        f'        <div class="studio-header">{studio_name}</div>',
        "        <h1>Ingest Manifest</h1>",
        '        <div class="meta-grid">',
        f'            <div class="meta-item"><strong>Project</strong>{project}</div>',
        f'            <div class="meta-item"><strong>Operator</strong>{operator}</div>',
        f'            <div class="meta-item"><strong>Date</strong>{timestamp}</div>',
        f'            <div class="meta-item"><strong>Volume</strong>{len(results)} Clips</div>',
        '        </div>',
        "        <table>",
        "            <thead>",
        "                <tr>",
        "                    <th>Visual</th>",
        "                    <th>Shot ID</th>",
        "                    <th>Step</th>",
        "                    <th>Status</th>",
        "                    <th>Frames</th>",
        "                    <th>Technical</th>",
        "                    <th>Timecode</th>",
        "                    <th>Destination</th>",
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
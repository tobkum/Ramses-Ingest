# Ramses-Ingest

Ramses-Ingest is a professional VFX pipeline tool for automating the ingestion of media files into a [Ramses](https://ramses.rxlab.guide/) production management system.

It bridges the gap between raw delivery folders and a structured production environment by automatically identifying shots, creating them in the Ramses database, and organizing files into the correct project hierarchy with bit-perfect integrity.

## Features

### Core Functionality

- **Professional Master-Detail UI**: Industry-standard 3-panel layout (ShotGrid-style) featuring a filter sidebar, editable clip table, and a comprehensive selection detail panel.
- **Robust Automated Scanning**: Powered by `pyseq` for reliable image sequence detection. Supports both `.` and `_` frame separators and recursive directory walking.
- **Transactional Ingest**: All-or-nothing execution. If a transfer or metadata write fails, the tool automatically rolls back and cleans up partial files to prevent "zombie" versions.
- **High-Performance Pipeline**: Multi-threaded parallel processing for file transfers, MD5 hashing, and preview generation, optimized for I/O-bound workloads.

### Data Integrity & QA

- **Bit-Perfect Verification**: 
  - Full MD5 verification for **every frame** in sequences.
  - "Fast Verify" mode (First/Mid/Last frames + size check) for rapid ingestion of massive deliveries.
  - Streaming progress reporting for long-running checksum operations.
- **Technical Validation**: Visual warnings for resolution and FPS mismatches against Ramses project standards.
- **Duplicate Detection**: Two-level verification (frame count + MD5) prevents re-ingesting identical versions.
- **Missing Frame Detection**: Automatically identifies and highlights gaps in sequence frame ranges.

### Production Workflows

- **Editorial Ready**:
  - Automatically extracts start timecodes from media metadata.
  - Supports **CMX 3600 EDL** mapping for name-to-shot resolution with robust error reporting.
- **Production Reporting**: Generates professional **HTML Ingest Manifests** with success/failure metrics and technical spec summaries.
- **Dry-Run Mode**: Full simulation mode to preview exactly where files will land without performing any disk operations.
- **Color Management**: Integrated **OpenColorIO (OCIO)** support for color-accurate thumbnails and MP4 proxies.

### Advanced Tools

- **Ramses Naming Architect**: A visual, drag-and-drop rule-building engine for creating custom naming patterns with a "Magic Wand" auto-detection feature.
- **Integrated Logging**: A dedicated GUI log panel with color-coded status tracking and real-time feedback from core scanner and prober modules.
- **Background Operations**: Non-blocking database connections and metadata probing to keep the UI responsive during heavy processing.

## Prerequisites

- **Python 3.10+**
- **FFmpeg/ffprobe**: Must be available on your system `PATH`.
- **Ramses Client**: The Ramses desktop application must be running with the Daemon active.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/ramses-ingest.git
   cd ramses-ingest
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Launching the GUI

```bash
python -m ramses_ingest
```

1. **Connect**: The tool automatically connects to your active Ramses project.
2. **Scan**: Drag and drop folders or files onto the center drop zone.
3. **Review**: Use the sidebar to filter by status (Ready/Warning/Error) or type (Sequence/Movie).
4. **Edit**: Double-click Shot IDs in the table or use the Detail Panel to override identifiers.
5. **Execute**: Click "Ingest" to begin the automated transfer and database registration.


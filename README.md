# Ramses-Ingest

Ramses-Ingest is a pipeline tool for automating the ingestion of media files into a [Ramses](https://ramses.rxlab.guide/) production management system.

It bridges the gap between raw delivery folders and a structured production environment by automatically identifying shots, creating them in the Ramses database, and organizing files into the correct project hierarchy.

## Features

### Core Functionality

- **Automated Scanning**: Detects image sequences (2+ digit padding) and movie files in source directories (supports multi-selection drop).
- **High-Performance Ingest**: Optimized two-phase pipeline using multi-threaded parallel processing for file transfers and preview generation.
- **Data Integrity**:
  - MD5 verification for **every frame** in sequences (not just first frame)
  - Streaming MD5 computation with granular progress reporting
  - Frame padding preservation from original filenames
- **Editorial Ready**:
  - Automatically extracts start timecodes from media metadata
  - Supports **CMX 3600 EDL** mapping for name-to-shot resolution
  - **EDL Frame Range Validation**: Validates delivered frame ranges against EDL expectations
- **Regex-based Matching**: Uses configurable naming rules to extract sequence and shot IDs.
- **Structure Enforcement**: Organizes files into the standard Ramses folder structure:
  `{Project}/{Shot}/{Step}/_published/v{Version}/`

### Quality Assurance

- **Colorspace Validation**: Batch-level consistency checking with visual warnings for mismatched colorspace metadata
- **Duplicate Detection**: Two-level verification (frame count + MD5) prevents re-ingesting identical versions
- **Missing Frame Detection**: Automatically identifies gaps in sequence frame ranges
- **Zombie Version Prevention**: Intelligent detection of incomplete/failed ingests

### Production Workflows

- **Production Reporting**: Automatically generates professional **HTML Ingest Manifests** in the project's `_ingest_reports/` folder with:
  - Error categorization for executives (naming, data integrity, technical specs)
  - Colorspace tooltips for non-technical clients
  - Success vs failure byte metrics
  - Visual attention boxes for critical issues
- **Dry-Run Mode**: Preview operations without copying files (Enhancement #8)
- **Studio Customization**: Persistent studio branding for manifests
- **Lazy Thumbnail Generation**: On-demand JPEG thumbnail creation
- **Preview Generation**: Automatically generates JPEG thumbnails and MP4 proxies

### Advanced Tools

- **Ramses Naming Architect**: Visual rule-building engine for creating custom naming patterns
  - Drag-and-drop token assembly
  - Live simulation lab with X-Ray filename highlighting
  - Vendor presets (Technicolor, Standard Shot, etc.)
  - Magic Wand auto-detection from sample filenames
- **Color Management**: Integrated **OpenColorIO (OCIO)** support for professional color-accurate previews
- **Version/Step Extraction**: Automatically extract version numbers and pipeline steps from filenames

## Prerequisites

- **Python 3.10+**
- **FFmpeg/ffprobe**: Must be available on your system `PATH`.
- **Ramses Client**: The Ramses desktop application must be running and the Daemon active for database integration.

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

The GUI allows you to:

1. Select a source directory.
2. Review matched shots and identify unmatched clips.
3. Configure the target project and step (e.g., `PLATE`, `ANIM`).
4. Execute the ingest process.

### Configuration

Naming rules are defined in `config/default_rules.yaml`. You can customize these regex patterns to match your project's naming conventions.

Example rule:

```yaml
- pattern: "(?P<sequence>SEQ\d+)[_-](?P<shot>SH\d+)"
  sequence_prefix: ""
  shot_prefix: ""
```

## Running Tests

Execute the test suite using the provided batch file (Windows):

```bash
run_tests.bat
```

Or manually:

```bash
set PYTHONPATH=.;./lib;%PYTHONPATH%
python -m unittest discover tests
```

## Project Structure

- `ramses_ingest/`: Core application logic.
- `lib/ramses/`: Vendored Ramses API library.
- `config/`: Configuration files and naming rules.
- `tests/`: Unit and integration tests.
- `preview.py`: FFmpeg-based preview generation.
- `publisher.py`: Database object creation and file organization.

## License

This project is licensed under the GPL v3 License - see the `lib/ramses/LICENSE` for details.

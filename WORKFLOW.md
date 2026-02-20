# Workflow Guide: Ingesting New Footage

This guide walks you through the process of using Ramses-Ingest when you receive a new delivery of footage from a client.

## 1. New Project Checklist (Ramses Client)

Before running the Ingest tool, perform these steps in the **Ramses Client** application:

1.  **Create the Project**: Set up your project name and folder path.
2.  **Define the Pipeline**: Go to *Project Settings > Pipeline*.
3.  **Create the PLATE Step**:
    *   Add a step named `PLATE` (or your preferred ingest step).
    *   Set its **Type** to `Shot Production`.
    *   *Why?* The Ingest tool queries these steps. If the step exists, Ramses defines exactly where the files live.
4.  **Ensure Project is Active**: The tool connects to whichever project is currently open in the Ramses Client.

## 2. Scanning the Delivery

1.  **Launch the Tool**: `python -m ramses_ingest`
2.  **Connection**: The tool will attempt to connect automatically. If the connection is lost, use the **"↻ Refresh"** button in the header.
3.  **Select Source**: 
    *   Drag and drop folders or files onto the center **"Drop Zone"**.
    *   The tool uses **PyAV (FFmpeg C-bindings)** for near-instant metadata extraction (10-20x faster than traditional scanning).
    *   It groups image sequences using a custom scanner that supports both `.` and `_` separators.
4.  **Editorial Mapping (Optional)**:
    *   If the delivery includes a **CMX 3600 EDL**, click **"Load EDL..."** in the Options dialog.
    *   The tool will automatically map clip names to shot IDs based on EDL comments.

## 3. Review & Verification

The professional 3-panel UI is designed for rapid verification:

1.  **Filter (Left Panel)**: 
    *   Click status dots (● All, ● Ready, ● Warnings, ● Errors) to isolate problematic clips.
    *   Toggle between "Sequences" and "Movies" to focus your review.
    *   Use the search box (`Ctrl+F`) to find specific shot IDs.
2.  **Verify (Center Table)**:
    *   **Status Dot**: Green means ready. Yellow/Red indicates technical mismatches (Res/FPS) or missing frames.
    *   **Color Science**: Review the Colorspace column. Professional standards (BT709, sRGB, etc.) are automatically mapped from raw file metadata.
    *   **Metadata**: Review the Resolution and FPS columns. Items mismatched with the Ramses Project Standards will be highlighted in yellow.
3.  **Edit (Right Panel)**:
    *   Select a clip to view its full metadata and destination path in the **Detail Panel**. The tool is hardened to display technical specs even in offline mode.
    *   **Override**: Use the Shot ID input in the right panel to manually correct a naming mismatch.

## 4. Configuration & Execution

1.  **Ingest Options**: Click the **⚙ (Options)** button in the sidebar.
    *   Enable **Generate Thumbnails** and **Generate Proxies** as needed.
    *   **Fast Verify**: Enabled by default. Uses strategic sampling (3-point validation for movies, first/mid/last for sequences) to ensure high performance. Toggle off if bit-perfect MD5 is required for every single frame.
2.  **Dry-Run**: Check the "Dry Run" box in the action bar to simulate the process and verify paths without moving files.
3.  **Process Ingest**: Click **Execute**. The tool follows a transactional workflow:
    *   **Phase 1**: Database registration (Sequences/Shots).
    *   **Phase 2**: Parallel multi-threaded transfer and verification.
    *   **Rollback**: If a critical error occurs, the tool automatically deletes the failed version folder to keep your project tree clean.

## 5. Post-Ingest Verification

Once the process finishes:
1.  **Ingest Manifest**: 
    *   A professional **HTML Ingest Manifest** is generated in `{ProjectRoot}/_ingest_reports/`.
    *   Click **"View Report"** in the action bar to open it immediately.
2.  **Check Ramses Client**: Refresh the client to see the newly created and linked shots.
3.  **Check Files**: Files are organized under your project root following the standard hierarchy:
    `SHOTS/{Shot}/{Step}/_published/v001/`

---

## Summary of Tasks

| Task | Where | Handling |
| :--- | :--- | :--- |
| Create Project/Steps | Ramses Client | **Manual** (Prerequisite) |
| Scan & Match Clips | Ingest Tool | **Automatic** |
| Technical QA (Res/FPS) | Ingest Tool | **Automatic (Visual Warning)** |
| DB Registration | Ingest Tool | **Automatic** |
| Copy & Verify Files | Ingest Tool | **Automatic** |
| Rollback on Failure | Ingest Tool | **Automatic** |
| Generate Report | Ingest Tool | **Automatic** |

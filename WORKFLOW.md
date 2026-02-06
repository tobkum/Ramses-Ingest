# Workflow Guide: Ingesting New Footage

This guide walks you through the process of using Ramses-Ingest when you receive a new delivery of footage from a client, specifically for a **completely new project**.

## 1. New Project Checklist (Ramses Client)

Before running the Ingest tool, perform these steps in the **Ramses Client** application:

1.  **Create the Project**: Set up your project name and folder path.
2.  **Define the Pipeline**: Go to *Project Settings > Pipeline*.
3.  **Create the PLATE Step**:
    *   Add a step named `PLATE`.
    *   Set its **Type** to `Shot Production`.
    *   *Why?* The Ingest tool queries the database for these steps. If the step exists, Ramses defines exactly where the files should live. If it doesn't exist, the tool will fall back to a default folder name, but the files won't be linked to a database task.
4.  **Ensure Project is Active**: The Ingest tool connects to whichever project is currently open/active in the Ramses Client.
    *   **CRITICAL**: Ingestion is disabled if the tool is not connected to the Ramses Daemon. Check the status indicator in the top right.

## 2. Scanning the Delivery

1.  **Launch the Tool**: `python -m ramses_ingest`
2.  **Select Source**: 
    *   Click **"Select Source Directory"** to choose a single folder.
    *   **Multi-Selection Drop**: Drag and drop multiple folders or a specific selection of files onto the "Drop Zone".
3.  **Review Matches**:
    *   **Destination Column**: Shows exactly where the files will land (e.g., `SH010/PLATE/_published/v001`). This conforms to the Ramses folder standard.
    *   **New Items**: Shots/Sequences will be highlighted as `[NEW]`.
    *   **Manual Overrides**: If a shot wasn't matched, you can click the shot ID in the list to type in the correct identifier.

## 3. Configuration & Execution

1.  **Select Target Step**: Ensure `PLATE` is selected in the Step dropdown.
2.  **Color Management (OCIO)**:
    *   The tool supports **OpenColorIO** for professional color transforms.
    *   Set your `$OCIO` environment variable to point to your `config.ocio` file.
    *   **Common Input Colorspaces (`ocio_in`)**:
        *   `ACES - ACEScg`: The standard for CG renders (linear, wide gamut).
        *   `Input - ARRI - V3 LogC (EI800) - Wide Gamut`: Standard for ARRI Alexa footage.
        *   `Input - Sony - S-Log3 - SGamut3.Cine`: Common for Sony Venice/Alpha cameras.
        *   `Input - RED - Log3G10 - REDWideGamutRGB`: For RED camera deliveries.
        *   `Input - Panasonic - V-Log - V-Gamut`: For Panasonic workflows.
        *   `Utility - Linear - Rec.709`: Generic linear data.
    *   **Common Output Colorspaces (`ocio_out`)**:
        *   `Output - sRGB`: Standard for computer monitors and web viewing.
        *   `Output - Rec.709`: Standard for HDTV and broadcast reference.
        *   `ACES - ACESproxy`: For low-bandwidth ACES workflows.
    *   *Note: Names must exactly match the "colorspaces" or "roles" defined in your specific `config.ocio` file.*
3.  **Preview Options**:
    *   **Generate Thumbnails**: Creates a `.jpg` in the `_preview` folder (recommended).
    *   **Generate Proxies**: Creates an `.mp4` for playback (useful for long sequences).
4.  **Process Ingest**: Click the button. The tool uses a **High-Performance Parallel Pipeline**:
    *   **Phase 1**: Sequentially registers objects in the database.
    *   **Phase 2**: Parallel processing across CPU cores for file copying and preview generation.
    *   **Data Verification**: Every file is verified for size integrity after copying.

## 4. Post-Ingest Verification

Once the process finishes:
1.  **Check Ramses Client**: Refresh the tree. You should see the new Sequences and Shots.
2.  **Check Files**: Navigate to your project root. You will find the files organized under:
    `04-SHOTS/{Shot}/PLATE/_published/v001/`
3.  **Check Previews**: Open the `_preview` folder to verify the generated thumbnails.

## Summary of Automatic vs. Manual Tasks

| Task | Where | Handling |
| :--- | :--- | :--- |
| Create Project | Ramses Client | **Manual** (Must be done first) |
| Create Steps (PLATE) | Ramses Client | **Manual** (Recommended first) |
| Create Sequences | Ingest Tool | **Automatic** |
| Create Shots | Ingest Tool | **Automatic** |
| Create Folders | Ingest Tool | **Automatic** |
| Rename & Copy Files | Ingest Tool | **Automatic** |
| Generate Thumbnails | Ingest Tool | **Automatic** |

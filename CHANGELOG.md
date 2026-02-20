# Changelog - Ramses Ingest

## [Released] - 2026-02-07

### ✨ New Features (Professional UI & Workflow)

#### Professional Master-Detail Interface
- **IMPLEMENTED**: Complete 3-panel layout (Filter | Table | Details) matching ShotGrid/production standards.
- **ADDED**: Status Sidebar with live count badges and clickable filters.
- **ADDED**: Editable Table with in-place cell editing for Shot IDs.
- **ADDED**: Detail Panel showing comprehensive metadata (Res, FPS, Codec) and override controls.
- **ADDED**: Color-coded status dots (●●●) replacing text labels for instant readability.
- **ADDED**: "Fast Verify" mode for rapid ingestion of massive deliveries (First/Mid/Last checks).
- **ADDED**: Integrated GUI Log Panel with syntax highlighting for Errors/Warnings/Success.

#### Robust Scanning Engine

- **ADDED**: Custom image sequence scanner supporting both `.` and `_` frame separators with padding-boundary grouping.
- **IMPROVED**: Scanner now supports both `.` and `_` frame separators (e.g., `shot.1001.exr` and `shot_1001.exr`).
- **ADDED**: Recursive directory walking with proper error handling for permission issues.

#### Transactional Integrity
- **ADDED**: All-or-nothing ingest logic. If a file copy or metadata write fails, the entire version folder is automatically rolled back (deleted) to prevent "zombie" versions.
- **ADDED**: Explicit "Disk Space Guard" checks before starting transfer.

### 🚀 Performance & Reliability

#### Responsiveness
- **OPTIMIZED**: Implemented `ConnectionWorker` for non-blocking background daemon connection on startup.
- **OPTIMIZED**: Added debouncing (300ms) to Shot ID overrides to prevent UI freezing during typing.
- **OPTIMIZED**: Refactored table population to perform in-place updates, eliminating flicker and scroll jumping.

#### Core System
- **FIXED**: Critical bug where source file paths were incorrectly reconstructed with hardcoded separators.
- **FIXED**: Hardcoded `"05-SHOTS"` folder path replaced with dynamic `FolderNames.shots` from Ramses API.
- **FIXED**: Missing `ffprobe` dependency now triggers a proactive startup warning.
- **FIXED**: Silent `OSError` failures during MD5 calculation are now properly caught and reported.

### 🔧 Previous Critical Fixes (Retained)

#### Scanner (EXR Sequence Detection)
- **FIXED**: Frame padding regex supports 2-digit padding.
- **FIXED**: Reverted to non-greedy regex to prevent catastrophic backtracking.

#### Cache System (Performance & LRU)
- **FIXED**: Implemented proper LRU (Least Recently Used) cache eviction.
- **OPTIMIZED**: Batched cache writes (writes once at end of processing).

#### Path Normalization (Cross-Platform)
- **FIXED**: Inconsistent path separators causing cache misses on Windows.
- **ADDED**: Centralized `path_utils.py` module.

#### Version Detection
- **IMPROVED**: Smart 3-tier validation for version folders to prevent collisions.

#### Security
- **ADDED**: Validation for extracted IDs to prevent path traversal and injection attacks.

---

## Impact Summary

| Feature | Before | After |
|---------|--------|-------|
| UI Layout | ❌ Crowded/Single | ✅ Professional 3-Panel |
| Data Safety | ❌ Zombie folders | ✅ Transactional Rollback |
| Responsiveness | ❌ UI Freezes | ✅ Async Background Threads |
| Sequence Support | ❌ Strict regex | ✅ Custom scanner + flexible separators |
| Error Handling | ⚠️ Silent failures | ✅ Explicit GUI logging + Alerts |

---

## Testing Checklist

- [x] **Scanner**: Correctly groups `.` and `_` separated sequences.
- [x] **Ingest**: Files copy correctly; rollback triggers on failure.
- [x] **UI**: Filters, Search, and Overrides work without lag.
- [x] **Performance**: Large lists update instantly without flicker.
- [x] **Integrity**: MD5 checks verify data; bad files trigger errors.


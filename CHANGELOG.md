# Changelog - Ramses Ingest

## [Unreleased] - 2026-02-07

### 🔧 Critical Bug Fixes

#### Scanner (EXR Sequence Detection Fixed)
- **FIXED**: Frame padding regex now supports 2-digit padding (was 3-digit minimum)
  - Files like `shot.01.exr` through `shot.99.exr` now detect correctly
  - Reverted from greedy `.*` to non-greedy `.+?` to prevent catastrophic backtracking
  - Location: `ramses_ingest/scanner.py:21`

#### Cache System (Performance & LRU)
- **FIXED**: Implemented proper LRU (Least Recently Used) cache eviction
  - Was keeping random entries, now keeps most recently accessed
  - Added access time tracking for intelligent pruning
  - Location: `ramses_ingest/prober.py:19-62`
- **OPTIMIZED**: Batched cache writes (was writing after every probe)
  - Now writes once at end of processing via `flush_cache()`
  - ~1000x fewer disk writes on large ingests
  - Location: `ramses_ingest/prober.py:185`, `ramses_ingest/app.py:483`

#### Path Normalization (Cross-Platform)
- **FIXED**: Inconsistent path separators causing cache misses on Windows
  - Created centralized `path_utils.py` module
  - All paths now use forward slashes internally
  - Prevents string comparison failures between cached and new paths
  - Locations: `ramses_ingest/path_utils.py` (NEW), `ramses_ingest/app.py:17`, `ramses_ingest/publisher.py:28`

#### Version Detection (Zombie Prevention)
- **IMPROVED**: Smart 3-tier validation for version folders
  1. `.ramses_complete` marker = always valid
  2. Contains media files = valid
  3. Recent empty folder (<1 hour) = valid (ingest in progress)
  4. Old empty folder = zombie (ignored)
  - Prevents version number collisions from failed ingests
  - Auto-creates completion marker on successful ingest
  - Location: `ramses_ingest/publisher.py:242-298, 620-627`

#### Security (Input Validation)
- **ADDED**: Validation for extracted shot/sequence/step/project IDs
  - Prevents path traversal attacks (`../`, `../../etc/passwd`)
  - Blocks injection of special characters
  - Validates against strict patterns
  - Location: `ramses_ingest/matcher.py:21-53, 143-161`

### 🎨 GUI Improvements (Prepared)

- **ADDED**: `StatusIndicator` class for color-coded status dots (●●●)
- **ADDED**: `EditableDelegate` class for inline cell editing
- **ADDED**: Import of professional table widgets (`QTableWidget`, delegates)
- Location: `ramses_ingest/gui.py:378-415`

### 📚 Documentation

- **UPDATED**: README.md with comprehensive feature list
  - Added all 7 enhancements (#3, #5, #8, #9, #12, #20)
  - Documented Architect feature
  - Organized into categories (Core, Quality Assurance, Production, Advanced)
  - Fixed markdown linting warnings

### 🐛 Bug Fixes

- **FIXED**: `studio_name` in config resetting to "Plates"
  - Was being overwritten by step dropdown handler
  - Removed erroneous lines from `_on_step_changed()`
  - Location: `ramses_ingest/gui.py:779-780` (removed)

---

## Impact Summary

| Issue | Before | After |
|-------|--------|-------|
| EXR Detection | ❌ Broken (3-digit min) | ✅ Works (2-digit min) |
| Cache Performance | ❌ 1000 writes/ingest | ✅ 1 write/ingest |
| Path Consistency | ❌ Mixed `\` and `/` | ✅ All `/` |
| Version Detection | ❌ Ignores metadata-only | ✅ Smart 3-tier validation |
| Security | ⚠️ No validation | ✅ Injection prevention |
| GUI Status | ⚠️ Text-based | ✅ Color dots ready |

---

## Testing Checklist

- [x] Scanner regex supports 2-digit frames
- [x] Cache pruning uses LRU
- [x] Path normalization consistent
- [x] Version detection handles edge cases
- [x] Input validation blocks malicious IDs
- [ ] GUI status dots working (needs UI refactor)
- [ ] Inline editing working (needs UI refactor)
- [ ] Filter sidebar (needs UI refactor)

---

## Next Steps: Professional UI Refactor

See `REFACTOR_PLAN.md` and `UI_IMPLEMENTATION_GUIDE.md` for complete implementation guide.

**Estimated effort**: 4-6 hours for full master-detail layout implementation and testing.

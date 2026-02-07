# Ramses Ingest — Production Roadmap (Tier 1)

## 🛡️ Data Integrity & Safety
- [ ] **Atomic Publishes**: Implement `.tmp` staging folders and `os.rename` for all-or-nothing version commits.
- [ ] **Disk Space Guard**: Verify destination volume capacity before initiating multi-clip transfers.
- [ ] **Hash Sampling Modes**: Add "Fast Verify" (First/Mid/Last + Size) as an alternative to "Gold" bit-perfect MD5.
- [ ] **Zombie Cleanup**: Proactive identification and removal of orphaned/empty version folders from failed sessions.

## 🏗️ Naming Architect (UX)
- [ ] **User Presets**: Enable persistence for custom blueprints in `config/default_rules.yaml`.
- [ ] **Regex Sanitization**: Harden Separator input to escape control characters and prevent engine crashes.
- [ ] **Heuristic Refinement**: Improve "Magic Wand" detection for complex vendor prefixes (e.g., "VND_SEQ_SHOT").

## 🚀 Advanced Features
- [ ] **Timecode Trimming**: Implement source-range clipping based on EXR/MOV metadata headers.
- [ ] **OCIO Proxy Burn-ins**: Integrate OCIO colorspace transformations into FFmpeg proxy generation logic.
- [ ] **Storage Optimization**: Add support for Hardlinks/Symlinks to minimize storage footprint on internal transfers.

## 🔌 System Resilience
- [ ] **Daemon Dropout**: Implement a reconnection grace period and auto-retry logic for transient API failures.
- [ ] **Volume Analytics**: Track exact physical bytes moved vs. logical size for precise manifest reporting.

# GUI Refactor Plan - Professional Master-Detail Layout

## Goal
Transform current crowded UI into industry-standard VFX tool (ShotGrid-style)

## Current Issues (Lines)
- 428-456: Project panel crowded (5 widgets in one row)
- 463-484: Rule selector cramped (4 buttons)
- 494-523: Tree widget (9 columns, not editable)
- 526-549: Two separate option rows
- 586-595: Separate log toggle

## New Layout Structure

```
┌──────────────────────────────────────────────────────────┐
│  [●] RAMSES INGEST     Project: PROJ▼  Step: PLATE▼     │ ← Minimal header (30px)
├──────┬───────────────────────────────────────────┬───────┤
│      │                                           │       │
│FILTER│         CLIP TABLE (Editable)             │DETAIL │
│(20%) │              (60%)                        │(20%) │
│      │                                           │       │
│ 🔍   │ ●Filename      Shot  Seq  Frames Status  │Selected│
│[__]  │ ●SEQ010…     SH010 SEQ…  96f   ✓         │SH010  │
│      │ ⚠comp…       ?     -     1f    ⚠         │       │
│Status│                                           │96f    │
│✓ 44  │ [Select multiple → Right-click menu]     │1920x… │
│⚠ 2   │                                           │       │
│✗ 1   │                                           │Override│
│      │                                           │Shot:  │
│Type  │                                           │[____] │
│□ Seq │                                           │       │
│□ Mov │                                           │       │
├──────┴───────────────────────────────────────────┴───────┤
│  [Clear]    47 clips, 44 ready       [⚙]  [Execute]     │ ← Action bar
└──────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Phase 1: Layout Structure ✓
1. Replace QVBoxLayout with QSplitter (3-panel)
2. Minimal top header (Project/Step only)
3. Filter sidebar (left)
4. Main table (center)
5. Detail panel (right)
6. Action bar (bottom)

### Phase 2: Table Widget
1. Replace QTreeWidget with QTableWidget
2. Add editable delegate for Shot column
3. Implement color-coded status (dots, not text)
4. Add context menu (right-click)

### Phase 3: Filter Sidebar
1. Search box
2. Status filters (✓ ⚠ ✗ counts, clickable)
3. Type filters (Sequences, Movies)

### Phase 4: Detail Panel
1. Show on selection
2. Display metadata (frames, resolution, codec)
3. Inline override controls (Shot ID)
4. Validation warnings

### Phase 5: Advanced Options
1. Move to floating panel (⚙ button)
2. Thumbnails, Proxies, Status, OCIO options

### Phase 6: Keyboard Shortcuts
1. Enter = Execute
2. Ctrl+F = Focus search
3. Escape = Clear selection
4. Delete = Remove selected clips

## Files to Modify
- `ramses_ingest/gui.py` (main refactor)
- Keep all methods, update to work with QTableWidget instead of QTreeWidget

## Testing Checklist
- [ ] Drag-drop still works
- [ ] Inline editing works
- [ ] Filtering works
- [ ] Sorting works
- [ ] Execute works
- [ ] Progress reporting works
- [ ] Architect still works

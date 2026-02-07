# Professional Architect Dialog Integration Guide

## ✅ What's Been Created

The Architect dialog has been redesigned to match professional VFX tool standards:

**File:** `architect_professional.py` - Complete improved implementation

---

## 🎯 Key Improvements

### Before (Current)
```
┌─────────┬────────────────────────────┬──────────┐
│ PRESETS │   BLUEPRINT                │INSPECTOR │
│         │   [tokens here]            │          │
│ Standard│   + Buttons + Buttons      │ Padding: │
│ Shot+Ver│                            │ [___]    │
│ Techni..│   ┌─────────────────────┐  │ Prefix:  │
│         │   │ Samples             │  │ [___]    │
│         │   │ (paste here)        │  │          │
│         │   ├─────────────────────┤  │          │
│         │   │ Results             │  │          │
│         │   │ (scroll to see)     │  │          │
│         │   └─────────────────────┘  │          │
│         │   Regex: ...               │          │
└─────────┴────────────────────────────┴──────────┘
```

**Problems:**
- Left sidebar wastes space (40px per button)
- Vertical splitter hides samples OR results
- Right inspector panel always visible (240px)
- Token buttons take 2 rows of space
- Blueprint too small (60px)

### After (Professional)
```
┌──────────────────────────────────────────────────────────┐
│ Quick Start: [— Build Custom —▼]        ✨ Magic Wand   │ ← Header
├──────────────────────────────────────────────────────────┤
│ PATTERN BLUEPRINT                                        │
│ ┌──────────────────────────────────────────────────────┐│
│ │ [Sequence] [_] [Shot] [_] [Version]          │ 80px │
│ └──────────────────────────────────────────────────────┘│
│ Add Token: [— Select —▼]   Click token to edit...       │
├──────────────┬───────────────────────────────────────────┤
│ SAMPLES      │  LIVE SIMULATION          2/3 matched 67%│
│              │                                           │
│ SEQ010_SH.. ││  ● SEQ010_SH010_v001  ✓ Matched         │
│ SEQ020_SH.. ││  ● SEQ020_SH030_v002  ✓ Matched         │
│ bad_file_01 ││  ✗ bad_file_01        Shot not found    │
│              │                                           │
│              │  [X-Ray highlighting in results →]       │
├──────────────┴───────────────────────────────────────────┤
│ ▼ Generated Regex  [Copy]                                │
│ ^(?P<sequence>[A-Za-z0-9]+)_(?P<shot>...                │
│                                  [Cancel]  [Apply Rule] ││
└──────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ No sidebars (save 420px horizontal space)
- ✅ Side-by-side samples|results (see both at once)
- ✅ Larger blueprint (80px vs 60px)
- ✅ Compact token dropdown (vs 5 buttons)
- ✅ Inline token editing (vs permanent inspector)
- ✅ Match stats visible (67% matched)
- ✅ Collapsible regex (clean by default)
- ✅ Professional spacing

---

## 🔧 Integration Steps

### Step 1: Backup Current File
```bash
cp ramses_ingest/architect.py ramses_ingest/architect_backup.py
```

### Step 2: Replace `_setup_ui()` Method

**Location:** `ramses_ingest/architect.py` line 625

Replace the entire `_setup_ui()` method with `_setup_ui_professional()` from `architect_professional.py`

### Step 3: Add New Supporting Methods

Add these methods to `NamingArchitectDialog` class (after `_setup_ui`):

From `architect_professional.py`:
- `_on_preset_selected()`
- `_on_token_selected()`
- `_on_token_clicked()` ← Update existing or add if missing
- `_toggle_regex()`
- `_copy_regex()`
- `_on_samples_changed()` ← Update existing
- `_on_rule_changed()` ← Update existing

### Step 4: Update Widget References

Some widget names changed:

| Old Widget | New Widget |
|------------|------------|
| `self.sidebar` | (removed) |
| (buttons in ribbon) | `self.token_combo` |
| (inspector panel) | (removed, now inline) |
| `self.regex_label` | (still exists, now collapsible) |
| (no stats) | `self.match_stats` (new) |
| (no preset combo) | `self.preset_combo` (new) |

### Step 5: Remove Inspector Panel

The inspector sidebar is removed. Token editing is now inline:
- Click token → Dialog appears
- Edit → Changes apply immediately

Remove these if they exist:
- `self.inspector` widget
- `TokenInspector` class references in this dialog

### Step 6: Test Functionality

```bash
python -m ramses_ingest
# Click "Architect..." button
```

**Checklist:**
- [ ] Dialog opens without errors
- [ ] Preset dropdown works
- [ ] Token dropdown adds tokens
- [ ] Tokens appear in blueprint
- [ ] Can drag to reorder tokens
- [ ] Click token → inline editor appears
- [ ] Paste samples → table updates
- [ ] Magic Wand works
- [ ] Match stats update (X/Y matched Z%)
- [ ] Regex toggle works
- [ ] Copy regex works
- [ ] Apply saves rule

---

## 📊 Size Comparison

| Element | Old Width | New Width | Saved |
|---------|-----------|-----------|-------|
| Left Sidebar | 180px | 0px | **180px** |
| Right Inspector | 240px | 0px | **240px** |
| Token Buttons | ~600px (5 btns) | ~200px (1 dropdown) | **400px** |
| **Total Saved** | | | **820px** |

**Window can be narrower or more content fits!**

---

## 🎨 Visual Improvements

### Blueprint Area
- **Height:** 60px → 80px (33% larger, easier to drop)
- **Border:** Solid → Dashed (clearer affordance)
- **Visual cue:** Placeholder text when empty

### Token Palette
- **Before:** 5 buttons + separator buttons (2 rows)
- **After:** 1 dropdown with icons (1 compact row)
- **Icons:** 🎬 Sequence, 🎥 Shot, 📦 Version, etc.

### Samples | Results Layout
- **Before:** Vertical splitter (scroll to see results)
- **After:** Side-by-side (see both always)
- **Width:** 40% samples | 60% results
- **Match stats:** Live feedback (2/3 matched 67%)

### Regex Display
- **Before:** Always visible (takes space)
- **After:** Collapsed by default (▼ to expand)
- **Copy button:** Quick clipboard access

### Token Editing
- **Before:** Sidebar inspector (always visible)
- **After:** Inline dialog (appears on click)
- **Faster:** Fewer clicks to edit

---

## 🚀 Integration Script (Automated)

Create `integrate_architect.py`:

```python
#!/usr/bin/env python
"""Integrate professional Architect UI"""

import re

# Read files
with open('ramses_ingest/architect.py', 'r') as f:
    content = f.read()

with open('ramses_ingest/architect_professional.py', 'r') as f:
    new_code = f.read()

# Extract new _setup_ui method
new_setup_ui = new_code.split('def _setup_ui_professional')[1]
new_setup_ui = 'def _setup_ui' + new_setup_ui.split('\n\n# ═══════════')[0]

# Extract new methods
new_methods = re.search(r'# Supporting Methods.*', new_code, re.DOTALL).group(0)

# Replace _setup_ui
pattern = r'def _setup_ui\(self\).*?(?=\n    def _)'
content = re.sub(pattern, new_setup_ui + '\n\n', content, flags=re.DOTALL)

# Append new methods before last method
insert_pos = content.rfind('\n    def get_final_regex')
content = content[:insert_pos] + '\n\n' + new_methods + '\n' + content[insert_pos:]

# Write updated file
with open('ramses_ingest/architect.py', 'w') as f:
    f.write(content)

print("✅ Professional Architect UI integrated!")
```

Run:
```bash
python integrate_architect.py
python -m ramses_ingest  # Test
```

---

## 🔍 Troubleshooting

### Issue: Import errors
**Solution:** Ensure all imports are at top of file (QInputDialog, QApplication.clipboard)

### Issue: Widgets not found
**Solution:** Check removed widgets (sidebar, inspector) aren't referenced elsewhere

### Issue: Token editing doesn't work
**Solution:** Verify `_on_token_clicked()` is properly connected to `drop_zone.token_clicked`

### Issue: Presets don't apply
**Solution:** Check `_apply_preset()` method exists (should already exist in original)

### Issue: Match stats don't update
**Solution:** Ensure `_on_rule_changed()` calls `self.match_stats.setText()`

---

## 📝 Rollback Plan

```bash
# Restore backup
cp ramses_ingest/architect_backup.py ramses_ingest/architect.py

# Or use git
git checkout ramses_ingest/architect.py
```

---

## 🎉 Success Criteria

You'll know it's working when:

1. ✅ Dialog is cleaner (no side panels)
2. ✅ Samples and results visible side-by-side
3. ✅ Preset dropdown at top works
4. ✅ Token dropdown adds tokens
5. ✅ Blueprint is taller (80px)
6. ✅ Click token → inline editor appears
7. ✅ Match stats show X/Y matched (%)
8. ✅ Regex collapses/expands with ▼/▲
9. ✅ Copy button copies regex
10. ✅ More breathing room overall

---

## 💡 Future Enhancements

After integration, consider:

1. **Token Preview** - Hover tooltip showing example match
2. **Sample Library** - Save common filename patterns
3. **Export/Import** - Share rules with team
4. **Validation** - Warn about common regex mistakes
5. **History** - Undo/redo for token changes

---

Good luck! 🚀

# Professional UI Integration Guide

## ✅ What's Been Prepared

Three implementation files have been created with the complete professional UI:

1. **`gui_professional.py`** - New `_build_ui_professional()` method
2. **`gui_professional_methods.py`** - All supporting methods (17 new methods)
3. **`gui_professional_populate.py`** - Table population logic

## 🔧 Integration Steps

### Step 1: Backup Current GUI
```bash
cp ramses_ingest/gui.py ramses_ingest/gui_backup.py
```

### Step 2: Add New Methods to `gui.py`

**Location:** After line 639 (after current `_build_ui` method)

1. Copy all methods from `gui_professional_methods.py`
2. Copy all methods from `gui_professional_populate.py`

**Methods to add:**
- `_setup_shortcuts()`
- `_apply_filter()`
- `_on_type_filter_changed()`
- `_apply_table_filters()`
- `_on_selection_changed()`
- `_on_override_changed()`
- `_on_table_item_changed()`
- `_on_remove_selected()`
- `_show_advanced_options()`
- `_update_filter_counts()`
- `_populate_table()` ← Replaces `_populate_tree()`
- `_on_checkbox_changed()`
- `_on_context_menu()` ← Update existing
- `_on_context_override_shot()`
- `_on_context_skip()`
- `_update_summary()` ← Update existing

### Step 3: Replace `_build_ui()` Method

**Location:** Line 440-639

Replace the entire `_build_ui()` method with `_build_ui_professional()` from `gui_professional.py`

### Step 4: Update Method Calls

**Find and Replace:**
```python
# OLD                      # NEW
self._tree               → self._table
self._populate_tree()    → self._populate_table()
```

**Files to check:**
- All methods in `IngestWindow` that reference `_tree`
- Specifically: `_on_drop()`, `_on_clear()`, `_on_ingest()`, etc.

### Step 5: Update Widget References

Some widget names have changed:

| Old Widget | New Widget |
|------------|------------|
| `self._tree` | `self._table` |
| `self._project_label` | `self._project_combo` |
| (no change) | `self._filter_all` (new) |
| (no change) | `self._filter_ready` (new) |
| (no change) | `self._detail_widget` (new) |
| (no change) | `self._override_shot` (new) |

### Step 6: Update `_try_connect()` Method

**Location:** Around line 647

Change:
```python
# OLD
self._project_label.setText(f"PROJECT: {pid} | {pname}")

# NEW
self._project_combo.clear()
self._project_combo.addItem(f"{pid} - {pname}")
self._project_combo.setCurrentIndex(0)
```

### Step 7: Test Basic Functionality

```bash
python -m ramses_ingest
```

**Checklist:**
- [ ] Window opens without errors
- [ ] Can drag-drop folders
- [ ] Table populates with clips
- [ ] Status dots show correctly (●●●)
- [ ] Filter sidebar works
- [ ] Detail panel updates on selection
- [ ] Inline editing works (double-click shot ID)
- [ ] Execute button enables/disables
- [ ] Keyboard shortcuts work (Ctrl+F, Enter, Delete)

### Step 8: Advanced Testing

- [ ] All filters work (status, type, search)
- [ ] Context menu works (right-click)
- [ ] Advanced options dialog works
- [ ] Architect still works
- [ ] EDL loading works
- [ ] Execute completes successfully
- [ ] Progress reporting works
- [ ] Report generation works

---

## 🚀 Quick Integration (Copy-Paste)

### Option A: Manual Integration
Follow steps 1-8 above

### Option B: Automated Script
Create `integrate_ui.py`:

```python
#!/usr/bin/env python
"""Integrate professional UI into gui.py"""

import re

# Read current gui.py
with open('ramses_ingest/gui.py', 'r') as f:
    content = f.read()

# Read new components
with open('ramses_ingest/gui_professional.py', 'r') as f:
    new_build_ui = f.read()

with open('ramses_ingest/gui_professional_methods.py', 'r') as f:
    new_methods = f.read()

with open('ramses_ingest/gui_professional_populate.py', 'r') as f:
    new_populate = f.read()

# Replace _build_ui method
pattern = r'def _build_ui\(self\).*?(?=\n    # -- Helpers)'
replacement = new_build_ui.split('def _build_ui_professional')[1]
content = re.sub(pattern, f'def _build_ui{replacement}', content, flags=re.DOTALL)

# Append new methods before last class
insert_pos = content.rfind('# ---------------------------------------------------------------------------')
content = content[:insert_pos] + new_methods + '\n\n' + new_populate + '\n\n' + content[insert_pos:]

# Replace tree → table
content = content.replace('self._tree', 'self._table')
content = content.replace('_populate_tree()', '_populate_table()')

# Write updated file
with open('ramses_ingest/gui.py', 'w') as f:
    f.write(content)

print("✅ Professional UI integrated!")
```

Run:
```bash
python integrate_ui.py
python -m ramses_ingest  # Test
```

---

## 🎯 What You Get

### Before (Current)
- Crowded layout with 9 stacked sections
- Text-based status ("Ready", "Warning", "Error")
- No inline editing
- No filtering
- No detail panel
- Tree widget (not editable)

### After (Professional)
- Clean 3-panel master-detail layout
- Color-coded status dots (●●●)
- Inline editing (double-click shot column)
- Smart filtering (status, type, search)
- Contextual detail panel
- Professional table with shortcuts
- Keyboard-driven workflow

---

## 📊 Comparison

| Feature | Old UI | New UI |
|---------|--------|--------|
| Layout | Stacked vertical | 3-panel splitter |
| Status | Text | Color dots ● |
| Editing | External dialog | Inline (double-click) |
| Filtering | Search only | Multi-level filters |
| Details | None | Right panel |
| Shortcuts | None | Ctrl+F, Enter, Del |
| Space Efficiency | Low | High |
| Professional Feel | Good | Excellent |

---

## 🔍 Troubleshooting

### Issue: Import errors
**Solution:** Add missing imports at top of gui.py (already done)

### Issue: Widgets not found
**Solution:** Check widget name changes (tree → table, etc.)

### Issue: Methods missing
**Solution:** Ensure all methods from gui_professional_methods.py are added

### Issue: Layout doesn't look right
**Solution:** Check splitter sizes in _build_ui_professional (line ~220)

### Issue: Checkboxes don't work
**Solution:** Verify _on_checkbox_changed is connected properly

---

## 📝 Rollback Plan

If something goes wrong:

```bash
# Restore backup
cp ramses_ingest/gui_backup.py ramses_ingest/gui.py

# Or use git
git checkout ramses_ingest/gui.py
```

---

## 🎉 Success Criteria

You'll know it's working when:

1. ✅ Window is wider (1200px vs 780px)
2. ✅ Three vertical panels visible (filters | table | details)
3. ✅ Status shows as colored dots, not text
4. ✅ Can double-click shot ID to edit inline
5. ✅ Clicking filter buttons hides/shows rows
6. ✅ Selecting clip shows details on right
7. ✅ Ctrl+F focuses search box
8. ✅ Enter executes ingest (when enabled)

---

## 💡 Next Steps After Integration

1. **Fine-tune styling** - Adjust colors, spacing, fonts
2. **Add more shortcuts** - Ctrl+A (select all), Ctrl+D (deselect)
3. **Enhance detail panel** - Add thumbnail preview
4. **Add batch operations** - "Set all to step COMP"
5. **Save/Load sessions** - Resume interrupted work

---

## 🆘 Need Help?

If integration fails or behavior is unexpected:

1. Check console for Python errors
2. Verify all methods are copied correctly
3. Ensure widget names are updated everywhere
4. Test with simple delivery (1-2 clips) first
5. Use debugger to step through _populate_table()

Good luck! 🚀

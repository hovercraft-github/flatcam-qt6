# ToolPaint & ToolNCC Shared Code — Implementation Plan v5

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire existing `ToolTableHelper` infrastructure into `Paint.py` and `Ncc.py` to eliminate ~600 lines of duplicated code.

**Architecture:** Composition pattern — `ToolTableHelper` instance operates on host's tools dict via `ToolManager`.

**Tech Stack:** Python 3.10+, PyQt6, dataclasses, existing ToolShared module.

**Worktree:** `D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared`

---

## Current State (from jcode analysis)

| Component | Status | Lines | Notes |
|-----------|--------|-------|-------|
| `ToolShared/types.py` | ✅ Exists | 347 | ToolEntry + config dataclasses |
| `ToolShared/ToolManager.py` | ✅ Exists | 373 | Uses ToolEntry, full CRUD |
| `ToolShared/ToolTableHelper.py` | ✅ Exists | 792 | Shared UI logic |
| `ToolShared/__init__.py` | ✅ Exists | 34 | Exports all classes |
| Tests | ✅ Exists | 68 | All passing |
| `Paint.py` | ❌ Unchanged | 1829 | **Must wire to helper** |
| `Ncc.py` | ❌ Unchanged | ~2026 | **Must wire to helper** |

---

## Key Differences: Paint vs NCC

| Aspect | ToolPaint | ToolNCC |
|--------|-----------|---------|
| Tools dict | `self.paint_tools` | `self.ncc_tools` |
| Order combo | `paint_order_combo` | `ncc_order_combo` |
| Generate button | `generate_paint_button` | `generate_ncc_button` |
| Rest checkbox | `rest_cb` | `ncc_rest_cb` |
| DB target | `_('Paint')` | `_('NCC')` |
| Tool key prefix | `tools_paint_` | `tools_ncc_` |
| DB source | `'paint'` | `'ncc'` |
| **Combo columns** | **`[2]`** | `[2]` |
| Store offset | `True` | `False` |

---

## Phase 1: Modify ToolPaint/Paint.py

### Task 1.1: Add imports (line 13)

**File:** `appPlugins/ToolPaint/Paint.py`

**Current line 13:**
```python
from appPlugins.ToolShared.ToolManager import ToolManager
```

**Change to:**
```python
from appPlugins.ToolShared.ToolManager import ToolManager
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import (
    ToolTableConfig,
    DeleteToolsParams,
)
```
**Note:** `FormStorageParams` removed — not used by host directly.

---

### Task 1.2: Add helper attribute (after line 87)

**File:** `appPlugins/ToolPaint/Paint.py`

**Find** (around line 87 in `__init__`):
```python
self.paint_tools = {}
```

**Add after:**
```python
self.tool_table_helper: Optional[ToolTableHelper] = None
```

---

### Task 1.3: Initialize helper in set_tool_ui() (BEFORE loop at line ~485)

**File:** `appPlugins/ToolPaint/Paint.py`

**Find** (after diameters are loaded, BEFORE `for dia in diameters:` loop):

**Add:**
```python
# Initialize ToolTableHelper with Paint-specific config
config = ToolTableConfig(
    log_prefix="ToolPaint",
    tool_target=_('Paint'),
    tool_key_prefix='tools_paint_',
    db_source='paint',
    combo_columns=[2],  # Paint only has combo in column 2 (verified line 856)
    store_offset=True,
    generate_button_attr='generate_paint_button',
    order_combo_attr='paint_order_combo',
    rest_cb_attr='rest_cb',
)
self.tool_table_helper = ToolTableHelper(
    host=self,
    tools_dict=self.paint_tools,
    config=config,
)
```

---

### Task 1.4: Replace method bodies with delegates

#### Method 1: `on_toggle_all_rows` (line 585)
```python
def on_toggle_all_rows(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_toggle_all_rows()
```

#### Method 2: `on_row_selection_change` (line 610)
```python
def on_row_selection_change(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_row_selection_change()
```

#### Method 3: `update_ui` (line 643)
```python
def update_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.update_ui()
```

#### Method 4: `on_apply_param_to_all_clicked` (line 722)
```python
def on_apply_param_to_all_clicked(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_apply_param_to_all_clicked()
```

#### Method 5: `on_tool_default_add` (line 1052)
```python
def on_tool_default_add(self, dia=None, muted=None):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_default_add(dia=dia, muted=muted)
```

#### Method 6: `on_tool_add` (line 899)
```python
def on_tool_add(self, custom_dia=None):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_add(custom_dia=custom_dia)
```

#### Method 7: `on_tool_edit` (line 1099)
```python
def on_tool_edit(self, item):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_edit(item)
```

#### Method 8: `on_tool_delete` (line 1139)
```python
def on_tool_delete(self, rows_to_delete=None, all_tools=None):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        params = DeleteToolsParams(
            rows_to_delete=rows_to_delete,
            all_tools=all_tools if all_tools is not None else False,
        )
        self.tool_table_helper.on_tool_delete(params=params)
```

#### Method 9: `on_tooltable_cell_widget_change` (line 758)
```python
def on_tooltable_cell_widget_change(self):
    """Delegate to ToolTableHelper - uses sender() pattern."""
    if self.tool_table_helper:
        widget = self.sender()
        self.tool_table_helper.on_tooltable_cell_widget_change(widget)
```

#### Method 10: `on_order_changed` (line 780)
```python
def on_order_changed(self, order):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_order_changed(order)
```

#### Method 11: `rebuild_ui` (line 784)
```python
def rebuild_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.rebuild_ui()
```

#### Method 12: `build_ui` (line 804)
```python
def build_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.build_ui()
```

#### Method 13: `on_object_selection_changed` (line 624) — **KEEP HOST LOGIC**
```python
def on_object_selection_changed(self, current):
    """Host-specific: handles updating obj_combo based on tree selection."""
    found_idx = None
    for tab_idx in range(self.app.ui.notebook.count()):
        if self.app.ui.notebook.tabText(tab_idx) == self.ui.pluginName:
            found_idx = True
            break

    if found_idx:
        try:
            name = current.indexes()[0].internalPointer().obj.obj_options['name']
            kind = current.indexes()[0].internalPointer().obj.kind

            if kind in ['gerber', 'geometry']:
                self.ui.type_obj_radio.set_value(kind)

            self.ui.obj_combo.set_value(name)
        except Exception:
            pass
```

#### Method 14: `on_paint_tool_add_from_db_clicked` (line 1808) — **KEEP HOST LOGIC**
```python
def on_paint_tool_add_from_db_clicked(self):
    """Open Tools DB dialog for Paint source, then delegate add to helper."""
    # if the Tools Database is already opened focus on it
    for idx in range(self.app.ui.plot_tab_area.count()):
        if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
            self.app.ui.plot_tab_area.setCurrentWidget(self.app.tools_db_tab)
            break
    ret_val = self.app.on_tools_database(source='paint')
    if ret_val == 'fail':
        return
    self.app.tools_db_tab.ok_to_add = True
    self.app.tools_db_tab.ui.buttons_frame.hide()
    self.app.tools_db_tab.ui.add_tool_from_db.show()
    self.app.tools_db_tab.ui.cancel_tool_from_db.show()
```

#### Method 15: `on_add_tool_by_key` (line 741) — **KEEP HOST LOGIC**
```python
def on_add_tool_by_key(self):
    """Open diameter spinner dialog, then delegate to on_tool_add."""
    tool_add_popup = FCInputDoubleSpinner(title='%s...' % _("New Tool"),
                                          text='%s:' % _('Enter a Tool Diameter'),
                                          min=0.0000, max=99.9999, decimals=self.decimals,
                                          parent=self.app.ui)
    tool_add_popup.set_icon(QtGui.QIcon(self.app.resource_location + '/letter_t_32.png'))

    val, ok = tool_add_popup.get_value()
    if ok:
        if float(val) == 0:
            self.app.inform.emit('[WARNING_NOTCL] %s' %
                                 _("Please enter a tool diameter with non-zero value, in Float format."))
            return
        self.on_tool_add(custom_dia=float(val))
    else:
        self.app.inform.emit('[WARNING_NOTCL] %s...' % _("Adding Tool cancelled"))
```

---

### Task 1.5: Update ui_connect() / ui_disconnect()

#### ui_connect() (line 1572)
```python
def ui_connect(self):
    """Connect signals via ToolTableHelper + host-specific."""
    if self.tool_table_helper:
        self.tool_table_helper.connect_table_signals()
        self.tool_table_helper.connect_form_signals()
    
    # Host-specific signals (Paint only) - NOT connected by helper
    self.ui.rest_cb.stateChanged.connect(self.ui.on_rest_machining_check)
    self.ui.paint_order_combo.currentIndexChanged.connect(self.on_order_changed)
```

#### ui_disconnect() (line 1626)
```python
def ui_disconnect(self):
    """Disconnect signals via ToolTableHelper + host-specific."""
    if self.tool_table_helper:
        self.tool_table_helper.disconnect_table_signals()
        self.tool_table_helper.disconnect_form_signals()
    
    # Host-specific disconnects (Paint only)
    try:
        self.ui.rest_cb.stateChanged.disconnect(self.ui.on_rest_machining_check)
    except (TypeError, AttributeError):
        pass
    try:
        self.ui.paint_order_combo.currentIndexChanged.disconnect(self.on_order_changed)
    except (TypeError, AttributeError):
        pass
```

---

## Phase 2: Modify ToolNCC/Ncc.py (Same Pattern)

### Task 2.1: Add imports (line 11)

**File:** `appPlugins/ToolNCC/Ncc.py`

**Add after line 11:**
```python
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import (
    ToolTableConfig,
    DeleteToolsParams,
)
```
**Note:** `FormStorageParams` removed — not used by host directly.

---

### Task 2.2: Add helper attribute in __init__ (after line 69)

**File:** `appPlugins/ToolNCC/Ncc.py`

**Find** (line 69 in `__init__`):
```python
self.ncc_tools = {}   # ← Already exists, do NOT duplicate
```

**Add after:**
```python
self.tool_table_helper: Optional[ToolTableHelper] = None
```
**Note:** Do NOT add `self.ncc_tools = {}` — it already exists from commit 892fc3a6.

---

### Task 2.3: Initialize helper in set_tool_ui() — **CRITICAL FIX**

**File:** `appPlugins/ToolNCC/Ncc.py`

**⚠️ CRITICAL:** Initialize helper **BEFORE** the `for tool_dia in dias:` loop, NOT after.

**Find** (lines 465-467):
```python
self.ncc_tools.clear()
for tool_dia in dias:
    self.on_tool_add(custom_dia=tool_dia)
```

**Add BETWEEN `clear()` and loop:**
```python
self.ncc_tools.clear()

# Initialize ToolTableHelper with NCC-specific config
config = ToolTableConfig(
    log_prefix="ToolNCC",
    tool_target=_('NCC'),
    tool_key_prefix='tools_ncc_',
    db_source='ncc',
    combo_columns=[2],  # NCC has combo only in column 2
    store_offset=False,  # NCC doesn't store offset
    generate_button_attr='generate_ncc_button',
    order_combo_attr='ncc_order_combo',
    rest_cb_attr='ncc_rest_cb',
)
self.tool_table_helper = ToolTableHelper(
    host=self,
    tools_dict=self.ncc_tools,
    config=config,
)

for tool_dia in dias:
    self.on_tool_add(custom_dia=tool_dia)
```

**Why BEFORE the loop:** After delegation, `on_tool_add` becomes `if self.tool_table_helper: helper.on_tool_add(...)`. If helper is uninitialized, all tool additions are silently skipped → empty tool table on startup.

---

### Task 2.4: Replace method bodies with delegates

Same pattern as Paint.py for these methods:

| Method | Line | Delegate |
|--------|------|----------|
| `on_toggle_all_rows` | 623 | `self.tool_table_helper.on_toggle_all_rows()` |
| `on_row_selection_change` | 648 | `self.tool_table_helper.on_row_selection_change()` |
| `update_ui` | 662 | `self.tool_table_helper.update_ui()` |
| `on_apply_param_to_all_clicked` | 754 | `self.tool_table_helper.on_apply_param_to_all_clicked()` |
| `on_tool_default_add` | 1415 | `self.tool_table_helper.on_tool_default_add(dia=dia, muted=muted)` |
| `on_tool_add` | 1266 | `self.tool_table_helper.on_tool_add(custom_dia=custom_dia)` |
| `on_tool_edit` | 1514 | `self.tool_table_helper.on_tool_edit(item)` |
| `on_tool_delete` | 1564 | `self.tool_table_helper.on_tool_delete(params)` |
| `on_tooltable_cellwidget_change` | 1029 | `self.tool_table_helper.on_tooltable_cell_widget_change(self.sender())` |
| `on_order_changed` | 1025 | `self.tool_table_helper.on_order_changed(order)` |
| `rebuild_ui` | 822 | `self.tool_table_helper.rebuild_ui()` |
| `build_ui` | 841 | `self.tool_table_helper.build_ui()` |

**The following methods must NOT be delegated — they contain host-specific logic:**

#### Method A: `on_object_selection_changed` (line 604) — **KEEP AS-IS**
```python
def on_object_selection_changed(self, current):
    """Host-specific: updates object_combo based on project tree selection."""
    found_idx = None
    for tab_idx in range(self.app.ui.notebook.count()):
        if self.app.ui.notebook.tabText(tab_idx) == self.ui.pluginName:
            found_idx = True
            break

    if found_idx:
        try:
            name = current.indexes()[0].internalPointer().obj.obj_options['name']
            kind = current.indexes()[0].internalPointer().obj.kind

            if kind in ['gerber', 'geometry']:
                self.ui.type_obj_radio.set_value(kind)

            self.ui.object_combo.set_value(name)  # NCC uses object_combo, not obj_combo
        except Exception:
            pass
```

#### Method B: `on_ncc_tool_add_from_db_clicked` (line 2005) — **KEEP AS-IS**
```python
def on_ncc_tool_add_from_db_clicked(self):
    """Open Tools DB dialog for NCC source, then delegate add to helper."""
    # if the Tools Database is already opened focus on it
    for idx in range(self.app.ui.plot_tab_area.count()):
        if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
            self.app.ui.plot_tab_area.setCurrentWidget(self.app.tools_db_tab)
            break
    ret_val = self.app.on_tools_database(source='ncc')  # NCC source
    if ret_val == 'fail':
        return
    self.app.tools_db_tab.ok_to_add = True
    self.app.tools_db_tab.ui.buttons_frame.hide()
    self.app.tools_db_tab.ui.add_tool_from_db.show()
    self.app.tools_db_tab.ui.cancel_tool_from_db.show()
```

#### Method C: `on_tool_add_by_key` (line 1478) — **KEEP AS-IS**
```python
def on_tool_add_by_key(self):
    """NCC-specific: has 'find optimal' button callback."""
    btn_icon = QtGui.QIcon(self.app.resource_location + '/open_excellon32.png')

    tool_add_popup = FCInputDialogSpinnerButton(
        title='%s...' % _("New Tool"),
        text='%s:' % _('Enter a Tool Diameter'),
        min=0.0001, max=10000.0000, decimals=self.decimals,
        button_icon=btn_icon,
        callback=self.on_find_optimal_tooldia,
        parent=self.app.ui,
    )
    tool_add_popup.setWindowIcon(QtGui.QIcon(self.app.resource_location + '/letter_t_32.png'))

    def find_optimal(valor):
        tool_add_popup.set_value(float(valor))

    self.optimal_found_sig.connect(find_optimal)

    val, ok = tool_add_popup.get_results()
    if ok:
        if float(val) == 0:
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Please enter a tool diameter with non-zero value, in Float format.")
            )
            self.optimal_found_sig.disconnect(find_optimal)
            return
        self.on_tool_add(custom_dia=float(val))
    else:
        self.app.inform.emit(
            '[WARNING_NOTCL] %s...' % _("Adding Tool cancelled")
        )
    self.optimal_found_sig.disconnect(find_optimal)
```

---

### Task 2.5: Update ui_connect() / ui_disconnect()

#### ui_connect() (line 935)
```python
def ui_connect(self):
    """Connect signals via ToolTableHelper + host-specific."""
    if self.tool_table_helper:
        self.tool_table_helper.connect_table_signals()
        self.tool_table_helper.connect_form_signals()
    
    # Host-specific signals (NCC only)
    self.ui.ncc_rest_cb.stateChanged.connect(self.ui.on_rest_machining_check)
    self.ui.ncc_order_combo.currentIndexChanged.connect(self.on_order_changed)
```

#### ui_disconnect() (line 962)
```python
def ui_disconnect(self):
    """Disconnect signals via ToolTableHelper + host-specific."""
    if self.tool_table_helper:
        self.tool_table_helper.disconnect_table_signals()
        self.tool_table_helper.disconnect_form_signals()
    
    # Host-specific disconnects (NCC only)
    try:
        self.ui.ncc_rest_cb.stateChanged.disconnect(self.ui.on_rest_machining_check)
    except (TypeError, AttributeError):
        pass
    try:
        self.ui.ncc_order_combo.currentIndexChanged.disconnect(self.on_order_changed)
    except (TypeError, AttributeError):
        pass
```

---

## Phase 3: Verification

### Task 3.1: Run existing tests

```bash
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
.venv\Scripts\activate
pytest tests/plugins/toolshared/ -v
```

**Expected:** All 68 tests pass

---

### Task 3.2: Runtime verification checklist

#### ToolPaint:
1. Launch FlatCAM from worktree
2. Open ToolPaint tab
3. **Verify tool table loads existing tools from options** (Task 1.3 placement)
4. Test "Add Tool" via keyboard shortcut (spinner dialog)
5. Test "Add from DB" button (opens Tools DB with Paint source)
6. Add tools via both methods
7. Test table operations: select/deselect, toggle, edit, delete, apply-to-all, order change
8. Test object selection from project tree updates UI
9. Generate paint job

#### ToolNCC:
1. Open ToolNCC tab
2. **Verify tool table loads existing tools from options** (Task 2.3 placement — CRITICAL)
3. Test "Add Tool" via keyboard shortcut (spinner with "find optimal" button)
4. Test "Add from DB" button (opens Tools DB with NCC source)
5. Add tools via both methods
6. Test table operations: select/deselect, toggle, edit, delete, apply-to-all, order change
7. Test object selection from project tree updates UI
8. Generate NCC job

---

## Phase 4: Cleanup (Optional — AFTER VERIFICATION)

**DO NOT REMOVE** the following methods until signal connections are migrated to ToolTableHelper:
- `storage_to_form()` — Still called by `ToolTableHelper.connect_form_signals()`
- `form_to_storage()` — Still called by `ToolTableHelper.connect_form_signals()`

**Safe to remove after verification:**
- Internal helper methods that are now fully delegated
- Duplicate logic that's now in ToolTableHelper

---

## Risks & Mitigations (UPDATED v5)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Signal connection issues | Low | High | Test ui_connect/disconnect thoroughly |
| PaintGen dict access breaks | Low | High | ToolEntry provides dict-like `__getitem__` |
| **"Add from DB" button breaks** | **LOW** | **HIGH** | **Host methods kept (1.4 Methods 14, 2.4 Method B)** |
| **Keyboard shortcut breaks** | **LOW** | **MEDIUM** | **Host methods kept (1.4 Method 15, 2.4 Method C)** |
| **Object selection breaks** | **LOW** | **MEDIUM** | **Host methods kept (1.4 Method 13, 2.4 Method A)** |
| **NCC tool table empty on startup** | **HIGH (if Task 2.3 wrong)** | **HIGH** | **Initialize helper BEFORE loop (line 466)** |
| Form signals fail after cleanup | Medium | High | **DO NOT remove form_to_storage/storage_to_form** |
| Duplicate ncc_tools = {} | Low | Low | **Check line 69 before adding** |

---

## Open Questions (ALL RESOLVED)

1. ~~**Paint column 4 combo:** Does Paint actually use column 4 for a combo widget?~~ 
   - **RESOLVED:** No, only column 2 has combo (verified line 856). Changed config to `[2]`.

2. ~~**NCC sender() pattern:** Confirm `self.sender()` works with helper's duck-typed approach.~~
   - **RESOLVED:** Helper uses duck typing (`hasattr(widget, 'currentText')`), safe for PyQt6 sender().

3. ~~**NCC helper init placement:** Where exactly should helper be initialized in set_tool_ui()?~~
   - **RESOLVED:** BEFORE `for tool_dia in dias:` loop (line 466), NOT after (line 469).

4. ~~**Duplicate ncc_tools in __init__:** Does it already exist?~~
   - **RESOLVED:** Yes, line 69. Only add `tool_table_helper` attribute.

5. ~~**FormStorageParams import:** Is it used by host?~~
   - **RESOLVED:** No, only used internally by ToolManager. Safe to omit.

---

## Changes from v4 to v5

| Section | Change | Reason |
|---------|--------|--------|
| Task 1.1, 2.1 | Removed `FormStorageParams` from imports | Not used by host directly |
| Task 2.2 | Removed `self.ncc_tools = {}` from additions | Already exists (line 69) |
| Task 2.3 | **CRITICAL:** Moved init to BEFORE loop (line 466) | Prevents empty tool table on startup |
| Task 1.4, 2.4 | Clarified Methods 13-15 / A-C as "KEEP HOST LOGIC" | Not delegated — host-specific |
| Phase 3.2 | Added verification for tool table loading | Catch Task 2.3 placement errors |
| Risks | Added NCC empty table risk | High impact if Task 2.3 wrong |
| Open Questions | Added #3-5, all marked resolved | Based on jcode verification |

---

**Plan complete. Ready for execution via superpowers:executing-plans.**

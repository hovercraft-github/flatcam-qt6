# ToolPaint & ToolNCC Shared Code — Implementation Plan v3

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
| Combo columns | `[2, 4]` | `[2]` |
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
    FormStorageParams,
    DeleteToolsParams,
)
```

---

### Task 1.2: Add helper attribute (after line 87)

**File:** `appPlugins/ToolPaint/Paint.py`

**Find** (around line 87):
```python
self.paint_tools = {}
```

**Add after:**
```python
self.tool_table_helper: Optional[ToolTableHelper] = None
```

---

### Task 1.3: Initialize helper in set_tool_ui() (around line 485)

**File:** `appPlugins/ToolPaint/Paint.py`

**Find** (after diameters are loaded, before `for dia in diameters:` loop):

**Add:**
```python
# Initialize ToolTableHelper with Paint-specific config
config = ToolTableConfig(
    log_prefix="ToolPaint",
    tool_target=_('Paint'),
    tool_key_prefix='tools_paint_',
    db_source='paint',
    combo_columns=[2, 4],  # Paint has combos in columns 2 and 4
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

**Replace with:**
```python
def on_toggle_all_rows(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_toggle_all_rows()
```

#### Method 2: `on_row_selection_change` (line 610)

**Replace with:**
```python
def on_row_selection_change(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_row_selection_change()
```

#### Method 3: `update_ui` (line 643)

**Replace with:**
```python
def update_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.update_ui()
```

#### Method 4: `on_apply_param_to_all_clicked` (line 722)

**Replace with:**
```python
def on_apply_param_to_all_clicked(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_apply_param_to_all_clicked()
```

#### Method 5: `on_tool_default_add` (line 1052)

**Replace with:**
```python
def on_tool_default_add(self, dia=None, muted=None):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_default_add(dia=dia, muted=muted)
```

#### Method 6: `on_tool_add` (line 899)

**Replace with:**
```python
def on_tool_add(self, custom_dia=None):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_add(custom_dia=custom_dia)
```

#### Method 7: `on_tool_edit` (line 1099)

**Replace with:**
```python
def on_tool_edit(self, item):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_tool_edit(item)
```

#### Method 8: `on_tool_delete` (line 1139)

**Replace with:**
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

**Replace with:**
```python
def on_tooltable_cell_widget_change(self):
    """Delegate to ToolTableHelper - uses sender() pattern."""
    if self.tool_table_helper:
        widget = self.sender()
        self.tool_table_helper.on_tooltable_cell_widget_change(widget)
```

#### Method 10: `on_order_changed` (line 780)

**Replace with:**
```python
def on_order_changed(self, order):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.on_order_changed(order)
```

#### Method 11: `rebuild_ui` (line 784)

**Replace with:**
```python
def rebuild_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.rebuild_ui()
```

#### Method 12: `build_ui` (line 804)

**Replace with:**
```python
def build_ui(self):
    """Delegate to ToolTableHelper."""
    if self.tool_table_helper:
        self.tool_table_helper.build_ui()
```

---

### Task 1.5: Update ui_connect() / ui_disconnect()

#### ui_connect() (line 1572)

**Replace with:**
```python
def ui_connect(self):
    """Connect signals via ToolTableHelper + host-specific."""
    if self.tool_table_helper:
        self.tool_table_helper.connect_table_signals()
        self.tool_table_helper.connect_form_signals()
    
    # Host-specific signals (Paint only)
    self.ui.rest_cb.stateChanged.connect(self.ui.on_rest_machining_check)
    self.ui.paint_order_combo.currentIndexChanged.connect(self.on_order_changed)
```

#### ui_disconnect() (line 1626)

**Replace with:**
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
    FormStorageParams,
    DeleteToolsParams,
)
```

---

### Task 2.2: Add helper attribute (after line ~87)

**File:** `appPlugins/ToolNCC/Ncc.py`

**Add:**
```python
self.ncc_tools = {}
self.tool_table_helper: Optional[ToolTableHelper] = None
```

---

### Task 2.3: Initialize helper in set_tool_ui() (around line 470)

**File:** `appPlugins/ToolNCC/Ncc.py`

**Add:**
```python
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
```

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

---

### Task 2.5: Update ui_connect() / ui_disconnect()

#### ui_connect() (line 935)

**Replace with:**
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

**Replace with:**
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

### Task 3.2: Runtime verification

1. Launch FlatCAM from worktree
2. Open ToolPaint tab
3. Add tools via "Add from DB" and "Default Add"
4. Test table operations: select/deselect, toggle, edit, delete, apply-to-all, order change
5. Generate paint job
6. Repeat for ToolNCC

---

## Phase 4: Cleanup (Optional)

After verification, remove unused code:
- `storage_to_form()` methods in both files
- `form_to_storage()` methods in both files
- Private helpers now in ToolTableHelper

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Signal connection issues | Low | High | Test ui_connect/disconnect thoroughly |
| PaintGen dict access breaks | Low | High | ToolEntry provides dict-like `__getitem__` |
| NCC combo columns differ | Medium | Medium | Verified via code inspection - NCC uses `[2]` only |
| Offset handling differs | Medium | Medium | `store_offset=False` for NCC, extra_attrs skipped |

---

## Open Questions

1. **Paint column 4 combo:** Does Paint actually use column 4 for a combo widget? Verify in `build_ui()`.

2. **NCC sender() pattern:** Confirm `self.sender()` works with helper's duck-typed approach.

---

**Plan complete.** Ready for execution via superpowers:executing-plans.

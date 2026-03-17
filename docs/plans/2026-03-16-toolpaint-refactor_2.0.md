Corrected Implementation Plan: ToolShared Refactor (Phase 1 - Paint.py)
Review Status: ✅ All critical bugs from Opus plan fixed  
Workflow: Worktree-based development (no commits during implementation)  
Changes from Opus Plan:
1. Fixed build_ui() — calls self.host.ui_connect() instead of importing non-existent module functions
2. Added reorder_tools() to ToolManager (was missing)
3. Added on_tooltable_cell_widget_change() to shared methods (22 lines extracted)
4. Documented UI connection differences — hosts keep their own ui_connect/ui_disconnect
5. Added PaintGen compatibility verification task
6. Fixed test directory structure (tests/plugins/toolshared/)
7. Added explicit dict-like access tests for ToolEntry
8. Removed all Git commit commands — worktree workflow
---
# ToolShared Refactor — Phase 1 (Paint.py) Implementation Plan
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
**Goal:** Extract ~800+ lines of duplicated tool table logic from Paint.py into shared composition-based infrastructure using dataclasses for type safety and parameter objects.
**Architecture:** Composition pattern — `ToolTableHelper` instance injected into ToolPaint, holding ToolManager and operating on ToolEntry dataclasses. Host classes keep `ui_connect`/`ui_disconnect` (differ between Paint/NCC).
**Tech Stack:** Python 3.10+, dataclasses, PyQt6, existing FlatCAM infrastructure.
**Workflow:** Worktree-based development. All changes stay in worktree until Phase 1 complete, then reviewed and merged.
---
## Architecture Overview
appPlugins/ToolShared/
├── init.py              # Updated exports
├── types.py                 # NEW: Dataclasses (ToolEntry, param objects)
├── ToolManager.py           # REWRITE: Uses ToolEntry, type hints
├── ToolTableHelper.py       # NEW: Composition class (replaces mixin idea)
└── BaseGenerator.py         # UNCHANGED
appPlugins/ToolPaint/
├── Paint.py                 # MODIFY: Uses helper instance, deletes ~20 methods
├── PaintGen.py              # UNCHANGED (Phase 1) — verify compatibility
├── PaintUI.py               # UNCHANGED
└── init.py              # UNCHANGED
appPlugins/ToolNCC/          # UNCHANGED (Phase 2)
### Key Design Decisions
| Decision | Rationale |
|----------|-----------|
| **No Mixins** | Composition via `ToolTableHelper` instance |
| **Dataclasses** | `ToolEntry`, `ToolUIParams`, `ToolTableConfig` for type safety |
| **Host ui_connect** | Paint/NCC have different widgets — keep separate |
| **Dict-like ToolEntry** | Backward compat with PaintGen.py `tool['data']` access |
| **Reference preservation** | `clear()/update()` pattern in `rebuild_ui` |
---
## Phase 1 Tasks
### Task 1: Create Dataclasses Module
**Files:**
- Create: `appPlugins/ToolShared/types.py`
- Test: `tests/plugins/toolshared/test_types.py`
**Step 1: Write types.py**
```python
"""Dataclasses for ToolShared module."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal
from copy import deepcopy
ToolType = Literal["Iso", "Rough"]
ToolShape = Literal["V", "C1", "C2", "B", "U"]
OffsetMode = Literal["Off", "On", "Auto"]
PaintOrder = Literal["Default", "Forward", "Reverse"]
@dataclass
class ToolEntry:
    """
    Single tool entry with type-safe fields.
    
    Replaces dict pattern: {'tooldia': float, 'data': dict, 'solid_geometry': list, ...}
    
    Backward Compatibility: Provides dict-like access via __getitem__, __setitem__,
    get(), keys(), etc. so existing code like tool['tooldia'] continues working.
    """
    tooldia: float
    data: Dict[str, Any] = field(default_factory=dict)
    solid_geometry: List[Any] = field(default_factory=list)
    type: ToolType = "Rough"
    tool_type: ToolShape = "C1"
    offset: Optional[str] = None
    offset_value: Optional[float] = None
    
    def __getitem__(self, key: str) -> Any:
        if key == "tooldia":
            return self.tooldia
        elif key == "data":
            return self.data
        elif key == "solid_geometry":
            return self.solid_geometry
        elif key == "type":
            return self.type
        elif key == "tool_type":
            return self.tool_type
        elif key == "offset":
            return self.offset
        elif key == "offset_value":
            return self.offset_value
        elif key in self.data:
            return self.data[key]
        raise KeyError(f"ToolEntry has no key: {key}")
    
    def __setitem__(self, key: str, value: Any) -> None:
        if key == "tooldia":
            self.tooldia = value
        elif key == "data":
            self.data = value
        elif key == "solid_geometry":
            self.solid_geometry = value
        elif key == "type":
            self.type = value
        elif key == "tool_type":
            self.tool_type = value
        elif key == "offset":
            self.offset = value
        elif key == "offset_value":
            self.offset_value = value
        elif key in self.data:
            self.data[key] = value
        else:
            self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default
    
    def update(self, other: Dict[str, Any]) -> None:
        for key, value in other.items():
            self[key] = value
    
    def keys(self) -> List[str]:
        """Note: offset/offset_value only included when non-None."""
        base_keys = ["tooldia", "data", "solid_geometry", "type", "tool_type"]
        if self.offset is not None:
            base_keys.append("offset")
        if self.offset_value is not None:
            base_keys.append("offset_value")
        return base_keys + list(self.data.keys())
    
    def values(self) -> List[Any]:
        return [self[k] for k in self.keys()]
    
    def items(self) -> List[tuple]:
        return [(k, self[k]) for k in self.keys()]
    
    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict (for serialization)."""
        result = {
            "tooldia": self.tooldia,
            "data": deepcopy(self.data),
            "solid_geometry": deepcopy(self.solid_geometry),
            "type": self.type,
            "tool_type": self.tool_type,
        }
        if self.offset is not None:
            result["offset"] = self.offset
        if self.offset_value is not None:
            result["offset_value"] = self.offset_value
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ToolEntry:
        """Create from dict (handles missing optional fields)."""
        return cls(
            tooldia=d.get("tooldia", 0.0),
            data=d.get("data", {}),
            solid_geometry=d.get("solid_geometry", []),
            type=d.get("type", "Rough"),
            tool_type=d.get("tool_type", "C1"),
            offset=d.get("offset"),
            offset_value=d.get("offset_value"),
        )
@dataclass
class ToolUIParams:
    """Parameters for UI form operations."""
    tooluids: List[int]
    option_changed: str
    new_value: Any
    source_uid: Optional[int] = None
@dataclass
class ToolTableConfig:
    """Configuration for tool table rendering."""
    decimals: int
    units: str
    order: PaintOrder
    tool_type_options: List[str]
    show_columns: List[str] = field(default_factory=lambda: ["id", "diameter", "type", "uid"])
@dataclass
class RebuildUIParams:
    """Parameters for rebuild_ui operation."""
    current_uid_list: List[int]
@dataclass
class BuildUIParams:
    """Parameters for build_ui operation."""
    config: ToolTableConfig
    tools: Dict[int, ToolEntry]
@dataclass  
class DeleteToolsParams:
    """Parameters for tool deletion."""
    rows_to_delete: Optional[List[int]] = None
    all_tools: bool = False
Step 2: Write test_types.py
"""Tests for ToolShared types."""
import pytest
from copy import deepcopy
from appPlugins.ToolShared.types import ToolEntry, ToolUIParams, ToolTableConfig
class TestToolEntry:
    def test_creation_with_defaults(self):
        entry = ToolEntry(tooldia=3.0)
        assert entry.tooldia == 3.0
        assert entry.data == {}
        assert entry.solid_geometry == []
        assert entry.type == "Rough"
        assert entry.tool_type == "C1"
        assert entry.offset is None
        assert entry.offset_value is None
    def test_dict_getitem(self):
        entry = ToolEntry(tooldia=3.0, type="Iso")
        assert entry["tooldia"] == 3.0
        assert entry["type"] == "Iso"
    def test_dict_setitem(self):
        entry = ToolEntry(tooldia=3.0)
        entry["tooldia"] = 5.0
        entry["type"] = "Iso"
        assert entry.tooldia == 5.0
        assert entry.type == "Iso"
    def test_dict_get(self):
        entry = ToolEntry(tooldia=3.0)
        assert entry.get("tooldia") == 3.0
        assert entry.get("missing", "default") == "default"
    def test_dict_update(self):
        entry = ToolEntry(tooldia=3.0)
        entry.update({"type": "Iso", "custom_key": "value"})
        assert entry.type == "Iso"
        assert entry["custom_key"] == "value"
    def test_keys_values_items(self):
        entry = ToolEntry(tooldia=3.0, offset="On")
        assert "tooldia" in entry.keys()
        assert "offset" in entry.keys()
        assert 3.0 in entry.values()
        assert ("tooldia", 3.0) in entry.items()
    def test_contains(self):
        entry = ToolEntry(tooldia=3.0)
        assert "tooldia" in entry
        assert "missing" not in entry
    def test_to_dict_from_dict_roundtrip(self):
        original = ToolEntry(
            tooldia=3.0,
            data={"feed": 100},
            type="Iso",
            tool_type="V",
            offset="On",
            offset_value=0.5
        )
        as_dict = original.to_dict()
        restored = ToolEntry.from_dict(as_dict)
        assert restored.tooldia == original.tooldia
        assert restored.data == original.data
        assert restored.type == original.type
        assert restored.offset == original.offset
    def test_optional_fields_not_in_keys_when_none(self):
        entry = ToolEntry(tooldia=3.0)
        assert "offset" not in entry.keys()
        assert "offset_value" not in entry.keys()
    def test_data_deepcopy_in_to_dict(self):
        entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        as_dict = entry.to_dict()
        as_dict["data"]["feed"] = 999
        assert entry.data["feed"] == 100  # Original unchanged
    def test_nested_dict_access(self):
        """Verify tool['data']['name'] = x pattern works (PaintGen.py compatibility)."""
        entry = ToolEntry(tooldia=3.0, data={"name": "test"})
        entry["data"]["name"] = "updated"
        assert entry.data["name"] == "updated"
        assert entry["data"]["name"] == "updated"
Step 3: Run tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_types.py -v
Expected: All tests pass.
---
Task 2: Rewrite ToolManager with ToolEntry
Files:
- Modify: appPlugins/ToolShared/ToolManager.py:1-148
- Test: tests/plugins/toolshared/test_tool_manager.py
Step 1: Rewrite ToolManager.py
"""ToolManager — Manages ToolEntry instances."""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy
from appPlugins.ToolShared.types import ToolEntry
class ToolManager:
    """
    Manages a tools dict: {int(uid): ToolEntry}
    
    THREAD SAFETY: Main-thread-only. No locks.
    """
    def __init__(
        self,
        app: Any,
        tools_dict: Dict[int, ToolEntry],
        form_fields: Dict[str, Any],
        name2option: Dict[str, str],
        default_data: dict,
        decimals: int,
    ):
        self.app = app
        self.tools = tools_dict          # Reference to parent's paint_tools/ncc_tools
        self.form_fields = form_fields
        self.name2option = name2option
        self.default_data = default_data
        self.decimals = decimals
    def _fmt_dia(self, diameter: float) -> float:
        """Format diameter to configured decimals."""
        return self.app.dec_format(diameter, self.decimals)
    def _next_uid(self) -> int:
        """Get next available tool UID."""
        return max(self.tools.keys(), default=0) + 1
    def tool_exists(self, diameter: float) -> bool:
        """Check if tool with same diameter exists."""
        truncated = self._fmt_dia(diameter)
        return any(
            self._fmt_dia(t.tooldia) == truncated
            for t in self.tools.values()
        )
    def add_tool(
        self,
        diameter: float,
        tool_data: Optional[dict] = None,
        solid_geometry: Optional[list] = None,
        extra_attrs: Optional[dict] = None,
    ) -> Optional[int]:
        """
        Add tool. Returns uid or None if duplicate.
        
        Args:
            diameter: Tool diameter
            tool_data: Optional data dict (uses default_data if None)
            solid_geometry: Optional geometry list
            extra_attrs: For DB-path fields like offset/offset_value
        
        Returns:
            Tool UID if added, None if duplicate
        """
        truncated = self._fmt_dia(diameter)
        if self.tool_exists(diameter):
            return None
        uid = self._next_uid()
        entry = ToolEntry(
            tooldia=truncated,
            data=tool_data if tool_data is not None else deepcopy(self.default_data),
            solid_geometry=solid_geometry if solid_geometry is not None else [],
        )
        if extra_attrs:
            entry.update(extra_attrs)
        self.tools[uid] = entry
        return uid
    def delete_tools(self, uids: List[int]) -> int:
        """Delete tools by UID list. Returns count of deleted tools."""
        count = 0
        for uid in uids:
            if uid in self.tools:
                del self.tools[uid]
                count += 1
        return count
    def edit_diameter(self, uid: int, new_dia: float) -> Tuple[bool, str]:
        """
        Edit tool diameter.
        
        Returns:
            (success, message) tuple
        """
        if uid not in self.tools:
            return False, "Tool not found"
        truncated = self._fmt_dia(new_dia)
        for other_uid, t in self.tools.items():
            if other_uid != uid and self._fmt_dia(t.tooldia) == truncated:
                return False, "Duplicate diameter"
        self.tools[uid].tooldia = truncated
        return True, "OK"
    def reorder_tools(self, uid_order: List[int]) -> None:
        """
        Reorder tools according to UID order list.
        Preserves dict reference (uses clear/update).
        
        Args:
            uid_order: List of old UIDs in new order (new UIDs assigned 1,2,3...)
        """
        new_tools = {}
        for new_uid, old_uid in enumerate(uid_order, start=1):
            new_tools[new_uid] = deepcopy(self.tools[old_uid])
        self.tools.clear()
        self.tools.update(new_tools)
    def storage_to_form(self, dict_storage: dict) -> None:
        """
        Populate UI form fields from a data dict.
        
        Note: Uses 'key in dict_storage' rather than 'value is not None' to allow
        explicit None values to be stored. If a key is missing, it's skipped.
        """
        for key in self.form_fields:
            if key in dict_storage:
                try:
                    self.form_fields[key].set_value(dict_storage[key])
                except Exception as e:
                    self.app.log.error(f"storage_to_form failed for {key}: {e}")
    def form_to_storage(
        self,
        tooluids: List[int],
        option_changed: str,
        new_value: Any,
    ) -> None:
        """
        Save one changed UI value to tool storage for selected tools.
        Checks both tool-level and tool['data']-level keys.
        """
        for uid in tooluids:
            tool = self.tools.get(uid)
            if tool is None:
                continue
            # Check tool-level
            if option_changed in tool:
                tool[option_changed] = new_value
            # Check data-level
            if option_changed in tool.get('data', {}):
                tool['data'][option_changed] = new_value
    def apply_params_to_all(self, source_uid: int) -> bool:
        """Copy data dict from source tool to all others via deepcopy."""
        if source_uid not in self.tools:
            return False
        source_data = self.tools[source_uid].get('data')
        if source_data is None:
            return False
        for uid, tool in self.tools.items():
            if uid != source_uid:
                tool.data = deepcopy(source_data)
        return True
    def get_tool(self, uid: int) -> Optional[ToolEntry]:
        """Get tool entry by UID."""
        return self.tools.get(uid)
    def get_diameters(self) -> List[float]:
        """Get list of all tool diameters."""
        return [t.tooldia for t in self.tools.values()]
    def to_entries_dict(self) -> Dict[int, dict]:
        """Convert all entries to plain dicts (for backward compat)."""
        return {uid: entry.to_dict() for uid, entry in self.tools.items()}
Step 2: Update existing test_tool_manager.py
Modify existing tests to work with ToolEntry (dict-like access ensures compatibility).
Add new test for reorder_tools:
def test_reorder_tools_preserves_reference():
    """Test reorder_tools preserves dict reference and reassigns UIDs."""
    app = MockApp()
    tools = {
        1: {'tooldia': 3.0, 'data': {}},
        2: {'tooldia': 5.0, 'data': {}},
    }
    form_fields = {}
    name2option = {}
    default_data = {}
    decimals = 4
    
    mgr = ToolManager(app, tools, form_fields, name2option, default_data, decimals)
    
    original_id = id(mgr.tools)
    mgr.reorder_tools([2, 1])  # Reverse order
    
    assert id(mgr.tools) == original_id  # Same dict object
    assert list(mgr.tools.keys()) == [1, 2]  # New UIDs
    assert mgr.tools[1]['tooldia'] == 5.0  # First is old UID 2
    assert mgr.tools[2]['tooldia'] == 3.0  # Second is old UID 1
Step 3: Run tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_tool_manager.py -v
Expected: All tests pass.
---
Task 3: Create ToolTableHelper (Composition Class)
Files:
- Create: appPlugins/ToolShared/ToolTableHelper.py
- Test: tests/plugins/toolshared/test_tool_table_helper.py
Step 1: Write ToolTableHelper.py
"""ToolTableHelper — Composition class for shared tool table operations."""
from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from copy import deepcopy
from PyQt6 import QtWidgets, QtCore
from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolUIParams,
    ToolTableConfig,
    RebuildUIParams,
    BuildUIParams,
    DeleteToolsParams,
    PaintOrder,
)
from appPlugins.ToolShared.ToolManager import ToolManager
if TYPE_CHECKING:
    from appPlugins.ToolPaint.Paint import ToolPaint
class ToolTableHelper:
    """
    Helper class containing shared tool table operations.
    
    Uses composition pattern — instantiated by host class (ToolPaint/ToolNcc)
    and operates on the host's tools dict via ToolManager.
    
    Host class must provide:
    - self.app, self.ui, self.decimals, self.default_data, self.form_fields
    - self.name2option, self.tool_type_item_options
    - self.paint_tools or self.ncc_tools (dict passed to ToolManager)
    - self.ui_connect(), self.ui_disconnect() — host-specific implementations
    - self._get_generate_button() — returns generate button
    - self._get_order_combo() — returns order combo box
    - self._get_log_prefix() — returns "ToolPaint" or "ToolNcc"
    """
    def __init__(self, host: Any, tools_dict: Dict[int, ToolEntry]):
        self.host = host
        self.app = host.app
        self.ui = host.ui
        self.decimals = host.decimals
        self.default_data = host.default_data
        self.form_fields = host.form_fields
        self.name2option = host.name2option
        self.tool_type_item_options = host.tool_type_item_options
        
        # ToolManager operates on the tools_dict reference
        self.tool_manager = ToolManager(
            app=self.app,
            tools_dict=tools_dict,
            form_fields=self.form_fields,
            name2option=self.name2option,
            default_data=self.default_data,
            decimals=self.decimals,
        )
        
        self.tools_dict = tools_dict  # Reference for direct access
    def _get_generate_button(self) -> Any:
        """Delegate to host."""
        return self.host._get_generate_button()
    def _get_order_combo(self) -> Any:
        """Delegate to host."""
        return self.host._get_order_combo()
    def _get_log_prefix(self) -> str:
        """Delegate to host."""
        return self.host._get_log_prefix()
    # ─────────────────────────────────────────────────────────────────────
    # Selection Handlers
    # ─────────────────────────────────────────────────────────────────────
    def on_toggle_all_rows(self) -> None:
        """Toggle selection of all rows in tools table."""
        sel_model = self.ui.tools_table.selectionModel()
        sel_indexes = sel_model.selectedIndexes()
        
        sel_rows = {idx.row() for idx in sel_indexes}
        
        if len(sel_rows) == self.ui.tools_table.rowCount():
            self.ui.tools_table.clearSelection()
            self.ui.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>" 
                % (_('Parameters for'), _("No Tool Selected"))
            )
        else:
            self.ui.tools_table.selectAll()
            self.ui.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>" 
                % (_('Parameters for'), _("Multiple Tools"))
            )
    def on_row_selection_change(self) -> None:
        """Handle row selection change — update UI if single row selected."""
        sel_model = self.ui.tools_table.selectionModel()
        sel_indexes = sel_model.selectedIndexes()
        sel_rows = {idx.row() for idx in sel_indexes}
        
        if len(sel_rows) == 1:
            self.update_ui()
    # ─────────────────────────────────────────────────────────────────────
    # UI Update
    # ─────────────────────────────────────────────────────────────────────
    def update_ui(self) -> None:
        """Update UI form based on selected tool(s)."""
        self.host.blockSignals(True)
        
        table_items = self.ui.tools_table.selectedItems()
        sel_rows = {it.row() for it in table_items} if table_items else set()
        
        generate_btn = self._get_generate_button()
        
        if not sel_rows:
            generate_btn.setDisabled(True)
            self.ui.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>" 
                % (_('Parameters for'), _("No Tool Selected"))
            )
            self.host.blockSignals(False)
            return
        
        generate_btn.setDisabled(False)
        
        for current_row in sel_rows:
            try:
                item = self.ui.tools_table.item(current_row, 3)
                if item is None:
                    return
                tooluid = int(item.text())
            except Exception as e:
                self.app.log.error(f"{self._get_log_prefix()}: Tool missing. {e}")
                return
            
            if len(sel_rows) == 1:
                cr = self.ui.tools_table.item(current_row, 0).text()
                self.ui.tool_data_label.setText(
                    "<b>%s: <font color='#0000FF'>%s %s</font></b>" 
                    % (_('Parameters for'), _("Tool"), cr)
                )
                
                try:
                    tool = self.tools_dict.get(tooluid)
                    if tool:
                        self.tool_manager.storage_to_form(tool.data)
                except Exception as e:
                    self.app.log.error(f"{self._get_log_prefix()}: update_ui failed: {e}")
            else:
                self.ui.tool_data_label.setText(
                    "<b>%s: <font color='#0000FF'>%s</font></b>" 
                    % (_('Parameters for'), _("Multiple Tools"))
                )
        
        self.host.blockSignals(False)
    # ─────────────────────────────────────────────────────────────────────
    # Form ↔ Storage
    # ─────────────────────────────────────────────────────────────────────
    def on_apply_param_to_all_clicked(self) -> None:
        """Apply current tool's parameters to all tools."""
        if self.ui.tools_table.rowCount() == 0:
            self.app.log.debug(f"{self._get_log_prefix()}: No tools in table, aborting.")
            return
        
        self.host.blockSignals(True)
        
        row = self.ui.tools_table.currentRow()
        if row < 0:
            row = 0
        tooluid_item = int(self.ui.tools_table.item(row, 3).text())
        
        self.tool_manager.apply_params_to_all(tooluid_item)
        
        self.app.inform.emit('[success] %s' % _("Current Tool parameters were applied to all tools."))
        self.host.blockSignals(False)
    # ─────────────────────────────────────────────────────────────────────
    # Tool CRUD
    # ─────────────────────────────────────────────────────────────────────
    def on_tool_default_add(self, dia: Optional[float] = None, muted: Optional[bool] = None) -> None:
        """Add default tool with given diameter."""
        self.host.blockSignals(True)
        
        tool_dia = dia if dia else self.ui.new_tooldia_entry.get_value()
        
        if tool_dia is None or tool_dia == 0:
            self.build_ui()
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Please enter a tool diameter with non-zero value.")
            )
            self.host.blockSignals(False)
            return
        
        tooluid = self.tool_manager.add_tool(
            diameter=tool_dia,
            tool_data=deepcopy(self.default_data),
            solid_geometry=[],
        )
        
        if tooluid is None:
            if muted is None:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s %s' % (_("Cancelled."), _("Tool already in Tool Table."))
                )
            self.host.blockSignals(False)
            return
        
        self.host.tooluid = tooluid
        self.host.blockSignals(False)
        self.build_ui()
        
        # Select the tool just added
        for row in range(self.ui.tools_table.rowCount()):
            if int(self.ui.tools_table.item(row, 3).text()) == tooluid:
                self.ui.tools_table.selectRow(row)
                break
        
        self.update_ui()
        
        if muted is None:
            self.app.inform.emit('[success] %s' % _("Default tool added to Tool Table."))
    def on_tool_delete(self, rows_to_delete: Optional[List[int]] = None, all_tools: bool = False) -> None:
        """Delete tools from table."""
        self.host.blockSignals(True)
        deleted_tools_list = []
        
        if all_tools:
            self.tools_dict.clear()
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        if rows_to_delete:
            try:
                for row in rows_to_delete:
                    tooluid_del = int(self.ui.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)
            except TypeError:
                deleted_tools_list.append(rows_to_delete)
            
            for t in deleted_tools_list:
                self.tools_dict.pop(t, None)
            
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        try:
            if self.ui.tools_table.selectedItems():
                for row_sel in self.ui.tools_table.selectedItems():
                    row = row_sel.row()
                    if row < 0:
                        continue
                    tooluid_del = int(self.ui.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)
                
                for t in deleted_tools_list:
                    self.tools_dict.pop(t, None)
        except AttributeError:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Delete failed. Select a tool to delete."))
            self.host.blockSignals(False)
            return
        except Exception as e:
            self.app.log.error(str(e))
        
        self.app.inform.emit('[success] %s' % _("Tools deleted from Tool Table."))
        self.host.blockSignals(False)
        self.build_ui()
    def on_tool_edit(self, item: Any) -> None:
        """Handle tool diameter edit."""
        self.host.blockSignals(True)
        
        edited_row = item.row()
        editeduid = int(self.ui.tools_table.item(edited_row, 3).text())
        
        try:
            new_tool_dia = float(self.ui.tools_table.item(edited_row, 1).text())
        except ValueError:
            try:
                new_tool_dia = float(self.ui.tools_table.item(edited_row, 1).text().replace(',', '.'))
            except ValueError:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered."))
                return
        
        tool_dias = [
            float('%.*f' % (self.decimals, v.tooldia)) 
            for v in self.tools_dict.values()
        ]
        
        if new_tool_dia not in tool_dias:
            self.tools_dict[editeduid].tooldia = new_tool_dia
            self.app.inform.emit('[success] %s' % _("Tool from Tool Table was edited."))
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        # Restore old value
        for k, v in self.tools_dict.items():
            if k == editeduid:
                old_tool_dia = v.tooldia
                restore_dia_item = self.ui.tools_table.item(edited_row, 1)
                restore_dia_item.setText(str(old_tool_dia))
                break
        
        self.app.inform.emit(
            '[WARNING_NOTCL] %s' % _("Cancelled. New diameter value is already in the Tool Table.")
        )
        self.host.blockSignals(False)
        self.build_ui()
    # ─────────────────────────────────────────────────────────────────────
    # Cell Widget Change (SHARED — Paint/NCC identical)
    # ─────────────────────────────────────────────────────────────────────
    def on_tooltable_cell_widget_change(self) -> None:
        """Handle tool type combo change in table."""
        cw = self.sender()
        
        assert isinstance(cw, QtWidgets.QComboBox), \
            "Expected a QtWidgets.QComboBox, got %s" % type(cw).__name__
        
        cw_index = self.ui.tools_table.indexAt(cw.pos())
        cw_row = cw_index.row()
        cw_col = cw_index.column()
        
        current_uid = int(self.ui.tools_table.item(cw_row, 3).text())
        
        # Column 2 = tool type combo
        if cw_col == 2:
            tt = cw.currentText()
            typ = 'Iso' if tt == 'V' else 'Rough'
            
            self.tools_dict[current_uid].update({
                'type': typ,
                'tool_type': tt,
            })
    # ─────────────────────────────────────────────────────────────────────
    # Table Rebuild
    # ─────────────────────────────────────────────────────────────────────
    def on_order_changed(self, order: int) -> None:
        """Handle order combo change."""
        if order != 0:  # Default order
            self.build_ui()
    def rebuild_ui(self) -> None:
        """Rebuild UI with new tool order."""
        current_uid_list = [
            int(self.ui.tools_table.item(row, 3).text())
            for row in range(self.ui.tools_table.rowCount())
        ]
        
        # Use ToolManager.reorder_tools() for proper handling
        self.tool_manager.reorder_tools(current_uid_list)
        
        QtCore.QTimer.singleShot(20, self.build_ui)
    def build_ui(self) -> None:
        """Build/rebuild the tools table."""
        # Call host-specific ui_disconnect (NOT shared)
        self.host.ui_disconnect()
        
        units = self.app.app_units.upper()
        order_val = self._get_order_combo().get_value()
        order_map = {0: "Default", 1: "Forward", 2: "Reverse"}
        order = order_map.get(order_val, "Default")
        
        sorted_tools = sorted(
            [t.tooldia for t in self.tools_dict.values()],
            reverse=(order == "Reverse")
        ) if order != "Default" else [t.tooldia for t in self.tools_dict.values()]
        
        n = len(sorted_tools)
        self.ui.tools_table.setRowCount(n)
        
        selected_enabled_flag = (
            QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        enabled_flag = QtCore.Qt.ItemFlag.ItemIsEnabled
        selected_enabled_editable_flag = (
            QtCore.Qt.ItemFlag.ItemIsEditable
            | QtCore.Qt.ItemFlag.ItemIsSelectable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        
        tool_id = 0
        for tool_sorted in sorted_tools:
            for tooluid, tool in self.tools_dict.items():
                if float('%.*f' % (self.decimals, tool.tooldia)) == tool_sorted:
                    tool_id += 1
                    row_no = tool_id - 1
                    
                    # ID column
                    id_item = QtWidgets.QTableWidgetItem(str(tool_id))
                    id_item.setFlags(selected_enabled_flag)
                    self.ui.tools_table.setItem(row_no, 0, id_item)
                    
                    # Diameter column
                    dia = QtWidgets.QTableWidgetItem('%.*f' % (self.decimals, tool.tooldia))
                    dia.setFlags(enabled_flag)
                    self.ui.tools_table.setItem(row_no, 1, dia)
                    
                    # Tool type combo
                    tool_type_item = QtWidgets.QComboBox()
                    for opt in self.tool_type_item_options:
                        tool_type_item.addItem(opt)
                    idx = int(tool.data.get('tools_mill_tool_shape', 0))
                    tool_type_item.setCurrentIndex(idx)
                    self.ui.tools_table.setCellWidget(row_no, 2, tool_type_item)
                    
                    # UID column (hidden)
                    tool_uid_item = QtWidgets.QTableWidgetItem(str(tooluid))
                    self.ui.tools_table.setItem(row_no, 3, tool_uid_item)
        
        # Make diameter editable
        for row in range(tool_id):
            self.ui.tools_table.item(row, 1).setFlags(selected_enabled_editable_flag)
        
        # Select all by default
        self.ui.tools_table.selectColumn(0)
        self.ui.tools_table.resizeColumnsToContents()
        self.ui.tools_table.resizeRowsToContents()
        
        # Hide vertical header
        self.ui.tools_table.verticalHeader().hide()
        self.ui.tools_table.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        
        # Horizontal header
        horizontal_header = self.ui.tools_table.horizontalHeader()
        horizontal_header.setMinimumSectionSize(10)
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        horizontal_header.resizeSection(0, 20)
        horizontal_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        
        self.ui.tools_table.setMinimumHeight(self.ui.tools_table.getHeight())
        self.ui.tools_table.setMaximumHeight(self.ui.tools_table.getHeight())
        
        # Call host-specific ui_connect (NOT shared — Paint/NCC differ)
        self.host.ui_connect()
Step 2: Write test_tool_table_helper.py
"""Tests for ToolTableHelper."""
import pytest
from unittest.mock import Mock, MagicMock
from PyQt6 import QtWidgets, QtCore
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import ToolEntry
@pytest.fixture
def mock_host():
    host = Mock()
    host.app = Mock()
    host.app.dec_format = lambda val, dec: round(val, dec)
    host.app.log = Mock()
    host.app.inform = Mock()
    host.app.inform.emit = Mock()
    host.app.app_units = "mm"
    
    host.ui = Mock()
    host.ui.tools_table = Mock()
    host.ui.tools_table.rowCount = Mock(return_value=0)
    host.ui.tools_table.selectedItems = Mock(return_value=[])
    host.ui.tool_data_label = Mock()
    host.ui.new_tooldia_entry = Mock()
    host.ui.new_tooldia_entry.get_value = Mock(return_value=3.0)
    host.ui.generate_paint_button = Mock()
    host.ui.paint_order_combo = Mock()
    host.ui.paint_order_combo.get_value = Mock(return_value=0)
    
    host.decimals = 4
    host.default_data = {"feed": 100}
    host.form_fields = {"feed": Mock()}
    host.name2option = {"feed_spin": "feed"}
    host.tool_type_item_options = ["V", "C1", "C2"]
    host.tooluid = 0
    
    host.blockSignals = Mock()
    host.ui_disconnect = Mock()
    host.ui_connect = Mock()
    host._get_generate_button = Mock(return_value=host.ui.generate_paint_button)
    host._get_order_combo = Mock(return_value=host.ui.paint_order_combo)
    host._get_log_prefix = Mock(return_value="ToolPaint")
    
    return host
@pytest.fixture
def helper(mock_host):
    tools_dict = {}
    return ToolTableHelper(host=mock_host, tools_dict=tools_dict)
class TestToolTableHelper:
    def test_on_toggle_all_rows_select(self, helper, mock_host):
        mock_host.ui.tools_table.rowCount = Mock(return_value=5)
        mock_host.ui.tools_table.selectionModel = Mock()
        mock_host.ui.tools_table.selectionModel().selectedIndexes = Mock(return_value=[])
        
        helper.on_toggle_all_rows()
        mock_host.ui.tools_table.selectAll.assert_called_once()
    def test_on_tool_default_add_success(self, helper, mock_host):
        helper.on_tool_default_add(dia=3.0, muted=True)
        assert mock_host.tooluid == 1
        assert 1 in helper.tools_dict
    def test_on_tool_delete_all(self, helper, mock_host):
        helper.tool_manager.add_tool(3.0)
        helper.on_tool_delete(all_tools=True)
        assert len(helper.tools_dict) == 0
    def test_rebuild_ui_calls_reorder_tools(self, helper, mock_host):
        uid1 = helper.tool_manager.add_tool(3.0)
        uid2 = helper.tool_manager.add_tool(5.0)
        mock_host.ui.tools_table.rowCount = Mock(return_value=2)
        mock_host.ui.tools_table.item = Mock(side_effect=lambda r, c: Mock(text=lambda: [uid2, uid1][r]))
        
        original_id = id(helper.tools_dict)
        helper.rebuild_ui()
        assert id(helper.tools_dict) == original_id
Step 3: Run tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_tool_table_helper.py -v
---
Task 4: Migrate Paint.py to Use Helper
Files:
- Modify: appPlugins/ToolPaint/Paint.py:56-1829
Step 1: Update imports
# Add after existing imports
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import ToolEntry
Step 2: Update class and init
class ToolPaint(Gerber, AppTool):
    def __init__(self, app):
        self.app = app
        self.decimals = self.app.decimals
        self.circle_steps = int(self.app.options.get("geometry_circle_steps", 64))
        AppTool.__init__(self, app)
        Geometry.__init__(self, geo_steps_per_circle=self.circle_steps, app=app)
        # ... existing variables ...
        self.paint_tools: Dict[int, ToolEntry] = {}  # Type hint
        self.tooluid = 0
        
        # NEW: ToolTableHelper instance (composition)
        self.tool_table_helper: Optional[ToolTableHelper] = None
        # ... rest of __init__ ...
    def set_tool_ui(self):
        # ... existing code ...
        
        # NEW: Initialize helper after form_fields, name2option are set
        self.tool_table_helper = ToolTableHelper(
            host=self,
            tools_dict=self.paint_tools,
        )
Step 3: Add abstraction methods for helper
# Add after __init__, before other methods
def _get_generate_button(self) -> Any:
    """Return generate button for helper."""
    return self.ui.generate_paint_button
def _get_order_combo(self) -> Any:
    """Return order combo for helper."""
    return self.ui.paint_order_combo
def _get_log_prefix(self) -> str:
    """Return log prefix for helper."""
    return "ToolPaint"
Step 4: Replace method bodies with helper calls
Methods to delegate (delete body, call helper):
def on_toggle_all_rows(self):
    self.tool_table_helper.on_toggle_all_rows()
def on_row_selection_change(self):
    self.tool_table_helper.on_row_selection_change()
def update_ui(self):
    self.tool_table_helper.update_ui()
def on_apply_param_to_all_clicked(self):
    self.tool_table_helper.on_apply_param_to_all_clicked()
def on_tool_default_add(self, dia=None, muted=None):
    self.tool_table_helper.on_tool_default_add(dia=dia, muted=muted)
def on_tool_delete(self, rows_to_delete=None, all_tools=None):
    self.tool_table_helper.on_tool_delete(rows_to_delete=rows_to_delete, all_tools=all_tools)
def on_tool_edit(self, item):
    self.tool_table_helper.on_tool_edit(item)
def on_order_changed(self, order):
    self.tool_table_helper.on_order_changed(order)
def rebuild_ui(self):
    self.tool_table_helper.rebuild_ui()
def build_ui(self):
    self.tool_table_helper.build_ui()
def on_tooltable_cell_widget_change(self):
    self.tool_table_helper.on_tooltable_cell_widget_change()
Step 5: Update storage_to_form and form_to_storage
def storage_to_form(self, dict_storage):
    self.tool_table_helper.tool_manager.storage_to_form(dict_storage)
def form_to_storage(self):
    if self.ui.tools_table.rowCount() == 0:
        return
    
    self.blockSignals(True)
    
    widget_changed = self.sender()
    wdg_objname = widget_changed.objectName()
    option_changed = self.name2option[wdg_objname]
    
    rows = sorted(set(index.row() for index in self.ui.tools_table.selectedIndexes()))
    tooluids = [int(self.ui.tools_table.item(row, 3).text()) for row in rows if row >= 0]
    
    new_value = self.form_fields[option_changed].get_value()
    self.tool_table_helper.tool_manager.form_to_storage(tooluids, option_changed, new_value)
    
    self.blockSignals(False)
---
Task 5: Update init.py Exports
Files:
- Modify: appPlugins/ToolShared/__init__.py
"""ToolShared — Shared tool table infrastructure."""
from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolUIParams,
    ToolTableConfig,
    RebuildUIParams,
    BuildUIParams,
    DeleteToolsParams,
    ToolType,
    ToolShape,
    OffsetMode,
    PaintOrder,
)
from appPlugins.ToolShared.ToolManager import ToolManager
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.BaseGenerator import BaseGenerator
__all__ = [
    "ToolEntry",
    "ToolUIParams",
    "ToolTableConfig",
    "RebuildUIParams",
    "BuildUIParams",
    "DeleteToolsParams",
    "ToolType",
    "ToolShape",
    "OffsetMode",
    "PaintOrder",
    "ToolManager",
    "ToolTableHelper",
    "BaseGenerator",
]
---
Task 6: Verify PaintGen Compatibility
Files:
- Create: tests/plugins/paint/test_paintgen_compatibility.py
Step 1: Write compatibility test
"""Verify PaintGen.py works with ToolEntry dataclass."""
import pytest
from copy import deepcopy
from appPlugins.ToolShared.types import ToolEntry
class TestPaintGenCompatibility:
    """Test patterns used in PaintGen.py work with ToolEntry."""
    
    def test_dict_access_pattern(self):
        """Test: tools_storage[uid]['tooldia']"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        assert tools[1]["tooldia"] == 3.0
    
    def test_nested_data_access(self):
        """Test: tools_storage[uid]['data']['feed']"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        assert tools[1]["data"]["feed"] == 100
        tools[1]["data"]["feed"] = 200
        assert tools[1].data["feed"] == 200
    
    def test_solid_geometry_assignment(self):
        """Test: tools_storage[uid]['solid_geometry'] = list"""
        tools = {1: ToolEntry(tooldia=3.0)}
        tools[1]["solid_geometry"] = ["geo1", "geo2"]
        assert tools[1].solid_geometry == ["geo1", "geo2"]
    
    def test_update_pattern(self):
        """Test: tools_storage[uid].update({...})"""
        tools = {1: ToolEntry(tooldia=3.0)}
        tools[1].update({"type": "Iso", "tool_type": "V"})
        assert tools[1].type == "Iso"
        assert tools[1].tool_type == "V"
    
    def test_get_method(self):
        """Test: tools_storage[uid].get('key', default)"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        assert tools[1].get("tooldia") == 3.0
        assert tools[1].get("missing", "default") == "default"
    
    def test_keys_iteration(self):
        """Test: for key in tools_storage[uid]"""
        tools = {1: ToolEntry(tooldia=3.0, offset="On")}
        keys = list(tools[1].keys())
        assert "tooldia" in keys
        assert "offset" in keys
    
    def test_values_iteration(self):
        """Test: list(tools_storage[uid].values())"""
        tools = {1: ToolEntry(tooldia=3.0)}
        values = tools[1].values()
        assert 3.0 in values
    
    def test_items_iteration(self):
        """Test: for k, v in tools_storage[uid].items()"""
        tools = {1: ToolEntry(tooldia=3.0)}
        items = list(tools[1].items())
        assert ("tooldia", 3.0) in items
    
    def test_contains_check(self):
        """Test: 'key' in tools_storage[uid]"""
        tools = {1: ToolEntry(tooldia=3.0)}
        assert "tooldia" in tools[1]
        assert "missing" not in tools[1]
    
    def test_deepcopy_compatibility(self):
        """Test: deepcopy(tools_storage[uid])"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        copied = deepcopy(tools[1])
        assert copied.tooldia == 3.0
        assert copied.data["feed"] == 100
        copied.data["feed"] = 200
        assert tools[1].data["feed"] == 100  # Original unchanged
    
    def test_to_dict_for_serialization(self):
        """Test: tools_storage[uid].to_dict() for JSON"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        as_dict = tools[1].to_dict()
        assert as_dict["tooldia"] == 3.0
        assert as_dict["data"]["feed"] == 100
Step 2: Run tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/paint/test_paintgen_compatibility.py -v
Expected: All tests pass.
---
Task 7: Run Full Test Suite & Smoke Test
Step 1: Run all new tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/ -v
Step 2: Run existing Paint tests
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/paint/ -v
Step 3: Import check
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -c "
from appPlugins.ToolShared import ToolEntry, ToolManager, ToolTableHelper
from appPlugins.ToolPaint.Paint import ToolPaint
print('All imports OK')
"
Step 4: Manual smoke test
1. Open FlatCAM
2. Open Paint Tool
3. Add/edit/delete/reorder tools
4. Change parameters, click "Apply to All"
5. Run paint operation
---
Summary of Changes
Component	Lines
types.py (NEW)	~250
ToolManager.py (REWRITE)	~180
ToolTableHelper.py (NEW)	~450
Paint.py (MODIFY)	-550 (deleted)
Net	+330
---
Critical Fixes from Opus Plan Review
Issue	Opus Plan
build_ui() imports	from ... import ui_connect (wrong)
Missing reorder_tools()	Not in ToolManager
Missing cell widget handler	Not extracted
UI connection abstraction	Tried to share
Test directory	Unclear
PaintGen compatibility	Assumed
---
Risks
Risk	Likelihood	Impact
Dict-like access breaks	Low	High
Reference lost in rebuild	Low	High
PaintGen.py compatibility	Low	High
getHeight() missing	Medium	Medium
---
## Open Questions
1. **NCC Phase 2 timing** — Start after Paint.py stable, or parallel?
2. **Generator migration** — Move PaintGen/NccGen to shared BaseGenerator?
3. **DB integration** — Keep in Paint.py or move to helper?
---
Index Notes
- Indexed: local/refactor-tool-shared-b8654c11 at 2026-03-16T22:46:39
- Paint.py: 1829 lines, 38 methods
- Ncc.py: 2026 lines, 41 methods
- ~60% duplication identified for Phase 1+2
- Worktree: D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
- .venv: Use worktree's virtual environment for testing
# ToolShared Refactor — Phase 1 (Paint.py) — Complete Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract ~600 lines of duplicated tool-table management code from Paint.py (1829 lines) into shared infrastructure using dataclasses for type safety, with composition pattern (ToolTableHelper holding ToolManager).

**Architecture:** 
- **Composition over inheritance** — `ToolTableHelper` instance injected into ToolPaint, operating on `paint_tools` dict via `ToolManager`
- **Dataclasses throughout** — `ToolEntry` replaces untyped dicts, parameter objects for method signatures
- **Backward compatible** — `ToolEntry` provides dict-like access for PaintGen.py compatibility
- **Host-specific UI** — `ui_connect`/`ui_disconnect` stay in Paint.py (different widgets for Paint/NCC)

**Tech Stack:** Python 3.10+, dataclasses, PyQt6, existing FlatCAM infrastructure

**Worktree:** `D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared`

**No Git Commits:** All changes stay in worktree until Phase 1 complete and verified.

---

## Current State (from jcode analysis)

| Component | Status | Lines | Notes |
|-----------|--------|-------|-------|
| `ToolShared/__init__.py` | ✅ Exists | 1 | Only comment, no exports |
| `ToolShared/ToolManager.py` | ✅ Exists | 148 | Uses plain dicts, missing `reorder_tools()`, `search_tools_db()` |
| `ToolShared/types.py` | ❌ Missing | 0 | **Must create first** |
| `ToolShared/ToolTableHelper.py` | ❌ Missing | 0 | **Must create** |
| `ToolShared/BaseGenerator.py` | ✅ Exists | - | Unchanged in Phase 1 |
| `Paint.py` | ✅ Exists | 1829 | Imports `ToolManager`, uses dict tools |
| `PaintGen.py` | ✅ Exists | - | Must verify compatibility |
| Tests | ❌ Missing | 0 | **Must create** |

---

## Critical Fixes from Plan Review

| # | Issue | Fix |
|---|-------|-----|
| 1 | `build_ui()` calls non-existent module imports | Host provides `ui_connect()`/`ui_disconnect()` |
| 2 | Missing `reorder_tools()` in ToolManager | Added with clear()/update() pattern |
| 3 | Missing `on_tooltable_cell_widget_change` extraction | Extracted with widget passed from host |
| 4 | Missing `search_tools_db()` implementation | Full DB search logic added to ToolManager |
| 5 | FormStorageParams not used | Added as typed parameter object |
| 6 | DeleteToolsParams signature mismatch | Host creates params internally |
| 7 | `getHeight()` may not exist | Added hasattr() check |
| 8 | Combo columns hardcoded | Configurable via ToolTableConfig.combo_columns |

---

## Phase 1 Tasks

### Task 1: Create Dataclasses Module (types.py)

**Files:**
- Create: `appPlugins/ToolShared/types.py`
- Test: `tests/plugins/toolshared/test_types.py`

**Why First:** All other tasks depend on these dataclasses.

---

#### Step 1: Create types.py with ToolEntry and parameter dataclasses

**File:** `appPlugins/ToolShared/types.py`

```python
"""
Dataclasses for ToolShared module.

ToolEntry provides typed tool storage with backward-compatible dict access
for PaintGen.py compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal
from copy import deepcopy


# ── Type Aliases ──────────────────────────────────────────────────────────────

ToolType = Literal["Iso", "Rough"]
"""Tool cutting type: Iso (isolation) or Rough (roughing)."""

ToolShape = Literal["V", "C1", "C2", "B", "U"]
"""Tool shape: V (V-bit), C1/C2 (chamfer), B (bullnose), U (unknown)."""

OffsetMode = Literal["Off", "On", "Auto"]
"""Offset mode for tool path generation."""

PaintOrder = Literal["Default", "Forward", "Reverse"]
"""Tool ordering in table: Default, Forward (ascending), Reverse (descending)."""


# ── ToolEntry Dataclass ───────────────────────────────────────────────────────

@dataclass
class ToolEntry:
    """
    Single tool entry with type-safe fields.
    
    Replaces untyped dict pattern:
        {'tooldia': float, 'data': dict, 'solid_geometry': list, ...}
    
    Backward Compatibility:
        Provides dict-like access via __getitem__, __setitem__, get(), keys(),
        etc. so existing code like tool['tooldia'] and tool['data']['name']
        continues working without changes to PaintGen.py.
    
    Attributes:
        tooldia: Tool diameter in current units (mm/in)
        data: Tool parameters dict (feed, speed, etc.)
        solid_geometry: List of geometry objects for this tool
        type: Cutting type (Iso/Rough)
        tool_type: Tool shape (V/C1/C2/B/U)
        offset: Offset mode (Off/On/Auto) - optional, Paint-specific
        offset_value: Offset value - optional, Paint-specific
    
    Example:
        >>> entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        >>> entry["tooldia"]  # dict-like access
        3.0
        >>> entry["data"]["feed"] = 200  # nested dict access
        >>> entry.update({"type": "Iso"})  # dict update pattern
    """
    
    tooldia: float
    data: Dict[str, Any] = field(default_factory=dict)
    solid_geometry: List[Any] = field(default_factory=list)
    type: ToolType = "Rough"
    tool_type: ToolShape = "C1"
    offset: Optional[str] = None
    offset_value: Optional[float] = None
    
    # ── Dict Protocol Methods (for backward compatibility) ─────────────────
    
    def __getitem__(self, key: str) -> Any:
        """
        Dict-like read access: tool['tooldia'], tool['data'], tool['custom_key'].
        
        Known fields return attributes. Unknown keys fall through to self.data.
        """
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
        """
        Dict-like write access: tool['tooldia'] = x, tool['custom_key'] = y.
        
        Known fields set attributes. Unknown keys go to self.data.
        """
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
        else:
            # Unknown keys go to data dict
            self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get with default: tool.get('missing', default)."""
        try:
            return self[key]
        except KeyError:
            return default
    
    def update(self, other: Dict[str, Any]) -> None:
        """Dict-like update: tool.update({'key': value, ...})."""
        for key, value in other.items():
            self[key] = value
    
    def keys(self) -> List[str]:
        """
        Return all accessible keys.
        
        Note: offset/offset_value only included when non-None to match
        dict behavior where missing keys don't appear in iteration.
        """
        base_keys = [
            "tooldia",
            "data",
            "solid_geometry",
            "type",
            "tool_type",
        ]
        if self.offset is not None:
            base_keys.append("offset")
        if self.offset_value is not None:
            base_keys.append("offset_value")
        # Include data keys for iteration compatibility
        return base_keys + list(self.data.keys())
    
    def values(self) -> List[Any]:
        """Return all values corresponding to keys()."""
        return [self[k] for k in self.keys()]
    
    def items(self) -> List[tuple]:
        """Return all (key, value) pairs corresponding to keys()."""
        return [(k, self[k]) for k in self.keys()]
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists: 'tooldia' in tool."""
        try:
            self[key]
            return True
        except KeyError:
            return False
    
    # ── Serialization Methods ────────────────────────────────────────────────
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to plain dict for JSON serialization.
        
        Only includes offset/offset_value when non-None.
        Deepcopies nested structures to prevent mutation.
        """
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
        """
        Create ToolEntry from dict (handles missing optional fields).
        
        Example:
            >>> d = {"tooldia": 3.0, "data": {"feed": 100}}
            >>> entry = ToolEntry.from_dict(d)
        """
        return cls(
            tooldia=d.get("tooldia", 0.0),
            data=d.get("data", {}),
            solid_geometry=d.get("solid_geometry", []),
            type=d.get("type", "Rough"),
            tool_type=d.get("tool_type", "C1"),
            offset=d.get("offset"),
            offset_value=d.get("offset_value"),
        )


# ── Configuration Dataclasses ────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolTableConfig:
    """
    Host-specific configuration for tool table operations.
    
    Frozen: Set once at helper init, never mutated. This ensures
    configuration is immutable and IDE shows all fields on hover.
    
    Provided by host (ToolPaint/ToolNcc) at ToolTableHelper init time.
    
    Attributes:
        log_prefix: "ToolPaint" or "ToolNcc" for log messages
        tool_target: _('Paint') or _('NCC') — for DB search filter
        tool_key_prefix: 'tools_paint_' or 'tools_ncc_' — for DB key filtering
        db_source: 'paint' or 'ncc' — for DB dialog source
        combo_columns: List of column indexes with combo widgets (Paint=[2], NCC=[2])
        store_offset: True for Paint (stores offset/offset_value), False for NCC
        generate_button_attr: 'generate_paint_button' or 'generate_ncc_button'
        order_combo_attr: 'paint_order_combo' or 'ncc_order_combo'
        rest_cb_attr: 'rest_cb' or 'ncc_rest_cb' — for Paint-specific checkbox
    
    Example (ToolPaint):
        >>> config = ToolTableConfig(
        ...     log_prefix="ToolPaint",
        ...     tool_target=_('Paint'),
        ...     tool_key_prefix='tools_paint_',
        ...     db_source='paint',
        ...     combo_columns=[2],
        ...     store_offset=True,
        ...     generate_button_attr='generate_paint_button',
        ...     order_combo_attr='paint_order_combo',
        ...     rest_cb_attr='rest_cb',
        ... )
    """
    
    log_prefix: str
    tool_target: str
    tool_key_prefix: str
    db_source: str
    combo_columns: List[int]
    store_offset: bool
    generate_button_attr: str
    order_combo_attr: str
    rest_cb_attr: str


@dataclass
class FormStorageParams:
    """
    Typed parameters for form-to-storage save operation.
    
    Created by host from self.sender(), passed to ToolManager.
    
    Attributes:
        tool_uids: List of tool UIDs to update
        option_changed: Option name that changed (e.g., 'feed')
        new_value: New value to store
    
    Example:
        >>> params = FormStorageParams(
        ...     tool_uids=[1, 2, 3],
        ...     option_changed='feed',
        ...     new_value=150.0,
        ... )
        >>> tool_manager.form_to_storage(params)
    """
    
    tool_uids: List[int]
    option_changed: str
    new_value: Any


@dataclass
class DeleteToolsParams:
    """
    Typed parameters for tool deletion.
    
    Either rows_to_delete OR all_tools should be set, not both.
    
    Attributes:
        rows_to_delete: List of row indexes to delete (from UI table)
        all_tools: If True, delete all tools from table
    
    Example:
        >>> # Delete specific rows
        >>> params = DeleteToolsParams(rows_to_delete=[0, 2, 4])
        >>> # Delete all
        >>> params = DeleteToolsParams(all_tools=True)
    """
    
    rows_to_delete: Optional[List[int]] = None
    all_tools: bool = False


@dataclass
class DBSearchResult:
    """
    Result of searching Tools Database for a matching tool.
    
    Returned by ToolManager.search_tools_db().
    
    Attributes:
        found_count: Number of matching tools found (0 = not found, 1 = success, >1 = error)
        tool_data: Tool data dict from DB (if found)
        updated_diameter: DB tool diameter (if found via tolerance match)
        offset: Offset mode from DB tool (default 'Path')
        offset_value: Offset value from DB tool (default 0.0)
    
    Example:
        >>> result = tool_manager.search_tools_db(3.0, config)
        >>> if result.found_count == 1:
        ...     tool_data = result.tool_data
    """
    
    found_count: int = 0
    tool_data: Optional[Dict[str, Any]] = None
    updated_diameter: Optional[float] = None
    offset: str = "Path"
    offset_value: float = 0.0


# ── Module Exports ───────────────────────────────────────────────────────────

__all__ = [
    # Types
    "ToolType",
    "ToolShape",
    "OffsetMode",
    "PaintOrder",
    # Dataclasses
    "ToolEntry",
    "ToolTableConfig",
    "FormStorageParams",
    "DeleteToolsParams",
    "DBSearchResult",
]
```

---

#### Step 2: Create test_types.py

**Directory:** Create `tests/plugins/toolshared/` if not exists

**File:** `tests/plugins/toolshared/test_types.py`

```python
"""
Tests for ToolShared dataclasses.

Verifies:
- ToolEntry creation with defaults
- Dict-like access patterns (PaintGen.py compatibility)
- to_dict/from_dict roundtrip
- Nested dict access
- Deepcopy compatibility
- Frozen config immutability
"""
import pytest
from copy import deepcopy

from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolTableConfig,
    FormStorageParams,
    DeleteToolsParams,
    DBSearchResult,
    ToolType,
    ToolShape,
)


class TestToolEntryCreation:
    """Test ToolEntry creation and defaults."""
    
    def test_creation_with_minimal_fields(self):
        """Test creating ToolEntry with only required tooldia."""
        entry = ToolEntry(tooldia=3.0)
        
        assert entry.tooldia == 3.0
        assert entry.data == {}
        assert entry.solid_geometry == []
        assert entry.type == "Rough"
        assert entry.tool_type == "C1"
        assert entry.offset is None
        assert entry.offset_value is None
    
    def test_creation_with_all_fields(self):
        """Test creating ToolEntry with all fields specified."""
        entry = ToolEntry(
            tooldia=5.0,
            data={"feed": 100, "speed": 200},
            solid_geometry=["geo1", "geo2"],
            type="Iso",
            tool_type="V",
            offset="On",
            offset_value=0.5,
        )
        
        assert entry.tooldia == 5.0
        assert entry.data == {"feed": 100, "speed": 200}
        assert entry.solid_geometry == ["geo1", "geo2"]
        assert entry.type == "Iso"
        assert entry.tool_type == "V"
        assert entry.offset == "On"
        assert entry.offset_value == 0.5
    
    def test_from_dict_with_all_fields(self):
        """Test creating ToolEntry from dict."""
        d = {
            "tooldia": 3.5,
            "data": {"feed": 150},
            "solid_geometry": ["geo"],
            "type": "Iso",
            "tool_type": "C1",
            "offset": "Auto",
            "offset_value": 0.25,
        }
        
        entry = ToolEntry.from_dict(d)
        
        assert entry.tooldia == 3.5
        assert entry.data == {"feed": 150}
        assert entry.type == "Iso"
        assert entry.offset == "Auto"
    
    def test_from_dict_with_missing_optional_fields(self):
        """Test from_dict handles missing optional fields."""
        d = {"tooldia": 3.0}
        
        entry = ToolEntry.from_dict(d)
        
        assert entry.tooldia == 3.0
        assert entry.data == {}
        assert entry.offset is None
        assert entry.offset_value is None


class TestToolEntryDictAccess:
    """Test dict-like access patterns for PaintGen.py compatibility."""
    
    def test_getitem_known_fields(self):
        """Test __getitem__ for known fields."""
        entry = ToolEntry(tooldia=3.0, type="Iso")
        
        assert entry["tooldia"] == 3.0
        assert entry["type"] == "Iso"
        assert entry["data"] == {}
        assert entry["solid_geometry"] == []
    
    def test_getitem_data_keys(self):
        """Test __getitem__ for keys in data dict."""
        entry = ToolEntry(tooldia=3.0, data={"feed": 100, "custom": "value"})
        
        assert entry["feed"] == 100
        assert entry["custom"] == "value"
    
    def test_getitem_raises_for_unknown_key(self):
        """Test __getitem__ raises KeyError for unknown keys."""
        entry = ToolEntry(tooldia=3.0)
        
        with pytest.raises(KeyError):
            _ = entry["nonexistent"]
    
    def test_setitem_known_fields(self):
        """Test __setitem__ for known fields."""
        entry = ToolEntry(tooldia=3.0)
        
        entry["tooldia"] = 5.0
        entry["type"] = "Iso"
        entry["tool_type"] = "V"
        
        assert entry.tooldia == 5.0
        assert entry.type == "Iso"
        assert entry.tool_type == "V"
    
    def test_setitem_data_keys(self):
        """Test __setitem__ for new keys goes to data dict."""
        entry = ToolEntry(tooldia=3.0)
        
        entry["feed"] = 100
        entry["custom"] = "value"
        
        assert entry.data["feed"] == 100
        assert entry.data["custom"] == "value"
    
    def test_nested_dict_access(self):
        """Test tool['data']['nested_key'] pattern (PaintGen.py compatibility)."""
        entry = ToolEntry(tooldia=3.0, data={"name": "original"})
        
        # This is the critical PaintGen.py pattern
        entry["data"]["name"] = "updated"
        
        assert entry.data["name"] == "updated"
        assert entry["data"]["name"] == "updated"
    
    def test_get_with_default(self):
        """Test get() method with default value."""
        entry = ToolEntry(tooldia=3.0)
        
        assert entry.get("tooldia") == 3.0
        assert entry.get("missing", "default") == "default"
        assert entry.get("offset", None) is None
    
    def test_update_method(self):
        """Test update() method."""
        entry = ToolEntry(tooldia=3.0, data={"existing": 1})
        
        entry.update({
            "type": "Iso",
            "feed": 100,  # goes to data
        })
        
        assert entry.type == "Iso"
        assert entry.data["feed"] == 100
        assert entry.data["existing"] == 1
    
    def test_keys_includes_data_keys(self):
        """Test keys() includes both field names and data keys."""
        entry = ToolEntry(
            tooldia=3.0,
            offset="On",
            data={"feed": 100},
        )
        
        keys = entry.keys()
        
        assert "tooldia" in keys
        assert "data" in keys
        assert "offset" in keys
        assert "feed" in keys
    
    def test_keys_excludes_none_optionals(self):
        """Test keys() excludes offset/offset_value when None."""
        entry = ToolEntry(tooldia=3.0)
        
        assert "offset" not in entry.keys()
        assert "offset_value" not in entry.keys()
    
    def test_contains(self):
        """Test __contains__ for 'key in tool' pattern."""
        entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        
        assert "tooldia" in entry
        assert "feed" in entry
        assert "missing" not in entry
    
    def test_values(self):
        """Test values() method."""
        entry = ToolEntry(tooldia=3.0, type="Iso")
        
        values = entry.values()
        
        assert 3.0 in values
        assert "Iso" in values
    
    def test_items(self):
        """Test items() method."""
        entry = ToolEntry(tooldia=3.0)
        
        items = entry.items()
        
        assert ("tooldia", 3.0) in items


class TestToolEntrySerialization:
    """Test to_dict/from_dict roundtrip."""
    
    def test_to_dict_with_all_fields(self):
        """Test to_dict includes all fields."""
        entry = ToolEntry(
            tooldia=3.0,
            data={"feed": 100},
            solid_geometry=["geo"],
            type="Iso",
            tool_type="V",
            offset="On",
            offset_value=0.5,
        )
        
        d = entry.to_dict()
        
        assert d["tooldia"] == 3.0
        assert d["data"] == {"feed": 100}
        assert d["solid_geometry"] == ["geo"]
        assert d["type"] == "Iso"
        assert d["tool_type"] == "V"
        assert d["offset"] == "On"
        assert d["offset_value"] == 0.5
    
    def test_to_dict_excludes_none_optionals(self):
        """Test to_dict excludes offset/offset_value when None."""
        entry = ToolEntry(tooldia=3.0)
        
        d = entry.to_dict()
        
        assert "offset" not in d
        assert "offset_value" not in d
    
    def test_to_dict_deepcopies_data(self):
        """Test to_dict deepcopies nested data to prevent mutation."""
        entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        
        d = entry.to_dict()
        d["data"]["feed"] = 999
        
        assert entry.data["feed"] == 100  # Original unchanged
    
    def test_roundtrip(self):
        """Test to_dict -> from_dict roundtrip preserves values."""
        original = ToolEntry(
            tooldia=3.5,
            data={"feed": 150, "speed": 200},
            type="Iso",
            tool_type="V",
            offset="Auto",
            offset_value=0.25,
        )
        
        restored = ToolEntry.from_dict(original.to_dict())
        
        assert restored.tooldia == original.tooldia
        assert restored.data == original.data
        assert restored.type == original.type
        assert restored.tool_type == original.tool_type
        assert restored.offset == original.offset
        assert restored.offset_value == original.offset_value


class TestToolEntryDeepcopy:
    """Test deepcopy compatibility (PaintGen.py pattern)."""
    
    def test_deepcopy_preserves_values(self):
        """Test deepcopy creates independent copy."""
        entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        
        copied = deepcopy(entry)
        
        assert copied.tooldia == 3.0
        assert copied.data["feed"] == 100
    
    def test_deepcopy_independent_data(self):
        """Test deepcopy data is independent."""
        entry = ToolEntry(tooldia=3.0, data={"feed": 100})
        
        copied = deepcopy(entry)
        copied.data["feed"] = 200
        
        assert entry.data["feed"] == 100  # Original unchanged
        assert copied.data["feed"] == 200


class TestToolTableConfig:
    """Test ToolTableConfig dataclass."""
    
    def test_creation(self):
        """Test creating ToolTableConfig."""
        config = ToolTableConfig(
            log_prefix="ToolPaint",
            tool_target="Paint",
            tool_key_prefix="tools_paint_",
            db_source="paint",
            combo_columns=[2],
            store_offset=True,
            generate_button_attr="generate_paint_button",
            order_combo_attr="paint_order_combo",
            rest_cb_attr="rest_cb",
        )
        
        assert config.log_prefix == "ToolPaint"
        assert config.tool_target == "Paint"
        assert config.combo_columns == [2]
        assert config.store_offset is True
    
    def test_is_frozen(self):
        """Test ToolTableConfig is immutable (frozen)."""
        config = ToolTableConfig(
            log_prefix="ToolPaint",
            tool_target="Paint",
            tool_key_prefix="tools_paint_",
            db_source="paint",
            combo_columns=[2],
            store_offset=True,
            generate_button_attr="generate_paint_button",
            order_combo_attr="paint_order_combo",
            rest_cb_attr="rest_cb",
        )
        
        with pytest.raises(AttributeError):
            config.log_prefix = "NewPrefix"


class TestFormStorageParams:
    """Test FormStorageParams dataclass."""
    
    def test_creation(self):
        """Test creating FormStorageParams."""
        params = FormStorageParams(
            tool_uids=[1, 2, 3],
            option_changed="feed",
            new_value=150.0,
        )
        
        assert params.tool_uids == [1, 2, 3]
        assert params.option_changed == "feed"
        assert params.new_value == 150.0


class TestDeleteToolsParams:
    """Test DeleteToolsParams dataclass."""
    
    def test_creation_with_rows(self):
        """Test creating DeleteToolsParams with rows_to_delete."""
        params = DeleteToolsParams(rows_to_delete=[0, 2, 4])
        
        assert params.rows_to_delete == [0, 2, 4]
        assert params.all_tools is False
    
    def test_creation_all_tools(self):
        """Test creating DeleteToolsParams with all_tools=True."""
        params = DeleteToolsParams(all_tools=True)
        
        assert params.rows_to_delete is None
        assert params.all_tools is True
    
    def test_default_values(self):
        """Test default values."""
        params = DeleteToolsParams()
        
        assert params.rows_to_delete is None
        assert params.all_tools is False


class TestDBSearchResult:
    """Test DBSearchResult dataclass."""
    
    def test_default_values(self):
        """Test default values (not found)."""
        result = DBSearchResult()
        
        assert result.found_count == 0
        assert result.tool_data is None
        assert result.updated_diameter is None
        assert result.offset == "Path"
        assert result.offset_value == 0.0
    
    def test_found_result(self):
        """Test successful search result."""
        result = DBSearchResult(
            found_count=1,
            tool_data={"feed": 100},
            updated_diameter=3.0,
            offset="On",
            offset_value=0.5,
        )
        
        assert result.found_count == 1
        assert result.tool_data == {"feed": 100}
        assert result.updated_diameter == 3.0
```

---

#### Step 3: Run tests

**Command:**
```bash
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_types.py -v
```

**Expected Output:**
```
tests/plugins/toolshared/test_types.py::TestToolEntryCreation::test_creation_with_minimal_fields PASSED
...
tests/plugins/toolshared/test_types.py::TestDBSearchResult::test_found_result PASSED

============================== 25 passed in 0.15s ==============================
```

---

### Task 2: Update ToolManager to Use ToolEntry

**Files:**
- Modify: `appPlugins/ToolShared/ToolManager.py`
- Test: `tests/plugins/toolshared/test_tool_manager.py`

**Why:** ToolManager currently uses plain dicts. Must update to use ToolEntry.

---

#### Step 1: Rewrite ToolManager.py

**File:** `appPlugins/ToolShared/ToolManager.py`

```python
"""
ToolManager: Manages ToolEntry instances for Paint/NCC tools.

Main-thread-only (no locking). Uses ToolEntry dataclass for type safety
while maintaining backward compatibility via dict-like access.

THREAD SAFETY: Main-thread-only. No locks required.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy
import simplejson as json
import sys

from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolTableConfig,
    FormStorageParams,
    DBSearchResult,
)


class ToolManager:
    """
    Manages a tools dict: {int(uid): ToolEntry}
    
    Provides:
    - CRUD operations (add, delete, edit diameter)
    - Form ↔ Storage synchronization
    - Apply-to-all parameter copying
    - Tools Database search
    
    THREAD SAFETY: Main-thread-only. No locks.
    
    Attributes:
        app: Application reference (for dec_format, log)
        tools: Reference to parent's paint_tools/ncc_tools dict
        form_fields: UI form field widgets
        name2option: Widget name to option name mapping
        default_data: Default tool parameters dict
        decimals: Decimal places for diameter formatting
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
    
    # ── Helpers ──────────────────────────────────────────────────────────────
    
    def _fmt_dia(self, diameter: float) -> float:
        """Format diameter to configured decimal places."""
        return self.app.dec_format(diameter, self.decimals)
    
    def _next_uid(self) -> int:
        """Get next available tool UID (max existing + 1)."""
        return max(self.tools.keys(), default=0) + 1
    
    def tool_exists(self, diameter: float) -> bool:
        """Check if tool with same formatted diameter exists."""
        truncated = self._fmt_dia(diameter)
        return any(
            self._fmt_dia(t.tooldia) == truncated
            for t in self.tools.values()
        )
    
    # ── CRUD Operations ──────────────────────────────────────────────────────
    
    def add_tool(
        self,
        diameter: float,
        tool_data: Optional[dict] = None,
        solid_geometry: Optional[list] = None,
        extra_attrs: Optional[dict] = None,
    ) -> Optional[int]:
        """
        Add new tool. Returns UID or None if duplicate.
        
        Args:
            diameter: Tool diameter in current units
            tool_data: Tool parameters dict (uses default_data if None)
            solid_geometry: List of geometry objects for this tool
            extra_attrs: Additional attributes (e.g., offset/offset_value from DB)
        
        Returns:
            Tool UID if added successfully, None if duplicate diameter
        
        Example:
            >>> uid = tool_manager.add_tool(3.0, extra_attrs={"offset": "On"})
            >>> if uid:
            ...     print(f"Added tool {uid}")
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
        """
        Delete tools by UID list.
        
        Args:
            uids: List of tool UIDs to delete
        
        Returns:
            Count of tools actually deleted
        """
        count = 0
        for uid in uids:
            if uid in self.tools:
                del self.tools[uid]
                count += 1
        return count
    
    def edit_diameter(self, uid: int, new_dia: float) -> Tuple[bool, str]:
        """
        Edit tool diameter.
        
        Args:
            uid: Tool UID to edit
            new_dia: New diameter value
        
        Returns:
            (success, message) tuple
            - (True, "OK") if successful
            - (False, "Tool not found") if UID doesn't exist
            - (False, "Duplicate diameter") if new diameter exists
        """
        if uid not in self.tools:
            return False, "Tool not found"
        
        truncated = self._fmt_dia(new_dia)
        
        # Check for duplicate
        for other_uid, t in self.tools.items():
            if other_uid != uid and self._fmt_dia(t.tooldia) == truncated:
                return False, "Duplicate diameter"
        
        self.tools[uid].tooldia = truncated
        return True, "OK"
    
    def reorder_tools(self, uid_order: List[int]) -> None:
        """
        Reorder tools according to UID tool_ordering list.
        
        Preserves dict reference (uses clear()/update()) so external
        references (e.g., PaintGen) remain valid.
        
        Args:
            uid_order: List of old UIDs in new tool_ordering (new UIDs assigned 1,2,3...)
        
        Example:
            >>> # Reverse tool_ordering: [3, 2, 1] means old UID 3 becomes new UID 1
            >>> tool_manager.reorder_tools([3, 2, 1])
        """
        new_tools = {}
        for new_uid, old_uid in enumerate(uid_order, start=1):
            new_tools[new_uid] = deepcopy(self.tools[old_uid])
        
        # Preserve dict reference
        self.tools.clear()
        self.tools.update(new_tools)
    
    # ── Form ↔ Storage ───────────────────────────────────────────────────────
    
    def storage_to_form(self, dict_storage: dict) -> None:
        """
        Populate UI form fields from a data dict.
        
        Note: Uses 'key in dict_storage' rather than 'value is not None' to
        allow explicit None values to be stored. If key is missing, skipped.
        
        Args:
            dict_storage: Tool data dict (typically tool.data or tool['data'])
        
        Example:
            >>> tool = tool_manager.get_tool(uid)
            >>> tool_manager.storage_to_form(tool.data)
        """
        for key in self.form_fields:
            if key in dict_storage:
                try:
                    self.form_fields[key].set_value(dict_storage[key])
                except Exception as e:
                    self.app.log.error(f"storage_to_form failed for {key}: {e}")
    
    def form_to_storage(self, params: FormStorageParams) -> None:
        """
        Save one changed UI value to tool storage for selected tools.
        
        Checks both tool-level and tool['data']-level keys.
        
        Args:
            params: Typed parameters with tool_uids, option_changed, new_value
        
        Example:
            >>> params = FormStorageParams(
            ...     tool_uids=[1, 2],
            ...     option_changed='feed',
            ...     new_value=150.0,
            ... )
            >>> tool_manager.form_to_storage(params)
        """
        for uid in params.tool_uids:
            tool = self.tools.get(uid)
            if tool is None:
                continue
            
            # Check tool-level key
            if params.option_changed in tool:
                tool[params.option_changed] = params.new_value
            
            # Check data-level key
            if params.option_changed in tool.get('data', {}):
                tool['data'][params.option_changed] = params.new_value
    
    def apply_params_to_all(self, source_uid: int) -> bool:
        """
        Copy data dict from source tool to all other tools.
        
        Uses deepcopy to prevent shared references.
        
        Args:
            source_uid: UID of tool to copy data from
        
        Returns:
            True if successful, False if source tool not found or has no data
        """
        if source_uid not in self.tools:
            return False
        
        source_data = self.tools[source_uid].data
        if source_data is None:
            return False
        
        for uid, tool in self.tools.items():
            if uid != source_uid:
                tool.data = deepcopy(source_data)
        
        return True
    
    # ── Tools Database Search ────────────────────────────────────────────────
    
    def search_tools_db(
        self,
        truncated_dia: float,
        config: ToolTableConfig,
    ) -> DBSearchResult:
        """
        Search Tools Database for matching tool.
        
        Looks for:
        1. Exact diameter match
        2. Tool within tolerance range (low_limit <= dia <= high_limit)
        
        Filters by:
        - config.tool_target (_('Paint') or _('NCC'))
        - config.tool_key_prefix (tools_paint_ or tools_ncc_)
        
        Args:
            truncated_dia: Formatted tool diameter to search for
            config: Host configuration with DB search parameters
        
        Returns:
            DBSearchResult with found_count, tool_data, etc.
        
        Example:
            >>> config = ToolTableConfig(..., tool_target=_('Paint'), ...)
            >>> result = tool_manager.search_tools_db(3.0, config)
            >>> if result.found_count == 1:
            ...     tool_data = result.tool_data
        """
        filename = self.app.tools_database_path()
        
        # Load DB file
        try:
            with open(filename) as f:
                tools_content = f.read()
        except IOError:
            self.app.log.error("Could not load tools DB file.")
            return DBSearchResult(found_count=0)
        
        try:
            tools_db_dict = json.loads(tools_content)
        except Exception as e:
            self.app.log.error(f"Failed to parse Tools DB file: {e}")
            return DBSearchResult(found_count=0)
        
        if not tools_db_dict:
            return DBSearchResult(found_count=0)
        
        tool_found = 0
        result_data = None
        updated_diameter = None
        offset = "Path"
        offset_value = 0.0
        
        for db_tool_id, db_tool_val in tools_db_dict.items():
            # Extract offset info
            offset = db_tool_val.get('data', {}).get('tools_mill_offset_type', 'Path')
            offset_value = db_tool_val.get('data', {}).get('tools_mill_offset_value', 0.0)
            
            db_tooldia = db_tool_val.get('tooldia', 0.0)
            low_limit = float(db_tool_val.get('data', {}).get('tol_min', 0.0))
            high_limit = float(db_tool_val.get('data', {}).get('tol_max', 0.0))
            
            # Filter by tool target (Paint vs NCC)
            if db_tool_val.get('data', {}).get('tool_target') != config.tool_target:
                continue
            
            # Exact diameter match
            if truncated_dia == db_tooldia:
                tool_found += 1
                updated_diameter = db_tooldia
                result_data = db_tool_val.get('data', {})
            
            # Tolerance match
            elif high_limit >= truncated_dia >= low_limit:
                tool_found += 1
                updated_diameter = db_tooldia
                result_data = db_tool_val.get('data', {})
        
        if tool_found != 1:
            # 0 = not found, >1 = multiple (error)
            return DBSearchResult(found_count=tool_found)
        
        return DBSearchResult(
            found_count=1,
            tool_data=result_data,
            updated_diameter=updated_diameter,
            offset=offset,
            offset_value=offset_value,
        )
    
    # ── Query Operations ─────────────────────────────────────────────────────
    
    def get_tool(self, uid: int) -> Optional[ToolEntry]:
        """Get tool entry by UID."""
        return self.tools.get(uid)
    
    def get_diameters(self) -> List[float]:
        """Get list of all tool diameters."""
        return [t.tooldia for t in self.tools.values()]
```

---

#### Step 2: Create test_tool_manager.py

**File:** `tests/plugins/toolshared/test_tool_manager.py`

```python
"""
Tests for ToolManager.

Verifies:
- CRUD operations with ToolEntry
- Form ↔ Storage synchronization
- Apply-to-all parameter copying
- Tools Database search (mocked)
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from copy import deepcopy

from appPlugins.ToolShared.ToolManager import ToolManager
from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolTableConfig,
    FormStorageParams,
    DBSearchResult,
)


@pytest.fixture
def mock_app():
    """Create mock app with required attributes."""
    app = Mock()
    app.dec_format = lambda val, dec: round(val, dec)
    app.log = Mock()
    app.log.error = Mock()
    app.tools_database_path = Mock(return_value="/fake/path/tools.json")
    return app


@pytest.fixture
def form_fields():
    """Create mock form fields dict."""
    return {
        "feed": Mock(),
        "speed": Mock(),
    }


@pytest.fixture
def name2option():
    """Create mock name2option mapping."""
    return {
        "feed_spin": "feed",
        "speed_spin": "speed",
    }


@pytest.fixture
def default_data():
    """Create default tool data."""
    return {"feed": 100, "speed": 200}


@pytest.fixture
def tool_manager(mock_app, form_fields, name2option, default_data):
    """Create ToolManager instance."""
    tools_dict = {}
    return ToolManager(
        app=mock_app,
        tools_dict=tools_dict,
        form_fields=form_fields,
        name2option=name2option,
        default_data=default_data,
        decimals=4,
    )


class TestToolManagerAddTool:
    """Test add_tool operation."""
    
    def test_add_tool_returns_uid(self, tool_manager):
        """Test add_tool returns UID."""
        uid = tool_manager.add_tool(3.0)
        
        assert uid == 1
        assert 1 in tool_manager.tools
        assert tool_manager.tools[1].tooldia == 3.0
    
    def test_add_tool_rejects_duplicate(self, tool_manager):
        """Test add_tool returns None for duplicate diameter."""
        uid1 = tool_manager.add_tool(3.0)
        uid2 = tool_manager.add_tool(3.0)
        
        assert uid1 == 1
        assert uid2 is None
        assert len(tool_manager.tools) == 1
    
    def test_add_tool_with_extra_attrs(self, tool_manager):
        """Test add_tool with extra attributes (offset/offset_value)."""
        uid = tool_manager.add_tool(
            3.0,
            extra_attrs={"offset": "On", "offset_value": 0.5},
        )
        
        assert uid == 1
        assert tool_manager.tools[1].offset == "On"
        assert tool_manager.tools[1].offset_value == 0.5
    
    def test_add_tool_deepcopies_default_data(self, tool_manager):
        """Test add_tool deepcopies default_data."""
        uid = tool_manager.add_tool(3.0)
        
        # Modify returned tool's data
        tool_manager.tools[uid].data["feed"] = 999
        
        # Default data should be unchanged
        assert tool_manager.default_data["feed"] == 100


class TestToolManagerDeleteTools:
    """Test delete_tools operation."""
    
    def test_delete_tools_removes_correct(self, tool_manager):
        """Test delete_tools removes specified tools."""
        uid1 = tool_manager.add_tool(3.0)
        uid2 = tool_manager.add_tool(5.0)
        uid3 = tool_manager.add_tool(7.0)
        
        count = tool_manager.delete_tools([uid1, uid3])
        
        assert count == 2
        assert uid1 not in tool_manager.tools
        assert uid2 in tool_manager.tools
        assert uid3 not in tool_manager.tools
    
    def test_delete_tools_returns_count(self, tool_manager):
        """Test delete_tools returns count of deleted tools."""
        tool_manager.add_tool(3.0)
        
        count = tool_manager.delete_tools([999])  # Non-existent
        
        assert count == 0


class TestToolManagerEditDiameter:
    """Test edit_diameter operation."""
    
    def test_edit_diameter_success(self, tool_manager):
        """Test edit_diameter succeeds with valid input."""
        uid = tool_manager.add_tool(3.0)
        
        success, msg = tool_manager.edit_diameter(uid, 5.0)
        
        assert success is True
        assert msg == "OK"
        assert tool_manager.tools[uid].tooldia == 5.0
    
    def test_edit_diameter_rejects_duplicate(self, tool_manager):
        """Test edit_diameter rejects duplicate diameter."""
        uid1 = tool_manager.add_tool(3.0)
        uid2 = tool_manager.add_tool(5.0)
        
        success, msg = tool_manager.edit_diameter(uid2, 3.0)
        
        assert success is False
        assert msg == "Duplicate diameter"
        assert tool_manager.tools[uid2].tooldia == 5.0  # Unchanged
    
    def test_edit_diameter_tool_not_found(self, tool_manager):
        """Test edit_diameter fails for non-existent tool."""
        success, msg = tool_manager.edit_diameter(999, 5.0)
        
        assert success is False
        assert msg == "Tool not found"


class TestToolManagerReorderTools:
    """Test reorder_tools operation."""
    
    def test_reorder_tools_preserves_reference(self, tool_manager):
        """Test reorder_tools preserves dict reference."""
        uid1 = tool_manager.add_tool(3.0)
        uid2 = tool_manager.add_tool(5.0)
        
        original_id = id(tool_manager.tools)
        
        tool_manager.reorder_tools([uid2, uid1])  # Reverse tool_ordering
        
        assert id(tool_manager.tools) == original_id  # Same dict object
    
    def test_reorder_tools_reassigns_uids(self, tool_manager):
        """Test reorder_tools reassigns UIDs in tool_ordering."""
        uid1 = tool_manager.add_tool(3.0)
        uid2 = tool_manager.add_tool(5.0)
        
        tool_manager.reorder_tools([uid2, uid1])
        
        # New UIDs: 1, 2
        assert list(tool_manager.tools.keys()) == [1, 2]
        assert tool_manager.tools[1].tooldia == 5.0  # First is old uid2
        assert tool_manager.tools[2].tooldia == 3.0  # Second is old uid1


class TestToolManagerStorageToForm:
    """Test storage_to_form operation."""
    
    def test_storage_to_form_populates_fields(self, tool_manager, form_fields):
        """Test storage_to_form calls set_value on form fields."""
        data = {"feed": 150, "speed": 250}
        
        tool_manager.storage_to_form(data)
        
        form_fields["feed"].set_value.assert_called_once_with(150)
        form_fields["speed"].set_value.assert_called_once_with(250)
    
    def test_storage_to_form_skips_missing_keys(self, tool_manager, form_fields):
        """Test storage_to_form skips keys not in data."""
        data = {"feed": 150}  # Missing "speed"
        
        tool_manager.storage_to_form(data)
        
        form_fields["feed"].set_value.assert_called_once_with(150)
        form_fields["speed"].set_value.assert_not_called()


class TestToolManagerFormToStorage:
    """Test form_to_storage operation."""
    
    def test_form_to_storage_updates_tool_level_key(self, tool_manager):
        """Test form_to_storage updates tool-level keys."""
        uid = tool_manager.add_tool(3.0, extra_attrs={"offset": "Off"})
        
        params = FormStorageParams(
            tool_uids=[uid],
            option_changed="offset",
            new_value="On",
        )
        
        tool_manager.form_to_storage(params)
        
        assert tool_manager.tools[uid].offset == "On"
    
    def test_form_to_storage_updates_data_level_key(self, tool_manager):
        """Test form_to_storage updates data-level keys."""
        uid = tool_manager.add_tool(3.0, tool_data={"feed": 100})
        
        params = FormStorageParams(
            tool_uids=[uid],
            option_changed="feed",
            new_value=150,
        )
        
        tool_manager.form_to_storage(params)
        
        assert tool_manager.tools[uid].data["feed"] == 150


class TestToolManagerApplyParamsToAll:
    """Test apply_params_to_all operation."""
    
    def test_apply_params_to_all_copies_data(self, tool_manager):
        """Test apply_params_to_all deepcopies data to all tools."""
        uid1 = tool_manager.add_tool(3.0, tool_data={"feed": 100})
        uid2 = tool_manager.add_tool(5.0, tool_data={"feed": 200})
        
        success = tool_manager.apply_params_to_all(uid1)
        
        assert success is True
        assert tool_manager.tools[uid1].data["feed"] == 100
        assert tool_manager.tools[uid2].data["feed"] == 100  # Copied
    
    def test_apply_params_to_all_deepcopies(self, tool_manager):
        """Test apply_params_to_all uses deepcopy."""
        uid1 = tool_manager.add_tool(3.0, tool_data={"feed": 100})
        uid2 = tool_manager.add_tool(5.0)
        
        tool_manager.apply_params_to_all(uid1)
        
        # Modify source
        tool_manager.tools[uid1].data["feed"] = 999
        
        # Copied data should be unchanged
        assert tool_manager.tools[uid2].data["feed"] == 100
    
    def test_apply_params_to_all_source_not_found(self, tool_manager):
        """Test apply_params_to_all returns False for missing source."""
        success = tool_manager.apply_params_to_all(999)
        
        assert success is False


class TestToolManagerSearchToolsDb:
    """Test search_tools_db operation."""
    
    def test_search_tools_db_not_found(self, tool_manager, mock_app):
        """Test search_tools_db returns found_count=0 when not found."""
        mock_db_content = '{"tool1": {"tooldia": 5.0, "data": {"tool_target": "Paint"}}}'
        
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda s, *a: None,
            read=MagicMock(return_value=mock_db_content),
        ))):
            config = ToolTableConfig(
                log_prefix="ToolPaint",
                tool_target="Paint",
                tool_key_prefix="tools_paint_",
                db_source="paint",
                combo_columns=[2],
                store_offset=True,
                generate_button_attr="generate_paint_button",
                order_combo_attr="paint_order_combo",
                rest_cb_attr="rest_cb",
            )
            
            result = tool_manager.search_tools_db(3.0, config)
        
        assert result.found_count == 0
    
    def test_search_tools_db_exact_match(self, tool_manager, mock_app):
        """Test search_tools_db finds exact diameter match."""
        mock_db_content = '''{
            "tool1": {
                "tooldia": 3.0,
                "data": {
                    "tool_target": "Paint",
                    "feed": 100,
                    "tools_mill_offset_type": "On",
                    "tools_mill_offset_value": 0.5
                }
            }
        }'''
        
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda s, *a: None,
            read=MagicMock(return_value=mock_db_content),
        ))):
            config = ToolTableConfig(
                log_prefix="ToolPaint",
                tool_target="Paint",
                tool_key_prefix="tools_paint_",
                db_source="paint",
                combo_columns=[2],
                store_offset=True,
                generate_button_attr="generate_paint_button",
                order_combo_attr="paint_order_combo",
                rest_cb_attr="rest_cb",
            )
            
            result = tool_manager.search_tools_db(3.0, config)
        
        assert result.found_count == 1
        assert result.tool_data is not None
        assert result.tool_data["feed"] == 100
        assert result.offset == "On"
        assert result.offset_value == 0.5
    
    def test_search_tools_db_filters_by_target(self, tool_manager, mock_app):
        """Test search_tools_db filters by tool_target."""
        mock_db_content = '''{
            "tool1": {
                "tooldia": 3.0,
                "data": {"tool_target": "NCC"}
            }
        }'''
        
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s: s,
            __exit__=lambda s, *a: None,
            read=MagicMock(return_value=mock_db_content),
        ))):
            config = ToolTableConfig(
                log_prefix="ToolPaint",
                tool_target="Paint",
                tool_key_prefix="tools_paint_",
                db_source="paint",
                combo_columns=[2],
                store_offset=True,
                generate_button_attr="generate_paint_button",
                order_combo_attr="paint_order_combo",
                rest_cb_attr="rest_cb",
            )
            
            result = tool_manager.search_tools_db(3.0, config)
        
        assert result.found_count == 0  # Filtered out (NCC, not Paint)


class TestToolManagerQuery:
    """Test query operations."""
    
    def test_get_tool(self, tool_manager):
        """Test get_tool returns ToolEntry."""
        uid = tool_manager.add_tool(3.0)
        
        tool = tool_manager.get_tool(uid)
        
        assert tool is not None
        assert tool.tooldia == 3.0
    
    def test_get_tool_not_found(self, tool_manager):
        """Test get_tool returns None for missing UID."""
        tool = tool_manager.get_tool(999)
        
        assert tool is None
    
    def test_get_diameters(self, tool_manager):
        """Test get_diameters returns list of diameters."""
        tool_manager.add_tool(3.0)
        tool_manager.add_tool(5.0)
        
        diameters = tool_manager.get_diameters()
        
        assert 3.0 in diameters
        assert 5.0 in diameters
        assert len(diameters) == 2
```

---

#### Step 3: Run tests

**Command:**
```bash
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_tool_manager.py -v
```

**Expected Output:**
```
tests/plugins/toolshared/test_tool_manager.py::TestToolManagerAddTool::test_add_tool_returns_uid PASSED
...
tests/plugins/toolshared/test_tool_manager.py::TestToolManagerQuery::test_get_diameters PASSED

============================== 22 passed in 0.25s ==============================
```

---

### Task 3: Create ToolTableHelper (Composition Class)

**Files:**
- Create: `appPlugins/ToolShared/ToolTableHelper.py`
- Test: `tests/plugins/toolshared/test_tool_table_helper.py`

**Why:** Main composition class that holds ToolManager and implements shared tool-table operations.

---

#### Step 1: Create ToolTableHelper.py

**File:** `appPlugins/ToolShared/ToolTableHelper.py`

```python
"""
ToolTableHelper: Composition class for shared tool table operations.

Uses composition pattern — instantiated by host class (ToolPaint/ToolNcc)
and operates on the host's tools dict via ToolManager.

Host class must provide:
- self.app, self.ui, self.decimals, self.default_data, self.form_fields
- self.name2option, self.tool_type_item_options
- self.paint_tools or self.ncc_tools (dict passed to ToolManager)
- self.ui_connect(), self.ui_disconnect() — host-specific implementations
- self.tooluid attribute
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PyQt6 import QtWidgets, QtCore
from copy import deepcopy

from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolTableConfig,
    FormStorageParams,
    DeleteToolsParams,
    DBSearchResult,
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
    - self.tooluid attribute
    
    Attributes:
        host: Reference to host class (ToolPaint/ToolNcc)
        app: Application reference
        ui: UI instance (PaintUI/NccUI)
        config: Host configuration (frozen dataclass)
        tool_manager: ToolManager instance for CRUD operations
        tools_dict: Reference to host's paint_tools/ncc_tools dict
    """
    
    def __init__(
        self,
        host: Any,
        tools_dict: Dict[int, ToolEntry],
        config: ToolTableConfig,
    ):
        self.host = host
        self.app = host.app
        self.ui = host.ui
        self.config = config              # frozen dataclass
        self.tools_dict = tools_dict      # same reference as host
        
        self.tool_manager = ToolManager(
            app=host.app,
            tools_dict=tools_dict,
            form_fields=host.form_fields,
            name2option=host.name2option,
            default_data=host.default_data,
            decimals=host.decimals,
        )
    
    # ── Config Accessors (read from frozen dataclass) ────────────────────────
    
    @property
    def generate_button(self) -> Any:
        """Get generate button from host UI."""
        return getattr(self.ui, self.config.generate_button_attr)
    
    @property
    def order_combo(self) -> Any:
        """Get tool_ordering combo from host UI."""
        return getattr(self.ui, self.config.order_combo_attr)
    
    # ── Selection Handlers ───────────────────────────────────────────────────
    
    def on_toggle_all_rows(self) -> None:
        """
        Toggle selection of all rows in tools table.
        
        If all rows selected → clear selection.
        If some/none selected → select all.
        """
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
        """
        Handle row selection change — update UI if single row selected.
        
        Called when user clicks on table row.
        """
        sel_model = self.ui.tools_table.selectionModel()
        sel_indexes = sel_model.selectedIndexes()
        sel_rows = {idx.row() for idx in sel_indexes}
        
        if len(sel_rows) == 1:
            self.update_ui()
    
    # ── UI Update ────────────────────────────────────────────────────────────
    
    def update_ui(self) -> None:
        """
        Update UI form fields based on selected tool(s).
        
        Single selection: Populate form with tool data.
        Multiple selection: Show "Multiple Tools" message.
        No selection: Disable generate button.
        """
        self.host.blockSignals(True)
        
        table_items = self.ui.tools_table.selectedItems()
        sel_rows = {it.row() for it in table_items} if table_items else set()
        
        if not sel_rows:
            self.generate_button.setDisabled(True)
            self.ui.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>"
                % (_('Parameters for'), _("No Tool Selected"))
            )
            self.host.blockSignals(False)
            return
        
        self.generate_button.setDisabled(False)
        
        for current_row in sel_rows:
            try:
                item = self.ui.tools_table.item(current_row, 3)
                if item is None:
                    return
                tooluid = int(item.text())
            except Exception as e:
                self.app.log.error(f"{self.config.log_prefix}: Tool missing. {e}")
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
                    self.app.log.error(f"{self.config.log_prefix}: update_ui failed: {e}")
            else:
                self.ui.tool_data_label.setText(
                    "<b>%s: <font color='#0000FF'>%s</font></b>"
                    % (_('Parameters for'), _("Multiple Tools"))
                )
        
        self.host.blockSignals(False)
    
    # ── Form ↔ Storage ───────────────────────────────────────────────────────
    
    def on_apply_param_to_all_clicked(self) -> None:
        """
        Apply current tool's parameters to all tools.
        
        Takes data from currently selected/row tool and deepcopies to all others.
        """
        if self.ui.tools_table.rowCount() == 0:
            self.app.log.debug(f"{self.config.log_prefix}: No tools in table, aborting.")
            return
        
        self.host.blockSignals(True)
        
        row = self.ui.tools_table.currentRow()
        if row < 0:
            row = 0
        
        tooluid_item = int(self.ui.tools_table.item(row, 3).text())
        
        self.tool_manager.apply_params_to_all(tooluid_item)
        
        self.app.inform.emit('[success] %s' % _("Current Tool parameters were applied to all tools."))
        self.host.blockSignals(False)
    
    # ── Tool CRUD Operations ─────────────────────────────────────────────────
    
    def on_tool_default_add(
        self,
        dia: Optional[float] = None,
        muted: Optional[bool] = None,
    ) -> None:
        """
        Add default tool with given diameter.
        
        Args:
            dia: Tool diameter (uses UI entry if None)
            muted: If True, suppress success message
        """
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
            tool_data=deepcopy(self.host.default_data),
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
    
    def on_tool_add(self, custom_dia: Optional[float] = None) -> None:
        """
        Add tool from Tools Database (or default if not found).
        
        Searches DB for matching tool by diameter/tolerance.
        Falls back to on_tool_default_add() when DB unavailable.
        
        Args:
            custom_dia: Tool diameter (uses UI entry if None)
        """
        self.host.blockSignals(True)
        
        # Determine tool diameter
        if custom_dia is None:
            tool_dia = self.ui.new_tooldia_entry.get_value()
        else:
            tool_dia = custom_dia
        
        if tool_dia is None or tool_dia == 0:
            self.build_ui()
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Please enter a tool diameter with non-zero value.")
            )
            self.host.blockSignals(False)
            return
        
        truncated_tooldia = self.app.dec_format(tool_dia, self.host.decimals)
        
        # Check for duplicate
        tool_dias = [
            self.app.dec_format(t.tooldia, self.host.decimals)
            for t in self.tools_dict.values()
        ]
        
        if truncated_tooldia in tool_dias:
            self.app.inform.emit(
                '[WARNING_NOTCL] %s %s' % (_("Cancelled."), _("Tool already in Tool Table."))
            )
            self.host.blockSignals(False)
            return
        
        # Search DB
        result = self.tool_manager.search_tools_db(truncated_tooldia, self.config)
        
        # Handle DB search results
        if result.found_count == 0:
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Tool not in Tools Database. Adding a default tool.")
            )
            self.host.blockSignals(False)
            self.on_tool_default_add(dia=tool_dia)
            return
        
        if result.found_count > 1:
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Cancelled.\nMultiple tools for one tool diameter found in Tools Database.")
            )
            self.host.blockSignals(False)
            return
        
        # Check if found DB tool diameter already exists
        if result.updated_diameter is not None:
            if result.updated_diameter in tool_dias:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s %s' % (_("Cancelled."), _("Tool already in Tool Table."))
                )
                self.host.blockSignals(False)
                return
        
        # Build tool data from DB result
        tool_uid_list = list(self.tools_dict.keys())
        max_uid = 0 if not tool_uid_list else max(tool_uid_list)
        tooluid = int(max_uid + 1)
        
        # Build tool data from DB result
        new_tools_dict = deepcopy(self.host.default_data)
        if result.tool_data:
            for key, value in result.tool_data.items():
                if key.startswith(self.config.tool_key_prefix):
                    new_tools_dict[key] = value
                elif key.startswith('tools_'):
                    continue  # Skip other tool prefixes
                else:
                    new_tools_dict[key] = value
        
        # Create tool entry
        new_tdia = result.updated_diameter if result.updated_diameter is not None else truncated_tooldia
        
        extra_attrs = {}
        if self.config.store_offset:
            extra_attrs["offset"] = result.offset
            extra_attrs["offset_value"] = result.offset_value
        
        entry = ToolEntry(
            tooldia=new_tdia,
            data=new_tools_dict,
            solid_geometry=[],
            **extra_attrs,
        )
        
        self.tools_dict[tooluid] = entry
        
        self.host.tooluid = tooluid
        self.host.blockSignals(False)
        self.build_ui()
        
        # Select the tool just added
        for row in range(self.ui.tools_table.rowCount()):
            if int(self.ui.tools_table.item(row, 3).text()) == tooluid:
                self.ui.tools_table.selectRow(row)
                break
        
        self.update_ui()
        
        self.app.inform.emit(
            '[success] %s' % _("New tool added to Tool Table from Tools Database.")
        )
    
    def on_tool_delete(self, params: Optional[DeleteToolsParams] = None) -> None:
        """
        Delete tools from table.
        
        Args:
            params: DeleteToolsParams with rows_to_delete or all_tools
                   If None, deletes currently selected rows
        """
        self.host.blockSignals(True)
        deleted_tools_list = []
        
        if params and params.all_tools:
            self.tools_dict.clear()
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        rows_to_delete = params.rows_to_delete if params else None
        
        if rows_to_delete:
            try:
                for row in rows_to_delete:
                    tooluid_del = int(self.ui.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)
            except (TypeError, IndexError):
                pass
            
            for t in deleted_tools_list:
                self.tools_dict.pop(t, None)
            
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        # Delete selected rows
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
            self.app.inform.emit(
                '[WARNING_NOTCL] %s' % _("Delete failed. Select a tool to delete.")
            )
            self.host.blockSignals(False)
            return
        except Exception as e:
            self.app.log.error(str(e))
        
        self.app.inform.emit('[success] %s' % _("Tools deleted from Tool Table."))
        self.host.blockSignals(False)
        self.build_ui()
    
    def on_tool_edit(self, item: Any) -> None:
        """
        Handle tool diameter edit in table.
        
        Validates new diameter and rejects duplicates.
        
        Args:
            item: QTableWidgetItem that was edited
        """
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
            float('%.*f' % (self.host.decimals, v.tooldia))
            for v in self.tools_dict.values()
        ]
        
        if new_tool_dia not in tool_dias:
            self.tools_dict[editeduid].tooldia = new_tool_dia
            self.app.inform.emit('[success] %s' % _("Tool from Tool Table was edited."))
            self.host.blockSignals(False)
            self.build_ui()
            return
        
        # Restore old value (duplicate)
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
    
    def on_tooltable_cell_widget_change(self, widget: QtWidgets.QComboBox) -> None:
        """
        Handle tool type combo change in table.
        
        Host calls self.sender() and passes widget to this method.
        
        Args:
            widget: QComboBox that changed (from sender())
        """
        assert isinstance(widget, QtWidgets.QComboBox), \
            "Expected a QtWidgets.QComboBox, got %s" % type(widget).__name__
        
        cw_index = self.ui.tools_table.indexAt(widget.pos())
        cw_row = cw_index.row()
        cw_col = cw_index.column()
        
        current_uid = int(self.ui.tools_table.item(cw_row, 3).text())
        
        # Column 2 = tool type combo
        if cw_col == 2:
            tt = widget.currentText()
            typ = 'Iso' if tt == 'V' else 'Rough'
            
            self.tools_dict[current_uid].update({
                'type': typ,
                'tool_type': tt,
            })
    
    # ── Table Management ─────────────────────────────────────────────────────
    
    def on_order_changed(self, order: int) -> None:
        """
        Handle tool_ordering combo change.
        
        Args:
            order: Order value (0=Default, 1=Forward, 2=Reverse)
        """
        if order != 0:  # Default tool_ordering
            self.build_ui()
    
    def rebuild_ui(self) -> None:
        """
        Rebuild UI with new tool tool_ordering.
        
        Reads current table tool_ordering, reorders tools_dict, triggers build_ui.
        """
        current_uid_list = [
            int(self.ui.tools_table.item(row, 3).text())
            for row in range(self.ui.tools_table.rowCount())
        ]
        
        self.tool_manager.reorder_tools(current_uid_list)
        
        QtCore.QTimer.singleShot(20, self.build_ui)
    
    def build_ui(self) -> None:
        """
        Build/rebuild the tools table.
        
        1. Calls host.ui_disconnect() first
        2. Reads tools and tool_ordering
        3. Creates table rows with ID, diameter, type combo, UID
        4. Configures headers and sizing
        5. Calls host.ui_connect() last
        """
        # Call host-specific ui_disconnect
        self.host.ui_disconnect()
        
        units = self.app.app_units.upper()
        order_val = self.order_combo.get_value()
        order_map = {0: "Default", 1: "Forward", 2: "Reverse"}
        order = order_map.get(order_val, "Default")
        
        # Sort tools
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
                if float('%.*f' % (self.host.decimals, tool.tooldia)) == tool_sorted:
                    tool_id += 1
                    row_no = tool_id - 1
                    
                    # ID column
                    id_item = QtWidgets.QTableWidgetItem(str(tool_id))
                    id_item.setFlags(selected_enabled_flag)
                    self.ui.tools_table.setItem(row_no, 0, id_item)
                    
                    # Diameter column
                    dia = QtWidgets.QTableWidgetItem('%.*f' % (self.host.decimals, tool.tooldia))
                    dia.setFlags(enabled_flag)
                    self.ui.tools_table.setItem(row_no, 1, dia)
                    
                    # Tool type combo (column 2)
                    tool_type_item = QtWidgets.QComboBox()
                    for opt in self.host.tool_type_item_options:
                        tool_type_item.addItem(opt)
                    idx = int(tool.data.get('tools_mill_tool_shape', 0))
                    tool_type_item.setCurrentIndex(idx)
                    self.ui.tools_table.setCellWidget(row_no, 2, tool_type_item)
                    
                    # UID column (hidden, column 3)
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
        
        # Set height
        if hasattr(self.ui.tools_table, 'getHeight'):
            self.ui.tools_table.setMinimumHeight(self.ui.tools_table.getHeight())
            self.ui.tools_table.setMaximumHeight(self.ui.tools_table.getHeight())
        
        # Call host-specific ui_connect
        self.host.ui_connect()
        
        # Set tool_data_label text
        sel_rows = set()
        sel_items = self.ui.tools_table.selectedItems()
        for it in sel_items:
            sel_rows.add(it.row())
        if len(sel_rows) > 1:
            self.ui.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>"
                % (_('Parameters for'), _("Multiple Tools"))
            )
    
    # ── Signal Helpers (called by host's ui_connect/ui_disconnect) ───────────
    
    def connect_table_signals(self) -> None:
        """
        Connect table-related signals.
        
        Called by host's ui_connect().
        """
        self.ui.tools_table.itemChanged.connect(self.host.on_tool_edit)
        self.ui.tools_table.clicked.connect(self.host.on_row_selection_change)
        self.ui.tools_table.horizontalHeader().sectionClicked.connect(self.host.on_toggle_all_rows)
        
        # Connect combo widgets in configured columns
        for row in range(self.ui.tools_table.rowCount()):
            for col in self.config.combo_columns:
                try:
                    widget = self.ui.tools_table.cellWidget(row, col)
                    if widget:
                        widget.currentIndexChanged.connect(self.host.on_tooltable_cell_widget_change)
                except (AttributeError, IndexError):
                    pass
    
    def disconnect_table_signals(self) -> None:
        """
        Disconnect table-related signals.
        
        Called by host's ui_disconnect().
        """
        try:
            self.ui.tools_table.itemChanged.disconnect()
        except (TypeError, AttributeError):
            pass
        
        try:
            self.ui.tools_table.clicked.disconnect()
        except (TypeError, AttributeError):
            pass
        
        try:
            self.ui.tools_table.horizontalHeader().sectionClicked.disconnect()
        except (TypeError, AttributeError):
            pass
        
        # Disconnect combo widgets
        for row in range(self.ui.tools_table.rowCount()):
            for col in self.config.combo_columns:
                try:
                    widget = self.ui.tools_table.cellWidget(row, col)
                    if widget:
                        widget.currentIndexChanged.disconnect()
                except (AttributeError, IndexError, TypeError):
                    pass
    
    def connect_form_signals(self) -> None:
        """
        Connect form field signals.
        
        Uses disconnect-then-reconnect pattern for safety.
        Called by host's ui_connect().
        """
        from appGUI.GUIElements import FCCheckBox, RadioSet, FCDoubleSpinner, FCComboBox
        
        # First disconnect
        for opt in self.host.form_fields:
            current_widget = self.host.form_fields[opt]
            if isinstance(current_widget, FCCheckBox):
                try:
                    current_widget.stateChanged.disconnect()
                except (TypeError, ValueError):
                    pass
            if isinstance(current_widget, RadioSet):
                try:
                    current_widget.activated_custom.disconnect()
                except (TypeError, ValueError):
                    pass
            elif isinstance(current_widget, FCDoubleSpinner):
                try:
                    current_widget.returnPressed.disconnect()
                except (TypeError, ValueError):
                    pass
        
        # Then reconnect
        for opt in self.host.form_fields:
            current_widget = self.host.form_fields[opt]
            if isinstance(current_widget, FCCheckBox):
                current_widget.stateChanged.connect(self.host.form_to_storage)
            if isinstance(current_widget, RadioSet):
                current_widget.activated_custom.connect(self.host.form_to_storage)
            elif isinstance(current_widget, FCDoubleSpinner):
                current_widget.returnPressed.connect(self.host.form_to_storage)
            elif isinstance(current_widget, FCComboBox):
                current_widget.currentIndexChanged.connect(self.host.form_to_storage)
    
    def disconnect_form_signals(self) -> None:
        """
        Disconnect form field signals.
        
        Called by host's ui_disconnect().
        """
        from appGUI.GUIElements import FCCheckBox, RadioSet, FCDoubleSpinner, FCComboBox
        
        for opt in self.host.form_fields:
            current_widget = self.host.form_fields[opt]
            if isinstance(current_widget, FCCheckBox):
                try:
                    current_widget.stateChanged.disconnect(self.host.form_to_storage)
                except (TypeError, ValueError):
                    pass
            if isinstance(current_widget, RadioSet):
                try:
                    current_widget.activated_custom.disconnect(self.host.form_to_storage)
                except (TypeError, ValueError):
                    pass
            elif isinstance(current_widget, FCDoubleSpinner):
                try:
                    current_widget.returnPressed.disconnect(self.host.form_to_storage)
                except (TypeError, ValueError):
                    pass
            elif isinstance(current_widget, FCComboBox):
                try:
                    current_widget.currentIndexChanged.disconnect(self.host.form_to_storage)
                except (TypeError, ValueError):
                    pass
```

---

#### Step 2: Create test_tool_table_helper.py

**File:** `tests/plugins/toolshared/test_tool_table_helper.py`

```python
"""
Tests for ToolTableHelper.

Verifies:
- Selection handlers
- CRUD operations delegation
- UI update methods
- Signal connection helpers
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt6 import QtWidgets, QtCore

from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import ToolEntry, ToolTableConfig, DeleteToolsParams


@pytest.fixture
def mock_host():
    """Create mock host with required attributes."""
    host = Mock()
    host.app = Mock()
    host.app.dec_format = lambda val, dec: round(val, dec)
    host.app.log = Mock()
    host.app.log.error = Mock()
    host.app.log.debug = Mock()
    host.app.inform = Mock()
    host.app.inform.emit = Mock()
    host.app.app_units = "mm"
    
    host.ui = Mock()
    host.ui.tools_table = Mock()
    host.ui.tools_table.rowCount = Mock(return_value=0)
    host.ui.tools_table.selectedItems = Mock(return_value=[])
    host.ui.tools_table.selectionModel = Mock(return_value=Mock(selectedIndexes=Mock(return_value=[])))
    host.ui.tool_data_label = Mock()
    host.ui.tool_data_label.setText = Mock()
    host.ui.new_tooldia_entry = Mock()
    host.ui.new_tooldia_entry.get_value = Mock(return_value=3.0)
    host.ui.generate_paint_button = Mock()
    host.ui.generate_paint_button.setDisabled = Mock()
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
    
    return host


@pytest.fixture
def config():
    """Create ToolTableConfig for tests."""
    return ToolTableConfig(
        log_prefix="ToolPaint",
        tool_target="Paint",
        tool_key_prefix="tools_paint_",
        db_source="paint",
        combo_columns=[2],
        store_offset=True,
        generate_button_attr="generate_paint_button",
        order_combo_attr="paint_order_combo",
        rest_cb_attr="rest_cb",
    )


@pytest.fixture
def helper(mock_host, config):
    """Create ToolTableHelper instance."""
    tools_dict = {}
    return ToolTableHelper(host=mock_host, tools_dict=tools_dict, config=config)


class TestToolTableHelperSelection:
    """Test selection handler methods."""
    
    def test_on_toggle_all_rows_select(self, helper, mock_host):
        """Test on_toggle_all_rows selects all when none selected."""
        mock_host.ui.tools_table.rowCount = Mock(return_value=5)
        mock_host.ui.tools_table.selectionModel().selectedIndexes = Mock(return_value=[])
        
        helper.on_toggle_all_rows()
        
        mock_host.ui.tools_table.selectAll.assert_called_once()
    
    def test_on_toggle_all_rows_clear(self, helper, mock_host):
        """Test on_toggle_all_rows clears when all selected."""
        mock_host.ui.tools_table.rowCount = Mock(return_value=5)
        mock_indexes = [Mock(row=i) for i in range(5)]
        mock_host.ui.tools_table.selectionModel().selectedIndexes = Mock(return_value=mock_indexes)
        
        helper.on_toggle_all_rows()
        
        mock_host.ui.tools_table.clearSelection.assert_called_once()


class TestToolTableHelperCRUD:
    """Test CRUD operations."""
    
    def test_on_tool_default_add_success(self, helper, mock_host):
        """Test on_tool_default_add adds tool."""
        helper.on_tool_default_add(dia=3.0, muted=True)
        
        assert mock_host.tooluid == 1
        assert 1 in helper.tools_dict
    
    def test_on_tool_default_add_zero_diameter(self, helper, mock_host):
        """Test on_tool_default_add rejects zero diameter."""
        helper.on_tool_default_add(dia=0.0, muted=True)
        
        mock_host.app.inform.emit.assert_called()
        assert '[WARNING_NOTCL]' in str(mock_host.app.inform.emit.call_args)
    
    def test_on_tool_delete_all(self, helper, mock_host):
        """Test on_tool_delete with all_tools=True clears all."""
        helper.tool_manager.add_tool(3.0)
        
        params = DeleteToolsParams(all_tools=True)
        helper.on_tool_delete(params)
        
        assert len(helper.tools_dict) == 0
    
    def test_on_tool_delete_specific_rows(self, helper, mock_host):
        """Test on_tool_delete with rows_to_delete."""
        # Setup: need to mock table items
        mock_host.ui.tools_table.rowCount = Mock(return_value=2)
        mock_host.ui.tools_table.item = Mock(side_effect=lambda r, c: Mock(text=lambda: [1, 2][r] if c == 3 else Mock()))
        
        helper.tool_manager.add_tool(3.0)
        helper.tool_manager.add_tool(5.0)
        
        params = DeleteToolsParams(rows_to_delete=[0])
        helper.on_tool_delete(params)
        
        assert len(helper.tools_dict) == 1


class TestToolTableHelperUI:
    """Test UI update methods."""
    
    def test_update_ui_no_selection(self, helper, mock_host):
        """Test update_ui disables button when no selection."""
        mock_host.ui.tools_table.selectedItems = Mock(return_value=[])
        
        helper.update_ui()
        
        mock_host.ui.generate_paint_button.setDisabled.assert_called_with(True)
    
    def test_on_apply_param_to_all_empty_table(self, helper, mock_host):
        """Test on_apply_param_to_all_with empty table."""
        mock_host.ui.tools_table.rowCount = Mock(return_value=0)
        
        helper.on_apply_param_to_all_clicked()
        
        mock_host.app.log.debug.assert_called()


class TestToolTableHelperSignals:
    """Test signal connection helpers."""
    
    def test_connect_table_signals(self, helper, mock_host):
        """Test connect_table_signals connects table signals."""
        mock_host.ui.tools_table.rowCount = Mock(return_value=0)
        
        helper.connect_table_signals()
        
        mock_host.ui.tools_table.itemChanged.connect.assert_called()
        mock_host.ui.tools_table.clicked.connect.assert_called()
        mock_host.ui.tools_table.horizontalHeader().sectionClicked.connect.assert_called()
    
    def test_disconnect_table_signals(self, helper, mock_host):
        """Test disconnect_table_signals handles missing connections."""
        mock_host.ui.tools_table.rowCount = Mock(return_value=0)
        mock_host.ui.tools_table.itemChanged.disconnect = Mock(side_effect=TypeError)
        
        # Should not raise
        helper.disconnect_table_signals()
```

---

#### Step 3: Run tests

**Command:**
```bash
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared
python -m pytest tests/plugins/toolshared/test_tool_table_helper.py -v
```

**Expected Output:**
```
tests/plugins/toolshared/test_tool_table_helper.py::TestToolTableHelperSelection::test_on_toggle_all_rows_select PASSED
...
tests/plugins/toolshared/test_tool_table_helper.py::TestToolTableHelperSignals::test_disconnect_table_signals PASSED

============================== 10 passed in 0.20s ==============================
```

---

### Task 4: Update ToolShared/__init__.py

**File:** `appPlugins/ToolShared/__init__.py`

```python
"""ToolShared — Shared tool table infrastructure for Paint/NCC."""

from appPlugins.ToolShared.types import (
    ToolEntry,
    ToolTableConfig,
    FormStorageParams,
    DeleteToolsParams,
    DBSearchResult,
    ToolType,
    ToolShape,
    OffsetMode,
    PaintOrder,
)
from appPlugins.ToolShared.ToolManager import ToolManager
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.BaseGenerator import BaseGenerator

__all__ = [
    # Types
    "ToolType",
    "ToolShape",
    "OffsetMode",
    "PaintOrder",
    # Dataclasses
    "ToolEntry",
    "ToolTableConfig",
    "FormStorageParams",
    "DeleteToolsParams",
    "DBSearchResult",
    # Classes
    "ToolManager",
    "ToolTableHelper",
    "BaseGenerator",
]
```

---

### Task 5: Migrate Paint.py to Use Helper

**Files:**
- Modify: `appPlugins/ToolPaint/Paint.py:1-1829`

**Why:** Delegate ~15 methods to ToolTableHelper.

---

#### Step 1: Add imports

**Modify:** `appPlugins/ToolPaint/Paint.py:13` (after existing imports)

```python
# Add after line 13 (after ToolManager import):
from appPlugins.ToolShared.ToolTableHelper import ToolTableHelper
from appPlugins.ToolShared.types import (
    ToolEntry, ToolTableConfig, FormStorageParams, DeleteToolsParams,
)
```

---

#### Step 2: Add helper attribute in __init__

**Modify:** `appPlugins/ToolPaint/Paint.py:87` (after `self.paint_tools = {}`)

```python
# After line 87 (self.paint_tools = {}), add:
self.tool_table_helper: Optional[ToolTableHelper] = None
```

---

#### Step 3: Initialize helper in set_tool_ui()

**Modify:** `appPlugins/ToolPaint/Paint.py:~450` (after form_fields/name2option are set)

```python
# After form_fields and name2option are set in set_tool_ui(), add:
config = ToolTableConfig(
    log_prefix="ToolPaint",
    tool_target=_('Paint'),
    tool_key_prefix='tools_paint_',
    db_source='paint',
    combo_columns=[2],
    store_offset=True,
    generate_button_attr='generate_paint_button',
    order_combo_attr='paint_order_combo',
    rest_cb_attr='rest_cb',
)
self.tool_table_helper = ToolTableHelper(
    host=self, tools_dict=self.paint_tools, config=config
)
```

---

#### Step 4: Replace method bodies with delegates

**Replace these methods:**

```python
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

def on_tool_add(self, custom_dia=None):
    self.tool_table_helper.on_tool_add(custom_dia=custom_dia)

def on_tool_delete(self, rows_to_delete=None, all_tools=None):
    params = DeleteToolsParams(rows_to_delete=rows_to_delete, all_tools=bool(all_tools)) if rows_to_delete or all_tools else None
    self.tool_table_helper.on_tool_delete(params)

def on_tool_edit(self, item):
    self.tool_table_helper.on_tool_edit(item)

def on_order_changed(self, order):
    self.tool_table_helper.on_order_changed(order)

def rebuild_ui(self):
    self.tool_table_helper.rebuild_ui()

def build_ui(self):
    self.tool_table_helper.build_ui()

def on_paint_tool_add_from_db_clicked(self):
    self.tool_table_helper.on_tool_add_from_db_clicked()

def storage_to_form(self, dict_storage):
    self.tool_table_helper.tool_manager.storage_to_form(dict_storage)
```

---

#### Step 5: Update form_to_storage (stays in host)

**Modify:** Keep `form_to_storage` in Paint.py but delegate data work:

```python
def form_to_storage(self):
    if self.ui.tools_table.rowCount() == 0:
        return
    
    self.blockSignals(True)
    
    widget_changed = self.sender()
    wdg_objname = widget_changed.objectName()
    option_changed = self.name2option[wdg_objname]
    
    rows = sorted(set(index.row() for index in self.ui.tools_table.selectedIndexes()))
    tooluids = [int(self.ui.tools_table.item(max(0, row), 3).text()) for row in rows]
    
    new_value = self.form_fields[option_changed].get_value()
    params = FormStorageParams(tool_uids=tooluids, option_changed=option_changed, new_value=new_value)
    
    self.tool_table_helper.tool_manager.form_to_storage(params)
    self.blockSignals(False)
```

---

#### Step 6: Update ui_connect/ui_disconnect

**Modify:**

```python
def ui_connect(self):
    # Shared signals via helper
    self.tool_table_helper.connect_table_signals()
    self.tool_table_helper.connect_form_signals()
    # Host-specific signals
    self.ui.rest_cb.stateChanged.connect(self.ui.on_rest_machining_check)
    self.ui.paint_order_combo.currentIndexChanged.connect(self.on_order_changed)

def ui_disconnect(self):
    # Shared signals via helper
    self.tool_table_helper.disconnect_table_signals()
    self.tool_table_helper.disconnect_form_signals()
    # Host-specific signals
    try:
        self.ui.rest_cb.stateChanged.disconnect()
    except (TypeError, AttributeError):
        pass
    try:
        self.ui.paint_order_combo.currentIndexChanged.disconnect()
    except (TypeError, AttributeError):
        pass
```

---

### Task 6: Create PaintGen Compatibility Tests

**File:** `tests/plugins/paint/test_paintgen_compatibility.py`

```python
"""Verify PaintGen.py patterns work with ToolEntry dataclass."""
import pytest
from copy import deepcopy
from appPlugins.ToolShared.types import ToolEntry


class TestPaintGenCompatibility:
    """Test patterns used in PaintGen.py work with ToolEntry."""
    
    def test_dict_access_tooldia(self):
        """Test: tools_storage[uid]['tooldia']"""
        tools = {1: ToolEntry(tooldia=3.0)}
        assert tools[1]["tooldia"] == 3.0
    
    def test_nested_data_access(self):
        """Test: tools_storage[uid]['data']['key']"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        assert tools[1]["data"]["feed"] == 100
        tools[1]["data"]["feed"] = 200
        assert tools[1].data["feed"] == 200
    
    def test_solid_geometry_assignment(self):
        """Test: tools_storage[uid]['solid_geometry'] = list"""
        tools = {1: ToolEntry(tooldia=3.0)}
        tools[1]["solid_geometry"] = ["geo1"]
        assert tools[1].solid_geometry == ["geo1"]
    
    def test_update_pattern(self):
        """Test: tools_storage[uid].update({...})"""
        tools = {1: ToolEntry(tooldia=3.0)}
        tools[1].update({"type": "Iso"})
        assert tools[1].type == "Iso"
    
    def test_get_method(self):
        """Test: tools_storage[uid].get('key', default)"""
        tools = {1: ToolEntry(tooldia=3.0)}
        assert tools[1].get("tooldia") == 3.0
        assert tools[1].get("missing", "default") == "default"
    
    def test_keys_iteration(self):
        """Test: for key in tools_storage[uid].keys()"""
        tools = {1: ToolEntry(tooldia=3.0, offset="On")}
        keys = list(tools[1].keys())
        assert "tooldia" in keys
        assert "offset" in keys
    
    def test_deepcopy_compatibility(self):
        """Test: deepcopy(tools_storage[uid])"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        copied = deepcopy(tools[1])
        assert copied.tooldia == 3.0
        copied.data["feed"] = 200
        assert tools[1].data["feed"] == 100  # Original unchanged
    
    def test_to_dict_serialization(self):
        """Test: tools_storage[uid].to_dict()"""
        tools = {1: ToolEntry(tooldia=3.0, data={"feed": 100})}
        as_dict = tools[1].to_dict()
        assert as_dict["tooldia"] == 3.0
```

---

### Task 7: Run Full Test Suite & Verify

**Commands:**
```bash
cd D:\1.Development\FlatCAM_EVO\.worktrees\refactor-tool-shared

# Run all new tests
python -m pytest tests/plugins/toolshared/ -v

# Run PaintGen compatibility tests
python -m pytest tests/plugins/paint/test_paintgen_compatibility.py -v

# Import check
python -c "from appPlugins.ToolShared import ToolEntry, ToolManager, ToolTableHelper; print('OK')"
```

**Expected Output:**
```
tests/plugins/toolshared/test_types.py .................. 25 passed
tests/plugins/toolshared/test_tool_manager.py ........... 22 passed
tests/plugins/toolshared/test_tool_table_helper.py ...... 10 passed
tests/plugins/paint/test_paintgen_compatibility.py ...... 8 passed

============================== 65 passed in 0.50s ==============================
All imports OK
```

---

## Summary of Changes

| Component | Action | Lines | Notes |
|-----------|--------|-------|-------|
| `types.py` | CREATE | ~350 | ToolEntry + 4 param dataclasses |
| `ToolManager.py` | MODIFY | ~280 | Uses ToolEntry, adds search_tools_db(), reorder_tools() |
| `ToolTableHelper.py` | CREATE | ~600 | Main composition class |
| `__init__.py` | MODIFY | ~25 | Export all new classes |
| `Paint.py` | MODIFY | -600/+80 | Delegate ~15 methods to helper |
| Tests | CREATE | ~500 | Full coverage |
| **Net** | | **+655** | ~600 lines extracted from Paint.py |

---

## NCC Phase 2 Preparation

Once Phase 1 is verified stable:

1. Create NCC config:
```python
ncc_config = ToolTableConfig(
    log_prefix="ToolNcc",
    tool_target=_('NCC'),
    tool_key_prefix='tools_ncc_',
    db_source='ncc',
    combo_columns=[2],  # NCC only has col 2
    store_offset=False,  # NCC doesn't store offset
    generate_button_attr='generate_ncc_button',
    order_combo_attr='ncc_order_combo',
    rest_cb_attr='ncc_rest_cb',  # If exists
)
```

2. NCC doesn't have `rest_cb`, so `ui_connect`/`ui_disconnect` will be slightly different.

3. Same delegation pattern as Paint.py.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ToolEntry dict access breaks | Low | High | Extensive PaintGen compatibility tests |
| Reference lost in rebuild | Low | High | clear()/update() pattern verified |
| getHeight() missing | Medium | Medium | hasattr() check added |
| Combo columns mismatch | Low | Medium | Configurable via ToolTableConfig |

---

**Plan complete. Execute task-by-task using superpowers:executing-plans.**

Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 ToolPaint Refactoring Plan — Revised (Post-Audit)

 Context

 Problem: appPlugins/ToolPaint/Paint.py and appPlugins/ToolNCC/Ncc.py share ~60% identical tool management code (add/delete/edit tools, form↔storage
 sync, apply-params-to-all). PaintGen has no base class, preventing shared generator logic.

 Goal: Extract shared code into appPlugins/ToolShared/, using composition (ToolManager) and inheritance (BaseGenerator), while preserving 100%
 backward compatibility.

 What changed from Rev 6: A thorough code audit revealed critical issues — most importantly that tool['data'] is a 30+ key dict dynamically populated
 from app.options (geometry params + tools params), NOT the 8-field PaintToolData dataclass the old plan proposed. Using a narrow dataclass would
 break build_ui(), paint_geo(), and downstream GCode generation.

 ---
 Critical Fixes vs Rev 6

 ┌─────┬───────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────┐
 │  #  │                           Rev 6 Bug                           │                                   Fix                                    │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F1  │ PaintToolData has only 8 fields but data dict has 30+ dynamic │ Drop PaintToolData dataclass entirely. Keep data as Dict[str, Any]       │
 │     │  keys                                                         │                                                                          │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F2  │ BaseGenerator._validate_object fallback uses get_objects()    │ Use self.app.collection.get_list() (ObjectCollection API)                │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F3  │ BaseGenerator._copy_common_state missing                      │ Add it (PaintGen line 63 copies it)                                      │
 │     │ tool_type_item_options                                        │                                                                          │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F4  │ _clear_temp_shapes iterates list                              │ temp_shapes is a ShapeCollection — call .clear(update=True)              │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F5  │ Plan targets on_paint_tool_add_from_db_clicked for DB add     │ That method just opens DB UI. Actual add logic is on_tool_add() (line    │
 │     │                                                               │ 905)                                                                     │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F6  │ storage_to_form signature changed to (self, tooluid: int)     │ Keep original (self, dict_storage) — callers pass tool['data'] directly  │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F7  │ ToolManager.storage_to_form has nested data lookup            │ Not needed — it always receives tool['data'] directly                    │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F8  │ tool_type/type called "phantom fields" and removed            │ They ARE used — added dynamically by on_tooltable_cell_widget_change     │
 │     │                                                               │ (line 782)                                                               │
 ├─────┼───────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
 │ F9  │ ToolManager uses tool_factory for PaintTool dataclass         │ Not needed — tools remain plain dicts; factory adds complexity for no    │
 │     │ creation                                                      │ gain                                                                     │
 └─────┴───────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────┘

 ---
 Architecture

 appPlugins/ToolShared/ (NEW)
 ├── __init__.py
 ├── ToolManager.py      ← Generic tool CRUD, form↔storage, apply-to-all
 └── BaseGenerator.py    ← ABC for PaintGen (future: NccGen)

 appPlugins/ToolPaint/
 ├── Paint.py            ← MODIFY: compose ToolManager, delegate 6 methods
 ├── PaintGen.py         ← MODIFY: extend BaseGenerator, no logic changes
 ├── PaintUI.py          ← UNCHANGED
 └── __init__.py

 tests/plugins/paint/ (NEW)
 ├── __init__.py
 ├── test_tool_manager.py
 └── test_base_generator.py

 ---
 Tasks

 Task 1: Create appPlugins/ToolShared/__init__.py

 Empty package init.

 Create: appPlugins/ToolShared/__init__.py

 ---
 Task 2: Create appPlugins/ToolShared/ToolManager.py

 Generic tool management via composition. Works with plain dicts (current) — no dataclass dependency.

 Create: appPlugins/ToolShared/ToolManager.py

 """
 ToolManager: Shared tool management for Paint/NCC tools.
 Main-thread-only (no locking). Tools are plain dicts.
 """
 from typing import Any, Dict, List, Optional, Tuple
 from copy import deepcopy


 class ToolManager:
     """
     Manages a tools dict: {int(uid): {'tooldia': float, 'data': dict, 'solid_geometry': list, ...}}

     THREAD SAFETY: Main-thread-only. No locks.
     """

     def __init__(
         self,
         app: Any,
         tools_dict: Dict[int, dict],
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

     # ── Helpers ──────────────────────────────────────────────

     def _fmt_dia(self, diameter: float) -> float:
         return self.app.dec_format(diameter, self.decimals)

     def _next_uid(self) -> int:
         return max(self.tools.keys(), default=0) + 1

     def tool_exists(self, diameter: float) -> bool:
         truncated = self._fmt_dia(diameter)
         return any(
             self._fmt_dia(t['tooldia']) == truncated
             for t in self.tools.values()
         )

     # ── CRUD ─────────────────────────────────────────────────

     def add_tool(
         self,
         diameter: float,
         tool_data: Optional[dict] = None,
         solid_geometry: Optional[list] = None,
         extra_attrs: Optional[dict] = None,
     ) -> Optional[int]:
         """
         Add tool. Returns uid or None if duplicate.
         extra_attrs: for DB-path fields like offset/offset_value.
         """
         truncated = self._fmt_dia(diameter)
         if self.tool_exists(diameter):
             return None

         uid = self._next_uid()
         tool = {
             'tooldia': truncated,
             'data': tool_data if tool_data is not None else deepcopy(self.default_data),
             'solid_geometry': solid_geometry if solid_geometry is not None else [],
         }
         if extra_attrs:
             tool.update(extra_attrs)

         self.tools[uid] = tool
         return uid

     def delete_tools(self, uids: List[int]) -> int:
         count = 0
         for uid in uids:
             if uid in self.tools:
                 del self.tools[uid]
                 count += 1
         return count

     def edit_diameter(self, uid: int, new_dia: float) -> Tuple[bool, str]:
         if uid not in self.tools:
             return False, "Tool not found"
         truncated = self._fmt_dia(new_dia)
         for other_uid, t in self.tools.items():
             if other_uid != uid and self._fmt_dia(t['tooldia']) == truncated:
                 return False, "Duplicate diameter"
         self.tools[uid]['tooldia'] = truncated
         return True, "OK"

     # ── Form ↔ Storage ───────────────────────────────────────

     def storage_to_form(self, dict_storage: dict) -> None:
         """
         Populate UI form fields from a data dict.
         Caller passes tool['data'] directly (matching current Paint.py pattern).
         """
         for key in self.form_fields:
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
         Checks both tool-level and tool['data']-level keys (matching current pattern).
         """
         for uid in tooluids:
             tool = self.tools.get(uid)
             if tool is None:
                 continue
             if option_changed in tool:
                 tool[option_changed] = new_value
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
                 tool['data'] = deepcopy(source_data)
         return True

     # ── Query ────────────────────────────────────────────────

     def get_tool(self, uid: int) -> Optional[dict]:
         return self.tools.get(uid)

     def get_diameters(self) -> List[float]:
         return [t['tooldia'] for t in self.tools.values()]

 Acceptance:
 - Works with plain dicts — no dataclass dependency
 - storage_to_form(dict_storage) keeps original signature (F6, F7)
 - form_to_storage checks both tool-level and data-level keys
 - apply_params_to_all uses deepcopy (matches current semantics)
 - add_tool supports extra_attrs for offset/offset_value (DB path)
 - No locks (main-thread-only)
 - No tool_factory (F9)

 ---
 Task 3: Create appPlugins/ToolShared/BaseGenerator.py

 ABC for PaintGen (and future NccGen).

 Create: appPlugins/ToolShared/BaseGenerator.py

 """
 BaseGenerator: Base class for PaintGen and future NccGen.
 Main-thread-only.
 """
 from typing import Any, Optional, Tuple
 from abc import ABC, abstractmethod


 class BaseGenerator(ABC):

     def __init__(self, parent_tool: Any):
         self.parent_tool = parent_tool
         self.app = parent_tool.app
         self.ui = parent_tool.ui
         self._copy_common_state(parent_tool)

     def _copy_common_state(self, tool: Any) -> None:
         """
         Copy shared state from parent tool.
         Matches actual PaintGen.__init__ attributes (verified via jcode).
         Subclasses add their own tool-specific refs after super().__init__().
         """
         self.decimals = tool.decimals
         self.units = tool.units
         self.circle_steps = getattr(tool, 'circle_steps', 64)
         self.first_click = tool.first_click
         self.cursor_pos = getattr(tool, 'cursor_pos', None)
         self.mouse_is_dragging = getattr(tool, 'mouse_is_dragging', False)
         self.sel_rect = getattr(tool, 'sel_rect', [])
         self.grid_status_memory = getattr(tool, 'grid_status_memory', None)
         self.obj_name = getattr(tool, 'obj_name', '')
         self.bound_obj = getattr(tool, 'bound_obj', None)
         self.bound_obj_name = getattr(tool, 'bound_obj_name', '')
         self.mm = getattr(tool, 'mm', None)
         self.mr = getattr(tool, 'mr', None)
         self.kp = getattr(tool, 'kp', None)
         self.mp = getattr(tool, 'mp', None)
         self.points = getattr(tool, 'points', [])
         self.poly_drawn = getattr(tool, 'poly_drawn', False)
         self.area_sel_disconnect_flag = getattr(tool, 'area_sel_disconnect_flag', False)
         self.poly_sel_disconnect_flag = getattr(tool, 'poly_sel_disconnect_flag', False)
         self.temp_shapes = getattr(tool, 'temp_shapes', None)
         # F3: was missing in Rev 6
         self.tool_type_item_options = getattr(tool, 'tool_type_item_options', [])

     @abstractmethod
     def on_generate_click(self) -> None:
         """Handle generate button click."""
         pass

     @abstractmethod
     def paint_polygon_worker(
         self, polyg, tooldiameter, paint_method, over, conn, cont, prog_plot, obj
     ) -> Optional[Any]:
         pass

     def _validate_object(self, obj_name: str) -> Optional[Any]:
         """Validate and retrieve object by name. F2: uses get_by_name + get_list."""
         if not obj_name:
             return None
         try:
             obj = self.app.collection.get_by_name(obj_name)
             if obj is not None:
                 return obj
         except Exception:
             pass
         # Case-insensitive fallback
         obj_lower = obj_name.lower()
         for obj in self.app.collection.get_list():
             try:
                 if obj.obj_options['name'].lower() == obj_lower:
                     return obj
             except Exception:
                 continue
         self.app.log.error(f"Object not found: {obj_name}")
         return None

     def _clear_temp_shapes(self) -> None:
         """F4: temp_shapes is a ShapeCollection, not a list."""
         if self.temp_shapes is not None:
             try:
                 self.temp_shapes.clear(update=True)
             except Exception:
                 pass

     def _get_point_in_poly(self, polygon) -> Optional[Tuple[float, float]]:
         try:
             if hasattr(polygon, 'representative_point'):
                 pt = polygon.representative_point()
                 return (pt.x, pt.y)
             elif hasattr(polygon, 'centroid'):
                 pt = polygon.centroid
                 return (pt.x, pt.y)
         except Exception as e:
             self.app.log.error(f"Failed to get point in poly: {e}")
         return None

 Acceptance:
 - _copy_common_state includes all 21 shared attributes (verified against PaintGen.init)
 - Includes tool_type_item_options (F3)
 - _validate_object uses get_by_name() + get_list() (F2)
 - _clear_temp_shapes calls .clear(update=True) (F4)
 - No paint/ncc-specific refs in base class

 ---
 Task 4: Create test infrastructure

 Create:
 - tests/plugins/paint/__init__.py
 - tests/plugins/paint/test_tool_manager.py
 - tests/plugins/paint/test_base_generator.py

 Tests use bare assert + plain classes (matching existing project style, pytest-compatible).

 test_tool_manager.py covers:
 - add_tool returns uid, rejects duplicates
 - add_tool with extra_attrs (offset/offset_value for DB path)
 - delete_tools removes correct tools
 - edit_diameter succeeds, rejects duplicate
 - storage_to_form populates form fields from dict
 - form_to_storage updates both tool-level and data-level keys
 - apply_params_to_all deepcopies data to all tools
 - tool_exists check
 - _next_uid returns max+1

 test_base_generator.py covers:
 - _copy_common_state copies all expected attributes
 - _validate_object with get_by_name hit, miss + fallback
 - _clear_temp_shapes calls clear(update=True)

 Acceptance:
 - All tests pass with pytest tests/plugins/paint/ -v
 - Uses MockApp pattern matching existing tests

 ---
 Task 5: Integrate ToolManager into Paint.py

 Modify: appPlugins/ToolPaint/Paint.py

 5a. Add import (top of file):
 from appPlugins.ToolShared.ToolManager import ToolManager

 5b. Create ToolManager in set_tool_ui() (after self.form_fields and self.name2option are set, ~line 350):
 self.tool_manager = ToolManager(
     app=app,
     tools_dict=self.paint_tools,
     form_fields=self.form_fields,
     name2option=self.name2option,
     default_data=self.default_data,
     decimals=self.decimals,
 )

 5c. Delegate storage_to_form (line 684-689):
 def storage_to_form(self, dict_storage):
     self.tool_manager.storage_to_form(dict_storage)

 5d. Delegate form_to_storage (line 691-717):
 def form_to_storage(self):
     if self.ui.tools_table.rowCount() == 0:
         return
     self.blockSignals(True)

     widget_changed = self.sender()
     wdg_objname = widget_changed.objectName()
     option_changed = self.name2option[wdg_objname]

     rows = sorted(set(index.row() for index in self.ui.tools_table.selectedIndexes()))
     tooluids = []
     for row in rows:
         if row < 0:
             row = 0
         tooluids.append(int(self.ui.tools_table.item(row, 3).text()))

     new_value = self.form_fields[option_changed].get_value()
     self.tool_manager.form_to_storage(tooluids, option_changed, new_value)

     self.blockSignals(False)

 5e. Delegate on_apply_param_to_all_clicked (line 719-746):
 def on_apply_param_to_all_clicked(self):
     if self.ui.tools_table.rowCount() == 0:
         return
     self.blockSignals(True)

     row = self.ui.tools_table.currentRow()
     if row < 0:
         row = 0
     tooluid_item = int(self.ui.tools_table.item(row, 3).text())

     self.tool_manager.apply_params_to_all(tooluid_item)

     self.app.inform.emit('[success] %s' % _("Current Tool parameters were applied to all tools."))
     self.blockSignals(False)

 5f. Delegate on_tool_default_add (line 1055-1112):
 Replace the manual UID calculation, duplicate check, and dict construction with:
 tooluid = self.tool_manager.add_tool(
     diameter=tool_dia,
     tool_data=deepcopy(self.default_data),
     solid_geometry=[],
 )
 if tooluid is None:
     # duplicate or invalid
     self.blockSignals(False)
     return
 self.tooluid = tooluid
 Keep everything else (blockSignals, build_ui, selectRow, update_ui) as-is.

 5g. Delegate DB path in on_tool_add (line 1037-1046, F5):
 Replace the manual self.paint_tools.update({...}) block with:
 tooluid = self.tool_manager.add_tool(
     diameter=new_tdia,
     tool_data=deepcopy(new_tools_dict),
     solid_geometry=[],
     extra_attrs={
         'offset': deepcopy(offset),
         'offset_value': deepcopy(offset_val),
     },
 )

 What stays unchanged:
 - update_ui() — still calls self.storage_to_form(tooluid_value['data'])
 - build_ui() — still reads paint_tools dict directly (it's the same reference)
 - on_tooltable_cell_widget_change() — still adds type/tool_type dynamically (F8)
 - blockSignals wrapper — stays in Paint.py, NOT in ToolManager
 - All UI logic, signal connections, connect_signals()

 Acceptance:
 - storage_to_form signature unchanged: (self, dict_storage) (F6)
 - form_to_storage still uses self.sender() in Paint.py, passes extracted values to ToolManager
 - blockSignals stays in Paint.py (not ToolManager)
 - DB path uses extra_attrs for offset/offset_value (F5)
 - type/tool_type dynamic addition unchanged (F8)
 - update_ui() unchanged
 - build_ui() unchanged

 ---
 Task 6: Integrate BaseGenerator into PaintGen.py

 Modify: appPlugins/ToolPaint/PaintGen.py

 6a. Add import and extend:
 from appPlugins.ToolShared.BaseGenerator import BaseGenerator

 class PaintGen(BaseGenerator):
     def __init__(self, tool):
         super().__init__(tool)
         # Paint-specific refs (not in BaseGenerator)
         self.paint_obj = tool.paint_obj
         self.paint_tools = tool.paint_tools
         self.tooldia_list = tool.tooldia_list
         self.tooldia = tool.tooldia
         self.overlap = tool.overlap
         self.connect = tool.connect
         self.contour = tool.contour
         self.select_method = tool.select_method
         self.o_name = tool.o_name

 6b. Implement abstract on_generate_click:
 def on_generate_click(self):
     self.on_paint_button_click()

 6c. Remove duplicate attribute assignments:
 Current PaintGen.init (lines 79-85) has duplicate assignments:
 self.mr = tool.mr      # line 79  (first)
 self.mm = tool.mm      # line 80
 self.kp = tool.kp      # line 81  (first)
 self.mp = tool.mp      # line 82
 self.mr = tool.mr      # line 83  (DUPLICATE of line 79)
 self.kp = tool.kp      # line 84  (DUPLICATE of line 81)
 self.kp = tool.kp      # line 85  (TRIPLICATE of line 81)
 These are all moved into BaseGenerator._copy_common_state (each copied exactly once). The duplicates are simply dropped.

 What stays unchanged:
 - on_paint_button_click() — all existing logic preserved
 - paint_polygon_worker() — all 5 paint methods preserved exactly
 - paint_geo(), paint_poly(), paint_poly_all(), paint_poly_area(), paint_poly_ref() — unchanged
 - grace exception handling — unchanged (from camlib import grace)

 Acceptance:
 - PaintGen extends BaseGenerator
 - super().__init__(tool) copies 21 shared attributes (each once, no duplicates)
 - Paint-specific refs added after super call
 - No method implementations changed
 - grace handling preserved
 - Removed 21 lines of attribute copying + 3 duplicate lines from PaintGen.init

 ---
 What is Deferred

 ┌──────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┐
 │               Item               │                                             Why                                             │
 ├──────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
 │ PaintToolData dataclass          │ data dict has 30+ dynamic keys from app.options; strict typing would break GCode generation │
 ├──────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
 │ PaintTool top-level dataclass    │ Adds complexity with no immediate benefit while tools are plain dicts                       │
 ├──────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
 │ ToolNCC integration              │ Separate refactoring — same ToolManager pattern applies                                     │
 ├──────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Geometry serialization (WKB/WKT) │ Not needed; solid_geometry stays as-is                                                      │
 ├──────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
 │ tool_factory pattern             │ Plain dict construction is simpler and correct                                              │
 └──────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┘

 ---
 Verification

 1. Unit tests: pytest tests/plugins/paint/ -v
 2. Manual smoke test:
   - Open FlatCAM → Paint Tool
   - Add tool via diameter entry → verify appears in table
   - Add tool via Tools Database → verify offset/offset_value preserved
   - Change parameters → verify form_to_storage updates correct tools
   - Select tool → verify storage_to_form populates form
   - Click "Apply to All" → verify all tools get same params
   - Run paint operation (all 5 methods) → verify geometry output unchanged
   - Multi-select rows → change param → verify all selected tools updated
 3. Import check: python -c "from appPlugins.ToolShared.ToolManager import ToolManager; from appPlugins.ToolShared.BaseGenerator import BaseGenerator;
  print('OK')"
 4. No circular imports: Verify ToolShared imports nothing from ToolPaint
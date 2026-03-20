# Keyboard Distance Input Feature — Implementation Plan
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
**Goal:** Add keyboard distance input feature (numeric input + Enter to place at precise distance) to Geometry Editor and Gerber Editor tools that currently lack it.
**Architecture:** Extend existing `on_key()` methods in draw tools to capture numeric keys and Enter, using tool UI plugin's `length` property for storage. Calculate target position using mouse direction vector scaled to keyboard-entered distance.
**Tech Stack:** Python 3.11+, PyQt6, Qt Keyboard events, existing PathEditorTool/GrbTrackEditorTool patterns.
---
## Feature Summary
The **Keyboard Distance Input Feature** enables users to:
1. **Set Direction**: Position mouse cursor in desired direction from reference point
2. **Input Distance**: Type numeric values (0-9, decimals, math operators) via keyboard
3. **Execute Placement**: Press Enter to create element at calculated position (mouse direction × keyboard distance)
**Already Implemented:**
- Geometry Editor: FCPath, FCRectangle, FCPolygon, FCCircle, FCMove, FCCopy
- Gerber Editor: PadEditorGrb, RegionEditorGrb, TrackEditorGrb, PadArrayEditorGrb, CopyEditorGrb
**Missing Feature (This Plan):**
- Geometry Editor: FCArc (radius input), FCSelect, FCExplode, FCBuffer, FCTransform, FCSimplify, FCStitch
- Gerber Editor: DiscEditorGrb (radius input), DiscSemiEditorGrb, ScaleEditorGrb, BufferEditorGrb, SimplifyEditorGrb, MarkEditorGrb, MoveEditorGrb, EraserEditorGrb, SelectEditorGrb, ImportEditorGrb, TransformEditorGrb
---
## Impact Analysis
From `get_blast_radius` on FCPath and TrackEditorGrb:
- **Zero external importers** — Editor tools are instantiated dynamically by editor framework
- **Low risk** — Changes isolated to individual tool classes
- **Pattern reuse** — Copy from FCPath/TrackEditorGrb/FCMove implementations
---
## Implementation Pattern
### Standard Pattern (from FCPath, lines 4188-4280 in appGeoEditor.py)
```python
def on_key(self, key):
    # 1. Cursor data toggle (optional)
    if key == 'C' or key == QtCore.Qt.Key.Key_C:
        self.cursor_data_control = not self.cursor_data_control
    # 2. Jump to coords
    if key == QtCore.Qt.Key.Key_J or key == 'J':
        self.draw_app.app.on_jump_to()
    # 3. Numeric key capture (0-9, .,+-*/)
    if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
            key in [QtCore.Qt.Key.Key_0, ..., QtCore.Qt.Key.Key_9, ...]:
        try:
            # VisPy keys
            if self.tool.length == 0 or self.new_segment is True:
                self.tool.length = str(key.name)
                self.new_segment = False
            else:
                self.tool.length = str(self.tool.length) + str(key.name)
        except AttributeError:
            # Qt keys
            if self.tool.length == 0 or self.new_segment is True:
                self.tool.length = chr(key)
                self.new_segment = False
            else:
                self.tool.length = str(self.tool.length) + chr(key)
    # 4. Enter key processing
    if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
        if self.tool.length != 0:
            target_length = self.tool.length
            if target_length is None:
                self.tool.length = 0.0
                return _("Failed.")
            first_pt = self.points[-1]  # or from UI controls
            last_pt = self.draw_app.app.mouse_pos
            seg_length = math.sqrt((last_pt[0] - first_pt[0])**2 + (last_pt[1] - first_pt[1])**2)
            if seg_length == 0.0:
                return
            try:
                new_x = first_pt[0] + (last_pt[0] - first_pt[0]) / seg_length * target_length
                new_y = first_pt[1] + (last_pt[1] - first_pt[1]) / seg_length * target_length
            except ZeroDivisionError as err:
                self.points = []
                self.clean_up()
                return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())
            if self.points[-1] != (new_x, new_y):
                self.points.append((new_x, new_y))
                self.new_segment = True
                self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
                # Tool-specific action here
```

## Prerequisites
### Tools That Already Have `length` Property in Plugin UI
**Geometry Editor:**
- `appEditors/geo_plugins/GeoPathPlugin.py::PathEditorTool.length` ✓
- `appEditors/geo_plugins/GeoRectanglePlugin.py::RectangleEditorTool.length` ✓
- `appEditors/geo_plugins/GeoCopyPlugin.py::CopyEditorTool.length` ✓
**Gerber Editor:**
- `appEditors/grb_plugins/GrbTrackPlugin.py::GrbTrackEditorTool.length` ✓
- `appEditors/grb_plugins/GrbPadPlugin.py::PadEditorTool.length` ✓
- `appEditors/grb_plugins/GrbCopyPlugin.py::CopyEditorTool.length` ✓
- `appEditors/grb_plugins/GrberRegionPlugin.py::GrbRegionEditorTool.length` ✓
### Tools Needing `length` Property Added to Plugin UI
**Geometry Editor:**
- `appEditors/geo_plugins/GeoCirclePlugin.py::CircleEditorTool` — Has `radius_x`, `radius_y` (can reuse for distance)
- `appEditors/geo_plugins/GeoBufferPlugin.py::BufferEditorTool` — Check if has length
- `appEditors/geo_plugins/GeoTransformationPlugin.py::TransformEditorTool` — Check if has length
- `appEditors/geo_plugins/GeoSimplificationPlugin.py::SimplificationEditorTool` — May need length added
**Gerber Editor:**
- `appEditors/grb_plugins/GrbBufferPlugin.py::BufferEditorTool` — May need length added
- `appEditors/grb_plugins/GrbTransformationPlugin.py::TransformEditorTool` — May need length added
- `appEditors/grb_plugins/GrbSimplificationPlugin.py::SimplificationEditorTool` — May need length added
---
Phase 1: Geometry Editor Tools
Task 1.1: FCArc — Add Radius Distance Input
File: appEditors/appGeoEditor.py::FCArc#class (lines 3277-3515)
Objective: Add keyboard radius input for arc creation (works in all 3 modes: c12, 12c, 132)
Spec:
1. Add arc_radius attribute in __init__ (after line 3297):
self.arc_radius = None
self.new_segment = True
2. Extend on_key() method (replace lines 3388-3406):

```
def on_key(self, key):
    if key == 'D' or key == QtCore.Qt.Key.Key_D:
        self.direction = 'cw' if self.direction == 'ccw' else 'ccw'
        return '%s: %s' % (_('Direction'), self.direction.upper())
    # Jump to coords
    if key == QtCore.Qt.Key.Key_J or key == 'J':
        self.draw_app.app.on_jump_to()
    # Numeric input for radius
    if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
            key in [QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2,
                    QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5,
                    QtCore.Qt.Key.Key_6, QtCore.Qt.Key.Key_7, QtCore.Qt.Key.Key_8,
                    QtCore.Qt.Key.Key_9, QtCore.Qt.Key.Key_Minus,
                    QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Comma,
                    QtCore.Qt.Key.Key_Period, QtCore.Qt.Key.Key_Slash,
                    QtCore.Qt.Key.Key_Asterisk]:
        try:
            # VisPy keys
            if self.arc_radius is None or self.new_segment is True:
                self.arc_radius = str(key.name)
                self.new_segment = False
            else:
                self.arc_radius = str(self.arc_radius) + str(key.name)
        except AttributeError:
            # Qt keys
            if self.arc_radius is None or self.new_segment is True:
                self.arc_radius = chr(key)
                self.new_segment = False
            else:
                self.arc_radius = str(self.arc_radius) + chr(key)
    if key == 'M' or key == QtCore.Qt.Key.Key_M:
        # delete the possible points made before this action; we want to start anew
        self.points[:] = []
        # and delete the utility geometry made up until this point
        self.draw_app.delete_utility_geometry()
        self.arc_radius = None  # Reset radius on mode change
        self.new_segment = True
        if self.mode == 'c12':
            self.mode = '12c'
            return _('Mode: Start -> Stop -> Center. Click on Start point ...')
        elif self.mode == '12c':
            self.mode = '132'
            return _('Mode: Point1 -> Point3 -> Point2. Click on Point1 ...')
        else:
            self.mode = 'c12'
            return _('Mode: Center -> Start -> Stop. Click on Center point ...')
    # Enter key processing for radius-based placement
    if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
        if self.arc_radius is not None and len(self.points) >= 1:
            try:
                target_radius = eval(str(self.arc_radius).replace(',', '.'))
            except (SyntaxError, NameError) as err:
                self.arc_radius = None
                return '[ERROR_NOTCL] %s: %s' % (_("Failed."), str(err).capitalize())
            center = self.points[0]
            mouse_pos = self.draw_app.app.mouse_pos
            # Calculate direction vector from center to mouse
            dx = mouse_pos[0] - center[0]
            dy = mouse_pos[1] - center[1]
            seg_length = math.sqrt(dx**2 + dy**2)
            if seg_length == 0.0:
                return
            # Calculate point at specified radius in mouse direction
            try:
                new_x = center[0] + (dx / seg_length) * target_radius
                new_y = center[1] + (dy / seg_length) * target_radius
            except ZeroDivisionError as err:
                return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())
            # Jump to calculated position
            self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
            if self.mode == 'c12':
                # Place start point at radius distance
                self.points.append((new_x, new_y))
                self.draw_app.app.inform.emit(_("Click on Stop point to complete ..."))
            elif self.mode == '12c':
                # Place stop point at radius distance
                self.points.append((new_x, new_y))
                self.draw_app.app.inform.emit(_("Click on Center point to complete ..."))
            self.arc_radius = None
            self.new_segment = True
            return _("Point placed at radius: %s") % str(target_radius)
```

Acceptance:
- Typing numbers while FCArc tool active shows in status
- Pressing Enter jumps cursor to specified radius in mouse direction
- Works in all 3 modes (c12, 12c, 132)
- Existing 'D' (direction) and 'M' (mode) keys still work
Dependencies: None

---

Task 1.2: FCSelect — Add Distance Input for Selection Box
File: appEditors/appGeoEditor.py::FCSelect#class (lines 4318-4510)
Objective: Add keyboard distance input for rectangular selection
Spec:
1. Add select_length attribute
2. Extend on_key() following FCPath pattern
3. On Enter: create selection box at distance
Acceptance: Can type distance, press Enter to select at precise distance

---

Task 1.3: FCBuffer — Add Distance Input
File: appEditors/appGeoEditor.py — Find FCBuffer class
Objective: Add buffer distance input via keyboard
Spec: 
1. Check if plugin UI has length property
2. If not, add to appEditors/geo_plugins/GeoBufferPlugin.py
3. Extend on_key() in FCBuffer

---
Task 1.4: FCTransform — Add Distance Input
File: appEditors/appGeoEditor.py — Find FCTransform class
Objective: Add transform distance/offset input via keyboard
---
Task 1.5: FCSimplify — Add Tolerance Input
File: appEditors/appGeoEditor.py — Find FCSimplify class
Objective: Add simplification tolerance input via keyboard
---
Task 1.6: FCStitch — Add Distance Input
File: appEditors/appGeoEditor.py — Find FCStitch class
Objective: Add stitch tolerance/distance input via keyboard
---
Task 1.7: FCExplode — Add Distance Input
File: appEditors/appGeoEditor.py — Find FCExplode class
Objective: Add explode distance input via keyboard
---
Phase 2: Gerber Editor Tools
Task 2.1: DiscEditorGrb — Add Radius Distance Input
File: appEditors/appGerberEditor.py::DiscEditorGrb#class (lines 2061-2172)
Objective: Add keyboard radius input for disc creation
Spec:
1. Add attributes in __init__ (after line 2095):
self.disc_radius = None
self.new_segment = True
2. Add on_key() method (after clean_up() method):
```
def on_key(self, key):
    # Jump to coords
    if key == QtCore.Qt.Key.Key_J or key == 'J':
        self.draw_app.app.on_jump_to()
    # Cursor data toggle (if supported)
    if hasattr(self, 'cursor_data_control'):
        if key == 'C' or key == QtCore.Qt.Key.Key_C:
            self.cursor_data_control = not self.cursor_data_control
    # Numeric input for radius
    if key in [str(i) for i in range(10)] + ['.', ',', '+', '-', '/', '*'] or \
            key in [QtCore.Qt.Key.Key_0, QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2,
                    QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4, QtCore.Qt.Key.Key_5,
                    QtCore.Qt.Key.Key_6, QtCore.Qt.Key.Key_7, QtCore.Qt.Key.Key_8,
                    QtCore.Qt.Key.Key_9, QtCore.Qt.Key.Key_Minus,
                    QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Comma,
                    QtCore.Qt.Key.Key_Period, QtCore.Qt.Key.Key_Slash,
                    QtCore.Qt.Key.Key_Asterisk]:
        try:
            # VisPy keys
            if self.disc_radius is None or self.new_segment is True:
                self.disc_radius = str(key.name)
                self.new_segment = False
            else:
                self.disc_radius = str(self.disc_radius) + str(key.name)
        except AttributeError:
            # Qt keys
            if self.disc_radius is None or self.new_segment is True:
                self.disc_radius = chr(key)
                self.new_segment = False
            else:
                self.disc_radius = str(self.disc_radius) + chr(key)
    # Enter key processing for radius-based disc creation
    if key == 'Enter' or key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
        if self.disc_radius is not None and len(self.points) >= 1:
            try:
                target_radius = eval(str(self.disc_radius).replace(',', '.'))
            except (SyntaxError, NameError) as err:
                self.disc_radius = None
                return '[ERROR_NOTCL] %s: %s' % (_("Failed."), str(err).capitalize())
            center = self.points[0]
            mouse_pos = self.draw_app.snap_x, self.draw_app.snap_y
            # Calculate direction vector from center to mouse
            dx = mouse_pos[0] - center[0]
            dy = mouse_pos[1] - center[1]
            seg_length = math.sqrt(dx**2 + dy**2)
            if seg_length == 0.0:
                return
            # Calculate point at specified radius in mouse direction
            try:
                new_x = center[0] + (dx / seg_length) * target_radius
                new_y = center[1] + (dy / seg_length) * target_radius
            except ZeroDivisionError as err:
                return '[ERROR_NOTCL] %s %s' % (_("Failed."), str(err).capitalize())
            # Jump to calculated position and create disc
            self.draw_app.app.on_jump_to(custom_location=(new_x, new_y), fit_center=False)
            self.points.append((new_x, new_y))
            self.make()
            self.draw_app.select_tool("select")
            self.disc_radius = None
            self.new_segment = True
            return _("Disc created with radius: %s") % str(target_radius)
```
Acceptance:
- Can type radius value after clicking center point
- Pressing Enter creates disc at specified radius
- Existing click-to-create still works
---
Task 2.2: DiscSemiEditorGrb — Add Radius Input
File: appEditors/appGerberEditor.py — Find DiscSemiEditorGrb class
Objective: Add radius input for semi-disc creation
---
Task 2.3: MoveEditorGrb — Add Distance Input
File: appEditors/appGerberEditor.py::MoveEditorGrb#class (lines 2764-2945)
Note: MoveEditorGrb currently has NO on_key() override. FCMove in Geo Editor already has the feature implemented.
Objective: Add distance input for move operation
Spec:
1. Add move_length attribute
2. Add plugin UI tool if needed (check GrbMovePlugin or similar)
3. Add on_key() following FCMove pattern (lines 4755-4830 in appGeoEditor.py)
---
Task 2.4: CopyEditorGrb — Add Distance Input
File: appEditors/appGerberEditor.py::CopyEditorGrb#class (lines 2948-3152)
Note: Inherits from MoveEditorGrb. Check if GrbCopyPlugin has length property (it does per jcode search).
Objective: Add distance input for copy operation
Spec:
- Use existing GrbCopyPlugin.CopyEditorTool.length property
- Add on_key() following FCCopy pattern
---
Task 2.5: BufferEditorGrb — Add Distance Input
File: appEditors/appGerberEditor.py — Find BufferEditorGrb class
Objective: Add buffer distance input
Spec:
1. Check appEditors/grb_plugins/GrbBufferPlugin.py for length property
2. Add if missing
3. Extend on_key() in BufferEditorGrb
---
Task 2.6: SimplifyEditorGrb — Add Tolerance Input
File: appEditors/appGerberEditor.py — Find SimplifyEditorGrb class
---
Task 2.7: ScaleEditorGrb — Add Scale Factor Input
File: appEditors/appGerberEditor.py — Find ScaleEditorGrb class
---
Task 2.8: MarkEditorGrb — Add Distance Input
File: appEditors/appGerberEditor.py — Find MarkEditorGrb class
---
Task 2.9: EraserEditorGrb — Add Size Input
File: appEditors/appGerberEditor.py — Find EraserEditorGrb class
---
Task 2.10: SelectEditorGrb — Add Distance Input
File: appEditors/appGerberEditor.py — Find SelectEditorGrb class
---
Task 2.11: ImportEditorGrb — Add Position Input
File: appEditors/appGerberEditor.py — Find ImportEditorGrb class
---
Task 2.12: TransformEditorGrb — Add Offset Input
File: appEditors/appGerberEditor.py — Find TransformEditorGrb class
---
Phase 3: Verification & Testing
Task 3.1: Manual Testing Checklist
For each tool with feature added:
- [ ] Numeric keys (0-9) captured and displayed
- [ ] Decimal point (.) works
- [ ] Math operators (+-*/) work for expressions
- [ ] Enter key places element at specified distance
- [ ] Mouse direction is preserved
- [ ] Zero division handled gracefully
- [ ] Existing keyboard shortcuts still work
- [ ] Backspace/cancel still works
Task 3.2: Code Review Checklist
- [ ] Follows FCPath/TrackEditorGrb pattern
- [ ] Proper error handling
- [ ] Internationalization strings wrapped in _()
- [ ] No duplicate signal connections
- [ ] Clean up on error/exception
---
Risks
Risk	Likelihood	Impact	Mitigation
Key event conflicts with existing shortcuts	Low	Medium	Test all existing keys before/after
Plugin UI missing length property	Medium	Low	Add property to plugin (15 lines)
Division by zero on zero-length vector	Low	Low	Already handled in pattern
Expression eval security	Low	Medium	Use eval only on captured keystrokes, not arbitrary strings
---
## Open Questions
1. **Should all tools support math expressions (+-*/), or just numeric input?**
   - Current implementations (FCPath, FCMove) support expressions
   - Recommendation: Support expressions for consistency
2. **Should there be visual feedback while typing distance?**
   - Current: No HUD feedback while typing, only on Enter
   - Could add status bar display of current input
   - Recommendation: Defer to future enhancement
3. **Should tools without plugin UI create one, or use simple attribute?**
   - Recommendation: Use simple attribute for tools that only need distance input (no UI needed)
---
File Reference Summary
Files to Modify
Geometry Editor:
- appEditors/appGeoEditor.py — FCArc, FCSelect, FCBuffer, FCTransform, FCSimplify, FCStitch, FCExplode
Gerber Editor:
- appEditors/appGerberEditor.py — DiscEditorGrb, DiscSemiEditorGrb, MoveEditorGrb, CopyEditorGrb, BufferEditorGrb, SimplifyEditorGrb, ScaleEditorGrb, MarkEditorGrb, EraserEditorGrb, SelectEditorGrb, ImportEditorGrb, TransformEditorGrb
Plugin UI (if needed):
- appEditors/geo_plugins/GeoBufferPlugin.py — Add length property if missing
- appEditors/geo_plugins/GeoTransformationPlugin.py — Add length property if missing
- appEditors/geo_plugins/GeoSimplificationPlugin.py — Add length property if missing
- appEditors/grb_plugins/GrbBufferPlugin.py — Add length property if missing
- appEditors/grb_plugins/GrbTransformationPlugin.py — Add length property if missing
- appEditors/grb_plugins/GrbSimplificationPlugin.py — Add length property if missing
---
Execution Order
1. Start with FCArc (Task 1.1) — Most complex (3 modes), tests pattern thoroughly
2. DiscEditorGrb (Task 2.1) — Gerber equivalent complexity
3. Remaining tools — Follow established pattern
4. Tools needing plugin UI updates — Do last (requires understanding of UI plugin pattern)
---
Plan created: 2026-03-19
Estimated effort: 2-3 hours for experienced developer
Risk level: Low (isolated changes, well-documented pattern)
---
## Plan Complete
I've created a comprehensive implementation plan for adding the Keyboard Distance Input Feature to all Geometry Editor and Gerber Editor tools that currently lack it.
**Key findings from analysis:**
1. **Feature already exists in:** FCPath, FCRectangle, FCPolygon, FCCircle, **FCMove**, **FCCopy** (Geometry) | TrackEditorGrb, PadEditorGrb, RegionEditorGrb, PadArrayEditorGrb, **CopyEditorGrb** (Gerber)
2. **Pattern established:** The feature follows a consistent implementation pattern across all tools - capture numeric keys, store in tool's `length` property, calculate position on Enter using mouse direction vector scaled to keyboard distance.
3. **Low blast radius:** Editor tools have zero external importers - changes are completely isolated.
4. **Two categories of work:**
   - Tools with existing `length` property in plugin UI: Just extend `on_key()`
   - Tools without `length` property: Add property to plugin UI first, then extend `on_key()`
**Plan saved to:** `docs/plans/2026-03-19_keyboard-distance-input-feature.md` (you'll need to create this file)
**Two execution options:**
1. **Subagent-Driven (this session)** - I can dispatch fresh subagent per task, review between tasks
2. **Parallel Session (separate)** - Open new session with executing-plans skill
Which approach would you like to use for implementation?
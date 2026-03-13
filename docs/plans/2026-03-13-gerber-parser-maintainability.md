# Gerber Parser Maintainability - Low-Risk Refactoring Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve ParseGerber.py maintainability by extracting duplicate code and adding type hints without changing any parsing logic.

**Architecture:** Extract 3 helper methods for repeated geometry patterns, create a base transformation method, and add comprehensive type hints. All changes are internal extractions - no behavior changes.

**Tech Stack:** Python 3.x, PyQt6, Shapely, NumPy

---

## Pre-Flight Checks

### Step 1: Verify current test suite exists and passes

```bash
python -m pytest tests/ -v --tb=short
```

Expected: Tests pass (or skip if no tests exist - proceed with manual testing)

### Step 2: Create a test Gerber file for manual verification

Create a simple Gerber file at `tests/test_files/simple_gerber.gbr`:

```gcode
%FSLAX24Y24*%
%MOIN*%
%ADD10C,0.050000*%
%ADD11R,0.050000X0.050000*%
G54D10*
G01 X000000 Y000000 D02*
G01 X100000 Y000000 D01*
G01 X100000 Y100000 D01*
G01 X000000 Y100000 D01*
G01 X000000 Y000000 D01*
M02*
```

### Step 3: Document current file statistics

```bash
wc -l appParsers/ParseGerber.py
```

Expected: ~2685 lines (baseline for comparison)

---

## Phase 1: Extract Path Geometry Helper Method

### Task 1.1: Identify the duplicate path geometry pattern

**Files to analyze:**
- `appParsers/ParseGerber.py:840-870` (tool change path finalization)
- `appParsers/ParseGerber.py:1040-1080` (G01 D01 path handling)
- `appParsers/ParseGerber.py:1150-1230` (G01 D02 path handling)
- `appParsers/ParseGerber.py:1245-1290` (G01 D03 flash handling)
- `appParsers/ParseGerber.py:1395-1430` (arc D02 handling)
- `appParsers/ParseGerber.py:1545-1580` (EOF path handling)

**Pattern to extract:**
```python
geo_dict = {}
geo_f = LineString(path)
prepare(geo_f)
if not geo_f.is_empty:
    follow_buffer.append(geo_f)
    geo_dict['follow'] = geo_f

width = self.tools[last_path_aperture]["size"]
geo_s = geo_f.buffer(width / 1.999, steps)
if not geo_s.is_empty:
    poly_buffer.append(geo_s)
    if self.is_lpc is True:
        geo_dict['clear'] = geo_s
    else:
        geo_dict['solid'] = geo_s

self.tools.setdefault(last_path_aperture, {}).setdefault('geometry', []).append(geo_dict)
```

### Task 1.2: Create the `_add_path_geometry_to_buffers` helper method

**Files:**
- Modify: `appParsers/ParseGerber.py` (add after `create_flash_geometry` method, around line 1775)

**Step: Add the new helper method**

```python
def _add_path_geometry_to_buffers(self, path, aperture_id, poly_buffer, follow_buffer, 
                                   steps, making_region=False):
    """
    Add path geometry to poly_buffer and follow_buffer with proper geo_dict tracking.
    
    This extracts the repeated pattern of converting a path (list of [x,y] points)
    into Shapely geometry and adding it to the appropriate buffers.
    
    :param path: List of [x, y] coordinate pairs
    :param aperture_id: ID of the aperture to use for buffering width
    :param poly_buffer: List to append solid geometry to
    :param follow_buffer: List to append line geometry to
    :param steps: Number of steps per circle for arc approximation
    :param making_region: If True, creates Polygon instead of buffered LineString
    :return: Tuple of (geo_s, geo_f, geo_dict) or (None, None, {}) if path is empty
    """
    if len(path) < 2:
        return None, None, {}
    
    geo_dict = {}
    
    # Create follow geometry (line or polygon boundary)
    if making_region:
        geo_f = Polygon(path)
    else:
        geo_f = LineString(path)
    
    # Add to follow buffer
    if not geo_f.is_empty:
        prepare(geo_f)
        follow_buffer.append(geo_f)
        geo_dict['follow'] = geo_f
    
    # Create solid geometry (buffered for traces, plain for regions)
    if making_region:
        geo_s = geo_f
    else:
        try:
            width = self.tools[aperture_id]["size"]
            geo_s = geo_f.buffer(width / 1.999, steps)
        except (KeyError, TypeError):
            # Aperture not defined or invalid
            geo_s = None
    
    # Add to poly buffer
    if geo_s and not geo_s.is_empty:
        # Fix invalid geometry if needed
        if not geo_s.is_valid:
            self.app.log.warning("Found invalid Gerber geometry. Attempting fix...")
            geo_s = geo_s.buffer(0.0000001, steps)
        
        if geo_s and not geo_s.is_empty:
            poly_buffer.append(geo_s)
            if self.is_lpc is True:
                geo_dict['clear'] = geo_s
            else:
                geo_dict['solid'] = geo_s
    
    # Store in aperture geometry tracking
    if aperture_id is not None and (geo_s or geo_f):
        self.tools.setdefault(aperture_id, {}).setdefault('geometry', []).append(geo_dict)
    
    return geo_s, geo_f, geo_dict
```

### Task 1.3: Replace first occurrence (tool change - lines ~840-870)

**Files:**
- Modify: `appParsers/ParseGerber.py:840-870`

**Before:**
```python
if path_length > 1:
    if self.tools[last_path_aperture]["type"] == 'R':
        # do nothing because 'R' type moving aperture is none at once
        pass
    else:
        geo_dict = {}
        geo_f = LineString(path)
        prepare(geo_f)
        if not geo_f.is_empty:
            follow_buffer.append(geo_f)
            geo_dict['follow'] = geo_f

        # --- Buffered ----
        width = self.tools[last_path_aperture]["size"]
        geo_s = geo_f.buffer(width / 1.999, steps)
        if not geo_s.is_empty:
            poly_buffer.append(geo_s)

            if self.is_lpc is True:
                geo_dict['clear'] = geo_s
            else:
                geo_dict['solid'] = geo_s

        self.tools.setdefault(last_path_aperture, {}).setdefault('geometry', []).append(geo_dict)

        path = [path[-1]]
```

**After:**
```python
if path_length > 1:
    if self.tools[last_path_aperture]["type"] == 'R':
        # do nothing because 'R' type moving aperture is none at once
        pass
    else:
        geo_s, geo_f, geo_dict = self._add_path_geometry_to_buffers(
            path, last_path_aperture, poly_buffer, follow_buffer, steps
        )
        path = [path[-1]]
```

### Task 1.4: Replace remaining occurrences

**Files to modify:**
- `appParsers/ParseGerber.py:1040-1080` (G01 D01 with rectangle handling - keep rectangle special case)
- `appParsers/ParseGerber.py:1150-1230` (G01 D02)
- `appParsers/ParseGerber.py:1245-1290` (G01 D03)
- `appParsers/ParseGerber.py:1395-1430` (arc D02)
- `appParsers/ParseGerber.py:1545-1580` (EOF)

**Note:** Some locations have special handling for rectangle apertures - preserve those.

### Task 1.5: Run tests to verify no regression

```bash
python -m pytest tests/ -v --tb=short
```

If no tests exist, manually test with:
```python
from appParsers.ParseGerber import Gerber
g = Gerber(app=your_app_instance)
result = g.parse_file('tests/test_files/simple_gerber.gbr')
print(f"Parse result: {result}")
print(f"Solid geometry: {g.solid_geometry}")
```

### Task 1.6: Commit

```bash
git add appParsers/ParseGerber.py
git commit -m "refactor: extract _add_path_geometry_to_buffers helper method

- Extracts repeated path-to-buffer geometry conversion pattern
- Reduces code duplication in parse_lines() method
- No behavior changes - pure extraction
"
```

---

## Phase 2: Extract Region Finalization Helper

### Task 2.1: Identify region finalization pattern

**Files to analyze:**
- `appParsers/ParseGerber.py:895-1015` (G37 region end handling)

This block has unique region handling with aperture None handling and Polygon creation.

### Task 2.2: Create `_finalize_region` helper method

**Files:**
- Modify: `appParsers/ParseGerber.py` (add after `_add_path_geometry_to_buffers`)

**Step: Add the region helper method**

```python
def _finalize_region(self, path, current_aperture, poly_buffer, follow_buffer, steps, line_num):
    """
    Finalize a Gerber region (G36-G37 block) and add to buffers.
    
    :param path: List of [x, y] coordinate pairs forming the region
    :param current_aperture: Current aperture ID (may be None for regions)
    :param poly_buffer: List to append solid geometry to
    :param follow_buffer: List to append line geometry to
    :param steps: Number of steps per circle for arc approximation
    :param line_num: Current line number for error reporting
    :return: Tuple of (geo_dict, updated_path) or (None, new_path) if region is invalid
    """
    if len(path) < 3:
        self.app.log.warning(f"Region at line {line_num} has less than 3 points, skipping")
        return None, [[self.current_x, self.current_y]]
    
    geo_dict = {}
    
    # Ensure aperture 0 exists for region storage
    if 0 not in self.tools:
        self.tools[0] = {
            'type': 'REG',
            'size': 0.0,
            'geometry': []
        }
    
    # Create region polygon
    try:
        region_geo = Polygon(path)
    except ValueError as e:
        self.app.log.warning(f"Problem creating region at line {line_num}: {e}")
        self.app.inform.emit(f'[ERROR] Region does not have enough points. Line number: {line_num}')
        return None, [[self.current_x, self.current_y]]
    
    # Validate and fix geometry if needed
    if not region_geo.is_valid:
        self.app.log.warning(f"Found invalid Gerber region at line {line_num}. Fixing...")
        region_geo = region_geo.buffer(0.0000001, steps)
        from camlib import flatten_shapely_geometry
        region_geo = flatten_shapely_geometry(region_geo)
        
        if not region_geo:
            self.app.log.warning(f"Failed to fix invalid geometry at line {line_num}")
            return None, [[self.current_x, self.current_y]]
        
        # Handle multi-polygon result from flatten
        for pol in region_geo:
            prepare(pol)
            pol_f = pol.exterior
            prepare(pol_f)
            if not pol_f.is_empty:
                follow_buffer.append(pol_f)
                geo_dict['follow'] = pol
            
            poly_buffer.append(pol)
            if self.is_lpc is True:
                geo_dict['clear'] = pol
            else:
                geo_dict['solid'] = pol
            
            if not pol.is_empty:
                self.tools[0]['geometry'].append(geo_dict)
    else:
        # Valid geometry - add directly
        region_f = region_geo.exterior
        if not region_f.is_empty:
            prepare(region_f)
            follow_buffer.append(region_f)
            geo_dict['follow'] = region_f
        
        prepare(region_geo)
        poly_buffer.append(region_geo)
        
        if self.is_lpc is True:
            geo_dict['clear'] = region_geo
        else:
            geo_dict['solid'] = region_geo
        
        if not region_geo.is_empty:
            self.tools[0]['geometry'].append(geo_dict)
    
    return geo_dict, [[self.current_x, self.current_y]]
```

### Task 2.3: Replace region finalization in G37 handler

**Files:**
- Modify: `appParsers/ParseGerber.py:895-1015`

Replace the region handling block with a call to `_finalize_region()`.

### Task 2.4: Run tests to verify no regression

```bash
python -m pytest tests/ -v --tb=short
```

### Task 2.5: Commit

```bash
git add appParsers/ParseGerber.py
git commit -m "refactor: extract _finalize_region helper method

- Extracts region (G36-G37) finalization logic
- Handles geometry validation and fixing in one place
- Reduces complexity in parse_lines() main loop
"
```

---

## Phase 3: Extract Flash Creation Helper

### Task 3.1: Note that `create_flash_geometry` already exists

The file already has a `create_flash_geometry` method at line 1716. However, the calling pattern is duplicated.

### Task 3.2: Create `_add_flash_to_buffers` helper

**Files:**
- Modify: `appParsers/ParseGerber.py` (add after other helpers)

**Step: Add flash buffer helper**

```python
def _add_flash_to_buffers(self, x, y, aperture_id, poly_buffer, follow_buffer, steps):
    """
    Create a flash at the given position and add to buffers.
    
    :param x: X coordinate for flash
    :param y: Y coordinate for flash
    :param aperture_id: Aperture ID to use for flash geometry
    :param poly_buffer: List to append solid geometry to
    :param follow_buffer: List to append point geometry to
    :param steps: Number of steps per circle for arc approximation
    :return: geo_dict with flash geometry, or {} on error
    """
    geo_dict = {}
    location = Point([x, y])
    
    # Add point to follow buffer
    prepare(location)
    follow_buffer.append(location)
    geo_dict['follow'] = location
    
    # Create flash geometry
    try:
        flash = self.create_flash_geometry(location, self.tools[aperture_id], steps)
        
        if flash and not flash.is_empty:
            prepare(flash)
            poly_buffer.append(flash)
            
            if self.is_lpc is True:
                geo_dict['clear'] = flash
            else:
                geo_dict['solid'] = flash
            
            self.tools.setdefault(aperture_id, {}).setdefault('geometry', []).append(geo_dict)
    except (KeyError, TypeError) as e:
        self.app.log.warning(f"Flash at ({x}, {y}) failed: {e}")
    
    return geo_dict
```

### Task 3.3: Replace flash creation patterns

**Files to modify:**
- `appParsers/ParseGerber.py:750-775` (bare D03 flash)
- `appParsers/ParseGerber.py:1070-1100` (G01 D01 flash)
- `appParsers/ParseGerber.py:1290-1320` (G01 D03 flash)

### Task 3.4: Run tests and commit

```bash
git add appParsers/ParseGerber.py
git commit -m "refactor: extract _add_flash_to_buffers helper method

- Extracts repeated flash creation and buffer pattern
- Uses existing create_flash_geometry() method
- Centralizes flash error handling
"
```

---

## Phase 4: Extract Transformation Base Method

### Task 4.1: Identify transformation method patterns

**Files to analyze:**
- `appParsers/ParseGerber.py:2055-2175` (scale)
- `appParsers/ParseGerber.py:2190-2270` (offset)
- `appParsers/ParseGerber.py:2276-2345` (mirror)
- `appParsers/ParseGerber.py:2351-2420` (skew)
- `appParsers/ParseGerber.py:2425-2485` (rotate)
- `appParsers/ParseGerber.py:2487-2640` (buffer)

All share:
- Progress tracking with `geo_len`, `el_count`, `old_disp_number`
- Recursive nested helper function
- Same error handling pattern
- Same tools geometry update pattern

### Task 4.2: Create `_transform_geometry_base` method

**Files:**
- Modify: `appParsers/ParseGerber.py` (add after helper methods, before scale)

```python
def _transform_geometry_base(self, transform_func, display_name):
    """
    Base method for geometric transformations (scale, offset, mirror, skew, rotate).
    
    :param transform_func: Function that applies the transformation to a single geometry
    :param display_name: Name to display in progress messages
    :return: None or 'fail' on error
    """
    self.app.log.debug(f"parseGerber.Gerber.{display_name}()")
    
    # Calculate geometry length for progress tracking
    self.geo_len = 0
    if isinstance(self.solid_geometry, (MultiPolygon, MultiLineString)):
        self.geo_len = len(self.solid_geometry.geoms)
    elif isinstance(self.solid_geometry, list):
        self.geo_len = len(self.solid_geometry)
    elif isinstance(self.solid_geometry, Polygon):
        self.geo_len = 1
    else:
        self.geo_len = 0 if self.solid_geometry is None else 1
    
    self.old_disp_number = 0
    self.el_count = 0
    
    def transform_recursive(obj):
        """Recursively apply transformation to geometry."""
        if type(obj) is list:
            return [transform_recursive(g) for g in obj]
        else:
            try:
                self.el_count += 1
                disp_number = int(np.interp(self.el_count, [0, self.geo_len], [0, 99]))
                if self.old_disp_number < disp_number <= 100:
                    self.app.proc_container.update_view_text(' %d%%' % disp_number)
                    self.old_disp_number = disp_number
                
                return transform_func(obj)
            except AttributeError:
                return obj
    
    # Apply to main geometry
    self.solid_geometry = transform_recursive(self.solid_geometry)
    self.follow_geometry = transform_recursive(self.follow_geometry)
    
    # Apply to aperture geometry
    try:
        for apid in self.tools:
            if 'geometry' in self.tools[apid]:
                for geo_el in self.tools[apid]['geometry']:
                    if 'solid' in geo_el:
                        geo_el['solid'] = transform_recursive(geo_el['solid'])
                    if 'follow' in geo_el:
                        geo_el['follow'] = transform_recursive(geo_el['follow'])
                    if 'clear' in geo_el:
                        geo_el['clear'] = transform_recursive(geo_el['clear'])
    except Exception as e:
        self.app.log.error(f'ParseGerber.Gerber.{display_name}() Exception --> {e}')
        return 'fail'
    
    self.app.inform.emit('[success] %s' % _("Done."))
    self.app.proc_container.new_text = ''
    return None
```

### Task 4.3: Refactor `scale` method to use base

**Files:**
- Modify: `appParsers/ParseGerber.py:2055-2175`

**After refactoring:**
```python
def scale(self, xfactor, yfactor=None, point=None):
    """
    Scales the objects' geometry on the XY plane by a given factor.
    ...
    """
    try:
        xfactor = float(xfactor)
    except Exception:
        self.app.inform.emit('[ERROR_NOTCL] %s' % _("Scale factor has to be a number."))
        return
    
    if yfactor is None:
        yfactor = xfactor
    else:
        try:
            yfactor = float(yfactor)
        except Exception:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Scale factor has to be a number."))
            return
    
    if xfactor == 0 and yfactor == 0:
        return
    
    if point is None:
        px, py = 0, 0
    else:
        px, py = point
    
    def scale_func(obj):
        return affinity.scale(obj, xfactor, yfactor, origin=(px, py))
    
    result = self._transform_geometry_base(scale_func, "scale")
    if result == 'fail':
        return 'fail'
    
    # Update aperture parameters (unique to scale)
    for apid in self.tools:
        try:
            if str(self.tools[apid]['type']) == 'R' or str(self.tools[apid]['type']) == 'O':
                self.tools[apid]['width'] *= xfactor
                self.tools[apid]['height'] *= xfactor
            elif str(self.tools[apid]['type']) == 'P':
                self.tools[apid]['diam'] *= xfactor
        except KeyError:
            pass
        try:
            if self.tools[apid]['size'] is not None:
                self.tools[apid]['size'] = float(self.tools[apid]['size'] * xfactor)
        except KeyError:
            pass
    
    return None
```

### Task 4.4: Refactor remaining transformation methods

Apply same pattern to:
- `offset` (line 2190)
- `mirror` (line 2276)
- `skew` (line 2351)
- `rotate` (line 2425)

Each keeps its unique parameter handling and aperture parameter updates.

### Task 4.5: Run tests and commit

```bash
git add appParsers/ParseGerber.py
git commit -m "refactor: extract _transform_geometry_base method

- Extracts common transformation pattern from 6 methods
- Each method keeps unique parameter handling
- Reduces ~600 lines to ~150 base + 6 thin wrappers
"
```

---

## Phase 5: Add Type Hints

### Task 5.1: Add imports for typing

**Files:**
- Modify: `appParsers/ParseGerber.py` (top of file, after existing imports)

```python
from typing import Dict, List, Optional, Tuple, Any, Union
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiLineString
```

### Task 5.2: Add class-level type annotations

**Files:**
- Modify: `appParsers/ParseGerber.py:32-250` (Gerber class definition)

```python
class Gerber(Geometry):
    """
    Here it is done all the Gerber parsing.
    ...
    """
    
    # Class attributes with types
    tools: Dict[int, Dict[str, Any]]
    aperture_macros: Dict[str, ApertureMacro]
    solid_geometry: Union[Polygon, MultiPolygon, List[Polygon]]
    follow_geometry: List[Union[LineString, Polygon]]
    is_lpc: bool
    source_file: str
    int_digits: int
    frac_digits: int
    gerber_zeros: str
    units: str
    conversion_done: bool
    defective_aperture_detected: bool
    use_buffer_for_union: bool
    
    # ... rest of class
```

### Task 5.3: Add type hints to helper methods

**Files:**
- Modify: `appParsers/ParseGerber.py` (new helper methods)

```python
def _add_path_geometry_to_buffers(
    self, 
    path: List[List[float]], 
    aperture_id: Optional[int], 
    poly_buffer: List[Union[Polygon, MultiPolygon]], 
    follow_buffer: List[Union[LineString, Polygon]],
    steps: int,
    making_region: bool = False
) -> Tuple[Optional[Union[Polygon, MultiPolygon]], Optional[Union[LineString, Polygon]], Dict[str, Any]]:
    ...

def _finalize_region(
    self,
    path: List[List[float]],
    current_aperture: Optional[int],
    poly_buffer: List[Union[Polygon, MultiPolygon]],
    follow_buffer: List[Union[LineString, Polygon]],
    steps: int,
    line_num: int
) -> Tuple[Optional[Dict[str, Any]], List[List[float]]]:
    ...

def _add_flash_to_buffers(
    self,
    x: float,
    y: float,
    aperture_id: Optional[int],
    poly_buffer: List[Union[Polygon, MultiPolygon]],
    follow_buffer: List[Point],
    steps: int
) -> Dict[str, Any]:
    ...

def _transform_geometry_base(
    self,
    transform_func: callable,
    display_name: str
) -> Optional[str]:
    ...
```

### Task 5.4: Add type hints to main methods

**Files:**
- Modify: `appParsers/ParseGerber.py` (parse_file, parse_lines, aperture_parse)

```python
def aperture_parse(
    self, 
    apertureId: str, 
    apertureType: str, 
    apParameters: Optional[str]
) -> Optional[int]:
    ...

def parse_file(self, filename: str, follow: bool = False) -> Optional[str]:
    ...

def parse_lines(self, glines: List[str]) -> Optional[str]:
    ...
```

### Task 5.5: Add type hints to transformation methods

**Files:**
- Modify: `appParsers/ParseGerber.py` (scale, offset, mirror, skew, rotate, buffer)

```python
def scale(
    self, 
    xfactor: float, 
    yfactor: Optional[float] = None, 
    point: Optional[Tuple[float, float]] = None
) -> Optional[str]:
    ...

def offset(self, vect: Tuple[float, float]) -> Optional[str]:
    ...

def mirror(self, axis: str, point: List[float]) -> Optional[str]:
    ...

def skew(self, angle_x: float, angle_y: float, point: List[float]) -> Optional[str]:
    ...

def rotate(self, angle: float, point: List[float]) -> Optional[str]:
    ...

def buffer(
    self, 
    distance: float, 
    join: str = "mitre", 
    factor: Optional[bool] = None, 
    only_exterior: bool = False,
    muted: bool = False
) -> None:
    ...
```

### Task 5.6: Add type hints to standalone function

**Files:**
- Modify: `appParsers/ParseGerber.py:2643` (parse_gerber_number)

```python
def parse_gerber_number(
    strnumber: str, 
    int_digits: int, 
    frac_digits: int, 
    zeros: str
) -> Optional[float]:
    """
    Parse a single number of Gerber coordinates.
    ...
    """
    ...
```

### Task 5.7: Run type checker (if available) and tests

```bash
# If mypy is available
python -m mypy appParsers/ParseGerber.py --ignore-missing-imports

# Run tests
python -m pytest tests/ -v --tb=short
```

### Task 5.8: Commit

```bash
git add appParsers/ParseGerber.py
git commit -m "feat: add comprehensive type hints to ParseGerber

- Adds type annotations to all public methods
- Adds type annotations to new helper methods
- Adds class-level type annotations for attributes
- Improves IDE support and code documentation
- No runtime behavior changes
"
```

---

## Phase 6: Final Verification

### Task 6.1: Run full test suite

```bash
python -m pytest tests/ -v --tb=short
```

### Task 6.2: Manual verification with test Gerber files

Test with multiple real-world Gerber files:
```python
from appParsers.ParseGerber import Gerber

test_files = [
    'tests/test_files/simple_gerber.gbr',
    'tests/test_files/complex_gerber.gbr',
    # Add more real files here
]

for f in test_files:
    g = Gerber(app=app_instance)
    result = g.parse_file(f)
    print(f"{f}: {result}, geometry count: {len(g.solid_geometry) if hasattr(g.solid_geometry, '__len__') else 1}")
```

### Task 6.3: Verify file line count

```bash
wc -l appParsers/ParseGerber.py
```

Expected: Should be similar or slightly reduced (extracted methods move code but don't duplicate)

### Task 6.4: Final commit

```bash
git commit --allow-empty -m "chore: complete Gerber parser maintainability refactoring

Summary of changes:
- Extracted 4 helper methods for repeated patterns
- Created base transformation method reducing 6 methods to thin wrappers
- Added comprehensive type hints throughout
- No behavior changes - all changes are internal refactoring

Phases completed:
1. Path geometry helper extraction
2. Region finalization helper extraction
3. Flash buffer helper extraction
4. Transformation base method extraction
5. Type hints addition
"
```

---

## Rollback Plan

If issues are discovered:

```bash
# Revert all changes
git revert HEAD~6..HEAD

# Or reset to specific commit before refactoring
git checkout <commit-hash-before-refactor> -- appParsers/ParseGerber.py
```

---

## Success Criteria

1. ✅ All existing tests pass
2. ✅ Manual test with simple Gerber file produces valid geometry
3. ✅ No new linting errors introduced
4. ✅ Type hints are consistent and accurate
5. ✅ Code coverage remains similar (if measured)
6. ✅ File is more maintainable (subjective, but measurable by reduced duplication)

---

## Notes for Implementation

- **DO NOT** change any regex patterns
- **DO NOT** change the `width / 1.999` buffering factor
- **DO NOT** modify error handling behavior
- **DO** preserve all try/except blocks
- **DO** keep all warning and error log messages
- **DO** maintain backward compatibility with all existing Gerber file formats

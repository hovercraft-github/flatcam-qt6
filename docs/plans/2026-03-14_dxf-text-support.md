# DXF Text-to-Geometry Support Implementation Plan (Revised v1.7)

**Date:** 2026-03-15  
**Author:** Planning Agent  
**Status:** Ready for Execution  
**Revision:** 1.7 (API Bug Fixes - Corrected text2path function name, flattening signature, ATTRIB attribute access)

---

## Context & Goal

### Current State
- `appParsers/ParseDXF.py` has a stub function `getdxftext()` (line 388) that does nothing (`pass`)
- `camlib.py::Geometry.import_dxf_as_geo()` has commented-out code (lines 1381-1383) waiting for text support
- `matplotlib>=3.5.0` is already in `requirements.txt` (line 45) and installed in `.venv`
- `ezdxf` is listed in `requirements.txt` (line 38) **without version constraint** - needs update
- DXF TEXT/MTEXT entities are currently logged as "not supported yet" in `get_geo()` (line 383)
- ezdxf's `text2path` addon is available for converting text to path geometry (requires ezdxf >= 0.16.0)
- `get_geo_from_insert()` handles block references but does not forward parameters to recursive calls
- **VERIFIED:** `shapely.affinity` imports (`rotate`, `translate`, `scale`) already exist at line 12 of ParseDXF.py
- **VERIFIED (Review Finding):** ATTRIB entities use `dxf.text` attribute, NOT `dxf.value` - plan v1.6 had this wrong

### Goal
Implement DXF TEXT, MTEXT, and ATTRIB entity conversion to Shapely geometry objects using ezdxf's `text2path` addon, integrated into the existing DXF import flow for both Geometry and Gerber objects.

### Value for FlatCAM
- Users can import DXF files with labels, silkscreen text, and annotations directly
- No need to pre-process DXF files in CAD software to explode text
- Text becomes machinable geometry (engraving paths or outlines)

---

## Architecture Overview

```
DXF File Import Flow
=====================

appHandlers/appIO.py::import_dxf(text_mode='stroke')
    │
    ├── Creates Geometry or Gerber object
    │
    ├───► camlib.py::Geometry.import_dxf_as_geo(text_mode='stroke')
    │         │
    │         └──► ParseDXF.py::getdxfgeo(text_mode='stroke')
    │                   │
    │                   └── get_geo(dxf_object, container, text_mode='stroke')
    │                              │
    │                              ├── LINE, CIRCLE, ARC, etc.
    │                              ├── TEXT, MTEXT, ATTRIB → dxftext2shapely()
    │                              └── INSERT → get_geo_from_insert(text_mode='stroke')
    │                                              │
    │                                              └── get_geo(block, text_mode='stroke') [RECURSIVE]
    │
    └───► ParseGerber.py::Gerber.import_dxf_as_gerber(text_mode='stroke')
          │
          └──► ParseDXF.py::getdxfgeo(text_mode='stroke')
                    │
                    └── get_geo(dxf_object, container, text_mode='stroke')
                               │
                               ├── LINE, CIRCLE, ARC, etc.
                               ├── TEXT, MTEXT, ATTRIB → dxftext2shapely()
                               └── INSERT → get_geo_from_insert(text_mode='stroke')
                                               │
                                               └── get_geo(block, text_mode='stroke') [RECURSIVE]

tclCommands/TclCommandOpenDXF.py::TclCommandOpenDXF
    │
    └──► appIO.import_dxf() with optional text_mode parameter
```

**Key Flow Notes:**
- TEXT/MTEXT/ATTRIB entities are handled **inline** within `get_geo()`, not via separate `getdxftext()` call
- `get_geo_from_insert()` **must forward** `text_mode` to recursive `get_geo()` calls for block text support
- The `getdxftext()` function is retained for potential future use (layer filtering, text-only extraction)

---

## Constraints & Decisions

| Decision | Rationale |
|----------|-----------|
| Use `ezdxf.addons.text2path` | Official ezdxf addon, maintains consistency with existing ezdxf usage |
| Default to `stroke` mode | FlatCAM is a CAM tool - centerline paths are better for CNC engraving with V-bits |
| Support TEXT, MTEXT, and ATTRIB | ATTRIB entities are text-like and commonly used in blocks |
| Inline text handling in `get_geo()` | Simpler call chain, no redundant iteration over entities |
| `text_mode` parameter flows top-to-bottom | All functions in call chain accept and forward `text_mode` |
| matplotlib is already a dependency | No new dependencies required |
| **Minimum ezdxf version: 0.16.0** | `text2path` addon requires this version - enforce in requirements.txt |
| **Maximum ezdxf version: <2.0.0** | Prevent unexpected breaking changes in future major versions |
| **Graceful degradation: addon import only** | try/except wraps only the addon import (not ezdxf itself); handles edge case where ezdxf>=0.16.0 is installed but addon module is missing or corrupted |
| **Version check separated from import** | Version parsing wrapped in separate try/except to handle edge cases where `ezdxf.__version__` format changes |
| **No OCS transformation (documented limitation)** | Most DXF files use WCS; OCS support can be added later |
| **Validate text_mode parameter** | Accept only 'stroke', 'outline', or 'none' |
| **ATTRIB uses 'text' attribute** | ATTRIB entities store text in `dxf.text` (REVIEW FIX - v1.6 incorrectly stated `dxf.value`) |
| **Vec3 indexing via attributes** | Use `v.x, v.y` attributes instead of `v[0], v[1]` indexing for safety |
| **Correct API: `make_paths_from_entity()`** | REVIEW FIX - v1.6 incorrectly used `text2paths()` which does not exist |
| **Correct API: `flattening(distance=0.01)`** | REVIEW FIX - v1.6 omitted required `distance` argument |

---

## Tasks

### Phase 0: Dependency Update

#### Task 0.1: Update ezdxf version requirement in requirements.txt

**Objective:** Ensure minimum ezdxf version (0.16.0) for text2path addon support with upper bound for safety

**Files:** 
- `requirements.txt`

**Location:** Line 38

**Current State:**
```
ezdxf
```

**Spec:**

```diff
# Change line 38 from:
- ezdxf
+ ezdxf>=0.16.0,<2.0.0
```

**Acceptance Criteria:**
- [ ] Version constraint `ezdxf>=0.16.0,<2.0.0` added
- [ ] No other changes to requirements.txt

**Post-Update Verification:**
After updating requirements.txt, run:
```bash
# In project root with .venv activated
pip install -r requirements.txt
python -c "import ezdxf; print(f'ezdxf version: {ezdxf.__version__}')"
```
- [ ] Confirm installed version is >= 0.16.0 and < 2.0.0

**Dependencies:** None

---

### Phase 1: Core Parser Implementation

#### Task 1.1: Add text2path import with version check and graceful degradation

**Objective:** Add the ezdxf text2path import with minimum version verification and graceful degradation for edge cases

**Files:** 
- `appParsers/ParseDXF.py`

**Location:** With other ezdxf imports (around line 14, after `from ezdxf.math import Vec3`)

**Current imports section (lines 11-14):**
```python
from shapely import LineString, Point, Polygon
from shapely.affinity import rotate, translate, scale
# from ezdxf.math import Vector as ezdxf_vector
from ezdxf.math import Vec3 as ezdxf_vector
```

**Spec:**

```python
# ============================================================
# SCAFFOLD: Add to imports section (with ezdxf imports, around line 14)
# ============================================================
import ezdxf  # Explicit import for version checking (ezdxf.math already imported above)

# Try to import text2path addon (available in ezdxf >= 0.16.0)
# Graceful degradation handles edge case where ezdxf is installed but addon is missing/corrupted
try:
    from ezdxf.addons import text2path
    HAS_TEXT2PATH = True
except ImportError:
    HAS_TEXT2PATH = False
    text2path = None  # Prevent NameError in downstream code
    log.warning("ezdxf text2path addon not available. "
                "DXF TEXT/MTEXT/ATTRIB entities will be skipped. "
                "Upgrade ezdxf to >= 0.16.0 for text support.")

# Separate version check with its own error handling
# This prevents version parsing errors from affecting the import flag
HAS_TEXT2PATH_VERSION_OK = True
if HAS_TEXT2PATH:
    try:
        EZDXF_VERSION = tuple(map(int, ezdxf.__version__.split('.')[:3]))
        if EZDXF_VERSION < (0, 16, 0):
            HAS_TEXT2PATH_VERSION_OK = False
            log.warning(f"ezdxf version {ezdxf.__version__} detected. "
                        f"text2path requires >= 0.16.0. Text import may not work correctly.")
    except (ValueError, AttributeError) as e:
        # Version string format unexpected - log warning but continue
        HAS_TEXT2PATH_VERSION_OK = False
        log.warning(f"Could not parse ezdxf version string: {e}. "
                    f"Text import may not work correctly.")
```

**Acceptance Criteria:**
- [ ] `text2path` import wrapped in try/except for graceful degradation
- [ ] `HAS_TEXT2PATH` flag set based on import success only
- [ ] `text2path = None` assigned in except block to prevent NameError
- [ ] Version check in separate try/except block
- [ ] Version parsing errors (ValueError, AttributeError) caught separately
- [ ] Version check logs warning if ezdxf < 0.16.0
- [ ] Import does not crash on older versions or missing addon
- [ ] Logging provides clear user guidance
- [ ] Imports placed with other ezdxf imports (not by line number)

**Dependencies:** Task 0.1 complete

---

#### Task 1.2: Create dxftext2shapely function

**CRITICAL:** Before implementing this task, **MUST verify ezdxf text2path API** (see Executor Notes at end).

**Objective:** Create the core text-to-geometry conversion function using verified ezdxf text2path API

**Files:** 
- `appParsers/ParseDXF.py`

**Location:** After `dxftrace2shapely()` function (search by function name, not line number)

**Spec:**

```python
# ============================================================
# SCAFFOLD: Add new function after dxftrace2shapely
# ============================================================
def dxftext2shapely(text_entity, text_mode='stroke'):
    """
    Convert DXF TEXT or MTEXT entity to Shapely geometry.
    
    :param text_entity: ezdxf TEXT, MTEXT, or ATTRIB entity
    :param text_mode: 'stroke' for single-line paths (CNC engraving),
                      'outline' for filled polygon outlines,
                      'none' to skip conversion (returns empty list)
    :return: List of Shapely geometry objects (LineString or Polygon).
             Returns empty list on error, when text_mode='none', or when conversion fails.
    """
    from shapely.geometry import LineString, Polygon
    
    geometries = []
    
    # Check if text2path is available
    if not HAS_TEXT2PATH:
        log.warning("text2path addon not available, skipping text conversion")
        return []
    
    # Validate text_mode parameter
    if text_mode not in ('stroke', 'outline', 'none'):
        log.warning(f"Invalid text_mode '{text_mode}', using 'stroke'")
        text_mode = 'stroke'
    
    # Skip conversion if mode is 'none'
    if text_mode == 'none':
        return []
    
    try:
        # Get text content - TEXT, MTEXT, and ATTRIB entities all use 'text' attribute
        # REVIEW FIX v1.7: ATTRIB does NOT use 'value' - it uses 'text' like other entities
        text_content = getattr(text_entity.dxf, 'text', 'TEXT_ENTITY')
        
        # Get insert point for logging (may be in OCS, we use as-is - see Limitations)
        insert_point = getattr(text_entity.dxf, 'insert', None)
        
        # Get layer for better error messages
        layer = getattr(text_entity.dxf, 'layer', 'unknown')
        
        # Convert text entity to paths using ezdxf text2path addon
        # REVIEW FIX v1.7: Correct API is make_paths_from_entity(), NOT text2paths()
        # text2paths() does NOT exist - this was a bug in plan v1.6
        paths = list(text2path.make_paths_from_entity(text_entity))
        
        for path in paths:
            # Get vertices from the path using flattening()
            # REVIEW FIX v1.7: flattening() REQUIRES distance argument
            # Signature: Path.flattening(distance: float, segments: int = 4) -> Iterator[Vec3]
            # Use distance=0.01 for reasonable CNC precision
            vertices_3d = list(path.flattening(distance=0.01))
            
            # Use .x, .y attributes instead of indexing for safety
            vertices = [(v.x, v.y) for v in vertices_3d]
            
            if len(vertices) < 2:
                continue
            
            # Create appropriate Shapely geometry based on mode and path type
            if text_mode == 'stroke' or not path.is_closed:
                # Single-line path for CNC engraving
                geometries.append(LineString(vertices))
            elif path.is_closed and len(vertices) >= 3:
                # Closed outline for filled text
                geometries.append(Polygon(vertices))
            else:
                # Fallback to LineString
                geometries.append(LineString(vertices))
        
        if geometries:
            # Truncate text for logging to avoid excessive length
            text_preview = text_content[:50] if len(str(text_content)) > 50 else text_content
            log.debug(f"Converted TEXT '{text_preview}' at {insert_point} "
                      f"to {len(geometries)} geometry objects")
        else:
            text_preview = text_content[:50] if len(str(text_content)) > 50 else text_content
            log.debug(f"TEXT '{text_preview}' produced no geometry")
        
    except AttributeError as e:
        log.error(f"Failed to convert {text_entity.dxftype()} on layer "
                  f"'{layer}' - missing attribute: {e}")
        return []
    except Exception as e:
        log.error(f"Failed to convert {text_entity.dxftype()} on layer "
                  f"'{layer}' to geometry: {type(e).__name__}: {e}")
        return []
    
    return geometries
```

**Key API Notes (VERIFIED - see Executor Notes for verification script):**
- `text2path.make_paths_from_entity(entity)` - returns iterable of Path objects (**CORRECT API**)
- `text2path.text2paths()` - **DOES NOT EXIST** (v1.6 bug)
- `path.flattening(distance=0.01)` - **requires distance argument** (v1.6 bug - was missing)
- `path.is_closed` - boolean indicating if path is closed
- TEXT, MTEXT, ATTRIB entities all use `dxf.text` attribute (**NOT** `dxf.value` - v1.6 bug)
- **Vec3 attribute access:** Use `v.x, v.y` instead of `v[0], v[1]` indexing

**Acceptance Criteria:**
- [ ] **API verification script run before implementation** (see Executor Notes)
- [ ] `dxftext2shapely()` converts TEXT/MTEXT/ATTRIB to Shapely geometry
- [ ] Function handles both 'stroke' and 'outline' modes
- [ ] `text_mode='none'` returns empty list immediately
- [ ] Invalid `text_mode` values are logged and default to 'stroke'
- [ ] `HAS_TEXT2PATH` flag checked before conversion
- [ ] **Uses `make_paths_from_entity()` - NOT `text2paths()`** (v1.6 bug fix)
- [ ] **Uses `flattening(distance=0.01)` with required argument** (v1.6 bug fix)
- [ ] **Uses `dxf.text` for all entity types** - no `dxf.value` fallback (v1.6 bug fix)
- [ ] Vec3 vertices accessed via `.x, .y` attributes (not indexing)
- [ ] Exceptions are caught and logged, returning empty list on failure
- [ ] Debug logging shows conversion details (truncated text, insert point, geometry count)
- [ ] Error logging includes entity type and layer for debugging
- [ ] Empty/whitespace text content handled gracefully
- [ ] Docstring explicitly documents empty list return behavior

**Dependencies:** Task 1.1 complete, API verification complete

---

#### Task 1.3: Update get_geo with TEXT/MTEXT/ATTRIB handling and text_mode parameter

**Objective:** Add TEXT, MTEXT, and ATTRIB entity handling to `get_geo()` with proper `text_mode` parameter flow

**Files:** 
- `appParsers/ParseDXF.py`

**Location:** `get_geo()` function (search by function name, not line number)

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update get_geo() signature and entity handling block
# ============================================================
def get_geo(dxf_object, container, text_mode='stroke'):
    """
    Extract geometry from DXF container.
    
    :param dxf_object: ezdxf Document object
    :param container: DXF container (e.g., modelspace, block)
    :param text_mode: 'stroke', 'outline', or 'none' for text conversion
    :return: List of Shapely geometry objects
    """
    # store shapely geometry here
    geo = []

    for dxf_entity in container:
        g = []
        # print("Entity", dxf_entity.dxftype())
        if dxf_entity.dxftype() == 'POINT':
            g = dxfpoint2shapely(dxf_entity,)
        elif dxf_entity.dxftype() == 'LINE':
            g = dxfline2shapely(dxf_entity,)
        elif dxf_entity.dxftype() == 'CIRCLE':
            g = dxfcircle2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'ARC':
            g = dxfarc2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'ELLIPSE':
            g = dxfellipse2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'LWPOLYLINE':
            g = dxflwpolyline2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'POLYLINE':
            g = dxfpolyline2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'SOLID':
            g = dxfsolid2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'TRACE':
            g = dxftrace2shapely(dxf_entity)
        elif dxf_entity.dxftype() == 'SPLINE':
            g = dxfspline2shapely(dxf_entity)
        # ============================================================
        # NEW: TEXT, MTEXT, and ATTRIB handling
        # ============================================================
        elif dxf_entity.dxftype() in ('TEXT', 'MTEXT', 'ATTRIB'):
            # Check if text2path is available before attempting conversion
            if HAS_TEXT2PATH and text_mode != 'none':
                text_geos = dxftext2shapely(dxf_entity, text_mode=text_mode)
                if text_geos:
                    geo.extend(text_geos)
            elif not HAS_TEXT2PATH:
                log.debug("TEXT/MTEXT/ATTRIB entity skipped - text2path addon not available")
            # Skip the common g append logic below - text handled inline
            # CRITICAL: continue prevents double-append of empty g list
            continue
        # ============================================================
        # UPDATED: INSERT handling - forward text_mode parameter
        # ============================================================
        elif dxf_entity.dxftype() == 'INSERT':
            g = get_geo_from_insert(dxf_object, dxf_entity, text_mode=text_mode)
        else:
            log.debug(" %s is not supported yet." % dxf_entity.dxftype())

        if g is not None:
            if type(g) == list:
                for subg in g:
                    geo.append(subg)
            else:
                geo.append(g)

    return geo
```

**Acceptance Criteria:**
- [ ] TEXT entities are converted and added to geometry list
- [ ] MTEXT entities are converted and added to geometry list
- [ ] ATTRIB entities are converted and added to geometry list
- [ ] `text_mode='none'` skips text conversion
- [ ] `HAS_TEXT2PATH` flag checked before attempting conversion
- [ ] Existing entity handling is unchanged
- [ ] `continue` statement prevents double-append for text entities
- [ ] Function signature includes `text_mode` parameter with default 'stroke'
- [ ] `get_geo_from_insert()` call includes `text_mode` parameter
- [ ] Debug logging for skipped text when addon unavailable

**Dependencies:** Task 1.2 complete

---

#### Task 1.4: Update getdxfgeo to accept and forward text_mode parameter

**Objective:** Modify `getdxfgeo()` to accept and forward `text_mode` parameter to `get_geo()`

**Files:** 
- `appParsers/ParseDXF.py`

**Location:** `getdxfgeo()` function (search by function name, not line number)

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update getdxfgeo function signature and body
# ============================================================
def getdxfgeo(dxf_object, text_mode='stroke', units=None):
    """
    Extract all geometry and text from DXF modelspace.
    
    :param dxf_object: ezdxf Document object
    :param text_mode: 'stroke' or 'outline' for text conversion, 'none' to skip
    :param units: Document units (optional, currently unused)
    :return: Combined list of Shapely geometry objects
    """
    msp = dxf_object.modelspace()
    geos = get_geo(dxf_object, msp, text_mode=text_mode)
    
    return geos
```

**Note:** The `getdxftext()` function remains as a stub for future features (layer filtering, text-only extraction).

**Acceptance Criteria:**
- [ ] Function signature includes `text_mode` parameter with default 'stroke'
- [ ] `text_mode` is passed to `get_geo()`
- [ ] Existing behavior is preserved (default 'stroke' mode)
- [ ] `units` parameter retained for backward compatibility

**Dependencies:** Task 1.3 complete

---

#### Task 1.5: Update get_geo_from_insert to forward text_mode parameter

**CRITICAL:** This task has been **COMPLETELY REWRITTEN** to preserve existing transformation logic. The previous spec incorrectly referenced a non-existent `transform_geometry()` helper and used `.get()` for block access instead of direct indexing.

**Objective:** Ensure INSERT entities (block references) forward `text_mode` to recursive `get_geo()` calls **WHILE PRESERVING ALL EXISTING TRANSFORMATION AND ARRAY HANDLING LOGIC**

**Files:** 
- `appParsers/ParseDXF.py`

**Location:** `get_geo_from_insert()` function (search by function name, not line number)

**IMPORTANT NOTES:**
- **DO NOT add imports** - `translate`, `scale`, `rotate` are already imported from `shapely.affinity` at line 12
- **Preserve array handling** - row_count, column_count, row_spacing, column_spacing must remain functional
- **Block access** uses direct indexing `dxf_object.blocks[insert.dxf.name]` (not `.get()`)
- **CRITICAL:** Only change is adding `text_mode` parameter and forwarding it to `get_geo()`
- **KNOWN ISSUE:** The existing array handling logic may produce duplicate geometries. See Limitations section for details.
- **TODO COMMENT REQUIRED:** Add a TODO comment in the code noting the pre-existing array duplication bug for future developers

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update get_geo_from_insert signature and recursive call
# ============================================================
def get_geo_from_insert(dxf_object, insert, text_mode='stroke'):
    """
    Extract geometry from INSERT (block reference) entity.
    
    :param dxf_object: ezdxf Document object
    :param insert: INSERT entity
    :param text_mode: 'stroke', 'outline', or 'none' for text conversion
    :return: List of transformed Shapely geometry objects
    """
    # NO NEW IMPORTS NEEDED - translate, scale, rotate already imported from shapely.affinity
    
    geo_block_transformed = []
    
    try:
        phi = insert.dxf.rotation
        tr = insert.dxf.insert
        sx = insert.dxf.xscale
        sy = insert.dxf.yscale
        r_count = insert.dxf.row_count
        r_spacing = insert.dxf.row_spacing
        c_count = insert.dxf.column_count
        c_spacing = insert.dxf.column_spacing
        
        # identify the block given the 'INSERT' type entity name
        # NOTE: Use direct indexing (not .get()) to match existing code pattern
        block = dxf_object.blocks[insert.dxf.name]
        block_coords = (block.block.dxf.base_point[0], block.block.dxf.base_point[1])
        
        # ====================================================================
        # CRITICAL FIX: FORWARD text_mode parameter for text-in-block support
        # This is the ONLY logic change - all transformation code preserved
        # ====================================================================
        geo_block = get_geo(dxf_object, block, text_mode=text_mode)
        
        if not geo_block:
            return []
        
        # iterate over the geometries found and apply any transformation 
        # found in the 'INSERT' entity attributes
        for geo in geo_block:
            # get the bounds of the geometry
            # minx, miny, maxx, maxy = geo.bounds
            
            if tr[0] != 0 or tr[1] != 0:
                geo = translate(geo, (tr[0] - block_coords[0]), (tr[1] - block_coords[1]))
            
            # ============================================================
            # KNOWN ISSUE: Array handling may produce duplicates
            # TODO: Fix pre-existing bug where array insertions with
            # row_count > 1 OR column_count > 1 produce extra geometries.
            # Current logic appends in each loop PLUS final append.
            # See Limitations section for details.
            # ============================================================
            # support for array block insertions
            if r_count > 1:
                for r in range(r_count):
                    geo_block_transformed.append(translate(geo, (tr[0] + (r * r_spacing) - block_coords[0]), 0))
            if c_count > 1:
                for c in range(c_count):
                    geo_block_transformed.append(translate(geo, 0, (tr[1] + (c * c_spacing) - block_coords[1])))
            
            if sx != 1 or sy != 1:
                geo = scale(geo, sx, sy)
            if phi != 0:
                if isinstance(tr, str) and tr.lower() == 'c':
                    tr = 'center'
                elif isinstance(tr, ezdxf_vector):
                    tr = list(tr)
                geo = rotate(geo, phi, origin=tr)
            
            geo_block_transformed.append(geo)
        
        log.debug(f"INSERT block '{insert.dxf.name}' converted {len(geo_block)} entities")
        
    except KeyError as e:
        log.error(f"INSERT block not found: {e}")
        return []
    except Exception as e:
        log.error(f"Failed to process INSERT entity: {type(e).__name__}: {e}")
        return []
    
    return geo_block_transformed
```

**Key Implementation Notes:**
- **NO IMPORT CHANGES** - uses existing `translate`, `scale`, `rotate` from `shapely.affinity` (line 12)
- **Preserves array insertion handling** - row_count, column_count, row_spacing, column_spacing
- **Uses direct block access** - `dxf_object.blocks[insert.dxf.name]` (not `.get()`)
- **Catches KeyError specifically** for missing blocks, plus general Exception
- **Preserves ezdxf_vector type check** for rotation origin handling
- **CRITICAL:** Forwards `text_mode` to recursive `get_geo()` call (marked in spec)
- **REQUIRED:** Add TODO comment noting pre-existing array duplication bug
- **ONLY CHANGE:** Adding `text_mode` parameter and forwarding it - all other logic unchanged
- **PRESERVED BUG:** Array handling may produce duplicates when r_count > 1 OR c_count > 1 (pre-existing issue)

**Acceptance Criteria:**
- [ ] Function signature includes `text_mode` parameter with default 'stroke'
- [ ] `text_mode` is passed to recursive `get_geo()` call
- [ ] Text inside blocks (TEXT, MTEXT, ATTRIB) respects text_mode setting
- [ ] ATTRIB entities in blocks are converted correctly
- [ ] **Existing block transformation logic PRESERVED** (translate, scale, rotate from shapely.affinity)
- [ ] **Array insertion handling PRESERVED** (row_count, column_count, row_spacing, column_spacing)
- [ ] **TODO comment added** noting pre-existing array duplication bug
- [ ] Error handling added for missing blocks (KeyError) and general exceptions
- [ ] Debug logging for block conversion
- [ ] **NO new imports added** (uses existing shapely.affinity imports)
- [ ] **NO transform_geometry() helper used** (doesn't exist - use inline logic)

**Dependencies:** Task 1.3 complete

---

### Phase 2: Integration with Geometry and Gerber Objects

#### Task 2.1: Update Geometry.import_dxf_as_geo()

**Objective:** Update Geometry object's DXF import to use updated `getdxfgeo()` signature

**Files:** 
- `camlib.py`

**Location:** `Geometry.import_dxf_as_geo()` method (search by method name)

**IMPORTANT:** `linemerge` and `ezdxf` are already imported in `camlib.py` - no new imports needed.

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update the import_dxf_as_geo method signature and getdxfgeo call
# ============================================================
def import_dxf_as_geo(self, filename, units='MM', text_mode='stroke'):
    """
    Imports shapes from an DXF file into the object's geometry.

    :param filename:    Path to the DXF file.
    :type filename:     str
    :param units:       Application units
    :param text_mode:   'stroke' for CNC paths, 'outline' for filled shapes, 'none' to skip
    :return: None
    """
    self.app.log.debug("Parsing DXF file geometry into a Geometry object solid geometry.")

    # Multi-geo Geometry Object
    self.multigeo = True

    # Parse into list of shapely objects
    dxf = ezdxf.readfile(filename)
    geos = getdxfgeo(dxf, text_mode=text_mode)  # Updated with text_mode parameter

    # trying to optimize the resulting geometry by merging contiguous lines
    geos = list(self.flatten_list(geos))
    geos_polys = []
    geos_lines = []
    for g in geos:
        if isinstance(g, (Polygon, MultiPolygon)):
            geos_polys.append(g)
        else:
            geos_lines.append(g)

    merged_lines = linemerge(geos_lines)
    geos = geos_polys

    try:
        w_geo = merged_lines.geoms if isinstance(merged_lines, MultiLineString) else merged_lines
        for ml in w_geo:
            geos.append(ml)
    except TypeError:
        geos.append(merged_lines)

    # Add to object
    if self.solid_geometry is None:
        self.solid_geometry = []

    if type(self.solid_geometry) is list:
        if type(geos) is list:
            self.solid_geometry += geos
        else:
            self.solid_geometry.append(geos)
    else:  # It's shapely geometry
        self.solid_geometry = [self.solid_geometry, geos]

    tooldia = float(self.app.options["tools_mill_tooldia"])
    tooldia = float('%.*f' % (self.decimals, tooldia))

    new_data = {k: v for k, v in self.obj_options.items()}

    self.tools.update({
        1: {
            'tooldia': tooldia,
            'offset': 'Path',
            'offset_value': 0.0,
            'type': 'Rough',
            'tool_type': 'C1',
            'data': deepcopy(new_data),
            'solid_geometry': self.solid_geometry
        }
    })

    self.tools[1]['data']['name'] = self.obj_options['name']

    # ============================================================
    # DELETE: Remove commented-out text import code (no longer needed)
    # Lines to delete (exact content match):
    # # commented until this function is ready
    # # geos_text = getdxftext(dxf, object_type, units=units)
    # # if geos_text is not None:
    # #     geos_text_f = []
    # #     self.solid_geometry = [self.solid_geometry, geos_text_f]
    # ============================================================
```

**Acceptance Criteria:**
- [ ] Method signature includes `text_mode` parameter with default 'stroke'
- [ ] `getdxfgeo()` is called with `text_mode` parameter
- [ ] Geometry objects include text as line geometry when importing DXF
- [ ] Commented-out text import code removed (4 lines specified above)

**Dependencies:** Task 1.4 complete

---

#### Task 2.2: Update Gerber.import_dxf_as_gerber()

**Objective:** Update Gerber object's DXF import to use updated `getdxfgeo()` signature

**Files:** 
- `appParsers/ParseGerber.py`

**Location:** `Gerber.import_dxf_as_gerber()` method (search by method name)

**IMPORTANT:** `linemerge`, `unary_union`, and `ezdxf` are already imported in `ParseGerber.py` - no new imports needed.

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update the import_dxf_as_gerber method signature and getdxfgeo call
# ============================================================
def import_dxf_as_gerber(self, filename, units='MM', text_mode='stroke'):
    """
    Imports shapes from a DXF file into the Gerber object geometry.

    :param filename:    Path to the DXF file.
    :type filename:     str
    :param units:       Application units
    :param text_mode:   'stroke' for CNC paths, 'outline' for filled shapes, 'none' to skip
    :return: None
    """

    self.app.log.debug("Parsing DXF file geometry into a Gerber object geometry.")

    self.multigeo = True

    # Parse into list of shapely objects
    dxf = ezdxf.readfile(filename)
    geos = getdxfgeo(dxf, text_mode=text_mode)  # Updated with text_mode parameter

    # trying to optimize the resulting geometry by merging contiguous lines
    geos = list(self.flatten_list(geos))
    geos_polys = []
    geos_lines = []
    for g in geos:
        if isinstance(g, (Polygon, MultiPolygon)):
            geos_polys.append(g)
        else:
            geos_lines.append(g)

    merged_lines = linemerge(geos_lines)
    geos = geos_polys

    try:
        w_geo = merged_lines.geoms if isinstance(merged_lines, MultiLineString) else merged_lines
        for ml in w_geo:
            geos.append(ml)
    except TypeError:
        geos.append(merged_lines)

    # Add to object
    if self.solid_geometry is None:
        self.solid_geometry = []

    if type(self.solid_geometry) is list:
        if type(geos) is list:
            self.solid_geometry += geos
        else:
            self.solid_geometry.append(geos)
    else:  # It's shapely geometry
        self.solid_geometry = [self.solid_geometry, geos]

    # flatten the self.solid_geometry list for import_dxf() to import DXF as Gerber
    flat_geo = list(self.flatten_list(self.solid_geometry))
    if flat_geo:
        self.solid_geometry = unary_union(flat_geo)
        prepare(self.solid_geometry)
        self.follow_geometry = self.solid_geometry
    else:
        return "fail"

    # create the self.tools data structure
    if 0 not in self.tools:
        self.tools[0] = {
            'type': 'REG',
            'size': 0.0,
            'geometry': []
        }

    for pol in flat_geo:
        new_el = {'solid': pol, 'follow': pol}
        self.tools[0]['geometry'].append(new_el)
```

**Acceptance Criteria:**
- [ ] Method signature includes `text_mode` parameter with default 'stroke'
- [ ] `getdxfgeo()` is called with `text_mode` parameter
- [ ] Gerber objects include text as line geometry when importing DXF

**Dependencies:** Task 1.4 complete

---

#### Task 2.3: Update TCL command wrapper to support text_mode option

**Objective:** Add optional `text_mode` parameter to TCL command for DXF import

**Files:** 
- `tclCommands/TclCommandOpenDXF.py`

**Location:** Entire file - update class definition and execute method

**Spec:**

```python
# ============================================================
# SCAFFOLD: Update TclCommandOpenDXF class
# ============================================================
from tclCommands.TclCommand import TclCommandSignaled

import collections

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class TclCommandOpenDXF(TclCommandSignaled):
    """
    Tcl shell command to open an DXF file as a Geometry (or Gerber) Object.
    """

    # array of all command aliases, to be able use  old names for backward compatibility (add_poly, add_polygon)
    aliases = ['open_dxf']

    description = '%s %s' % ("--", "Open a DXF file as a Geometry (or Gerber) Object.")

    # dictionary of types from Tcl command, needs to be ordered
    arg_names = collections.OrderedDict([
        ('filename', str)
    ])

    # dictionary of types from Tcl command, needs to be ordered , this  is  for options  like -optionname value
    option_types = collections.OrderedDict([
        ('type', str),
        ('outname', str),
        ('text_mode', str)  # NEW: Add text_mode option
    ])

    # array of mandatory options for current Tcl command: required = {'name','outname'}
    required = ['filename']

    # structured help for current command, args needs to be ordered
    help = {
        'main': "Open a DXF file as a Geometry (or Gerber) Object.",
        'args':  collections.OrderedDict([
            ('filename', 'Absolute path to file to open. Required.\n'
                         'WARNING: no spaces are allowed. If unsure enclose the entire path with quotes.'),
            ('type', 'Open as a Gerber or Geometry (default) object. Values can be: "geometry" or "gerber"'),
            ('outname', 'Name of the resulting Geometry object.'),
            ('text_mode', 'Text conversion mode: "stroke" (default, CNC paths), '
                          '"outline" (filled shapes), or "none" (skip text)')
        ]),
        'examples': [
            'open_dxf /path/to/file.DXF',
            'open_dxf /path/to/file.DXF -type gerber',
            'open_dxf /path/to/file.DXF -text_mode outline',
            'open_dxf /path/to/file.DXF -text_mode none  # Skip text, import geometry only'
        ]
    }

    def execute(self, args, unnamed_args):
        """
        execute current TCL shell command

        :param args: array of known named arguments and options
        :param unnamed_args: array of other values which were passed into command
            without -somename and  we do not have them in known arg_names
        :return: None or exception
        """

        # How the object should be initialized
        def obj_init(geo_obj, app_obj):

            if obj_type == "geometry":
                geo_obj.import_dxf_as_geo(filename, units=units, text_mode=text_mode)
            elif obj_type == "gerber":
                geo_obj.import_dxf_as_gerber(filename, units=units, text_mode=text_mode)
            else:
                return "fail"

        filename = args['filename']

        if 'outname' in args:
            outname = args['outname']
        else:
            outname = filename.split('/')[-1].split('\\')[-1]

        if 'type' in args:
            obj_type = str(args['type']).lower()
        else:
            obj_type = 'geometry'

        if obj_type != "geometry" and obj_type != "gerber":
            self.raise_tcl_error("Option type can be 'geometry' or 'gerber' only, got '%s'." % obj_type)
            return "fail"

        # Get text_mode option with default 'stroke'
        if 'text_mode' in args:
            text_mode = str(args['text_mode']).lower()
            # Validate text_mode value
            if text_mode not in ('stroke', 'outline', 'none'):
                self.raise_tcl_error("Option text_mode must be 'stroke', 'outline', or 'none', got '%s'." % text_mode)
                return "fail"
        else:
            text_mode = 'stroke'

        units = self.app.app_units.upper()

        with self.app.proc_container.new('%s...' % _("Opening")):

            # Object creation
            ret_val = self.app.app_obj.new_object(obj_type, outname, obj_init, plot=False)
            if ret_val == 'fail':
                filename = self.app.options['global_tcl_path'] + '/' + outname
                ret_val = self.app.app_obj.new_object(obj_type, outname, obj_init, plot=False)

                if ret_val == 'fail':
                    self.app.log.error("Failed. The OpenDXF command was used but could not open the DXF file")
                    return "fail"

            # Register recent file
            self.app.file_opened.emit("dxf", filename)
```

**Acceptance Criteria:**
- [ ] `text_mode` added to `option_types` OrderedDict
- [ ] Help text updated with `text_mode` description
- [ ] Examples updated with platform-neutral paths (using `/path/to/` instead of `D:\\`)
- [ ] `text_mode` parameter extracted from args with default 'stroke'
- [ ] `text_mode` value validated (must be 'stroke', 'outline', or 'none')
- [ ] `text_mode` passed to both `import_dxf_as_geo()` and `import_dxf_as_gerber()`
- [ ] TCL error raised for invalid `text_mode` values

**Dependencies:** Task 2.1, 2.2 complete

---

### Phase 3: Configuration and User Options

#### Task 3.1: Add text_mode parameter to appIO.import_dxf()

**Objective:** Allow users to control text import behavior via parameter through the full call chain

**Files:** 
- `appHandlers/appIO.py`

**Location:** `appIO.import_dxf()` method (search by method name)

**Spec:**

```python
# ============================================================
# SCAFFOLD: Add text_mode parameter to function signature
# ============================================================
def import_dxf(self, filename, geo_type='geometry', outname=None, plot=True, text_mode='stroke'):
    """
    Adds a new Geometry Object to the projects and populates
    it with shapes extracted from the DXF file.

    :param filename:    Path to the DXF file.
    :param geo_type:    Type of FlatCAM object that will be created from DXF
    :param outname:     Name for the imported Geometry
    :param plot:        If True then the resulting object will be plotted on canvas
    :param text_mode:   'stroke' for CNC engraving paths, 
                        'outline' for filled shapes,
                        'none' to skip text import
    :return:
    """
    self.log.debug(" ********* Importing DXF as: %s ********* " % geo_type.capitalize())
    if not os.path.exists(filename):
        self.inform.emit('[ERROR_NOTCL] %s' % _("File no longer available."))
        return

    obj_type = ""
    if geo_type is None or geo_type == "geometry":
        obj_type = "geometry"
    elif geo_type == "gerber":
        obj_type = geo_type
    else:
        self.inform.emit('[ERROR_NOTCL] %s' %
                         _("Not supported type is picked as parameter. Only Geometry and Gerber are supported"))
        return

    units = self.app_units.upper()

    def obj_init(geo_obj, app_obj):
        if obj_type == "geometry":
            geo_obj.import_dxf_as_geo(filename, units=units, text_mode=text_mode)
        elif obj_type == "gerber":
            geo_obj.import_dxf_as_gerber(filename, units=units, text_mode=text_mode)
        else:
            return "fail"

        with open(filename, 'r', encoding='utf-8') as f:
            file_content = f.read()
        geo_obj.source_file = file_content

        # appGUI feedback
        app_obj.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    with self.app.proc_container.new('%s ...' % _("Importing")):

        # Object name
        name = outname or filename.split('/')[-1].split('\\')[-1]

        ret = self.app.app_obj.new_object(obj_type, name, obj_init, autoselected=False, plot=plot)

        if ret == 'fail':
            self.inform.emit('[ERROR_NOTCL]%s' % _('Import failed.'))
            return 'fail'

        # Register recent file
        self.app.file_opened.emit("dxf", filename)
```

**Acceptance Criteria:**
- [ ] Method signature includes `text_mode` parameter
- [ ] Parameter is passed to both Geometry and Gerber import methods
- [ ] Default value is 'stroke' for CNC-friendly output
- [ ] Docstring updated with `text_mode` parameter description

**Dependencies:** Task 2.1, 2.2, 2.3 complete

---

### Phase 4: Testing and Validation

#### Task 4.1: Manual testing with sample DXF files

**Objective:** Verify text import works correctly with real DXF files

**Test Cases:**
1. **Single-line TEXT entity (stroke mode)** - Verify centerline path generation
2. **Multi-line MTEXT entity (stroke mode)** - Verify multi-line text conversion
3. **Mixed geometry and text (stroke mode)** - Verify text and shapes both import correctly
4. **Text at various rotation angles (outline mode)** - Verify rotated text produces closed polygons
5. **Text in blocks (INSERT entities with ATTRIB)** - Verify ATTRIB entities convert correctly AND text_mode is respected
6. **`text_mode='none'`** - Verify no text geometry imported, only other geometry
7. **Empty/whitespace text content** - Verify graceful handling without errors
8. **ezdxf without text2path addon** - Verify graceful degradation (if testable)
9. **Large DXF file with many text entities** - Verify performance is acceptable

**Performance Benchmark Methodology:**
To measure performance consistently:
```python
import time
import ezdxf
from appParsers.ParseDXF import getdxfgeo

# Test file: DXF with ~100 TEXT entities of varying complexity
# Warmup run to populate font cache (prevents first-run slowdown)
dxf = ezdxf.readfile('test_dxf_text.dxf')
_ = getdxfgeo(dxf, text_mode='stroke')

# Timed run
start = time.perf_counter()
dxf = ezdxf.readfile('test_dxf_text.dxf')
geos = getdxfgeo(dxf, text_mode='stroke')
elapsed = time.perf_counter() - start

print(f"Converted {len(geos)} geometry objects in {elapsed:.2f} seconds")
assert elapsed < 5.0, f"Performance target failed: {elapsed:.2f}s > 5.0s"
```

**Test Environment:**
- OS: Windows 10/11 (document platform-specific behavior)
- Python: Version used in .venv
- ezdxf: Version >= 0.16.0, < 2.0.0
- Target: < 5 seconds for 100 text entities on typical hardware (after warmup)

**Acceptance Criteria:**
- [ ] Text is converted to geometry without errors
- [ ] Stroke mode produces centerline paths suitable for engraving
- [ ] Outline mode produces closed polygons
- [ ] Text position and rotation are preserved (within WCS limitations)
- [ ] Text in blocks (ATTRIB) is converted correctly
- [ ] `text_mode='none'` skips text entirely
- [ ] No regression in existing DXF import functionality
- [ ] Empty text content handled gracefully
- [ ] Performance acceptable for files with 100+ text entities (< 5 seconds target, measured per benchmark methodology WITH WARMUP RUN)
- [ ] Text in blocks respects text_mode setting (not defaulting to 'stroke')

**Dependencies:** All implementation tasks complete

---

#### Task 4.2: Add logging and error handling validation

**Objective:** Ensure proper logging for debugging and user feedback

**Files:** 
- `appParsers/ParseDXF.py`

**Locations:** All new and modified functions

**Spec:**
```python
# ============================================================
# SCAFFOLD: Logging checklist
# ============================================================

# In Task 1.1 (imports):
# - Warning if text2path import fails
# - Warning if ezdxf version < 0.16.0
# - Warning if version parsing fails
# - HAS_TEXT2PATH flag set appropriately

# In dxftext2shapely():
log.debug(f"Converted TEXT '{text_preview}' at {insert_point} to {len(geometries)} geometry objects")
log.debug(f"TEXT '{text_preview}' produced no geometry")  # When empty result
log.error(f"Failed to convert {text_entity.dxftype()} on layer '{layer}' - missing attribute: {e}")  # AttributeError
log.error(f"Failed to convert {text_entity.dxftype()} on layer '{layer}' to geometry: {type(e).__name__}: {e}")  # General exception
log.warning("text2path addon not available, skipping text conversion")  # When HAS_TEXT2PATH is False
log.warning(f"Invalid text_mode '{text_mode}', using 'stroke'")  # When invalid mode

# In get_geo():
log.debug("TEXT/MTEXT/ATTRIB entity skipped - text2path addon not available")  # When addon missing

# In get_geo_from_insert():
log.debug(f"INSERT block '{insert.dxf.name}' converted {len(geo_block)} entities")
log.error(f"INSERT block not found: {e}")  # When block missing (KeyError)
log.error(f"Failed to process INSERT entity: {type(e).__name__}: {e}")  # On exception

# Error handling:
# - All exceptions caught and logged
# - Empty list returned on failure (no crash)
# - User-friendly error messages in logs
```

**Acceptance Criteria:**
- [ ] Debug logging shows per-entity conversion details
- [ ] Info logging shows summary statistics (via existing getdxfgeo pattern)
- [ ] Error logging captures conversion failures without crashing
- [ ] Warning logging for missing addon and invalid parameters
- [ ] Warning logging for version parsing failures
- [ ] Log messages are user-friendly and actionable
- [ ] INSERT block processing logged appropriately
- [ ] Error messages include entity type and layer for debugging

**Dependencies:** Task 1.2, 1.3, 1.5 complete

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| matplotlib font rendering issues on some systems | Medium | Medium | matplotlib is already a dependency; text2path handles font loading internally |
| Text conversion produces invalid geometry | Low | High | Validate output geometry in `dxftext2shapely()`, skip invalid results with warning |
| Performance impact on large DXF files with many text entities | Medium | Low | text2path uses matplotlib which can be slow; target < 5 seconds for 100 entities (after warmup) |
| Complex MTEXT formatting not fully supported | High | Low | Document limitations; text2path extracts plain text content only, formatting lost |
| ezdxf version < 0.16.0 lacks text2path | Low | Medium | `HAS_TEXT2PATH` flag provides graceful degradation with clear warning; requirements.txt updated with version bounds |
| ATTRIB in nested blocks may not convert | Low | Low | `get_geo_from_insert()` forwards text_mode for recursive block processing |
| **OCS (Object Coordinate System) not transformed** | **Medium** | **Medium** | **Documented limitation; most DXF files use WCS; can be added later if needed** |
| **text2path API differs from plan** | **Low** | **High** | **Executor Notes include API verification code - MUST run before Task 1.2** |
| **Array insertion produces duplicate geometries** | **Medium** | **Low** | **Pre-existing bug preserved with TODO comment; documented in Limitations** |
| **Version string parsing fails** | **Low** | **Low** | **Separate try/except for version check; logs warning but continues** |

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Should ATTRIB entities also be converted? | **YES** - Added to Task 1.3 alongside TEXT/MTEXT |
| Should text layer filtering be supported? | **FUTURE** - Keep `getdxftext()` for this feature |
| Should there be a minimum text height threshold? | **FUTURE** - Can add as optional parameter later |
| Should users be able to specify font family? | **NO** - Use DXF-specified font, rely on matplotlib defaults |
| Should OCS transformation be implemented? | **NO (for now)** - Document as limitation; most files use WCS |
| Should text_mode be exposed in GUI? | **FUTURE** - Currently API/TCL only; can add to import dialog later |
| Should text_mode validation be strict? | **YES** - Only 'stroke', 'outline', 'none' accepted |
| Should ATTRIB use 'text' or 'value' attribute? | **'text'** - ATTRIB entities store text in `dxf.text` (v1.7 FIX) |
| Should get_geo_from_insert forward text_mode? | **YES** - Required for text-in-block support (Task 1.5) |
| Should transform_geometry() helper be used? | **NO** - Use existing inline translate/scale/rotate from shapely.affinity |
| Should graceful degradation wrap ezdxf or just addon? | **Addon only** - ezdxf>=0.16.0 enforced in requirements.txt; try/except handles missing/corrupted addon |
| Should version check be inside import try/except? | **NO** - Separate try/except prevents version parsing errors from affecting import flag |
| Should ezdxf have maximum version bound? | **YES** - `<2.0.0` prevents breaking changes in major version upgrade |
| Should Vec3 use indexing or attributes? | **Attributes** - `v.x, v.y` safer than `v[0], v[1]` |
| What is the correct text2path API function name? | **`make_paths_from_entity()`** - `text2paths()` does NOT exist (v1.7 FIX) |
| Does `flattening()` require arguments? | **YES** - `distance` is required; use `flattening(distance=0.01)` (v1.7 FIX) |

---

## Limitations (Documented)

1. **OCS Transformation**: Text entities with non-WCS extrusion vectors may not be positioned correctly. Most DXF files use WCS by default.

2. **MTEXT Formatting**: Complex MTEXT formatting (colors, fonts, spacing) is not preserved. Only plain text content is converted.

3. **Font Dependencies**: Text rendering depends on matplotlib's font availability. Missing fonts may cause fallback behavior.
   - **Windows-Specific**: On Windows, matplotlib may not find all system fonts. Users may need to rebuild matplotlib's font cache by deleting `~/.matplotlib/fontlist-vXXX.json`.

4. **Performance**: Text-to-path conversion is slower than basic geometry parsing. Target: < 5 seconds for 100 text entities (after font cache warmup).

5. **GUI Configuration**: `text_mode` parameter is currently only available via API and TCL commands. GUI import dialog does not expose this option.

6. **Nested Blocks**: Deeply nested block references (blocks within blocks) are supported via recursive `get_geo()` calls, but performance may degrade.

7. **Array Insertion Duplicates (KNOWN ISSUE)**: When an INSERT entity has `row_count > 1` OR `column_count > 1`, the existing array handling logic may produce duplicate geometries. This is a **pre-existing bug** that has been preserved to avoid introducing new issues during this implementation. A TODO comment has been added to `get_geo_from_insert()` to alert future developers. 
   - **Example 1:** An INSERT with row_count=2 and column_count=1 may produce 3 geometries (2 from row loop + 1 from final append) instead of 2.
   - **Example 2:** An INSERT with row_count=1 and column_count=2 may produce 3 geometries (2 from column loop + 1 from final append) instead of 2.
   - **Example 3:** An INSERT with row_count=2 and column_count=2 may produce more than 4 geometries due to both loops firing plus final append.

---

## Rollback Plan

If implementation causes regressions:

1. **Quick rollback:** Revert all changes to `appParsers/ParseDXF.py` only (core parser changes)
2. **Partial rollback:** Keep Tasks 0.1, 1.1 (imports) but comment out Tasks 1.2-1.5 (text handling)
3. **Full rollback:** Restore all affected files to pre-implementation state

**Files to restore for full rollback:**
- `requirements.txt` (Task 0.1)
- `appParsers/ParseDXF.py` (Tasks 1.1-1.5)
- `camlib.py` (Task 2.1)
- `appParsers/ParseGerber.py` (Task 2.2)
- `tclCommands/TclCommandOpenDXF.py` (Task 2.3)
- `appHandlers/appIO.py` (Task 3.1)

**Commit Strategy:**
Implementation should be committed as **multiple atomic commits** to enable easier partial rollbacks:
- Commit 1: Task 0.1 (requirements.txt update)
- Commit 2: Tasks 1.1-1.5 (core parser implementation)
- Commit 3: Tasks 2.1-2.3 (integration)
- Commit 4: Task 3.1 (appIO configuration)
- Commit 5: Tasks 4.1-4.2 (tests and validation)

This allows rolling back individual phases without affecting others.

---

## Index Notes

- **indexed_at:** 2026-03-14T19:35:19.765665
- **repo:** `local/FlatCAM_EVO-abd24de5`

**Key symbol IDs to verify after implementation:**
- `appParsers/ParseDXF.py::dxftext2shapely#function` (NEW)
- `appParsers/ParseDXF.py::getdxftext#function` (UNCHANGED - reserved for future)
- `appParsers/ParseDXF.py::get_geo#function` (MODIFIED - added text_mode param + TEXT/MTEXT/ATTRIB handling)
- `appParsers/ParseDXF.py::getdxfgeo#function` (MODIFIED - added text_mode param)
- `appParsers/ParseDXF.py::get_geo_from_insert#function` (MODIFIED - added text_mode param)
- `camlib.py::Geometry.import_dxf_as_geo#method` (MODIFIED - added text_mode param)

---

## Executor Notes: API Verification Script

**MUST RUN BEFORE Task 1.2 Implementation**

```python
"""
ezdxf text2path API Verification Script
Run this before implementing dxftext2shapely() to confirm API matches plan assumptions.

REVIEW FINDINGS (v1.6 bugs that this script would have caught):
1. text2paths() does NOT exist - correct function is make_paths_from_entity()
2. flattening() requires distance argument - cannot call without parameters
3. ATTRIB.dxf.text returns the text value - dxf.value fallback is unnecessary
"""
import sys
import ezdxf

print(f"ezdxf version: {ezdxf.__version__}")

# Check version
version = tuple(map(int, ezdxf.__version__.split('.')[:3]))
if version < (0, 16, 0):
    print(f"ERROR: ezdxf {ezdxf.__version__} is too old. Need >= 0.16.0")
    sys.exit(1)

# Try to import text2path
try:
    from ezdxf.addons import text2path
    print("✓ text2path addon available")
except ImportError as e:
    print(f"ERROR: text2path addon not available: {e}")
    sys.exit(1)

# Create a minimal test document
doc = ezdxf.new()
msp = doc.modelspace()

# Add a simple TEXT entity
text = msp.add_text("TEST", dxfattribs={
    'height': 2.5,
    'insert': (0, 0),
    'rotation': 0,
})

# Test the API
print("\n--- API Verification ---")

# TEST 1: Verify correct function name
print("\nTest 1: Function name verification")
try:
    # CORRECT API - this should work
    paths = list(text2path.make_paths_from_entity(text))
    print(f"✓ make_paths_from_entity() returned {len(paths)} path(s)")
except Exception as e:
    print(f"ERROR: make_paths_from_entity() failed: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    # WRONG API - this should NOT exist (v1.6 bug)
    paths = list(text2path.text2paths(text))
    print(f"✗ WARNING: text2paths() exists (unexpected - plan v1.6 was wrong)")
except AttributeError:
    print(f"✓ Confirmed: text2paths() does NOT exist (use make_paths_from_entity)")

# TEST 2: Verify flattening() signature
print("\nTest 2: flattening() signature verification")
if paths:
    path = paths[0]
    print(f"✓ path.is_closed = {path.is_closed} (type: {type(path.is_closed).__name__})")
    
    try:
        # WRONG - missing required argument (v1.6 bug)
        vertices = list(path.flattening())
        print(f"✗ WARNING: flattening() worked without distance (unexpected)")
    except TypeError as e:
        print(f"✓ Confirmed: flattening() requires distance argument: {e}")
    
    try:
        # CORRECT - with distance argument
        vertices = list(path.flattening(distance=0.01))
        print(f"✓ flattening(distance=0.01) returned {len(vertices)} vertices")
        
        if vertices:
            v = vertices[0]
            print(f"✓ Vec3 type: {type(v).__name__}")
            print(f"✓ Vec3 access: v.x={v.x}, v.y={v.y}, v.z={v.z}")
            # Test indexing support (may not be available)
            try:
                print(f"✓ Vec3 indexing: v[0]={v[0]}, v[1]={v[1]}")
            except (TypeError, IndexError) as e:
                print(f"✗ Vec3 does NOT support indexing: {e}")
                print("  → Use v.x, v.y attributes instead")
    except Exception as e:
        print(f"ERROR: flattening(distance=0.01) failed: {type(e).__name__}: {e}")
        sys.exit(1)

# Test ATTRIB entity
print("\n--- ATTRIB Entity Test ---")
block = doc.blocks.new('TEST_BLOCK')
block.add_text("BLOCK_TEXT", dxfattribs={'height': 2.5})
insert = msp.add_blockref('TEST_BLOCK', (0, 0))
attrib = insert.add_attrib('TAG1', 'ATTRIB_VALUE')

print(f"✓ ATTRIB.dxf.tag = {attrib.dxf.tag}")
print(f"✓ ATTRIB.dxf.value = {attrib.dxf.value}")
text_attr = getattr(attrib.dxf, 'text', 'NOT_FOUND')
print(f"✓ ATTRIB.dxf.text = {text_attr}")

if text_attr != 'NOT_FOUND':
    print(f"✓ CONFIRMED: ATTRIB has 'text' attribute - use dxf.text for ALL entity types")
    print(f"  (v1.6 bug: incorrectly claimed ATTRIB uses dxf.value)")
else:
    print(f"✗ ATTRIB.dxf.text not found - may need dxf.value fallback")

print("\n--- API Verification Complete ---")
print("All API assumptions confirmed. Proceed with implementation.")
```

**Expected Output (based on ezdxf 1.4.3):**
```
ezdxf version: 1.4.3
✓ text2path addon available

--- API Verification ---

Test 1: Function name verification
✓ make_paths_from_entity() returned N path(s)
✓ Confirmed: text2paths() does NOT exist (use make_paths_from_entity)

Test 2: flattening() signature verification
✓ path.is_closed = True/False
✓ Confirmed: flattening() requires distance argument: missing 1 required positional argument: 'distance'
✓ flattening(distance=0.01) returned N vertices
✓ Vec3 type: Vec3
✓ Vec3 access: v.x=0.0, v.y=0.0, v.z=0.0
✓/✗ Vec3 indexing: may or may not work → use attributes

--- ATTRIB Entity Test ---
✓ ATTRIB.dxf.tag = TAG1
✓ ATTRIB.dxf.value = ATTRIB_VALUE
✓ ATTRIB.dxf.text = ATTRIB_VALUE
✓ CONFIRMED: ATTRIB has 'text' attribute - use dxf.text for ALL entity types
  (v1.6 bug: incorrectly claimed ATTRIB uses dxf.value)

--- API Verification Complete ---
All API assumptions confirmed. Proceed with implementation.
```

**If output differs from expected:**
1. Document the actual API behavior
2. Update Task 1.2 spec to match actual API
3. Notify planning agent of discrepancy before proceeding

---

## Revision History (v1.7 Changes)

| Bug ID | Issue | v1.6 (Wrong) | v1.7 (Correct) |
|--------|-------|--------------|----------------|
| Bug 1 | Function name | `text2path.text2paths(entity)` | `text2path.make_paths_from_entity(entity)` |
| Bug 2 | flattening signature | `path.flattening()` | `path.flattening(distance=0.01)` |
| Bug 3 | ATTRIB attribute | `dxf.value` fallback | `dxf.text` for all types |
| Doc 1 | API Notes | Listed wrong function name | Corrected to `make_paths_from_entity()` |
| Doc 2 | Constraints table | "ATTRIB uses 'value' attribute" | "ATTRIB uses 'text' attribute" |
| Script | Verification | Would not have caught bugs | Added explicit tests for all 3 bugs |

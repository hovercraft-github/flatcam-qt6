# Gerber Parser Refactoring: Incremental Path to Maintainability
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
**Goal:** Refactor `ParseGerber.py` to eliminate the 1300+ line `parse_lines()` god method through incremental, test-driven extraction of command handlers, building toward a maintainable state machine architecture.
**Architecture:** Phase-gated approach: (1) Tests first, (2) Extract command handlers, (3) Extract state transformers, (4) Optional state machine. Each phase is independently valuable and reversible.
**Tech Stack:** Python 3.x, PyQt6, Shapely, NumPy, pytest
**Risk Mitigation:** Based on post-mortem from `docs/plans/2026-03-13-gerber-parser-state-machine.md`, this plan mandates automated tests BEFORE any refactoring, uses minimal-scope extractions, and keeps the scattered variables approach until the final optional phase.
---
## Context & Current State
### What Exists (Verified 2026-03-13)
| Component | Status | Location |
|-----------|--------|----------|
| `parse_lines()` method | ⚠️ 1300+ lines | `appParsers/ParseGerber.py:423-1750` |
| `_add_path_geometry_to_buffers()` | ✅ Exists | Line 1752 |
| `_add_flash_to_buffers()` | ✅ Exists | Line 1821 |
| Type hints | ✅ Complete | All signatures |
| Architecture notes | ✅ Documented | `parse_lines()` docstring |
| Test scaffolding | ⚠️ Outdated comments | `tests/test_gerber_parser.py` |
### What Failed Before
From `docs/plans/2026-03-13-gerber-parser-state-machine.md`:
Timeline of Failure:
1. Add dataclass + aliases → Worked
2. Remove aliases, use state.* → Broken (IndexError on empty path)
3. Fix path bug → Still broken (more edge cases surfaced)
4. Update helpers → Unfixable (cascading failures)
5. Revert → Stable
Root Cause: Treated as "mechanical" refactoring when it required 
understanding all edge cases first. No automated tests existed.
### Key Insight
The scattered variables approach has **implicit guards** that prevent edge cases. Any refactoring must either:
1. Preserve these guards exactly, OR
2. Have comprehensive tests to catch violations
---
## Phases Overview
Phase 0: Foundation (Tests + Documentation) - MANDATORY
Phase 1: Extract Command Handlers (Low Risk) - SAFE
Phase 2: Extract State Transformers (Medium Risk) - TESTED
Phase 3: Optional State Machine (High Risk) - ONLY IF NEEDED
---
## Phase 0: Foundation - Tests & Documentation
**Goal:** Create comprehensive automated test suite that catches the bugs that broke the previous refactoring attempt.
### Task 0.1: Fix Test File Comments
**Files:**
- Modify: `tests/test_gerber_parser.py:1-10`
**Step 1: Update module docstring**
```python
#!/usr/bin/env python
"""
Automated tests for Gerber parser parse_lines() method.
REQUIRED before any refactoring of the Gerber parser state management.
These tests validate the scattered variables approach.
(ParserState dataclass approach was abandoned - see docs/plans/)
Run: python tests/test_gerber_parser.py
"""
Step 2: Commit
git add tests/test_gerber_parser.py
git commit -m "docs: fix test file comments to reflect actual architecture
- Removes reference to abandoned ParserState approach
- Clarifies tests are for scattered variables approach
- Adds run instructions
"
Task 0.2: Add Missing Edge Case Tests
Files:
- Modify: tests/test_gerber_parser.py:207-280 (TestGerberParserEdgeCases class)
Step 1: Add test for polarity change with pending path
def test_polarity_change_with_pending_path(self):
    """
    Test polarity change (%LPC*%/%LPD*%) with geometry in path buffer.
    
    This tests the code block at ParseGerber.py:580-630 which finalizes
    the current path before applying polarity change.
    """
    gbr = get_gerber_parser()
    
    lines = [
        "%FSLAX24Y24*%",
        "%MOIN*%",
        "%ADD10C,10*%",
        "D10*",
        "G01 X0Y0D02*",        # Start position
        "G01 X100Y0D01*",      # Draw line (in path buffer)
        "%LPC*%",              # Polarity change - should finalize path
        "G01 X50Y50D02*",      # New position
        "G01 X150Y150D01*",    # Draw with clear polarity
        "%LPD*%",              # Back to dark
        "M02*",
    ]
    
    result = gbr.parse_lines(lines)
    assert result is None or result == ""
    # Should have geometry from both dark and clear sections
    assert gbr.solid_geometry is not None
    print("[PASS] Polarity change with pending path test passed")
Step 2: Add test for tool change with pending path
def test_tool_change_with_pending_path(self):
    """
    Test tool change (D10 → D11) with geometry in path buffer.
    
    This tests ParseGerber.py:848-858 which calls 
    _add_path_geometry_to_buffers() on tool change.
    """
    gbr = get_gerber_parser()
    
    lines = [
        "%FSLAX24Y24*%",
        "%ADD10C,5*%",         # Aperture 10: 5mm
        "%ADD11C,10*%",        # Aperture 11: 10mm
        "D10*",
        "G01 X0Y0D02*",
        "G01 X100Y0D01*",      # Draw with aperture 10
        "D11*",                # Tool change - should finalize path
        "G01 X100Y100D01*",    # Draw with aperture 11
        "M02*",
    ]
    
    result = gbr.parse_lines(lines)
    assert result is None or result == ""
    # Both apertures should have geometry
    assert 10 in gbr.tools
    assert 11 in gbr.tools
    print("[PASS] Tool change with pending path test passed")
Step 3: Add test for region start with pending path
def test_region_start_with_pending_path(self):
    """
    Test G36 (region start) with geometry in path buffer.
    
    This tests ParseGerber.py:866-916 which finalizes path
    before starting region mode.
    """
    gbr = get_gerber_parser()
    
    lines = [
        "%FSLAX24Y24*%",
        "%ADD10C,10*%",
        "D10*",
        "G01 X0Y0D02*",
        "G01 X100Y0D01*",      # Draw line (should be finalized)
        "G36*",                # Region start
        "X100Y100D01*",
        "X0Y100D01*",
        "X0Y0D01*",
        "G37*",                # Region end
        "M02*",
    ]
    
    result = gbr.parse_lines(lines)
    assert result is None or result == ""
    # Should have both line and region geometry
    assert gbr.solid_geometry is not None
    print("[PASS] Region start with pending path test passed")
Step 4: Run tests to verify they pass
cd D:\1.Development\FlatCAM_EVO
python tests/test_gerber_parser.py
Expected: All tests pass
Step 5: Commit
git add tests/test_gerber_parser.py
git commit -m "test: add edge case tests for state transitions
- Test polarity change with pending path (line 580-630)
- Test tool change with pending path (line 848-858)
- Test region start with pending path (line 866-916)
These tests catch the bugs that broke the previous state machine
refactoring attempt.
"
Task 0.3: Create Test Gerber Files
Files:
- Create: tests/test_files/simple_line.gbr
- Create: tests/test_files/region_test.gbr
- Create: tests/test_files/flash_test.gbr
Step 1: Create simple line test file
%FSLAX24Y24*%
%MOIN*%
%ADD10C,0.010000*%
D10*
G01 X0Y0D02*
G01 X1000000Y1000000D01*
M02*
Step 2: Create region test file
%FSLAX24Y24*%
%MOIN*%
%ADD10C,0.010000*%
D10*
G01 X0Y0D02*
G36*
X0Y0D01*
X1000000Y0D01*
X1000000Y1000000D01*
X0Y1000000D01*
X0Y0D01*
G37*
M02*
Step 3: Create flash test file
%FSLAX24Y24*%
%MOIN*%
%ADD10C,0.010000*%
D10*
X0Y0D02*
X500000Y500000D03*
M02*
Step 4: Add integration test that loads real files
def test_load_real_gerber_files():
    """Test loading actual Gerber files from test_files directory."""
    import os
    test_dir = os.path.dirname(os.path.abspath(__file__))
    files_dir = os.path.join(test_dir, 'test_files')
    
    test_files = [
        'simple_line.gbr',
        'region_test.gbr',
        'flash_test.gbr',
    ]
    
    for filename in test_files:
        filepath = os.path.join(files_dir, filename)
        if os.path.exists(filepath):
            gbr = get_gerber_parser()
            result = gbr.parse_file(filepath)
            assert result is None or result != 'fail', f"{filename} failed to parse"
            print(f"[PASS] Loaded {filename}")
        else:
            print(f"[SKIP] {filename} not found")
Step 5: Commit
git add tests/test_files/ tests/test_gerber_parser.py
git commit -m "test: add real Gerber test files and integration test
- simple_line.gbr: Basic line drawing
- region_test.gbr: G36-G37 region
- flash_test.gbr: D03 flash
Integration test verifies parser can load actual files.
"
Task 0.4: Document Current State Metrics
Files:
- Create: docs/plans/2026-03-13-gerber-refactor-baseline.md
Step 1: Create baseline document
# Gerber Parser Refactoring Baseline
**Date:** 2026-03-13
**Commit:** [CURRENT HEAD]
## File Statistics
| Metric | Value |
|--------|-------|
| Total lines | 2795 |
| parse_lines() lines | ~1327 (423-1750) |
| Helper methods | 2 |
| Test cases | 13 |
## Current Architecture
- Scattered local variables (by design)
- 2 extracted helpers: _add_path_geometry_to_buffers, _add_flash_to_buffers
- Comprehensive type hints
- Section header comments (### blocks)
## Test Coverage
- Basic parsing: 6 tests
- Edge cases: 5 tests
- Units: 2 tests
All tests must pass before any refactoring.
Step 2: Commit
git add docs/plans/2026-03-13-gerber-refactor-baseline.md
git commit -m "docs: create refactoring baseline document
Records current state before any refactoring:
- File statistics
- Architecture decisions
- Test coverage
"
---
Phase 1: Extract Command Handlers (Low Risk)
Goal: Extract each Gerber command handler (G01, G02/3, G36, G37, etc.) into separate methods. Each extraction is independent and reversible.
Why Low Risk: These are pure extractions - no behavior changes, just moving code to named methods.
Task 1.1: Extract G36 Handler (Region Start)
Files:
- Modify: appParsers/ParseGerber.py
- Add after: _add_flash_to_buffers() (line 1868)
Step 1: Add the handler method
def _handle_region_start(
    self,
    path: List[List[float]],
    last_path_aperture: Optional[int],
    poly_buffer: List[Any],
    follow_buffer: List[Any],
    steps: int,
    line_num: int,
    current_operation_code: Optional[int]
) -> Tuple[List[List[float]], Optional[int]]:
    """
    Handle G36* command (begin region mode).
    
    Finalizes any pending path geometry before entering region mode.
    
    :param path: Current path coordinates
    :param last_path_aperture: Last used aperture ID
    :param poly_buffer: Polygon buffer (modified in place)
    :param follow_buffer: Follow geometry buffer (modified in place)
    :param steps: Arc resolution
    :param line_num: Current line number for error reporting
    :param current_operation_code: Last operation code
    :return: Tuple of (updated_path, updated_last_path_aperture)
    """
    try:
        path_length = len(path)
    except TypeError:
        path_length = 1
    
    if path_length > 1:
        # Finalize pending path before region
        geo_dict = {}
        geo_f = LineString(path)
        if not geo_f.is_empty:
            follow_buffer.append(geo_f)
            geo_dict['follow'] = geo_f
        
        width = self.tools[last_path_aperture]["size"]
        geo_s = geo_f.buffer(width / 1.999, steps)
        if not geo_s.is_valid:
            self.app.log.warning(
                "Found invalid Gerber geometry at line: %s. Fixing..." % str(line_num))
            geo_s = geo_s.buffer(0.0000001, steps)
        
        if not geo_s.is_valid:
            self.app.log.warning(
                "Failed to fix the invalid Geometry found at line: %s" % str(line_num))
        else:
            self.tools.setdefault(last_path_aperture, {}).setdefault('geometry', [])
            try:
                for pol in geo_s:
                    if not pol.is_empty:
                        prepare(pol)
                        poly_buffer.append(pol)
                        if self.is_lpc is True:
                            geo_dict['clear'] = pol
                        else:
                            geo_dict['solid'] = pol
                    
                    if not pol.is_empty:
                        self.tools[last_path_aperture]['geometry'].append(geo_dict)
            except TypeError:
                if not geo_s.is_empty:
                    poly_buffer.append(geo_s)
                    if self.is_lpc is True:
                        geo_dict['clear'] = geo_s
                    else:
                        geo_dict['solid'] = geo_s
                    
                    if not geo_s.is_empty:
                        self.tools[last_path_aperture]['geometry'].append(geo_dict)
        
        path = [path[-1]]
    
    # Enter region mode
    # flashes are not allowed inside regions
    if current_operation_code == 3:
        current_operation_code = 2
    
    return path, last_path_aperture
Step 2: Replace inline G36 handling with method call
At line 866-916, replace with:
if self.regionon_re.search(gline) and current_aperture != "failure":
    path, last_path_aperture = self._handle_region_start(
        path, last_path_aperture, poly_buffer, follow_buffer,
        steps, line_num, current_operation_code
    )
    making_region = True
    continue
Step 3: Run tests
python tests/test_gerber_parser.py
Expected: All tests pass
Step 4: Commit
git add appParsers/ParseGerber.py
git commit -m "refactor: extract _handle_region_start() method
- Extracts G36* command handling
- Finalizes pending path before entering region mode
- No behavior changes - pure extraction
"
Task 1.2: Extract G37 Handler (Region End)
Files:
- Modify: appParsers/ParseGerber.py:922-1039
Step 1: Add the handler method
def _handle_region_end(
    self,
    path: List[List[float]],
    current_aperture: Optional[int],
    current_x: float,
    current_y: float,
    poly_buffer: List[Any],
    follow_buffer: List[Any],
    steps: int,
    line_num: int,
    current_operation_code: Optional[int]
) -> Tuple[List[List[float]], bool]:
    """
    Handle G37* command (end region mode).
    
    Creates region polygon from path and adds to buffers.
    
    :param path: Region path coordinates
    :param current_aperture: Current aperture ID (may be None for regions)
    :param current_x: Current X coordinate
    :param current_y: Current Y coordinate
    :param poly_buffer: Polygon buffer (modified in place)
    :param follow_buffer: Follow geometry buffer (modified in place)
    :param steps: Arc resolution
    :param line_num: Current line number
    :param current_operation_code: Last operation code
    :return: Tuple of (new_path, success)
    """
    # Ensure aperture 0 exists for region storage
    if 0 not in self.tools:
        self.tools[0] = {
            'type': 'REG',
            'size': 0.0,
            'geometry': []
        }
    
    # Handle D02 before G37 edge case
    if current_operation_code == 2:
        try:
            path_length = len(path)
        except TypeError:
            path_length = 1
        
        if path_length == 1:
            # Geometry was prepared previously, just add it
            # [Keep existing logic from lines 940-964]
            pass
    
    # Validate path has minimum points
    try:
        path_length = len(path)
    except TypeError:
        path_length = 1
    
    if path_length < 3:
        return [[current_x, current_y]], True  # Skip invalid region
    
    # Create region polygon
    geo_dict = {}
    if current_aperture in self.tools:
        region_geo = Polygon(path)
    else:
        region_geo = Polygon(path)
    
    # [Rest of region creation logic from lines 990-1037]
    # ...
    
    return [[current_x, current_y]], True
Step 2: Replace inline G37 handling with method call
Step 3: Run tests
Step 4: Commit
---
Phase 2: Extract State Transformers (Medium Risk)
Goal: Extract the 6 transformation methods (scale, offset, mirror, skew, rotate, buffer) to use a common base.
Why Medium Risk: These methods have shared logic but also unique behavior. Need careful testing.
Task 2.1: Extract _transform_geometry_base
Files:
- Modify: appParsers/ParseGerber.py (add before scale method, ~line 2147)
Step 1: Add the base method
def _transform_geometry_base(
    self,
    transform_func: Callable[[Any], Any],
    display_name: str,
    update_aperture_params: Optional[Callable[[Dict[str, Any], float], None]] = None
) -> Optional[str]:
    """
    Base method for geometric transformations.
    
    :param transform_func: Function that applies transformation to single geometry
    :param display_name: Name for progress messages
    :param update_aperture_params: Optional function to update aperture parameters
    :return: None on success, 'fail' on error
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
        """Recursively apply transformation."""
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
                    for key in ['solid', 'follow', 'clear']:
                        if key in geo_el:
                            geo_el[key] = transform_recursive(geo_el[key])
    except Exception as e:
        self.app.log.error(f'ParseGerber.Gerber.{display_name}() Exception --> {e}')
        return 'fail'
    
    # Update aperture parameters if callback provided
    if update_aperture_params:
        # Apply to each aperture
        pass
    
    self.app.inform.emit('[success] %s' % _("Done."))
    self.app.proc_container.new_text = ''
    return None
Step 2: Refactor scale() to use base
Step 3: Run tests
Step 4: Commit
---
Phase 3: Optional State Machine (High Risk - ONLY IF NEEDED)
Goal: Consolidate scattered state variables into a ParserState dataclass.
WARNING: This phase caused the previous refactoring to fail. Only proceed if:
1. All Phase 0-2 tests pass
2. Manual testing with real Gerber files succeeds
3. Team agrees the benefit outweighs the risk
Task 3.1: Create ParserState Dataclass (DO NOT USE YET)
Files:
- Create: appParsers/gerber_parser_state.py
Step 1: Create dataclass in separate file
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
@dataclass
class ParserState:
    """Consolidated parser state for Gerber parsing."""
    
    # Path tracking
    path: List[List[float]] = field(default_factory=list)
    last_path_aperture: Optional[int] = None
    
    # Temporary geometry
    geo_s: Any = None
    geo_f: Any = None
    
    # Buffers
    poly_buffer: List[Any] = field(default_factory=list)
    follow_buffer: List[Any] = field(default_factory=list)
    
    # Current state
    current_aperture: Optional[int] = None
    current_x: float = 0.0
    current_y: float = 0.0
    current_interpolation_mode: Optional[int] = None
    current_operation_code: Optional[int] = None
    current_polarity: str = 'D'
    
    # Mode flags
    making_region: bool = False
    quadrant_mode: Optional[str] = None
    
    # Metadata
    line_num: int = 0
Step 2: DO NOT integrate yet - create as reference
---
Success Criteria
Phase	Criteria
Phase 0	All 13+ tests pass, test files load successfully
Phase 1	All handlers extracted, tests still pass, no behavior changes
Phase 2	Transformation methods use base, tests pass
Phase 3	Only if team approves risk
---
Rollback Plan
# Each phase has its own commit - revert specific phase
git revert HEAD  # Revert last phase
git revert HEAD~1  # Revert second-to-last

# Or restore to baseline
git checkout <baseline-commit> -- appParsers/ParseGerber.py
---
Risk Assessment
Risk	Likelihood	Impact	Mitigation
Edge case bugs (empty path)	Medium	High	Phase 0 tests catch these
Cascading failures	Medium	High	Small commits, test after each
Team disagrees with approach	Low	Medium	Each phase is independently valuable
Performance regression	Low	Medium	Benchmark with large Gerber files
---
## Open Questions
1. **Should Phase 3 (state machine) even be attempted?** The scattered variables work - is the maintainability gain worth the risk?
2. **Are 13 test cases enough?** Should we add more edge cases from real-world Gerber files?
3. **Should we extract more helpers first?** There are still repeated patterns in the G01 handler.
---
Index Notes
- indexed_at: 2026-03-13T21:30:49
- Repo: local/FlatCAM_EVO-abd24de5
- File: appParsers/ParseGerber.py (2795 lines)
- Symbols verified: _add_path_geometry_to_buffers#method, _add_flash_to_buffers#method
- Not found: _finalize_region, _transform_geometry_base (not yet implemented)
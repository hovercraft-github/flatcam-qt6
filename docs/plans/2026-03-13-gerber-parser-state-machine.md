# Gerber Parser State Machine Refactoring Plan

> **STATUS: ABANDONED (2026-03-13)** - Refactoring was reverted after introducing breaking bugs. See "Post-Mortem" section for full analysis.

> **For Future Maintainers:** DO NOT attempt this refactoring without first writing comprehensive automated tests for `parse_lines()`. The manual testing approach (load files in GUI) is insufficient for this scale of change.

---

## Executive Summary

**Attempted:** Consolidate ~20 scattered local variables in `parse_lines()` into a `ParserState` dataclass.

**Result:** ❌ **Reverted** - Introduced breaking bugs that cascaded through the codebase.

**What We're Keeping:**
- ✅ `_add_path_geometry_to_buffers()` helper (commit `0bc56d86`)
- ✅ `_add_flash_to_buffers()` helper (commit `85843992`)  
- ✅ Comprehensive type hints (commit `a7557b2c`)

**What We're Abandoning:**
- ❌ `ParserState` dataclass
- ❌ Direct `state.*` usage throughout `parse_lines()`
- ❌ Helper method signature changes

---

## Post-Mortem: What Went Wrong

### Timeline of Failure

| Attempt | Commit | Result | Bug Introduced |
|---------|--------|--------|----------------|
| 1. Add dataclass + aliases | `b954713d` | ✅ Worked | None |
| 2. Remove aliases, use `state.*` | `06e4c630` | ⚠️ Broken | `state.path[-1]` on empty list |
| 3. Fix path bug | `71503d08` | ⚠️ Still broken | More edge cases surfaced |
| 4. Update helpers | `53fe57a3` | ❌ Unfixable | Cascading failures |
| **Revert** | `git reset --hard a7557b2c` | ✅ Stable | - |

### The Breaking Bug (and Why It Mattered)

```python
# Line 903 - After refactoring:
state.path = [state.path[-1]]  # IndexError: list index out of range

# Original code (line ~658):
path = [path[-1]]  # Also would fail, BUT...
```

**Why the original worked:** The original code had implicit guards scattered throughout 1,139 lines that we didn't fully map:
- Some code paths set `path = []` then `continue` before reaching the reset
- Some code paths check `if path:` before operations
- The D02-before-G37 edge case (which we fixed in Phase 2 of the helper extraction) has special handling

**Our mistake:** We assumed the refactoring was mechanical (`path` → `state.path`), but the *interactions* between state variables created edge cases we didn't catalog.

### All Bugs We Encountered

| Bug | Location | Root Cause | Fix Attempted |
|-----|----------|------------|---------------|
| `IndexError: list index out of range` | Line 903 | `state.path[-1]` on empty list | Added `if state.path:` guard |
| More edge cases | Multiple | Interconnected state mutations | Would have required full audit |
| LSP type errors | Throughout | Helper method signature changes | Would need extensive `# type: ignore` |

### The Fundamental Problem

**We treated this as a "mechanical" refactoring when it was actually a "understand all edge cases first" refactoring.**

```
Mechanical refactoring (safe):
  - Rename a variable everywhere
  - Extract a method with no side effects
  - Add type hints to existing code

Understanding-first refactoring (risky without tests):
  - Change how state is stored/accessed
  - Modify helper method signatures
  - Alter control flow patterns
```

### Why We Couldn't Test Our Way Out

| Testing Approach | Why It Failed |
|------------------|---------------|
| Manual GUI testing | Only tests happy paths we think to try |
| Syntax checking (`python -m py_compile`) | Only validates Python syntax, not logic |
| Import testing | Only validates module loads, not parsing |
| **What we needed** | **Automated tests with known-good Gerber files** |

---

## Documentation Comments: What We Learned

### The Value We Were Chasing

The original motivation was **maintainability through explicit state**:

```python
# Before (implicit state scattered across 68 lines):
path = []
geo_s = None
current_x = 0
# ... 17 more variables

# After (explicit state in one place):
state = ParserState()  # All 24 fields documented in dataclass
```

### What Actually Helps Maintainability

Based on this experience, here's what **actually** improves this codebase:

| Technique | Risk | Value | Verdict |
|-----------|------|-------|---------|
| Helper method extraction | Low | High | ✅ **DO THIS** |
| Type hints on signatures | Low | Medium | ✅ **DO THIS** |
| Section comments (the `###` headers) | None | High | ✅ **KEEP THESE** |
| Inline variable comments | None | Medium | ✅ **KEEP THESE** |
| Dataclass for state | **High** | Medium | ❌ **NOT WORTH IT** |
| State machine pattern | **High** | Low | ❌ **OVERKILL** |

### The Comments That Matter Most

The Gerber parser has excellent section comments that **must be preserved**:

```python
# ###############################################################
# ################   Ignored lines   ############################
# ################     Comments      ############################
# ###############################################################

# ###############################################################
# ################  Polarity change #############################
# ########   Example: %LPD*% or %LPC*%        ###################
# ########   If polarity changes, creates geometry from current #
# ########    buffer, then adds or subtracts accordingly.       #
# ###############################################################
```

**These comments are more valuable than a state machine** because they explain *why* the code does what it does, not just *what* variables it uses.

---

## Guidance for Future Maintainers

### If You Want to Improve This Code

**Start here (safe, valuable):**

1. ✅ **Add automated tests** - Create test Gerber files and verify parsing output
2. ✅ **Extract more helpers** - Find repeated code patterns in `parse_lines()`
3. ✅ **Add section documentation** - Explain what each code block does
4. ✅ **Add type hints** - To function signatures, not internal variables

**Avoid until you have tests:**

1. ❌ **Changing state representation** - Variables → dataclass → ???
2. ❌ **Changing helper signatures** - Breaks call sites in hard-to-test ways
3. ❌ **"Mechanical" refactors** - They're never truly mechanical in 1,139-line functions

### Minimum Viable Test Suite (Before Any Refactoring)

```python
def test_simple_line():
    """Test basic D01 line drawing"""
    gbr = Gerber(app)
    gbr.parse_lines(["%FSLAX24Y24*%", "G01 X0Y0*", "G01 X100Y100D02*", "M02*"])
    assert len(gbr.solid_geometry) > 0

def test_flash():
    """Test D03 flash"""
    # ...

def test_region():
    """Test G36-G37 region"""
    # ...

def test_d02_before_g37():
    """Test edge case: D02 before G37 (we fixed this in Phase 2)"""
    # ...

def test_empty_path():
    """Test that empty paths don't crash"""
    # ...

def test_all_aperture_types():
    """Test circle, rectangle, polygon apertures"""
    # ...
```

**Without these tests, any refactoring is gambling.**

---

## Original Plan (Archived - For Reference Only)

> ⚠️ **DO NOT IMPLEMENT** - This plan was attempted and failed. Preserved for historical context.

### Problem: `parse_lines()` Has 20+ Scattered State Variables

The function has 68 lines of variable initialization (lines 435-502 in original):

```python
path = []                      # Coordinates of current path
geo_s = None                   # Temporary solid geometry
geo_f = None                   # Temporary follow geometry  
poly_buffer = []               # Polygons until polarity change
follow_buffer = []             # Follow geometry storage
current_aperture = None        # Current aperture number
current_x = 0                  # Current X coordinate
current_y = 0                  # Current Y coordinate
# ... and ~13 more variables
```

### Proposed Solution (Abandoned)

Create a `ParserState` dataclass:

```python
@dataclass
class ParserState:
    """Consolidated parser state - DON'T USE THIS, SEE POST-MORTEM"""
    current_x: float = 0.0
    current_y: float = 0.0
    path: List[List[float]] = field(default_factory=list)
    # ... 20+ more fields
```

Then convert all 1,139 lines to use `state.field` instead of bare variables.

### Why This Seemed Like A Good Idea

| Perceived Benefit | Reality |
|-------------------|---------|
| "All state in one place" | ✅ True, but not worth the risk |
| "Type safety" | ⚠️ Partial - mypy still complained |
| "Easier to understand" | ❌ Harder - comments got scattered |
| "Mechanical/safe" | ❌ **False** - edge cases everywhere |

---

## Commits From This Effort

| Commit | Description | Status |
|--------|-------------|--------|
| `a7557b2c` | feat: add comprehensive type hints | ✅ **Kept** |
| `85843992` | refactor: extract `_add_flash_to_buffers` | ✅ **Kept** |
| `0bc56d86` | refactor: extract `_add_path_geometry_to_buffers` | ✅ **Kept** |
| `e0815843` | refactor: add ParserState dataclass | ❌ Reverted |
| `b954713d` | refactor: use ParserState with aliases | ❌ Reverted |
| `06e4c630` | refactor: remove aliases, use `state.*` | ❌ Reverted |
| `71503d08` | refactor: update `_add_path_geometry_to_buffers` | ❌ Reverted |
| `53fe57a3` | refactor: update `_add_flash_to_buffers` | ❌ Reverted |

---

## Final Recommendation

**For the next developer who looks at this code:**

1. The helper method extractions we completed **are improvements** - they reduced code duplication and are working correctly.

2. The state machine idea **isn't wrong** - it's just not worth the risk without:
   - Automated tests for all edge cases
   - A full map of state interactions
   - Ability to test with real Gerber files programmatically

3. **The comments are your friend** - The `###` section headers explain the Gerber spec requirements. Understanding those is more valuable than knowing which object holds `current_x`.

4. **If you must refactor** - Do it one tiny piece at a time, with manual testing after each commit. Be prepared to revert quickly.

---

**Document created:** 2026-03-13  
**Status:** Abandoned after failed implementation  
**Author:** Refactoring team (Marius + AI assistant)

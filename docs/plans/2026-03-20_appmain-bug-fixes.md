# appMain.py — Bug Fixes and Reliability Improvements

**Created:** 2026-03-20  
**Target File:** `appMain.py` (8,200 lines)  
**Source:** 4 external code reviews + 1 independent review  
**Status:** Research complete, ready for implementation

---

## Context & Goal

Multiple code reviews identified 6 confirmed bugs in `appMain.py` across data integrity, crash prevention, resource cleanup, and robustness. All findings have been **verified against actual code** via jcode MCP.

### Research Summary (Phase 1 Complete)

| Fix | Location | Severity | Verified |
|-----|----------|----------|----------|
| 1. copy_and_overwrite data loss | L1436-1451 | **HIGH** | ✓ |
| 2. image_opener None crash | L7111-7126 | **HIGH** | ✓ |
| 3. Editor cleanup gated | L3860-3899 | MEDIUM | ✓ |
| 4. ArgsThread infinite loop | L8132-8161 | MEDIUM | ✓ |
| 5. version_check KeyError | L7416-7427 | MEDIUM | ✓ |
| 6. Autosave timer leak | L861-863, L3851 | LOW | ✓ |

---

## Impact Analysis

### Blast Radius Assessment

**appMain.py::App** is the central hub (~154 methods). Changes must be minimal and surgical.

```
appMain.py (App class)
├── Direct dependents: All plugins, editors, handlers
├── Inherited by: None (base class)
└── Called by: flatcam.py (entry point), tests/
```

**Risk Level:** HIGH — but fixes are isolated to specific methods with no cross-method dependencies.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     flatcam.py (entry)                       │
│                          ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              App (appMain.py) ← FIXES HERE              │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │ │
│  │  │ copy_and_   │ │ image_opener│ │ quit_           │   │ │
│  │  │ overwrite() │ │ lambda      │ │ application()   │   │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘   │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │ │
│  │  │ ArgsThread  │ │ version_    │ │ autosave_timer  │   │ │
│  │  │ .my_loop()  │ │ check()     │ │ (not stopped)   │   │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
│           ↓           ↓           ↓                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Editors  │  │ Handlers │  │ Plugins  │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Constraints & Decisions

### Hard Requirements (from code structure)

1. **No new dependencies** — Must use existing `shutil`, `os`, `json`, `QtCore`
2. **Signal compatibility** — `inform.emit()` requires string format `'[LEVEL] message'`
3. **Thread safety** — ArgsThread runs in QThread; `thread_exit` flag must be respected
4. **Backward compatibility** — `copy_and_overwrite()` is static; no `self` access

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Minimal changes per fix | Reduces regression risk in 8,200 LOC file |
| No refactoring beyond bug fixes | Scope creep prevention |
| Tests before implementation (TDD) | Per skill requirements |
| Log errors, don't silent-fail | Observability for debugging |

### [UNCERTAIN] Items

1. **Fix 4 (ArgsThread):** Should `os.remove('/tmp/testipc')` use a configurable temp path? Current: hardcoded `/tmp/testipc`
2. **Fix 6 (Autosave):** Should timer stop trigger a final autosave? Current plan: just stop

---

## Tasks

### Phase 1: Test Infrastructure (TDD)

#### Task 1.1: Create test_appmain.py skeleton
- **Objective:** Establish test framework for appMain.py bugs
- **Files:** `tests/test_appmain.py` (new)
- **Spec:**
  ```python
  #!/usr/bin/env python
  """
  Automated tests for appMain.py bug fixes.
  
  Run: python tests/test_appmain.py
  """
  import sys, os, tempfile, shutil
  sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  
  # Mock classes: MockLog, MockInform, MockApp (follow test_gerber_parser.py pattern)
  ```
- **Acceptance:** File exists, follows project test conventions, imports successfully
- **Dependencies:** None

#### Task 1.2: Test for Fix 1 — copy_and_overwrite data loss
- **Objective:** Write failing test for source-verified copy
- **Files:** `tests/test_appmain.py::TestCopyAndOverwrite`
- **Spec:**
  ```python
  class TestCopyAndOverwrite:
      def test_source_not_exists_dest_preserved(self):
          """If source doesn't exist, destination should NOT be deleted."""
          # Create temp dest with content
          # Call copy_and_overwrite(nonexistent_src, dest)
          # Assert: dest still exists (current bug: dest is deleted)
          
      def test_copy_error_logged(self):
          """If copytree fails, error should be logged."""
  ```
- **Acceptance:** Test fails with current code (RED state per TDD)
- **Dependencies:** Task 1.1

#### Task 1.3: Test for Fix 2 — image_opener None crash
- **Objective:** Write failing test for image_tool AttributeError
- **Files:** `tests/test_appmain.py::TestImageOpener`
- **Spec:**
  ```python
  class TestImageOpener:
      def test_image_tool_missing_no_crash(self):
          """When image_tool doesn't exist, recent file lambda should not crash."""
          # Create mock app without image_tool
          # Trigger 'image' lambda from openers dict
          # Assert: No TypeError, user informed instead
  ```
- **Acceptance:** Test fails (TypeError: 'NoneType' not callable)
- **Dependencies:** Task 1.1

#### Task 1.4: Test for Fix 3 — Editor cleanup
- **Objective:** Write test verifying all editors deactivated on quit
- **Files:** `tests/test_appmain.py::TestEditorCleanup`
- **Spec:**
  ```python
  class TestEditorCleanup:
      def test_all_editors_deactivated(self):
          """All non-None editors should be deactivated, not just call_source."""
          # Mock all 4 editors with deactivate() spies
          # Set call_source='geo_editor' (mismatch scenario)
          # Call quit_application()
          # Assert: ALL editors had deactivate() called
  ```
- **Acceptance:** Test fails (only geo_editor deactivated)
- **Dependencies:** Task 1.1

#### Task 1.5: Test for Fix 4 — ArgsThread infinite loop
- **Objective:** Write test for thread_exit check in ConnectionRefusedError handler
- **Files:** `tests/test_appmain.py::TestArgsThread`
- **Spec:**
  ```python
  class TestArgsThread:
      def test_thread_exit_respected_after_refused(self):
          """my_loop should check thread_exit after ConnectionRefusedError."""
          # Mock ConnectionRefusedError scenario
          # Set thread_exit = True
          # Assert: while loop exits (current bug: while True ignores flag)
  ```
- **Acceptance:** Test fails (infinite loop)
- **Dependencies:** Task 1.1  
- **[UNCERTAIN]:** May require integration test with QThread

#### Task 1.6: Test for Fix 5 — version_check JSON validation
- **Objective:** Write test for missing JSON keys
- **Files:** `tests/test_appmain.py::TestVersionCheck`
- **Spec:**
  ```python
  class TestVersionCheck:
      def test_missing_version_key(self):
          """Malformed response without 'version' key should not crash."""
          # Mock urllib.request.urlopen returning {"name": "test"}
          # Call version_check()
          # Assert: No KeyError, error logged
          
      def test_missing_name_message_keys(self):
          """Should use .get() with defaults for name/message."""
  ```
- **Acceptance:** Test fails (KeyError on data["version"])
- **Dependencies:** Task 1.1

#### Task 1.7: Test for Fix 6 — Autosave timer
- **Objective:** Write test verifying timer stopped on quit
- **Files:** `tests/test_appmain.py::TestAutosaveTimer`
- **Spec:**
  ```python
  class TestAutosaveTimer:
      def test_timer_stopped_on_quit(self):
          """autosave_timer.stop() should be called in quit_application()."""
          # Create app with running autosave_time

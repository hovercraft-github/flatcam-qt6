#!/usr/bin/env python
"""
Automated tests for appMain.py bug fixes.
Tests read source code directly to avoid import issues with dependencies.

Run: python tests/test_appmain.py
"""

import sys
import os
import re
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APPMMAIN_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'appMain.py')


def read_appmain():
    """Read appMain.py source."""
    with open(APPMMAIN_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def extract_method(source, method_name):
    """Extract a method's source code from the App class."""
    # Find the method definition
    pattern = rf'    def {method_name}\(.*?\):'
    match = re.search(pattern, source)
    if not match:
        return None

    start = match.start()
    # Find the end of the method (next method at same indentation or class end)
    lines = source[start:].split('\n')
    method_lines = [lines[0]]

    for i in range(1, len(lines)):
        line = lines[i]
        # Stop at next method at same indentation level (4 spaces for App methods)
        if line and not line[0].isspace():
            break
        if line.strip().startswith('def ') and line.startswith('    def '):
            break
        method_lines.append(line)

    return '\n'.join(method_lines)


# =============================================================================
# FIX 1: copy_and_overwrite — Prevent data loss
# =============================================================================

class TestCopyAndOverwrite(unittest.TestCase):
    """Test that copy_and_overwrite protects against data loss."""

    def test_source_checked_before_destination_delete(self):
        """
        RED: copy_and_overwrite deletes destination BEFORE checking if source exists.
        If source doesn't exist, destination is permanently lost.
        """
        source = read_appmain()
        method = extract_method(source, 'copy_and_overwrite')
        self.assertIsNotNone(method, "copy_and_overwrite method not found")

        lines = method.split('\n')

        # Find the order: rmtree vs source validation
        rmtree_line = None
        source_check_line = None

        for i, line in enumerate(lines):
            if 'shutil.rmtree(to_path)' in line:
                rmtree_line = i
            # Check for source existence validation (should exist before rmtree)
            # After fix: "if not os.path.exists(from_path):"
            if ('not os.path.exists(from_path)' in line or
                'from_path' in line and 'raise FileNotFoundError' in line):
                if source_check_line is None:
                    source_check_line = i

        # After fix: source should be validated FIRST (source_check_line < rmtree_line)
        if rmtree_line is not None and source_check_line is not None:
            self.assertLess(source_check_line, rmtree_line,
                f"Source existence should be checked BEFORE deleting destination. "
                f"Found source check at line {source_check_line}, rmtree at line {rmtree_line}")
        else:
            self.fail("Source existence should be validated before deleting destination. "
                     "No 'not os.path.exists(from_path)' check found.")

    def test_fallback_copytree_has_error_handling(self):
        """
        RED: The fallback copytree (except FileNotFoundError) has no error handling.
        If it fails, the error propagates up with no cleanup.
        """
        source = read_appmain()
        method = extract_method(source, 'copy_and_overwrite')
        self.assertIsNotNone(method, "copy_and_overwrite method not found")

        lines = method.split('\n')

        # Find the fallback copytree call
        fallback_idx = None
        for i, line in enumerate(lines):
            if 'copytree' in line and 'from_new_path' in line:
                fallback_idx = i
                break

        self.assertIsNotNone(fallback_idx, "Fallback copytree not found")

        # Check for error handling after fallback
        has_error_handling = False
        for i in range(fallback_idx + 1, min(fallback_idx + 5, len(lines))):
            line = lines[i].strip()
            if line.startswith('except'):
                has_error_handling = True
                break
            if line and not line.startswith('#') and line != '' and line != 'pass':
                break

        self.assertTrue(has_error_handling,
            "Fallback copytree should be wrapped in try/except for error handling")


# =============================================================================
# FIX 2: image_opener None crash
# =============================================================================

class TestImageOpener(unittest.TestCase):
    """Test that image_opener handles missing self.image_tool gracefully."""

    def test_image_opener_has_fallback(self):
        """
        RED: When self.image_tool doesn't exist, image_opener is set to None.
        The lambda passes None as the function to worker_task.emit(),
        which causes TypeError when trying to call it.
        """
        source = read_appmain()

        # Find the code that builds the openers dict with 'image' key
        lines = source.split('\n')

        # Find where image_opener is handled (after AttributeError catch)
        image_opener_idx = None
        for i, line in enumerate(lines):
            if 'image_opener' in line and ('import_image' in line or 'fallback' in line):
                image_opener_idx = i
                break

        self.assertIsNotNone(image_opener_idx,
            "image_opener handling not found")

        # Get context around the image_opener assignment
        context_start = max(0, image_opener_idx - 2)
        context_end = min(len(lines), image_opener_idx + 10)
        image_opener_block = '\n'.join(lines[context_start:context_end])

        # After fix: should NOT have 'image_opener = None'
        # Should have a fallback function that uses self.inform
        self.assertNotIn('image_opener = None', image_opener_block,
            "image_opener should not be set to None. Should use a fallback function.")
        self.assertIn('self.inform', image_opener_block,
            "Fallback function should use self.inform to notify the user.")


# =============================================================================
# FIX 3: Editor cleanup gated on call_source
# =============================================================================

class TestEditorCleanup(unittest.TestCase):
    """Test that all editors are deactivated on quit, not just the matching one."""

    def test_all_editors_deactivated_unconditionally(self):
        """
        RED: quit_application() only deactivates the editor matching self.call_source.
        If another editor is open (but call_source doesn't match), it stays active.
        """
        source = read_appmain()
        method = extract_method(source, 'quit_application')
        self.assertIsNotNone(method, "quit_application method not found")

        # The BUG: editors are deactivated ONLY if call_source matches
        # This means if geo_editor is open but call_source is 'gcode_editor',
        # geo_editor stays active and causes issues during shutdown.

        # Find all call_source checks that gate editor deactivation
        lines = method.split('\n')
        call_source_gates = []
        for i, line in enumerate(lines):
            if 'self.call_source ==' in line:
                # Check if this gates an editor deactivation (check next few lines)
                context = '\n'.join(lines[i:i+10])
                if any(editor in context for editor in ['geo_editor', 'exc_editor', 'grb_editor', 'gcode_editor']):
                    call_source_gates.append((i+1, line.strip()))

        # BUG PRESENT: call_source gates found
        self.assertEqual(len(call_source_gates), 0,
            f"Editor deactivation should NOT be gated on call_source. "
            f"Found {len(call_source_gates)} call_source gates: {call_source_gates}. "
            f"All editors should be deactivated unconditionally when not None.")

        # After fix: check for unconditional deactivation pattern
        unconditional_geo = 'self.geo_editor is not None' in method
        unconditional_exc = 'self.exc_editor is not None' in method
        unconditional_grb = 'self.grb_editor is not None' in method
        unconditional_gcode = 'self.gcode_editor is not None' in method

        all_unconditional = (unconditional_geo and unconditional_exc and
                            unconditional_grb and unconditional_gcode)

        self.assertTrue(all_unconditional,
            f"All editors should be deactivated with 'is not None' checks. "
            f"Found: geo={unconditional_geo}, exc={unconditional_exc}, "
            f"grb={unconditional_grb}, gcode={unconditional_gcode}")

        # Also verify grb_editor uses deactivate_grb_editor
        if unconditional_grb:
            self.assertIn('deactivate_grb_editor', method,
                "grb_editor should use deactivate_grb_editor() method")


# =============================================================================
# FIX 4: ArgsThread.my_loop — Infinite loop and cleanup
# =============================================================================

class TestArgsThreadMyLoop(unittest.TestCase):
    """Test ArgsThread.my_loop for infinite loop and cleanup issues."""

    def test_infinite_loop_has_exit_condition(self):
        """
        RED: The 'while True:' loop in ConnectionRefusedError handler
        has no exit condition - self.thread_exit is never checked.
        """
        source = read_appmain()
        method = extract_method(source, 'my_loop')
        self.assertIsNotNone(method, "my_loop method not found")

        lines = method.split('\n')

        # Find the ConnectionRefusedError block
        in_connection_refused_block = False
        found_infinite_loop = False

        for i, line in enumerate(lines):
            if 'ConnectionRefusedError' in line:
                in_connection_refused_block = True
            if in_connection_refused_block and 'while True' in line:
                # Found the infinite loop - check if thread_exit is checked
                remaining = '\n'.join(lines[i:i+10])
                if 'thread_exit' not in remaining:
                    found_infinite_loop = True
                break

        self.assertFalse(found_infinite_loop,
            "Found 'while True:' loop without thread_exit check in my_loop(). "
            "This creates an infinite loop on Linux when ConnectionRefusedError occurs.")

    def test_os_system_replaced_with_os_remove(self):
        """
        RED: os.system('rm /tmp/testipc') is a hardcoded shell command.
        Should use os.remove('/tmp/testipc') for cross-platform safety.
        """
        source = read_appmain()
        method = extract_method(source, 'my_loop')
        self.assertIsNotNone(method, "my_loop method not found")

        # The bug: os.system('rm /tmp/testipc')
        self.assertNotIn("os.system('rm", method,
            "Should not use os.system() with shell command. Use os.remove() instead.")
        self.assertNotIn('os.system("rm', method,
            "Should not use os.system() with shell command. Use os.remove() instead.")

        # After fix: should use os.remove('/tmp/testipc')
        self.assertIn("os.remove", method,
            "Should use os.remove() instead of os.system() for file deletion")

    def test_bare_except_logs_instead_of_silencing(self):
        """
        RED: 'except Exception: pass' swallows all errors without logging.
        Should log the exception.
        """
        source = read_appmain()
        method = extract_method(source, 'my_loop')
        self.assertIsNotNone(method, "my_loop method not found")

        lines = method.split('\n')

        # Find bare except blocks at the TOP-LEVEL of the method (not nested in inner try blocks)
        # A top-level except has 8 spaces of indentation (inside the method body)
        # A nested except has more indentation
        top_level_indent = '        '  # 8 spaces for method body

        bare_except_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == 'except Exception:' or stripped == 'except:':
                # Check if this is a top-level except (8 spaces indentation)
                leading_spaces = len(line) - len(line.lstrip())
                if leading_spaces == 8:  # Top-level
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        all_lines = '\n'.join(lines[i:i+3])
                        if 'log.error' not in all_lines and ('pass' in next_line or 'pass  #' in next_line):
                            bare_except_lines.append(i + 1)

        self.assertEqual(len(bare_except_lines), 0,
            f"Found bare 'except Exception: pass' at lines {bare_except_lines}. "
            "Top-level except should log the exception instead of silencing.")


# =============================================================================
# FIX 5: version_check JSON key validation
# =============================================================================

class TestVersionCheck(unittest.TestCase):
    """Test that version_check validates JSON keys before accessing them."""

    def test_json_keys_validated_before_access(self):
        """
        RED: data["version"], data["name"], data["message"] are accessed
        without checking if keys exist. Malformed server response causes KeyError.
        """
        source = read_appmain()
        method = extract_method(source, 'version_check')
        self.assertIsNotNone(method, "version_check method not found")

        # After fix: should use .get() method for name and message
        uses_get_for_name = (
            'data.get("name"' in method or
            "data.get('name'" in method or
            "'name' in data" in method or
            '"name" in data' in method
        )
        uses_get_for_message = (
            'data.get("message"' in method or
            "data.get('message'" in method or
            "'message' in data" in method or
            '"message" in data' in method
        )

        self.assertTrue(uses_get_for_name,
            "Should use data.get('name') or 'name' in data instead of data['name']")
        self.assertTrue(uses_get_for_message,
            "Should use data.get('message') or 'message' in data instead of data['message']")

    def test_version_key_checked(self):
        """
        RED: The 'version' key is accessed without validation.
        Should check if key exists before comparing.
        """
        source = read_appmain()
        method = extract_method(source, 'version_check')
        self.assertIsNotNone(method, "version_check method not found")

        # After fix: should use 'version' in data check before accessing
        uses_version_in_check = (
            "'version' not in data" in method or
            '"version" not in data' in method or
            "'version' in data" in method or
            '"version" in data' in method
        )

        self.assertTrue(uses_version_in_check,
            "Should check 'version' in data before accessing data['version']")

        # Check that direct data["version"] is NOT used outside of try block after validation
        # After fix: should use data_version variable for comparisons
        lines = method.split('\n')
        unsafe_version_access = []

        for i, line in enumerate(lines):
            # Direct access is OK if it's inside a try block (where we convert to int)
            # But NOT OK if it's in a comparison like self.version >= data["version"]
            if 'data["version"]' in line or "data['version']" in line:
                # Check if this line is a comparison (unsafe) vs assignment in try (safe)
                if 'data_version = ' not in line and 'int(data' not in line:
                    unsafe_version_access.append(i + 1)

        self.assertEqual(len(unsafe_version_access), 0,
            f"data['version'] accessed directly at lines {unsafe_version_access}. "
            "Should use data_version variable for comparisons.")


# =============================================================================
# FIX 6: Autosave timer not stopped on quit
# =============================================================================

class TestAutosaveTimer(unittest.TestCase):
    """Test that autosave timer is stopped on quit."""

    def test_autosave_timer_stopped_on_quit(self):
        """
        RED: self.autosave_timer is started during init but never stopped
        in quit_application(). Timer can fire after shutdown begins.
        """
        source = read_appmain()
        method = extract_method(source, 'quit_application')
        self.assertIsNotNone(method, "quit_application method not found")

        # After fix: should call autosave_timer.stop()
        self.assertIn('autosave_timer.stop', method,
            "quit_application() should call self.autosave_timer.stop() "
            "to prevent timer from firing during shutdown")

    def test_autosave_timer_started_in_init(self):
        """
        Verify that autosave_timer is indeed started in __init__.
        This confirms the timer needs to be stopped on quit.
        """
        source = read_appmain()
        method = extract_method(source, '__init__')

        # The timer setup includes autosave_timer creation
        self.assertIn('autosave_timer', method,
            "autosave_timer should be present in __init__")


# =============================================================================
# Test runner
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCopyAndOverwrite))
    suite.addTests(loader.loadTestsFromTestCase(TestImageOpener))
    suite.addTests(loader.loadTestsFromTestCase(TestEditorCleanup))
    suite.addTests(loader.loadTestsFromTestCase(TestArgsThreadMyLoop))
    suite.addTests(loader.loadTestsFromTestCase(TestVersionCheck))
    suite.addTests(loader.loadTestsFromTestCase(TestAutosaveTimer))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {len(result.failures)}")
        print(f"ERRORS: {len(result.errors)}")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

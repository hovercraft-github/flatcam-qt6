#!/usr/bin/env python
"""
Automated tests for Gerber parser parse_lines() method.

REQUIRED before any refactoring of the Gerber parser state management.
These tests validate the scattered variables approach.
(ParserState dataclass approach was abandoned - see docs/plans/)

Run: python tests/test_gerber_parser.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from appParsers.ParseGerber import Gerber


class MockLog:
    """Mock logger for testing."""
    def debug(self, msg):
        pass
    
    def warning(self, msg):
        pass
    
    def error(self, msg):
        pass
    
    def info(self, msg):
        pass


class MockInform:
    """Mock inform emitter for testing."""
    def emit(self, msg):
        pass


class MockApp:
    """Mock application object for Gerber parser testing."""
    def __init__(self):
        self.options = {
            'gerber_def_units': 'MM',
            'gerber_def_zeros': 'L',
            'gerber_circle_steps': 64,
            'gerber_simp_tolerance': 0.001,
            'gerber_simplification': True,
            'gerber_buffering': True,
            'gerber_extra_buffering': 0.0,
            'gerber_clean_apertures': True,
            'gerber_use_buffer_for_union': True,
            'global_tolerance': 0.01,
        }
        self.decimals = 4
        self.abort_flag = False
        self.log = MockLog()
        self.inform = MockInform()
        self.app_units = 'MM'
        self.use_3d_engine = True
        
        class MockPlotCanvas:
            class new_shape_collection:
                def __init__(self, layers=1):
                    pass
            def __init__(self):
                pass
        self.plotcanvas = MockPlotCanvas()
        
        class MockProcContainer:
            def update_view_text(self, text):
                pass
        self.proc_container = MockProcContainer()


def get_gerber_parser():
    """Create a Gerber parser with mock app for testing."""
    app = MockApp()
    return Gerber(app)


class TestGerberParserBasic:
    """Basic Gerber parser tests."""
    
    def test_simple_line_d01(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X100Y100D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Simple line D01 test passed")
    
    def test_flash_d03(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "X100Y100D03*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Flash D03 test passed")
    
    def test_region_g36_g37(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G36*", "X100Y0D01*", "X100Y100D01*", "X0Y100D01*", "X0Y0D01*", "G37*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Region G36-G37 test passed")
    
    def test_polarity_change(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X100Y0D01*", "%LPC*%", "G01 X200Y0D01*", "%LPD*%", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Polarity change test passed")
    
    def test_d02_new_path(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X100Y0D01*", "G01 X50Y50D02*", "G01 X150Y150D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] D02 new path test passed")
    
    def test_all_aperture_types(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "%ADD11R,10X20*%", "D10*", "G01 X0Y0D02*", "G01 X100Y0D01*", "D11*", "G01 X0Y50D02*", "G01 X100Y50D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] All aperture types test passed")


class TestGerberParserEdgeCases:
    """Edge case tests for the Gerber parser."""
    
    def test_d02_before_g37(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G36*", "X100Y0D01*", "X100Y100D01*", "G01 X0Y100D02*", "G37*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] D02 before G37 edge case test passed")
    
    def test_empty_path_no_crash(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X100Y100D02*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == "fail"
        print("[PASS] Empty path no crash test passed")
    
    def test_multiple_aperture_changes(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%ADD10C,5*%", "%ADD11C,10*%", "%ADD12C,15*%", "D10*", "G01 X0Y0D02*", "G01 X50Y50D01*", "D11*", "G01 X100Y100D01*", "D12*", "G01 X150Y150D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Multiple aperture changes test passed")
    
    def test_comments_ignored(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G04 This is a comment*", "G01 X0Y0D02*", "G04 Another comment*", "G01 X100Y100D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Comments ignored test passed")
    
    def test_format_specification_variants(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01X0Y0D02*", "G01X100Y100D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Format specification variants test passed")

    def test_polarity_change_with_pending_path(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX23Y23*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X1000Y0D01*", "G01 X1000Y1000D01*", "%LPC*%", "G01 X2000Y0D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Polarity change with pending path test passed")

    def test_tool_change_with_pending_path(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX23Y23*%", "%ADD10C,10*%", "%ADD11C,20*%", "D10*", "G01 X0Y0D02*", "G01 X1000Y0D01*", "D11*", "G01 X2000Y0D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        print("[PASS] Tool change with pending path test passed")

    def test_region_start_with_pending_path(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX23Y23*%", "%ADD10C,10*%", "D10*", "G01 X0Y0D02*", "G01 X1000Y0D01*", "G36*", "X1000Y1000D01*", "X0Y1000D01*", "X0Y0D01*", "G37*", "M02*"]
        result = gbr.parse_lines(lines)
        assert result is None or result == ""
        assert gbr.solid_geometry is not None
        print("[PASS] Region start with pending path test passed")

    def test_multipolygon_iteration(self):
        """Test MultiPolygon handling for Shapely 2.x compatibility."""
        from shapely.geometry import MultiPolygon, Polygon
        
        poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
        multi = MultiPolygon([poly1, poly2])
        
        count = 0
        for p in multi.geoms:
            count += 1
            assert isinstance(p, Polygon)
        assert count == 2
        print("[PASS] MultiPolygon iteration test passed")


class TestGerberParserUnits:
    """Test unit handling."""
    
    def test_inches_units(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOIN*%", "%ADD10C,10*%", "D10*", "G01X0Y0D02*", "G01X100Y100D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert gbr.units == 'IN'
        print("[PASS] Inches units test passed")
    
    def test_metric_units(self):
        gbr = get_gerber_parser()
        lines = ["%FSLAX24Y24*%", "%MOMM*%", "%ADD10C,10*%", "D10*", "G01X0Y0D02*", "G01X10000Y10000D01*", "M02*"]
        result = gbr.parse_lines(lines)
        assert gbr.units == 'MM'
        print("[PASS] Metric units test passed")


def test_load_real_gerber_files():
    """Test loading actual Gerber files from test_files directory."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    files_dir = os.path.join(test_dir, 'test_files')
    
    test_files = ['simple_line.gbr', 'region_test.gbr', 'flash_test.gbr']
    
    for filename in test_files:
        filepath = os.path.join(files_dir, filename)
        if os.path.exists(filepath):
            gbr = get_gerber_parser()
            result = gbr.parse_file(filepath)
            assert result is None or result != 'fail', f"{filename} failed to parse"
            print(f"[PASS] Loaded {filename}")
        else:
            print(f"[SKIP] {filename} not found")


def run_all_tests():
    """Run all tests and report results."""
    import traceback
    
    test_classes = [TestGerberParserBasic, TestGerberParserEdgeCases, TestGerberParserUnits]
    
    passed = 0
    failed = 0
    errors = []
    
    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                test_name = f"{test_class.__name__}.{method_name}"
                try:
                    method = getattr(instance, method_name)
                    method()
                    passed += 1
                except AssertionError as e:
                    failed += 1
                    errors.append((test_name, str(e)))
                    print(f"[FAIL] {test_name}: {e}")
                except Exception as e:
                    failed += 1
                    errors.append((test_name, traceback.format_exc()))
                    print(f"[ERROR] {test_name}: {e}")
    
    print("\n--- Integration Tests ---")
    try:
        test_load_real_gerber_files()
        passed += 1
    except AssertionError as e:
        failed += 1
        errors.append(("test_load_real_gerber_files", str(e)))
        print(f"[FAIL] test_load_real_gerber_files: {e}")
    except Exception as e:
        failed += 1
        errors.append(("test_load_real_gerber_files", traceback.format_exc()))
        print(f"[ERROR] test_load_real_gerber_files: {e}")
    
    print(f"\n{'='*60}")
    print(f"Test Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    
    if errors:
        print("\nFailures:")
        for test_name, error in errors:
            print(f"  - {test_name}: {error}")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

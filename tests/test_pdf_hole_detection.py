#!/usr/bin/env python
"""Test PDF hole detection modes."""

import sys
sys.path.insert(0, 'D:/1.Development/FlatCAM_EVO/.worktrees/refactor-parsepdf')

from appParsers.ParsePDF import PdfParser

def test_default_mode():
    """Test default 'both' detection mode."""
    parser = PdfParser(units='MM', resolution=10, abort=False)
    assert parser.hole_detection_mode == 'both'
    assert parser.DETECT_BOTH == 'both'
    print("[PASS] Default mode test passed")

def test_fill_only_mode():
    """Test 'fill_only' detection mode."""
    parser = PdfParser(units='MM', resolution=10, abort=False, hole_detection_mode='fill_only')
    assert parser.hole_detection_mode == 'fill_only'
    print("[PASS] Fill-only mode test passed")

def test_stroke_only_mode():
    """Test 'stroke_only' detection mode."""
    parser = PdfParser(units='MM', resolution=10, abort=False, hole_detection_mode='stroke_only')
    assert parser.hole_detection_mode == 'stroke_only'
    print("[PASS] Stroke-only mode test passed")

def test_invalid_mode():
    """Test invalid detection mode raises error."""
    try:
        parser = PdfParser(units='MM', resolution=10, abort=False, hole_detection_mode='invalid')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid hole_detection_mode" in str(e)
        print("[PASS] Invalid mode rejection test passed")

def test_class_constants():
    """Test class constants are accessible."""
    assert PdfParser.DETECT_BOTH == 'both'
    assert PdfParser.DETECT_FILL_ONLY == 'fill_only'
    assert PdfParser.DETECT_STROKE_ONLY == 'stroke_only'
    print("[PASS] Class constants test passed")

if __name__ == '__main__':
    test_default_mode()
    test_fill_only_mode()
    test_stroke_only_mode()
    test_invalid_mode()
    test_class_constants()
    print("\n=== All tests passed! ===")

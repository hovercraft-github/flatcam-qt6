#!/usr/bin/env python
"""
Automated tests for VisPy batch processing optimizations (Phase 2).

Tests cover:
1. add_batch() functionality
2. Synchronous add() behavior
3. Backface culling configuration
4. redraw() batch result collection
5. _collect_elements() method
6. Edge cases (empty batches, missing fc_options, etc.)

Run: python tests/test_vispy_batch.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import Mock, MagicMock, patch
from shapely.geometry import Polygon, LineString, MultiPolygon


class MockAsyncResult:
    """Mock multiprocessing.AsyncResult for testing."""
    def __init__(self, data):
        self._data = data
    
    def wait(self):
        pass
    
    def get(self):
        return self._data


class MockPool:
    """Mock multiprocessing pool for testing."""
    def __init__(self, return_data=None):
        self._return_data = return_data
        self.call_args = []
    
    def map_async(self, func, iterable):
        self.call_args.append((func, iterable))
        # Simulate processing
        result = [func(item) for item in iterable]
        return MockAsyncResult(result)


class TestShapeCollectionVisualBatch(unittest.TestCase):
    """Tests for ShapeCollectionVisual batch processing."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Import after path setup
        from appGUI.VisPyVisuals import ShapeCollectionVisual, _update_shape_buffers
        self.ShapeCollectionVisual = ShapeCollectionVisual
        self._update_shape_buffers = _update_shape_buffers
        
        # Mock fc_options with all required keys
        self.default_fc_options = {
            "global_graphic_engine_3d_no_mp": False,
            "global_backface_culling": True,
        }
    
    def test_add_batch_empty_data(self):
        """Test add_batch() with empty shapes_data returns empty list."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        result = collection.add_batch([])
        
        self.assertEqual(result, [])
        self.assertEqual(len(collection.data), 0)
    
    def test_add_batch_single_shape(self):
        """Test add_batch() with a single shape."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [{
            'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            'color': 'red',
            'face_color': 'blue'
        }]
        
        result = collection.add_batch(shapes_data, visible=True)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(len(collection.data), 1)
        self.assertIn(result[0], collection.data)
        self.assertEqual(collection.data[result[0]]['color'], 'red')
        self.assertEqual(collection.data[result[0]]['face_color'], 'blue')
        self.assertTrue(collection.data[result[0]]['visible'])
    
    def test_add_batch_multiple_shapes(self):
        """Test add_batch() with multiple shapes."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'color': 'red'},
            {'shape': Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]), 'color': 'green'},
            {'shape': Polygon([(4, 0), (5, 0), (5, 1), (4, 1)]), 'color': 'blue'},
        ]
        
        result = collection.add_batch(shapes_data, visible=True)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(len(collection.data), 3)
        # Verify keys are unique and in order
        self.assertEqual(len(set(result)), 3)
    
    def test_add_batch_with_pool(self):
        """Test add_batch() uses pool when available."""
        mock_pool = MockPool()
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=mock_pool,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'color': 'red'},
            {'shape': Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]), 'color': 'green'},
        ]
        
        result = collection.add_batch(shapes_data, visible=True)
        
        # Verify pool.map_async was called once (not per shape)
        self.assertEqual(len(mock_pool.call_args), 1)
        # Verify all shapes were passed to single call
        func, iterable = mock_pool.call_args[0]
        self.assertEqual(len(iterable), 2)
        # Verify batch_results stored the result
        self.assertEqual(len(collection._batch_results), 1)
    
    def test_add_batch_synchronous_mode(self):
        """Test add_batch() processes synchronously when no_mp option is True."""
        fc_options = {"global_graphic_engine_3d_no_mp": True}
        mock_pool = MockPool()
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=mock_pool,
            fcoptions=fc_options
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'color': 'red'},
        ]
        
        result = collection.add_batch(shapes_data, visible=True)
        
        # Verify pool was NOT called
        self.assertEqual(len(mock_pool.call_args), 0)
        # Verify _batch_results is empty (no async results)
        self.assertEqual(len(collection._batch_results), 0)
        # Verify data was processed (has mesh_vertices after _update_shape_buffers)
        self.assertIn('mesh_vertices', collection.data[result[0]])
    
    def test_add_batch_missing_fc_option_key(self):
        """Test add_batch() handles missing fc_options key gracefully (BUG 1 fix)."""
        # fc_options without the key - should use .get() to avoid KeyError
        fc_options = {"some_other_option": True}
        mock_pool = MockPool()
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=mock_pool,
            fcoptions=fc_options
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'color': 'red'},
        ]
        
        # Should NOT raise KeyError
        try:
            result = collection.add_batch(shapes_data, visible=True)
            self.assertEqual(len(result), 1)
        except KeyError as e:
            self.fail(f"add_batch() raised KeyError for missing option key: {e}")
    
    def test_add_batch_none_fc_options(self):
        """Test add_batch() handles None fc_options gracefully."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=None
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'color': 'red'},
        ]
        
        # Should NOT raise AttributeError
        try:
            result = collection.add_batch(shapes_data, visible=True)
            self.assertEqual(len(result), 1)
        except (AttributeError, TypeError) as e:
            self.fail(f"add_batch() raised exception for None fc_options: {e}")
    
    def test_add_batch_default_layer(self):
        """Test add_batch() uses default layer parameter."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [{'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])}]
        
        result = collection.add_batch(shapes_data, layer=5)
        
        self.assertEqual(collection.data[result[0]]['layer'], 5)
    
    def test_add_batch_per_shape_layer_override(self):
        """Test add_batch() allows per-shape layer override."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [
            {'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), 'layer': 1},
            {'shape': Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]), 'layer': 2},
        ]
        
        result = collection.add_batch(shapes_data, layer=0)
        
        # Per-shape layer should override default
        self.assertEqual(collection.data[result[0]]['layer'], 1)
        self.assertEqual(collection.data[result[1]]['layer'], 2)
    
    def test_add_batch_dirty_flag(self):
        """Test add_batch() sets dirty flag."""
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=self.default_fc_options
        )
        
        collection._dirty = False
        
        shapes_data = [{'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])}]
        collection.add_batch(shapes_data)
        
        self.assertTrue(collection._dirty)
    
    def test_redraw_collects_batch_results(self):
        """Test redraw() collects batch results from _batch_results."""
        mock_pool = MockPool()
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=mock_pool,
            fcoptions=self.default_fc_options
        )
        
        shapes_data = [{'shape': Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])}]
        result = collection.add_batch(shapes_data)
        
        # Verify batch was submitted but not yet collected
        self.assertEqual(len(collection._batch_results), 1)
        
        # Mock __update to avoid VisPy canvas requirement
        with patch.object(collection, '_ShapeCollectionVisual__update'):
            # Call redraw to collect results
            collection.redraw()
        
        # Verify batch_results was cleared after collection
        self.assertEqual(len(collection._batch_results), 0)
        # Verify data was updated with processed results
        self.assertIn(result[0], collection.data)
    
    def test_add_synchronous(self):
        """Test individual add() is always synchronous (Phase 2 optimization)."""
        mock_pool = MockPool()
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=mock_pool,
            fcoptions=self.default_fc_options
        )
        
        shape = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        result = collection.add(shape=shape, color='red')
        
        # Verify pool was NOT called (synchronous processing)
        self.assertEqual(len(mock_pool.call_args), 0)
        # Verify results dict is empty (no async result stored)
        self.assertEqual(len(collection.results), 0)
        # Verify data was processed directly
        self.assertIn(result, collection.data)


class TestBackfaceCulling(unittest.TestCase):
    """Tests for backface culling configuration."""
    
    def setUp(self):
        """Set up test fixtures."""
        from appGUI.VisPyVisuals import ShapeCollectionVisual
        self.ShapeCollectionVisual = ShapeCollectionVisual
    
    @patch('appGUI.VisPyVisuals.MeshVisual')
    def test_backface_culling_default_true(self, mock_mesh):
        """Test backface culling is True by default."""
        fc_options = {}  # No backface_culling option - should default to True
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=fc_options
        )
        
        # Verify set_gl_state was called with cull_face=True (default)
        for call in mock_mesh.return_value.set_gl_state.call_args_list:
            kwargs = call[1]
            self.assertTrue(kwargs.get('cull_face', False), 
                "Expected cull_face=True by default")
    
    @patch('appGUI.VisPyVisuals.MeshVisual')
    def test_backface_culling_explicit_true(self, mock_mesh):
        """Test backface culling when explicitly set to True."""
        fc_options = {"global_backface_culling": True}
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=fc_options
        )
        
        # Verify cull_face=True
        for call in mock_mesh.return_value.set_gl_state.call_args_list:
            kwargs = call[1]
            self.assertTrue(kwargs.get('cull_face', False),
                "Expected cull_face=True when explicitly set")
    
    @patch('appGUI.VisPyVisuals.MeshVisual')
    def test_backface_culling_false(self, mock_mesh):
        """Test backface culling when set to False."""
        fc_options = {"global_backface_culling": False}
        collection = self.ShapeCollectionVisual(
            linewidth=1,
            layers=3,
            pool=None,
            fcoptions=fc_options
        )
        
        # Verify cull_face=False
        for call in mock_mesh.return_value.set_gl_state.call_args_list:
            kwargs = call[1]
            self.assertFalse(kwargs.get('cull_face', True),
                "Expected cull_face=False when explicitly disabled")


class TestCollectElements(unittest.TestCase):
    """Tests for GeometryObject._collect_elements() method."""
    
    def setUp(self):
        """Set up test fixtures."""
        from appObjects.GeometryObject import GeometryObject
        # Can't fully instantiate without app, so we'll test the method directly
        self.GeometryObject = GeometryObject
    
    def test_collect_elements_single_polygon(self):
        """Test _collect_elements with a single Polygon."""
        from appObjects.GeometryObject import GeometryObject
        
        # Create a mock object with just the method we need
        class MockGeo:
            pass
        
        mock_geo = MockGeo()
        mock_geo._collect_elements = GeometryObject._collect_elements.__get__(mock_geo, GeometryObject)
        
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        result = mock_geo._collect_elements(poly, color='red')
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['shape'], poly)
        self.assertEqual(result[0]['color'], 'red')
        self.assertEqual(result[0]['layer'], 0)
    
    def test_collect_elements_multi_polygon(self):
        """Test _collect_elements with a MultiPolygon."""
        from appObjects.GeometryObject import GeometryObject
        
        class MockGeo:
            pass
        
        mock_geo = MockGeo()
        mock_geo._collect_elements = GeometryObject._collect_elements.__get__(mock_geo, GeometryObject)
        
        poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = Polygon([(2, 0), (3, 0), (3, 1), (2, 1)])
        multi = MultiPolygon([poly1, poly2])
        
        result = mock_geo._collect_elements(multi, color='blue')
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['color'], 'blue')
        self.assertEqual(result[1]['color'], 'blue')
    
    def test_collect_elements_default_color(self):
        """Test _collect_elements uses default color when not specified."""
        from appObjects.GeometryObject import GeometryObject
        
        class MockGeo:
            pass
        
        mock_geo = MockGeo()
        mock_geo._collect_elements = GeometryObject._collect_elements.__get__(mock_geo, GeometryObject)
        
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        result = mock_geo._collect_elements(poly)
        
        self.assertEqual(result[0]['color'], '#FF0000FF')


class TestDefaultsConfiguration(unittest.TestCase):
    """Tests for defaults.py configuration."""
    
    def test_global_backface_culling_default(self):
        """Test global_backface_culling is True by default."""
        from defaults import AppDefaults
        
        defaults = AppDefaults()
        # Access the defaults dict directly
        self.assertIn("global_backface_culling", defaults.defaults)
        self.assertTrue(defaults.defaults["global_backface_culling"])


if __name__ == '__main__':
    unittest.main()

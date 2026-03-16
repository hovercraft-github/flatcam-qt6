# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# http://flatcam.org                                       #
# File Author: Dennis Hayrullin                            #
# Date: 2/5/2016                                           #
# MIT Licence                                              #
# ##########################################################

from vispy.visuals import CompoundVisual, LineVisual, MeshVisual, TextVisual, MarkersVisual
from vispy.scene.visuals import VisualNode, generate_docstring, visuals
from vispy.gloo import set_state
from vispy.color import Color
from shapely import Polygon, LineString, LinearRing
import threading
import numpy as np
from appGUI.VisPyTesselators import GLUTess


# class FlatCAMLineVisual(LineVisual):
#     def __init__(self, pos=None, color=(0.5, 0.5, 0.5, 1), width=1, connect='strip', method='gl', antialias=False):
#         LineVisual.__init__(self, pos=pos, color=color, width=width, connect=connect,
#                             method=method, antialias=True)
#
#     def clear_data(self):
#         self._bounds = None
#         self._pos = None
#         self._changed['pos'] = True
#         self.update()


def _update_shape_buffers(data, triangulation='glu'):
    """
    Translates Shapely geometry to internal buffers for speedup redraws
    :param data: dict
        Input shape data
    :param triangulation: str
        Triangulation engine
    """
    mesh_vertices = []                                              # Vertices for mesh
    mesh_tris = []                                                  # Faces for mesh
    mesh_colors = []                                                # Face colors
    line_pts = []                                                   # Vertices for line
    line_colors = []                                                # Line color

    geo, color, face_color, tolerance = data['geometry'], data['color'], data['face_color'], data['tolerance']

    if geo is not None and not geo.is_empty:
        simplified_geo = geo.simplify(tolerance) if tolerance else geo      # Simplified shape
        pts = []                                                            # Shape line points
        tri_pts = []                                                        # Mesh vertices
        tri_tris = []                                                       # Mesh faces

        if type(geo) == LineString:
            # Prepare lines
            pts = _linestring_to_segments(simplified_geo.coords)

        elif type(geo) == LinearRing:
            # Prepare lines
            pts = _linearring_to_segments(simplified_geo.coords)

        elif type(geo) == Polygon:
            # Prepare polygon faces
            if face_color is not None:
                if triangulation == 'glu':
                    gt = GLUTess()
                    tri_tris, tri_pts = gt.triangulate(simplified_geo)
                else:
                    print("Triangulation type '%s' isn't implemented. Drawing only edges." % triangulation)

            # Prepare polygon edges
            if color is not None:
                pts = _linearring_to_segments(simplified_geo.exterior.coords)
                for ints in simplified_geo.interiors:
                    pts += _linearring_to_segments(ints.coords)

        # Appending data for mesh
        if len(tri_pts) > 0 and len(tri_tris) > 0:
            mesh_tris += tri_tris
            mesh_vertices += tri_pts
            face_color_rgba = Color(face_color).rgba
            # Use list multiplication (faster than list comprehension for uniform values)
            mesh_colors += [face_color_rgba] * (len(tri_tris) // 3)

        # Appending data for line
        if len(pts) > 0:
            line_pts += pts
            colo_rgba = Color(color).rgba
            # Use list multiplication (faster than list comprehension for uniform values)
            line_colors += [colo_rgba] * len(pts)

    # Store buffers as numpy arrays for faster concatenation in __update()
    data['line_pts'] = np.array(line_pts, dtype=np.float32) if line_pts else np.empty((0, 2), dtype=np.float32)
    data['line_colors'] = np.array(line_colors, dtype=np.float32) if line_colors else np.empty((0, 4), dtype=np.float32)
    data['mesh_vertices'] = np.array(mesh_vertices, dtype=np.float32) if mesh_vertices else np.empty((0, 2), dtype=np.float32)
    data['mesh_tris'] = np.array(mesh_tris, dtype=np.uint32) if mesh_tris else np.empty(0, dtype=np.uint32)
    data['mesh_colors'] = np.array(mesh_colors, dtype=np.float32) if mesh_colors else np.empty((0, 4), dtype=np.float32)

    # Clear shapely geometry
    del data['geometry']

    return data


def _linearring_to_segments(arr):
    # Close linear ring
    """
    Translates linear ring to line segments
    :param arr: numpy.array
        Array of linear ring vertices
    :return: numpy.array
        Line segments
    """
    # Use zip for pair generation - works for both open and closed rings
    # zip(arr[:-1], arr[1:]) gives pairs of consecutive elements
    segments = [coord for pair in zip(arr[:-1], arr[1:]) for coord in pair]
    
    # Close ring if not already closed (add final segment from last to first)
    if arr[0] != arr[-1]:
        segments.append(arr[-1])
        segments.append(arr[0])
    
    return segments


def _linestring_to_segments(arr):
    """
    Translates line strip to segments
    :param arr: numpy.array
        Array of line strip vertices
    :return: numpy.array
        Line segments
    """
    # Optimized: direct pair generation using zip - avoids creating oversized intermediate list
    # zip(arr[:-1], arr[1:]) creates pairs of consecutive vertices
    # flatten with list comprehension
    return [coord for pair in zip(arr[:-1], arr[1:]) for coord in pair]


class ShapeGroup(object):
    def __init__(self, collection):
        """
        Represents group of shapes in collection
        :param collection: ShapeCollection
            Collection to work with
        """
        self._collection = collection
        self._indexes = []
        self._visible = True
        self._enabled = True
        self._color = None

    def add(self, **kwargs):
        """
        Adds shape to collection and store index in group
        :param kwargs: keyword arguments.
            Arguments for ShapeCollection.add function
        """
        key = self._collection.add(**kwargs)
        self._indexes.append(key)
        return key

    def add_batch(self, shapes_data, **kwargs):
        """
        Batch adds shapes to collection and stores indexes in group.
        """
        keys = self._collection.add_batch(shapes_data, **kwargs)
        self._indexes.extend(keys)
        return keys
    
    def remove(self, idx, update=False):
        self._indexes.remove(idx)
        self._collection.remove(idx, False)
        if update:
            self._collection.redraw([])             # Skip waiting results

    def clear(self, update=False):
        """
        Removes group shapes from collection, clear indexes
        :param update: bool
            Set True to redraw collection
        """
        for i in self._indexes:
            self._collection.remove(i, False)

        del self._indexes[:]

        if update:
            self._collection.redraw([])             # Skip waiting results

    def redraw(self, update_colors=None):
        """
        Redraws shape collection
        """
        if update_colors:
            self._collection.redraw(self._indexes, update_colors=update_colors)
        else:
            self._collection.redraw(self._indexes)

    @property
    def visible(self):
        """
        Visibility of group
        :return: bool
        """
        return self._visible

    @visible.setter
    def visible(self, value):
        """
        Visibility of group
        :param value: bool
        """
        self._visible = value
        for i in self._indexes:
            self._collection.data[i]['visible'] = value

        self._collection.redraw([])

    @property
    def enabled(self):
        """
        Another way to toggle visibility on canvas
        :return:
        :rtype:
        """
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        """
        Another way to toggle visibility on canvas
        :param value: bool
        """
        self._collection.enabled = value

    def update_visibility(self, state, indexes=None):
        if indexes:
            for i in indexes:
                if i in self._indexes:
                    self._collection.data[i]['visible'] = state
        else:
            for i in self._indexes:
                self._collection.data[i]['visible'] = state

        self._collection.redraw([])


class ShapeCollectionVisual(CompoundVisual):

    def __init__(self, linewidth=1, triangulation='vispy', layers=3, pool=None, fcoptions=None, **kwargs):
        """
        Represents collection of shapes to draw on VisPy scene
        :param linewidth: float
            Width of lines/edges
        :param triangulation: str
            Triangulation method used for polygons translation
            'vispy' - VisPy lib triangulation
            'gpc' - Polygon2 lib
        :param layers: int
            Layers count
            Each layer adds 2 visuals on VisPy scene. Be careful: more layers cause less fps
        :param kwargs:
        """
        self.fc_options = fcoptions

        self.data = {}
        self.last_key = -1
        
        # Dirty flag to track whether buffers need rebuilding
        self._dirty = True

        # Thread locks
        self.key_lock = threading.Lock()
        self.results_lock = threading.Lock()
        self.update_lock = threading.Lock()

        # Process pool
        self.pool = pool
        self.results = {}
        self._batch_results = []  # NEW: list of (keys, AsyncResult) tuples for batch processing

        self._meshes = [MeshVisual() for _ in range(0, layers)]
        # self._lines = [LineVisual(antialias=True) for _ in range(0, layers)]
        self._lines = [LineVisual(antialias=True) for _ in range(0, layers)]

        self._line_width = linewidth
        self._triangulation = triangulation

        visuals_ = [self._lines[i // 2] if i % 2 else self._meshes[i // 2] for i in range(0, layers * 2)]

        CompoundVisual.__init__(self, visuals_, **kwargs)

        for m in self._meshes:
            # Backface culling - safe with CCW winding enforcement in tessellator
            cull = True
            if self.fc_options:
                cull = self.fc_options.get("global_backface_culling", True)
            m.set_gl_state(polygon_offset_fill=True, polygon_offset=(1, 1), cull_face=cull)

        for lne in self._lines:
            pass
            lne.set_gl_state(blend=True)

        self.freeze()

    def add(self, shape=None, color=None, face_color=None, alpha=None, visible=True,
            update=False, layer=1, tolerance=0.001, linewidth=None):
        """
        Adds shape to collection
        :return:
        :param shape: shapely.geometry
            Shapely geometry object
        :param color: str, tuple
            Line/edge color
        :param face_color: str, tuple
            Polygon face color
        :param alpha: str
            Polygon transparency
        :param visible: bool
            Shape visibility
        :param update: bool
            Set True to redraw collection
        :param layer: int
            Layer number. 0 - lowest.
        :param tolerance: float
            Geometry simplifying tolerance
        :param linewidth: int
            Width of the line
        :return: int
            Index of shape
        """
        # Get new key
        self.key_lock.acquire(True)
        self.last_key += 1
        key = self.last_key
        self.key_lock.release()

        # Prepare data for translation
        self.data[key] = {
            'geometry': shape,
            'color': color,
            'alpha': alpha,
            'face_color': face_color,
            'visible': visible,
            'layer': layer,
            'tolerance': tolerance,
            # the following keys are updated in the _update_shape_buffers() method
            'mesh_vertices': np.empty((0, 2), dtype=np.float32),    # Vertices for mesh
            'mesh_tris': np.empty(0, dtype=np.uint32),              # Faces for mesh
            'mesh_colors': np.empty((0, 4), dtype=np.float32),      # Face colors
            'line_pts': np.empty((0, 2), dtype=np.float32),         # Vertices for line
            'line_colors': np.empty((0, 4), dtype=np.float32)       # Line colors
        }

        if linewidth:
            self._line_width = linewidth

        # Always process synchronously for individual adds (pool IPC overhead > compute)
        self.data[key] = _update_shape_buffers(self.data[key])

        # Mark buffers as dirty
        self._dirty = True

        if update:
            self.redraw()   # redraw() waits for pool process end

        return key

    def add_batch(self, shapes_data, layer=1, tolerance=0.001, linewidth=None, visible=True):
        """
        Add multiple shapes in one pool call. Dramatically reduces IPC overhead.

        :param shapes_data: list of dicts, each with keys:
            'shape' (required), 'color', 'face_color', 'alpha', 'layer', 'tolerance'
        :param layer: int - default layer for shapes that don't specify one
        :param tolerance: float - default tolerance for shapes that don't specify one
        :param linewidth: int - line width override
        :param visible: bool - visibility for all shapes in the batch
        :return: list of int - keys for all added shapes (in same order as shapes_data)
        """
        if not shapes_data:
            return []

        if linewidth:
            self._line_width = linewidth

        keys = []
        data_list = []

        self.key_lock.acquire(True)
        for item in shapes_data:
            self.last_key += 1
            key = self.last_key
            keys.append(key)
            self.data[key] = {
                'geometry': item.get('shape'),
                'color': item.get('color'),
                'alpha': item.get('alpha'),
                'face_color': item.get('face_color'),
                'visible': visible,
                'layer': item.get('layer', layer),
                'tolerance': item.get('tolerance', tolerance),
                'mesh_vertices': np.empty((0, 2), dtype=np.float32),
                'mesh_tris': np.empty(0, dtype=np.uint32),
                'mesh_colors': np.empty((0, 4), dtype=np.float32),
                'line_pts': np.empty((0, 2), dtype=np.float32),
                'line_colors': np.empty((0, 4), dtype=np.float32)
            }
            data_list.append(self.data[key])
        self.key_lock.release()

        if self.fc_options and self.fc_options.get("global_graphic_engine_3d_no_mp") is True:
            # Synchronous mode
            for k, d in zip(keys, data_list):
                self.data[k] = _update_shape_buffers(d)
        else:
            try:
                # ONE pool.map_async call for ALL shapes
                # Pool distributes items across workers automatically
                result = self.pool.map_async(_update_shape_buffers, data_list)
                self._batch_results.append((keys, result))
            except Exception:
                # Fallback: process synchronously
                for k, d in zip(keys, data_list):
                    self.data[k] = _update_shape_buffers(d)

        self._dirty = True
        return keys

    def remove(self, key, update=False):
        """
        Removes shape from collection
        :param key: int
            Shape index to remove
        :param update:
            Set True to redraw collection
        """
        # Remove process result
        self.results_lock.acquire(True)
        if key in list(self.results.copy().keys()):
            del self.results[key]
        self.results_lock.release()

        # Remove data
        if key in self.data:
            del self.data[key]

        # Mark buffers as dirty
        self._dirty = True

        if update:
            self.__update()

    def clear(self, update=False):
        """
        Removes all shapes from collection
        :param update: bool
            Set True to redraw collection
        """
        self.last_key = -1
        self.data.clear()
        
        # Mark buffers as dirty
        self._dirty = True
        
        if update:
            self.__update()

    def update_visibility(self, state: bool, indexes=None) -> None:
        # Lock sub-visuals updates
        self.update_lock.acquire(True)
        if indexes is None:
            for k, data in list(self.data.items()):
                self.data[k]['visible'] = state
        else:
            for k, data in list(self.data.items()):
                if k in indexes:
                    self.data[k]['visible'] = state

        self.update_lock.release()
        
        # Mark buffers as dirty
        self._dirty = True

    def update_color(self, new_mesh_color=None, new_line_color=None, indexes=None):
        if new_mesh_color is None and new_line_color is None:
            return

        if not self.data:
            return

        # Mark buffers as dirty (color changes require visual update)
        self._dirty = True
        
        # Rest of the method...

        # if a new color is empty string then make it None so it will not be updated
        # if a new color is valid then transform it here in a format palatable
        mesh_color_rgba = None
        line_color_rgba = None
        if new_mesh_color:
            if new_mesh_color != '':
                mesh_color_rgba = Color(new_mesh_color).rgba
            else:
                new_mesh_color = None
        if new_line_color:
            if new_line_color != '':
                line_color_rgba = Color(new_line_color).rgba
            else:
                new_line_color = None

        mesh_colors_chunks = [[] for _ in range(len(self._meshes))]     # Face colors chunks
        line_colors_chunks = [[] for _ in range(len(self._meshes))]     # Line colors chunks
        line_pts_chunks = [[] for _ in range(len(self._lines))]         # Vertices for line chunks

        # Lock sub-visuals updates
        self.update_lock.acquire(True)
        # Merge shapes buffers

        if indexes is None:
            for k, data in list(self.data.items()):
                if data['visible'] and 'line_pts' in data:
                    if new_mesh_color and new_mesh_color != '':
                        dim_mesh_tris = (len(data['mesh_tris']) // 3)
                        if dim_mesh_tris != 0:
                            try:
                                mesh_colors_chunks[data['layer']].append(np.tile(mesh_color_rgba, (dim_mesh_tris, 1)))
                                self.data[k]['face_color'] = new_mesh_color
                                # Invalidate cached rgba
                                data['face_color_rgba'] = mesh_color_rgba
                                data['mesh_colors'] = np.tile(mesh_color_rgba, (len(data['mesh_colors']), 1))
                            except Exception as e:
                                print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                      "Create mesh colors --> Data error. %s" % str(e))

                    if new_line_color and new_line_color != '':
                        dim_line_pts = (len(data['line_pts']))
                        if dim_line_pts != 0:
                            try:
                                line_pts_chunks[data['layer']].append(data['line_pts'])
                                line_colors_chunks[data['layer']].append(np.tile(line_color_rgba, (dim_line_pts, 1)))
                                self.data[k]['color'] = new_line_color
                                # Invalidate cached rgba
                                data['color_rgba'] = line_color_rgba
                                data['line_colors'] = np.tile(line_color_rgba, (len(data['line_colors']), 1))
                            except Exception as e:
                                print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                      "Create line colors --> Data error. %s" % str(e))
        else:
            for k, data in list(self.data.items()):
                if data['visible'] and 'line_pts' in data:
                    dim_mesh_tris = (len(data['mesh_tris']) // 3)
                    dim_line_pts = (len(data['line_pts']))

                    if k in indexes:
                        if new_mesh_color and new_mesh_color != '':
                            if dim_mesh_tris != 0:
                                try:
                                    mesh_colors_chunks[data['layer']].append(np.tile(mesh_color_rgba, (dim_mesh_tris, 1)))
                                    self.data[k]['face_color'] = new_mesh_color
                                    # Invalidate cached rgba
                                    data['face_color_rgba'] = mesh_color_rgba
                                    data['mesh_colors'] = np.tile(mesh_color_rgba, (len(data['mesh_colors']), 1))
                                except Exception as e:
                                    print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                          "Create mesh colors --> Data error. %s" % str(e))
                        if new_line_color and new_line_color != '':
                            if dim_line_pts != 0:
                                try:
                                    line_pts_chunks[data['layer']].append(data['line_pts'])
                                    line_colors_chunks[data['layer']].append(np.tile(line_color_rgba, (dim_line_pts, 1)))
                                    self.data[k]['color'] = new_line_color
                                    # Invalidate cached rgba
                                    data['color_rgba'] = line_color_rgba
                                    data['line_colors'] = np.tile(line_color_rgba, (len(data['line_colors']), 1))
                                except Exception as e:
                                    print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                          "Create line colors --> Data error. %s" % str(e))
                    else:
                        if dim_mesh_tris != 0:
                            try:
                                # Use cached rgba value if available
                                if 'face_color_rgba' not in data:
                                    data['face_color_rgba'] = Color(data['face_color']).rgba
                                mesh_colors_chunks[data['layer']].append(np.tile(data['face_color_rgba'], (dim_mesh_tris, 1)))
                            except Exception as e:
                                print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                      "Create mesh colors --> Data error. %s" % str(e))

                        if dim_line_pts != 0:
                            try:
                                line_pts_chunks[data['layer']].append(data['line_pts'])
                                # Use cached rgba value if available
                                if 'color_rgba' not in data:
                                    data['color_rgba'] = Color(data['color']).rgba
                                line_colors_chunks[data['layer']].append(np.tile(data['color_rgba'], (dim_line_pts, 1)))
                            except Exception as e:
                                print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                                      "Create line colors --> Data error. %s" % str(e))

        # Concatenate chunks for GPU upload
        mesh_colors = [np.concatenate(c) if c else np.empty((0, 4), dtype=np.float32) for c in mesh_colors_chunks]
        line_pts = [np.concatenate(c) if c else np.empty((0, 2), dtype=np.float32) for c in line_pts_chunks]
        line_colors = [np.concatenate(c) if c else np.empty((0, 4), dtype=np.float32) for c in line_colors_chunks]

        # Updating meshes
        if new_mesh_color and new_mesh_color != '':
            for i, mesh in enumerate(self._meshes):
                if len(mesh_colors[i]) > 0:
                    try:
                        mesh._meshdata.set_face_colors(colors=mesh_colors[i])
                        mesh.mesh_data_changed()
                    except Exception as e:
                        print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                              "Apply mesh colors --> Data error. %s" % str(e))

        # Updating lines
        if new_line_color and new_line_color != '':
            for i, line in enumerate(self._lines):
                if len(line_pts[i]) > 0:
                    line.visible = True
                    try:
                        line._color = line_colors[i]
                        line._changed['color'] = True
                        line.update()
                    except Exception as e:
                        print("VisPyVisuals.ShapeCollectionVisual.update_color(). "
                              "Apply line colors --> Data error. %s" % str(e))
                else:
                    # line.clear_data()
                    line.visible = False

        self.update_lock.release()

    def __update(self):
        """
        Merges internal buffers, sets data to visuals, redraws collection on scene
        """
        # Skip if nothing has changed
        if not self._dirty:
            return
        
        # Optimized: Phase 1 - Collect references (O(1) per shape)
        layer_line_pts_chunks = [[] for _ in range(len(self._lines))]
        layer_mesh_verts_chunks = [[] for _ in range(len(self._meshes))]
        layer_mesh_tris_chunks = [[] for _ in range(len(self._meshes))]
        layer_mesh_colors_chunks = [[] for _ in range(len(self._meshes))]
        layer_line_colors_chunks = [[] for _ in range(len(self._lines))]
        
        # Track cumulative vertex counts per layer for mesh_tris offsets
        # mesh_tris contains triangle indices into mesh_vertices.
        # When merging multiple shapes, indices must be offset by the
        # cumulative vertex count of all previously merged shapes.
        layer_vert_counts = [0] * len(self._meshes)

        # Lock sub-visuals updates
        self.update_lock.acquire(True)

        # Collect shape buffers
        for data in list(self.data.values()):
            if data['visible'] and 'line_pts' in data:
                layer = data['layer']
                layer_line_pts_chunks[layer].append(data['line_pts'])
                layer_line_colors_chunks[layer].append(data['line_colors'])

                if len(data['mesh_tris']) > 0 and len(data['mesh_vertices']) > 0:
                    offset = layer_vert_counts[layer]
                    layer_mesh_tris_chunks[layer].append(
                        data['mesh_tris'] + offset
                    )
                    layer_mesh_verts_chunks[layer].append(data['mesh_vertices'])
                    layer_mesh_colors_chunks[layer].append(data['mesh_colors'])
                    layer_vert_counts[layer] += len(data['mesh_vertices'])

        # Phase 2: Single flatten per layer using np.concatenate
        def _concat(chunks, empty_shape, dtype):
            return np.concatenate(chunks) if chunks else np.empty(empty_shape, dtype=dtype)

        line_pts = [_concat(layer_line_pts_chunks[i], (0, 2), np.float32) for i in range(len(self._lines))]
        line_colors = [_concat(layer_line_colors_chunks[i], (0, 4), np.float32) for i in range(len(self._lines))]
        mesh_vertices = [_concat(layer_mesh_verts_chunks[i], (0, 2), np.float32) for i in range(len(self._meshes))]
        mesh_tris = [_concat(layer_mesh_tris_chunks[i], (0,), np.uint32) for i in range(len(self._meshes))]
        mesh_colors = [_concat(layer_mesh_colors_chunks[i], (0, 4), np.float32) for i in range(len(self._meshes))]

        # Set GPU state once, outside the mesh loop (Step 1a optimization)
        set_state(polygon_offset_fill=False)

        # Updating meshes
        for i, mesh in enumerate(self._meshes):
            if len(mesh_vertices[i]) > 0:
                mesh.set_data(
                    vertices=mesh_vertices[i],
                    faces=mesh_tris[i].reshape((-1, 3)),
                    face_colors=mesh_colors[i]
                )
            else:
                mesh.set_data()

            mesh._bounds_changed()

        # Updating lines
        for i, line in enumerate(self._lines):
            if len(line_pts[i]) > 0:
                line.visible = True
                line.set_data(
                    pos=line_pts[i],
                    color=line_colors[i],
                    width=self._line_width,
                    connect='segments')
            else:
                # line.clear_data()
                line.visible = False

            line._bounds_changed()

        self._bounds_changed()
        
        # Reset dirty flag AFTER acquiring lock and completing update
        # This prevents race conditions where another thread sets dirty
        # between the initial check and the actual update
        self._dirty = False
        
        self.update_lock.release()

    def redraw(self, indexes=None, update_colors=None):
        """
        Redraws collection
        :param indexes:     list
            Shape indexes to get from process pool
        :param update_colors:
        """
        # Only one thread can update data
        self.results_lock.acquire(True)

        results_collected = False

        # --- Collect batch results (Step 3c optimization) ---
        for batch_keys, batch_result in self._batch_results:
            try:
                batch_result.wait()
                batch_data = batch_result.get()
                for k, r in zip(batch_keys, batch_data):
                    if k in self.data:
                        self.data[k] = r
                        results_collected = True
            except Exception as e:
                print("VisPyVisuals.ShapeCollectionVisual.redraw() --> Batch error = %s" % str(e))

        self._batch_results.clear()
        # --- End batch results collection ---

        # Existing per-shape result collection (backward compat with add())
        for i in list(self.data.keys()) if not indexes else indexes:
            if i in list(self.results.keys()):
                try:
                    self.results[i].wait()                                  # Wait for process results
                    if i in self.data:
                        self.data[i] = self.results[i].get()[0]             # Store translated data
                        del self.results[i]
                        results_collected = True
                except Exception as e:
                    print("VisPyVisuals.ShapeCollectionVisual.redraw() --> Data error = %s. Indexes = %s" %
                          (str(e), str(indexes)))

        self.results_lock.release()

        # Mark dirty if pool results were collected (data changed)
        if results_collected:
            self._dirty = True

        if update_colors is None or update_colors is False:
            self.__update()
        else:
            try:
                self.update_color(
                    new_mesh_color=update_colors[0],
                    new_line_color=update_colors[1],
                    indexes=indexes
                )
            except Exception as e:
                print("VisPyVisuals.ShapeCollectionVisual.redraw() --> Update colors error = %s." % str(e))

    def lock_updates(self):
        self.update_lock.acquire(True)

    def unlock_updates(self):
        self.update_lock.release()


class TextGroup(object):
    def __init__(self, collection):
        self._collection = collection
        self._index = None
        self._visible = None

    def set(self, **kwargs):
        """
        Adds text to collection and store index
        :param kwargs: keyword arguments
            Arguments for TextCollection.add function
        """
        self._index = self._collection.add(**kwargs)

    def clear(self, update=False):
        """
        Removes text from collection, clear index
        :param update: bool
            Set True to redraw collection
        """

        if self._index is not None:
            self._collection.remove(self._index, False)
            self._index = None

        if update:
            self._collection.redraw()

    def redraw(self):
        """
        Redraws text collection
        """
        self._collection.redraw()

    @property
    def visible(self):
        """
        Visibility of group
        :return: bool
        """
        return self._visible

    @visible.setter
    def visible(self, value):
        """
        Visibility of group
        :param value: bool
        """
        self._visible = value
        if self._index:
            try:
                self._collection.data[self._index]['visible'] = value
            except KeyError as e:
                print("VisPyVisuals.TextGroup.visible --> KeyError --> %s" % str(e))
                pass
            self._collection.redraw()


class TextCollectionVisual(TextVisual):

    def __init__(self, **kwargs):
        """
        Represents collection of shapes to draw on VisPy scene
        :param kwargs: keyword arguments
            Arguments to pass for TextVisual
        """
        self.data = {}
        self.last_key = -1
        self.lock = threading.Lock()
        self.method = 'gpu'
        super(TextCollectionVisual, self).__init__(**kwargs)

        self.freeze()

    def add(self, text, pos, visible=True, update=True, font_size=9, color='black'):
        """
        Adds array of text to collection
        :param text: list
            Array of strings ['str1', 'str2', ... ]
        :param pos: list
            Array of string positions   [(0, 0), (10, 10), ... ]
        :param visible: bool
        |   Set True to make it visible
        :param update: bool
            Set True to redraw collection
        :param font_size: int
            Set font size to redraw collection
        :param color: string
            Set font color to redraw collection
        :return: int
            Index of array
        """
        # Get new key
        self.lock.acquire(True)
        self.last_key += 1
        key = self.last_key
        self.lock.release()

        # Prepare data for translation
        self.data[key] = {'text': text, 'pos': pos, 'visible': visible, 'font_size': font_size, 'color': color}

        if update:
            self.redraw()

        return key

    def remove(self, key, update=False):
        """
        Removes shape from collection
        :param key: int
            Shape index to remove
        :param update:
            Set True to redraw collection
        """
        del self.data[key]

        if update:
            self.__update()

    def clear(self, update=False):
        """
        Removes all shapes from collection
        :param update: bool
            Set True to redraw collection
        """
        self.data.clear()
        if update:
            self.__update()

    def __update(self):
        """
        Merges internal buffers, sets data to visuals, redraws collection on scene
        """
        labels = []
        pos = []
        font_s = 9
        color = 'black'

        # Merge buffers
        for data in list(self.data.values()):
            if data['visible']:
                try:
                    labels += data['text']
                    pos += data['pos']
                    font_s = data['font_size']
                    color = data['color']
                except Exception as e:
                    print("VisPyVisuals.TextCollectionVisual._update() --> Data error. %s" % str(e))

        # Updating text
        if len(labels) > 0:
            self.text = labels
            self.pos = pos
            self.font_size = font_s
            self.color = color
        else:
            self.text = None
            self.pos = (0, 0)

        self._bounds_changed()

    def redraw(self):
        """
        Redraws collection
        """
        self.__update()


# Add 'enabled' property to visual nodes
def create_fast_node(subclass):
    # Create a new subclass of Node.

    # Decide on new class name
    clsname = subclass.__name__
    if not (clsname.endswith('Visual') and issubclass(subclass, visuals.BaseVisual)):
        raise RuntimeError('Class "%s" must end with Visual, and must '
                           'subclass BaseVisual' % clsname)
    clsname = clsname[:-6]

    # Generate new docstring based on visual docstring
    try:
        doc = generate_docstring(subclass, clsname)
    except Exception:
        # If parsing fails, just return the original Visual docstring
        doc = subclass.__doc__

    # New __init__ method
    def __init__(self, *args, **kwargs):
        parent = kwargs.pop('parent', None)
        name = kwargs.pop('name', None)
        self.name = name  # to allow __str__ before Node.__init__
        self._visual_superclass = subclass

        # parent: property,
        # _parent: attribute of Node class
        # __parent: attribute of fast_node class
        self.__parent = parent
        self._enabled = False

        subclass.__init__(self, *args, **kwargs)
        self.unfreeze()
        VisualNode.__init__(self, parent=parent, name=name)
        self.freeze()

    # Create new class
    cls = type(
        clsname, (VisualNode, subclass), {'__init__': __init__, '__doc__': doc}
    )

    # 'Enabled' property clears/restores 'parent' property of Node class
    # Scene will be painted quicker than when using 'visible' property
    def get_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        if enabled:
            self.parent = self.__parent                 # Restore parent
        else:
            if self.parent:                             # Store parent
                self.__parent = self.parent
            self.parent = None

    cls.enabled = property(get_enabled, set_enabled)

    return cls


ShapeCollection = create_fast_node(ShapeCollectionVisual)
TextCollection = create_fast_node(TextCollectionVisual)
Cursor = create_fast_node(MarkersVisual)

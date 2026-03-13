# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Author: Marius Adrian Stanciu (c)                   #
# Date: 3/13/2026                                         #
# MIT Licence                                              #
# ##########################################################

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

from appCommon.Common import GracefulException as grace

from shapely import Polygon, LineString, MultiPolygon

from copy import copy, deepcopy
import numpy as np
import re
import logging

log = logging.getLogger('base')


@dataclass
class ParsingContext:
    """Holds shared state during PDF parsing."""
    object_dict: Dict[int, Any] = field(default_factory=dict)
    layer_nr: int = 1
    apertures_dict: Dict[str, Any] = field(default_factory=dict)
    clear_apertures_dict: Dict[int, Any] = field(default_factory=lambda: {0: {'size': 0.0, 'type': 'C', 'geometry': []}})
    old_color: List[Optional[float]] = field(default_factory=lambda: [None, None, None])
    flag_clear_geo: bool = False
    # Track if detection mode allows triggering clear geo
    detection_triggered: bool = False


class PdfParser:

    WHITE_THRESHOLD = 1.0
    INITIAL_APERTURE = 10
    BUFFER_EPSILON = 0.0000001
    DEFAULT_SCALE = [1, 1]
    DEFAULT_OFFSET = [0, 0]

    # Hole detection modes
    DETECT_BOTH = 'both'           # Detect on both stroke and fill color change (default)
    DETECT_FILL_ONLY = 'fill_only' # Detect on fill color change only
    DETECT_STROKE_ONLY = 'stroke_only'  # Detect on stroke color change only

    def __init__(self, units: str, resolution: int, abort: bool,
                 hole_detection_mode: str = 'both') -> None:
        """
        Initialize PDF Parser.

        Args:
            units: 'MM' or 'INCH'
            resolution: Steps per circle for arc approximation
            abort: Abort flag for graceful termination
            hole_detection_mode: How to detect excellon holes from PDF
                                 'both' (default) - detect on both stroke and fill color change
                                 'fill_only' - detect on fill color change only
                                 'stroke_only' - detect on stroke color change only
        """
        self.step_per_circles = resolution
        self.units = units
        self.abort_flag = abort
        self.hole_detection_mode = hole_detection_mode

        # Validate detection mode
        if hole_detection_mode not in [self.DETECT_BOTH, self.DETECT_FILL_ONLY, self.DETECT_STROKE_ONLY]:
            raise ValueError(
                f"Invalid hole_detection_mode: {hole_detection_mode}. "
                f"Must be one of: '{self.DETECT_BOTH}', '{self.DETECT_FILL_ONLY}', '{self.DETECT_STROKE_ONLY}'"
            )

        self.stroke_color_re = re.compile(r'^\s*(\d+\.?\d*) (\d+\.?\d*) (\d+\.?\d*)\s*RG$')
        self.fill_color_re = re.compile(r'^\s*(\d+\.?\d*) (\d+\.?\d*) (\d+\.?\d*)\s*rg$')
        self.rect_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s*re$')
        self.start_subpath_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\sm$')
        self.draw_line_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\sl')
        self.draw_arc_3pt_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)'
                                          r'\s(-?\d+\.?\d*)\s*c$')
        self.draw_arc_2pt_c1start_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s*v$')
        self.draw_arc_2pt_c2stop_re = re.compile(r'^(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s(-?\d+\.?\d*)\s*y$')
        self.end_subpath_re = re.compile(r'^h$')
        self.strokewidth_re = re.compile(r'^(\d+\.?\d*)\s*w$')
        self.stroke_path__re = re.compile(r'^S\s?Q?$')
        self.close_stroke_path__re = re.compile(r'^s$')
        self.fill_path_re = re.compile(r'^[f|F][*]?$')
        self.fill_stroke_path_re = re.compile(r'^B[*]?$')
        self.close_fill_stroke_path_re = re.compile(r'^b[*]?$')
        self.no_op_re = re.compile(r'^n$')
        self.combined_transform_re = re.compile(r'^(q)?\s*(-?\d+\.?\d*) (-?\d+\.?\d*) (-?\d+\.?\d*) (-?\d+\.?\d*) '
                                                r'(-?\d+\.?\d*) (-?\d+\.?\d*)\s+cm$')
        self.clip_path_re = re.compile(r'^W[*]? n?$')
        self.save_gs_re = re.compile(r'^q.*?$')
        self.restore_gs_re = re.compile(r'^.*Q.*$')

        self.gs = {'transform': [], 'line_width': []}

        self.point_to_unit_factor = 0.01388888888

    def _find_or_create_aperture(self, apertures_dict: dict, applied_size: float, aperture: int) -> Tuple[str, int]:
        """Find or create an aperture by size.

        Args:
            apertures_dict: Dictionary of apertures
            applied_size: The size to search for
            aperture: Default aperture number to use if creating new

        Returns:
            Tuple of (aperture_id_to_use, aperture_number)
        """
        found_aperture = None
        for apid in apertures_dict:
            if apertures_dict[apid]['size'] == round(applied_size, 5):
                found_aperture = apid
                break

        if found_aperture:
            ap_to_use = found_aperture
        else:
            ap_list = [int(k) for k in apertures_dict.keys()]
            if 0 in ap_list and len(ap_list) == 1:
                ap_list.remove(0)
            if not ap_list:
                aperture = self.INITIAL_APERTURE
            else:
                aperture = max(ap_list) + 1

            ap_to_use = str(aperture)
            apertures_dict[ap_to_use] = {
                'size': round(applied_size, 5),
                'type': 'C',
                'geometry': []
            }

        return ap_to_use, aperture

    def _store_geometry(self, apertures_dict: dict, path_geo: list, aperture_id: str, clear_geo: bool = False) -> None:
        """Store geometry in the aperture dictionary.

        Args:
            apertures_dict: Dictionary of apertures
            path_geo: List of geometries to store
            aperture_id: The aperture ID to store geometry in
            clear_geo: If True, store as clear geometry; otherwise store as solid with follow
        """
        for pdf_geo in path_geo:
            if isinstance(pdf_geo, MultiPolygon):
                for poly in pdf_geo.geoms:
                    if clear_geo:
                        new_el = {'clear': poly}
                    else:
                        new_el = {'solid': poly, 'follow': poly.exterior}
                    apertures_dict[aperture_id]['geometry'].append(deepcopy(new_el))
            elif isinstance(pdf_geo, Polygon):
                if clear_geo:
                    new_el = {'clear': pdf_geo}
                else:
                    new_el = {'solid': pdf_geo, 'follow': pdf_geo.exterior}
                apertures_dict[aperture_id]['geometry'].append(deepcopy(new_el))
            else:
                if clear_geo:
                    new_el = {'clear': pdf_geo}
                else:
                    new_el = {'solid': pdf_geo, 'follow': pdf_geo}
                apertures_dict[aperture_id]['geometry'].append(deepcopy(new_el))

    def parse_pdf(self, pdf_content):

        if self.units.upper() == 'MM':
            self.point_to_unit_factor = 25.4 / 72
        else:
            self.point_to_unit_factor = 1 / 72

        path = {
            'lines': [],
            'bezier': [],
            'rectangle': []
        }

        subpath = {
            'lines': [],
            'bezier': [],
            'rectangle': []
        }

        current_subpath = None
        close_subpath = False
        start_point = None
        current_point = None
        size = 0

        offset_geo = self.DEFAULT_OFFSET[:]
        scale_geo = self.DEFAULT_SCALE[:]

        ctx = ParsingContext()
        ctx.object_dict[ctx.layer_nr] = {}

        aperture = self.INITIAL_APERTURE

        line_nr = 0
        lines = pdf_content.splitlines()

        for pline in lines:
            if self.abort_flag:
                raise grace

            line_nr += 1

            match = self.stroke_color_re.search(pline)
            if match:
                color = [float(match.group(1)), float(match.group(2)), float(match.group(3))]
                ctx = self._handle_stroke_color_change(color, line_nr, ctx)
                continue

            match = self.fill_color_re.search(pline)
            if match:
                fill_color = [float(match.group(1)), float(match.group(2)), float(match.group(3))]
                ctx = self._handle_fill_color_change(fill_color, ctx, line_nr)
                continue

            match = self.combined_transform_re.search(pline)
            if match:
                self._handle_combined_transform(match, line_nr, offset_geo, scale_geo, size)
                continue

            match = self.save_gs_re.search(pline)
            if match:
                self._save_graphic_state(offset_geo, scale_geo, size, line_nr)

            match = self.restore_gs_re.search(pline)
            if match:
                offset_geo, scale_geo, size = self._restore_graphic_state()

            match = self.start_subpath_re.search(pline)
            if match:
                close_subpath = False
                subpath, start_point = self._start_subpath(
                    match, offset_geo, scale_geo, subpath
                )
                current_point = start_point
                continue

            match = self.draw_line_re.search(pline)
            if match:
                subpath, current_point, current_subpath = self._draw_line(
                    match, offset_geo, scale_geo, subpath
                )
                continue

            match = self.draw_arc_3pt_re.search(pline)
            if match:
                current_subpath = 'bezier'
                subpath, current_point = self._draw_bezier_c(
                    match, offset_geo, scale_geo, subpath, current_point
                )
                continue

            match = self.draw_arc_2pt_c1start_re.search(pline)
            if match:
                current_subpath = 'bezier'
                subpath, current_point = self._draw_bezier_v(
                    match, offset_geo, scale_geo, subpath, current_point
                )
                continue

            match = self.draw_arc_2pt_c2stop_re.search(pline)
            if match:
                subpath, current_point = self._draw_bezier_y(
                    match, offset_geo, scale_geo, subpath, current_point
                )
                continue

            match = self.rect_re.search(pline)
            if match:
                current_subpath = 'rectangle'
                subpath, current_point = self._draw_rectangle(
                    match, offset_geo, scale_geo, subpath
                )
                continue

            match = self.clip_path_re.search(pline)
            if match:
                subpath, close_subpath = self._handle_clip_path(
                    subpath, path, current_subpath, close_subpath
                )
                continue

            match = self.end_subpath_re.search(pline)
            if match:
                subpath, close_subpath = self._close_subpath(
                    subpath, path, current_subpath, start_point
                )
                continue

            match = self.strokewidth_re.search(pline)
            if match:
                size = float(match.group(1))
                continue

            match = self.no_op_re.search(pline)
            if match:
                subpath['lines'] = []
                subpath['bezier'] = []
                subpath['rectangle'] = []
                continue

            match = self.stroke_path__re.search(pline)
            if match:
                applied_size = size * scale_geo[0] * self.point_to_unit_factor
                self._stroke_path(
                    path, subpath, current_subpath, applied_size,
                    line_nr, pline, ctx.apertures_dict, aperture
                )
                continue

            match = self.fill_path_re.search(pline)
            if match:
                applied_size = size * scale_geo[0] * self.point_to_unit_factor
                close_subpath = self._fill_path(
                    path, subpath, current_subpath, applied_size,
                    start_point, close_subpath, ctx.flag_clear_geo,
                    ctx.clear_apertures_dict, ctx.apertures_dict
                )
                continue

            match = self.fill_stroke_path_re.search(pline)
            if match:
                applied_size = size * scale_geo[0] * self.point_to_unit_factor
                close_subpath = self._fill_stroke_path(
                    path, subpath, current_subpath, applied_size,
                    start_point, close_subpath, ctx.flag_clear_geo,
                    ctx.apertures_dict, aperture
                )
                continue

        return self._finalize_object_dict(
            ctx.object_dict, ctx.apertures_dict, ctx.clear_apertures_dict,
            ctx.layer_nr, self.abort_flag
        )

    def _handle_combined_transform(self, match, line_nr: int,
                                    offset_geo: List[float], scale_geo: List[float],
                                    size: float) -> bool:
        """Handle combined transformation. Returns True if transformation detected.

        Args:
            match: Regex match object
            line_nr: Current line number for logging
            offset_geo: [offset_x, offset_y] to mutate
            scale_geo: [scale_x, scale_y] to mutate
            size: Current line width

        Returns:
            True if transformation was applied
        """
        transformed = False

        if match.group(1) == 'q':
            log.debug(
                "parse_pdf() --> Save to GS found on line: %s --> offset=[%f, %f] ||| scale=[%f, %f]" %
                (line_nr, offset_geo[0], offset_geo[1], scale_geo[0], scale_geo[1]))

            self.gs['transform'].append(deepcopy([offset_geo, scale_geo]))
            self.gs['line_width'].append(deepcopy(size))

        if (float(match.group(3)) == 0 and float(match.group(4)) == 0) and \
                (float(match.group(6)) != 0 or float(match.group(7)) != 0):
            log.debug(
                "parse_pdf() --> OFFSET transformation found on line: %s" % line_nr)

            offset_geo[0] += float(match.group(6))
            offset_geo[1] += float(match.group(7))
            transformed = True

        if float(match.group(2)) != 1 and float(match.group(5)) != 1:
            log.debug(
                "parse_pdf() --> SCALE transformation found on line: %s" % line_nr)

            scale_geo[0] *= float(match.group(2))
            scale_geo[1] *= float(match.group(5))
            transformed = True

        return transformed

    def _save_graphic_state(self, offset_geo: List[float], scale_geo: List[float],
                            size: float, line_nr: int) -> None:
        """Save current transform and line width to graphic state stack.

        Args:
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            size: Current line width
            line_nr: Current line number for logging
        """
        log.debug(
            "parse_pdf() --> Save to GS found on line: %s --> offset=[%f, %f] ||| scale=[%f, %f]" %
            (line_nr, offset_geo[0], offset_geo[1], scale_geo[0], scale_geo[1]))
        self.gs['transform'].append(deepcopy([offset_geo, scale_geo]))
        self.gs['line_width'].append(deepcopy(size))

    def _restore_graphic_state(self) -> Tuple[List[float], List[float], float]:
        """Restore transform and line width from graphic state stack.

        Returns:
            Tuple of (offset_geo, scale_geo, size)
        """
        offset_geo = self.DEFAULT_OFFSET[:]
        scale_geo = self.DEFAULT_SCALE[:]
        size = 0

        try:
            restored_transform = self.gs['transform'].pop(-1)
            offset_geo = restored_transform[0]
            scale_geo = restored_transform[1]
        except IndexError:
            pass

        try:
            size = self.gs['line_width'].pop(-1)
        except IndexError:
            pass

        return offset_geo, scale_geo, size

    def _handle_stroke_color_change(self, color: List[float], line_nr: int,
                                     ctx: ParsingContext) -> ParsingContext:
        """Handle stroke color change. Returns updated context.

        Args:
            color: [r, g, b] color values
            line_nr: Current line number for logging
            ctx: ParsingContext to update

        Returns:
            Updated ParsingContext
        """
        log.debug(
            "parse_pdf() --> STROKE Color change on line: %s --> RED=%f GREEN=%f BLUE=%f" %
            (line_nr, color[0], color[1], color[2]))

        if color[0] == ctx.old_color[0] and color[1] == ctx.old_color[1] and color[2] == ctx.old_color[2]:
            return ctx

        # Check if stroke color change should trigger detection based on mode
        if self.hole_detection_mode in [self.DETECT_BOTH, self.DETECT_STROKE_ONLY]:
            ctx.detection_triggered = True
        else:
            ctx.detection_triggered = False

        if ctx.apertures_dict:
            ctx.object_dict[ctx.layer_nr] = deepcopy(ctx.apertures_dict)
            ctx.apertures_dict = {}
            ctx.layer_nr += 1
            ctx.object_dict[ctx.layer_nr] = {}

        ctx.old_color = [color[0], color[1], color[2]]
        # Only set flag_clear_geo to False if detection was triggered
        if ctx.detection_triggered:
            ctx.flag_clear_geo = False
        return ctx

    def _apply_transform_to_point(self, x: float, y: float,
                                    offset_geo: List[float], scale_geo: List[float]) -> Tuple[float, float]:
        """Apply offset and scale transformation to a point.

        Args:
            x: Raw x coordinate
            y: Raw y coordinate
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]

        Returns:
            Tuple of transformed (x, y) coordinates
        """
        x_transformed = (x + offset_geo[0]) * self.point_to_unit_factor * scale_geo[0]
        y_transformed = (y + offset_geo[1]) * self.point_to_unit_factor * scale_geo[1]
        return x_transformed, y_transformed

    def _start_subpath(self, match, offset_geo: List[float], scale_geo: List[float],
                       subpath: dict) -> Tuple[dict, Tuple]:
        """Handle 'm' command - Start a new subpath.

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict

        Returns:
            Tuple of (subpath, start_point)
        """
        subpath['lines'] = []
        subpath['bezier'] = []
        subpath['rectangle'] = []

        x = float(match.group(1))
        y = float(match.group(2))
        start_point = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        subpath['lines'].append(start_point)
        return subpath, start_point

    def _draw_line(self, match, offset_geo: List[float], scale_geo: List[float],
                   subpath: dict) -> Tuple[dict, Tuple, str]:
        """Handle 'l' command - Draw a line.

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict

        Returns:
            Tuple of (subpath, current_point, 'lines')
        """
        x = float(match.group(1))
        y = float(match.group(2))
        current_point = self._apply_transform_to_point(x, y, offset_geo, scale_geo)
        subpath['lines'].append(current_point)
        return subpath, current_point, 'lines'

    def _draw_bezier_c(self, match, offset_geo: List[float], scale_geo: List[float],
                       subpath: dict, current_point) -> Tuple[dict, Tuple]:
        """Handle 'c' command - Draw cubic Bezier's curve (3 control points).

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict
            current_point: Current point (will be updated)

        Returns:
            Tuple of (subpath, current_point)
        """
        start = current_point

        x = float(match.group(1))
        y = float(match.group(2))
        c1 = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        x = float(match.group(3))
        y = float(match.group(4))
        c2 = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        x = float(match.group(5))
        y = float(match.group(6))
        stop = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        subpath['bezier'].append([start, c1, c2, stop])
        current_point = stop
        return subpath, current_point

    def _draw_bezier_v(self, match, offset_geo: List[float], scale_geo: List[float],
                       subpath: dict, current_point) -> Tuple[dict, Tuple]:
        """Handle 'v' command - Draw cubic Bezier's curve with first control point = start.

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict
            current_point: Current point (will be updated)

        Returns:
            Tuple of (subpath, current_point)
        """
        start = current_point

        x = float(match.group(1))
        y = float(match.group(2))
        c2 = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        x = float(match.group(3))
        y = float(match.group(4))
        stop = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        subpath['bezier'].append([start, start, c2, stop])
        current_point = stop
        return subpath, current_point

    def _draw_bezier_y(self, match, offset_geo: List[float], scale_geo: List[float],
                       subpath: dict, current_point) -> Tuple[dict, Tuple]:
        """Handle 'y' command - Draw cubic Bezier's curve with second control point = stop.

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict
            current_point: Current point (will be updated)

        Returns:
            Tuple of (subpath, current_point)
        """
        start = current_point

        x = float(match.group(1))
        y = float(match.group(2))
        c1 = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        x = float(match.group(3))
        y = float(match.group(4))
        stop = self._apply_transform_to_point(x, y, offset_geo, scale_geo)

        subpath['bezier'].append([start, c1, stop, stop])
        current_point = stop
        return subpath, current_point

    def _draw_rectangle(self, match, offset_geo: List[float], scale_geo: List[float],
                        subpath: dict) -> Tuple[dict, Tuple]:
        """Handle 're' command - Draw rectangle.

        Args:
            match: Regex match object
            offset_geo: [offset_x, offset_y]
            scale_geo: [scale_x, scale_y]
            subpath: Current subpath dict

        Returns:
            Tuple of (subpath, current_point)
        """
        x = (float(match.group(1)) + offset_geo[0]) * self.point_to_unit_factor * scale_geo[0]
        y = (float(match.group(2)) + offset_geo[1]) * self.point_to_unit_factor * scale_geo[1]
        width = (float(match.group(3)) + offset_geo[0]) * self.point_to_unit_factor * scale_geo[0]
        height = (float(match.group(4)) + offset_geo[1]) * self.point_to_unit_factor * scale_geo[1]
        pt1 = (x, y)
        pt2 = (x + width, y)
        pt3 = (x + width, y + height)
        pt4 = (x, y + height)
        subpath['rectangle'] += [pt1, pt2, pt3, pt4, pt1]
        current_point = pt1
        return subpath, current_point

    def _close_subpath(self, subpath: dict, path: dict, current_subpath: str,
                       start_point: Tuple) -> Tuple[dict, bool]:
        """Handle 'h' command - Close current subpath.

        Args:
            subpath: Current subpath dict
            path: Path dict with lines/bezier/rectangle lists
            current_subpath: Current subpath type ('lines', 'bezier', 'rectangle')
            start_point: Start point of subpath

        Returns:
            Tuple of (subpath, close_subpath)
        """
        close_subpath = True
        if current_subpath == 'lines':
            subpath['lines'].append(start_point)
            path['lines'].append(copy(subpath['lines']))
            subpath['lines'] = []
        elif current_subpath == 'bezier':
            path['bezier'].append(copy(subpath['bezier']))
            subpath['bezier'] = []
        elif current_subpath == 'rectangle':
            path['rectangle'].append(copy(subpath['rectangle']))
            subpath['rectangle'] = []
        return subpath, close_subpath

    def _handle_clip_path(self, subpath: dict, path: dict, current_subpath: str,
                          close_subpath: bool) -> Tuple[dict, bool]:
        """Handle 'W' command - Handle clipping path (clear current subpath).

        Args:
            subpath: Current subpath dict
            path: Path dict with lines/bezier/rectangle lists
            current_subpath: Current subpath type
            close_subpath: Close flag (will be updated)

        Returns:
            Tuple of (subpath, close_subpath)
        """
        subpath['lines'] = []
        subpath['bezier'] = []
        subpath['rectangle'] = []
        if close_subpath is True:
            close_subpath = False
            if current_subpath == 'lines':
                path['lines'].pop(-1)
            if current_subpath == 'rectangle':
                path['rectangle'].pop(-1)
        return subpath, close_subpath

    def _handle_fill_color_change(self, fill_color: List[float], ctx: ParsingContext, line_nr: int) -> ParsingContext:
        """Handle fill color change. Returns updated context.

        Args:
            fill_color: [r, g, b] color values
            ctx: ParsingContext to update
            line_nr: Current line number for logging

        Returns:
            Updated ParsingContext
        """
        log.debug(
            "parse_pdf() --> FILL Color change on line: %s --> RED=%f GREEN=%f BLUE=%f" %
            (line_nr, fill_color[0], fill_color[1], fill_color[2]))

        # Check if fill color change should trigger detection based on mode
        if self.hole_detection_mode in [self.DETECT_BOTH, self.DETECT_FILL_ONLY]:
            ctx.detection_triggered = True
            # Only check for white (clear geometry) if detection is triggered
            if fill_color[0] == self.WHITE_THRESHOLD and fill_color[1] == self.WHITE_THRESHOLD and fill_color[2] == self.WHITE_THRESHOLD:
                ctx.flag_clear_geo = True
            else:
                ctx.flag_clear_geo = False
        else:
            ctx.detection_triggered = False
            # Don't change flag_clear_geo when fill detection is disabled
        return ctx

    def bezier_to_points(self, start, c1, c2, stop):
        """Convert Bezier curve to points.

        Args:
            start: Start point (x, y)
            c1: First control point (x, y)
            c2: Second control point (x, y)
            stop: End point (x, y)

        Returns:
            List of point coordinates tuples (x, y)
        """

        nr_points = np.linspace(0.0, 1.0, self.step_per_circles, endpoint=False)
        t = nr_points
        term_p0 = (1 - t) ** 3
        term_p1 = 3 * t * (1 - t) ** 2
        term_p2 = 3 * (1 - t) * t ** 2
        term_p3 = t ** 3
        x = start[0] * term_p0 + c1[0] * term_p1 + c2[0] * term_p2 + stop[0] * term_p3
        y = start[1] * term_p0 + c1[1] * term_p1 + c2[1] * term_p2 + stop[1] * term_p3
        points = np.column_stack((x, y))
        return points.tolist()

    def _apply_line_buffer_to_subpaths(self, subpaths: List, applied_size: float,
                                        subpath_type: str) -> List:
        """Apply line buffer to subpaths for stroke operations.

        Args:
            subpaths: List of subpaths (either from path dict or current subpath)
            applied_size: The stroke size (already scaled)
            subpath_type: Type of subpath ('lines', 'bezier', 'rectangle')

        Returns:
            List of buffered geometries
        """
        path_geo = []

        if subpath_type == 'lines' or subpath_type == 'rectangle':
            for subp in subpaths:
                geo = copy(subp)
                try:
                    geo = LineString(geo).buffer(
                        (float(applied_size) / 2),
                        resolution=self.step_per_circles
                    )
                    path_geo.append(geo)
                except ValueError:
                    pass

        elif subpath_type == 'bezier':
            for subp in subpaths:
                geo = []
                for b in subp:
                    geo += self.bezier_to_points(start=b[0], c1=b[1], c2=b[2], stop=b[3])
                try:
                    geo = LineString(geo).buffer(
                        (float(applied_size) / 2),
                        resolution=self.step_per_circles
                    )
                    path_geo.append(geo)
                except ValueError:
                    pass

        return path_geo

    def _apply_polygon_buffer_to_subpaths(self, subpaths: List, subpath_type: str,
                                          close_subpath: bool) -> List:
        """Apply polygon buffer to subpaths for fill operations.

        Args:
            subpaths: List of subpaths (either from path dict or current subpath)
            subpath_type: Type of subpath ('lines', 'bezier', 'rectangle')
            close_subpath: Whether subpath is already closed

        Returns:
            List of buffered polygon geometries
        """
        path_geo = []

        if subpath_type == 'lines':
            for subp in subpaths:
                geo = copy(subp)
                if close_subpath is False:
                    geo.append(geo[0])
                try:
                    geo_el = Polygon(geo).buffer(
                        self.BUFFER_EPSILON,
                        resolution=self.step_per_circles
                    )
                    path_geo.append(geo_el)
                except ValueError:
                    pass

        elif subpath_type == 'bezier':
            geo = []
            for subp in subpaths:
                for b in subp:
                    geo += self.bezier_to_points(start=b[0], c1=b[1], c2=b[2], stop=b[3])
                    if close_subpath is False:
                        geo.append(geo[0])
                    try:
                        geo_el = Polygon(geo).buffer(
                            self.BUFFER_EPSILON,
                            resolution=self.step_per_circles
                        )
                        path_geo.append(geo_el)
                    except ValueError:
                        pass

        elif subpath_type == 'rectangle':
            for subp in subpaths:
                geo = copy(subp)
                try:
                    geo_el = Polygon(geo).buffer(
                        self.BUFFER_EPSILON,
                        resolution=self.step_per_circles
                    )
                    path_geo.append(geo_el)
                except ValueError:
                    pass

        return path_geo

    def _stroke_path(self, path: dict, subpath: dict, current_subpath: str,
                     applied_size: float, line_nr: int, pline: str,
                     apertures_dict: dict, aperture: int) -> None:
        """Handle 'S' command - Stroke the path.

        Args:
            path: Path dict with lines/bezier/rectangle lists
            subpath: Current subpath dict
            current_subpath: Current subpath type
            applied_size: The stroke size (already scaled)
            line_nr: Current line number for logging
            pline: Current line content for logging
            apertures_dict: Apertures dictionary to store geometry
            aperture: Current aperture number
        """
        path_geo = []

        if current_subpath == 'lines':
            if path['lines']:
                path_geo = self._apply_line_buffer_to_subpaths(path['lines'], applied_size, 'lines')
                path['lines'] = []
            else:
                path_geo = self._apply_line_buffer_to_subpaths([subpath['lines']], applied_size, 'lines')
                subpath['lines'] = []

        if current_subpath == 'bezier':
            if path['bezier']:
                path_geo = self._apply_line_buffer_to_subpaths(path['bezier'], applied_size, 'bezier')
                path['bezier'] = []
            else:
                path_geo = self._apply_line_buffer_to_subpaths([subpath['bezier']], applied_size, 'bezier')
                subpath['bezier'] = []

        if current_subpath == 'rectangle':
            if path['rectangle']:
                path_geo = self._apply_line_buffer_to_subpaths(path['rectangle'], applied_size, 'rectangle')
                path['rectangle'] = []
            else:
                path_geo = self._apply_line_buffer_to_subpaths([subpath['rectangle']], applied_size, 'rectangle')
                subpath['rectangle'] = []

        if apertures_dict:
            try:
                ap_to_use, aperture = self._find_or_create_aperture(
                    apertures_dict, applied_size, aperture
                )
                self._store_geometry(apertures_dict, path_geo, ap_to_use, clear_geo=False)
            except Exception as e:
                log.error(
                    "line %d: %s ||| PdfParser.parse_pdf() Store Stroke geo -> %s" % (line_nr, pline, str(e))
                )
        else:
            apertures_dict[str(aperture)] = {
                'size': round(applied_size, 5),
                'type': 'C',
                'geometry': []
            }
            self._store_geometry(apertures_dict, path_geo, str(aperture), clear_geo=False)

    def _fill_path(self, path: dict, subpath: dict, current_subpath: str,
                   applied_size: float, start_point: Tuple, close_subpath: bool,
                   flag_clear_geo: bool, clear_apertures_dict: dict,
                   apertures_dict: dict) -> bool:
        """Handle 'f'/'F' command - Fill the path.

        Args:
            path: Path dict with lines/bezier/rectangle lists
            subpath: Current subpath dict
            current_subpath: Current subpath type
            applied_size: The fill size (already scaled)
            start_point: Start point of subpath
            close_subpath: Whether subpath is already closed
            flag_clear_geo: Flag indicating clear geometry
            clear_apertures_dict: Clear apertures dictionary
            apertures_dict: Apertures dictionary to store geometry

        Returns:
            Updated close_subpath value
        """
        path_geo = []

        if current_subpath == 'lines':
            if path['lines']:
                path_geo = self._apply_polygon_buffer_to_subpaths(
                    path['lines'], 'lines', close_subpath
                )
                path['lines'] = []
            else:
                geo = copy(subpath['lines'])
                if close_subpath is False:
                    geo.append(start_point)
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    path_geo.append(geo_el)
                except ValueError:
                    pass
                subpath['lines'] = []

        if current_subpath == 'bezier':
            geo = []
            if path['bezier']:
                path_geo = self._apply_polygon_buffer_to_subpaths(
                    path['bezier'], 'bezier', close_subpath
                )
                path['bezier'] = []
            else:
                for b in subpath['bezier']:
                    geo += self.bezier_to_points(start=b[0], c1=b[1], c2=b[2], stop=b[3])
                if close_subpath is False:
                    geo.append(start_point)
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    path_geo.append(geo_el)
                except ValueError:
                    pass
                subpath['bezier'] = []

        if current_subpath == 'rectangle':
            if path['rectangle']:
                path_geo = self._apply_polygon_buffer_to_subpaths(
                    path['rectangle'], 'rectangle', close_subpath
                )
                path['rectangle'] = []
            else:
                geo = copy(subpath['rectangle'])
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    path_geo.append(geo_el)
                except ValueError:
                    pass
                subpath['rectangle'] = []

        close_subpath = True

        if flag_clear_geo is True:
            if current_subpath == 'bezier':
                if path_geo:
                    try:
                        for g in path_geo:
                            new_el = {'clear': g}
                            clear_apertures_dict[0]['geometry'].append(new_el)
                    except TypeError:
                        new_el = {'clear': path_geo}
                        clear_apertures_dict[0]['geometry'].append(new_el)

            if '0' not in apertures_dict:
                apertures_dict['0'] = {
                    'size': applied_size,
                    'type': 'C',
                    'geometry': []
                }
            self._store_geometry(apertures_dict, path_geo, '0', clear_geo=True)
        else:
            if '0' not in apertures_dict:
                apertures_dict['0'] = {
                    'size': applied_size,
                    'type': 'C',
                    'geometry': []
                }
            self._store_geometry(apertures_dict, path_geo, '0', clear_geo=False)

        return close_subpath

    def _fill_stroke_path(self, path: dict, subpath: dict, current_subpath: str,
                          applied_size: float, start_point: Tuple, close_subpath: bool,
                          flag_clear_geo: bool, apertures_dict: dict, aperture: int) -> bool:
        """Handle 'B'/'B*' command - Fill and stroke the path.

        Args:
            path: Path dict with lines/bezier/rectangle lists
            subpath: Current subpath dict
            current_subpath: Current subpath type
            applied_size: The stroke/fill size (already scaled)
            start_point: Start point of subpath
            close_subpath: Whether subpath is already closed
            flag_clear_geo: Flag indicating clear geometry
            apertures_dict: Apertures dictionary to store geometry
            aperture: Current aperture number

        Returns:
            Updated close_subpath value
        """
        path_geo = []
        fill_geo = []

        if current_subpath == 'lines':
            if path['lines']:
                fill_geo = self._apply_polygon_buffer_to_subpaths(
                    path['lines'], 'lines', close_subpath
                )
                path_geo = self._apply_line_buffer_to_subpaths(path['lines'], applied_size, 'lines')
                path['lines'] = []
            else:
                geo = copy(subpath['lines'])
                if close_subpath is False:
                    geo.append(start_point)
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    fill_geo.append(geo_el)
                except ValueError:
                    pass
                path_geo = self._apply_line_buffer_to_subpaths([subpath['lines']], applied_size, 'lines')
                subpath['lines'] = []

        if current_subpath == 'bezier':
            geo = []
            if path['bezier']:
                fill_geo = self._apply_polygon_buffer_to_subpaths(
                    path['bezier'], 'bezier', close_subpath
                )
                path_geo = self._apply_line_buffer_to_subpaths(path['bezier'], applied_size, 'bezier')
                path['bezier'] = []
            else:
                for b in subpath['bezier']:
                    geo += self.bezier_to_points(start=b[0], c1=b[1], c2=b[2], stop=b[3])
                if close_subpath is False:
                    geo.append(start_point)
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    fill_geo.append(geo_el)
                except ValueError:
                    pass
                path_geo = self._apply_line_buffer_to_subpaths([subpath['bezier']], applied_size, 'bezier')
                subpath['bezier'] = []

        if current_subpath == 'rectangle':
            if path['rectangle']:
                fill_geo = self._apply_polygon_buffer_to_subpaths(
                    path['rectangle'], 'rectangle', close_subpath
                )
                path_geo = self._apply_line_buffer_to_subpaths(path['rectangle'], applied_size, 'rectangle')
                path['rectangle'] = []
            else:
                geo = copy(subpath['rectangle'])
                try:
                    geo_el = Polygon(geo).buffer(self.BUFFER_EPSILON, resolution=self.step_per_circles)
                    fill_geo.append(geo_el)
                except ValueError:
                    pass
                path_geo = self._apply_line_buffer_to_subpaths([subpath['rectangle']], applied_size, 'rectangle')
                subpath['rectangle'] = []

        close_subpath = True

        if apertures_dict:
            ap_to_use, aperture = self._find_or_create_aperture(
                apertures_dict, applied_size, aperture
            )
            self._store_geometry(apertures_dict, path_geo, ap_to_use, clear_geo=False)
        else:
            apertures_dict[str(aperture)] = {
                'size': round(applied_size, 5),
                'type': 'C',
                'geometry': []
            }
            self._store_geometry(apertures_dict, path_geo, str(aperture), clear_geo=False)

        if flag_clear_geo is True:
            if 0 not in apertures_dict:
                apertures_dict[0] = {
                    'size': round(applied_size, 5),
                    'type': 'C',
                    'geometry': []
                }
            self._store_geometry(apertures_dict, fill_geo, '0', clear_geo=True)

        else:
            if '0' not in apertures_dict:
                apertures_dict['0'] = {
                    'size': round(applied_size, 5),
                    'type': 'C',
                    'geometry': []
                }

            self._store_geometry(apertures_dict, fill_geo, '0', clear_geo=False)

        return close_subpath

    def _finalize_object_dict(self, object_dict: dict, apertures_dict: dict,
                               clear_apertures_dict: dict, layer_nr: int,
                               abort_flag: bool) -> dict:
        """Finalize the object dictionary by copying apertures and cleaning up empty layers.

        Args:
            object_dict: The object dictionary to finalize
            apertures_dict: Apertures dictionary to copy to object_dict
            clear_apertures_dict: Clear apertures dictionary
            layer_nr: Current layer number
            abort_flag: Abort flag from caller

        Returns:
            Finalized object_dict
        """
        if apertures_dict:
            object_dict[layer_nr] = deepcopy(apertures_dict)

        if clear_apertures_dict[0]['geometry']:
            object_dict[0] = deepcopy(clear_apertures_dict)

        empty_layers = [layer for layer in object_dict if not object_dict[layer]]
        for x in empty_layers:
            if x in object_dict:
                object_dict.pop(x)

        if abort_flag:
            raise grace

        return object_dict
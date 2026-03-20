
from PyQt6 import QtWidgets     # noqa

from dataclasses import dataclass, field

from copy import deepcopy
import numpy as np

import traceback
import logging

try:
    from numpy import Inf
except ImportError:
    from numpy import inf as Inf    # noqa

from shapely import (
    LineString,
    Polygon,
    MultiLineString,
    MultiPolygon,
    Point,
    LinearRing,
)
from shapely.geometry import base
from shapely.ops import unary_union, linemerge
from shapely.geometry.base import BaseGeometry

from typing import TYPE_CHECKING, Union

import gettext
import appTranslation as fcTranslate
import builtins

from camlib import (
    AppRTreeStorage,
    grace,
    flatten_shapely_geometry,
)

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

if TYPE_CHECKING:
    from appObjects.GerberObject import GerberObject
    from appObjects.GeometryObject import GeometryObject
    from appMain import App

log = logging.getLogger('base')


@dataclass
class Params:
    units: str
    tool_ordering: int
    paint_method: int
    rest_machining_choice: bool
    simplification_value: float
    prog_plot: bool
    tools_storage: field(default_factory=dict)
    output_object_name: str | None
    run_threaded: bool


class PaintGen:
    def __init__(self, tool):
        self.app = tool.app
        self.ui = tool.ui
        self.obj_name = tool.obj_name

        self.decimals = tool.decimals

        self.paint_obj = tool.paint_obj
        self.paint_tools = tool.paint_tools

        self.o_name = tool.o_name
        self.circle_steps = tool.circle_steps

        self.overlap = tool.overlap
        self.connect = tool.connect
        self.contour = tool.contour

        self.tooldia_list = tool.tooldia_list
        self.tool_type_item_options = tool.tool_type_item_options
        self.tooldia = tool.tooldia

        self.units = tool.units
        self.select_method = tool.select_method
        self.first_click = tool.first_click
        self.cursor_pos = tool.cursor_pos
        self.mouse_is_dragging = tool.mouse_is_dragging

        self.temp_shapes = tool.temp_shapes

        self.grid_status_memory = tool.grid_status_memory
        self.poly_sel_disconnect_flag = tool.poly_sel_disconnect_flag
        self.area_sel_disconnect_flag = tool.area_sel_disconnect_flag

        self.bound_obj_name = tool.bound_obj_name
        self.bound_obj = tool.bound_obj

        self.mr = tool.mr
        self.mm = tool.mm
        self.kp = tool.kp
        self.mp = tool.mp
        self.mr = tool.mr
        self.kp = tool.kp
        self.kp = tool.kp

        self.poly_drawn = tool.poly_drawn
        self.points = tool.points

        self.parent_tool = tool

    def on_paint_button_click(self):
        """
        Slot for clicking signal
        :return: None
        """

        self.app.defaults.report_usage("on_paint_button_click")

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False

        prog_plot = True if self.app.options.get("tools_paint_plotting") == 'progressive' else False
        if prog_plot:
            self.temp_shapes.clear(update=True)

        self.parent_tool.area_to_paint_list = []

        obj_type = self.ui.type_obj_radio.get_value()
        gerber_circle_steps = int(self.app.options.get("gerber_circle_steps"))
        geometry_circle_steps = int(self.app.options.get("geometry_circle_steps"))
        self.circle_steps = gerber_circle_steps if obj_type == 'gerber' else geometry_circle_steps
        self.obj_name = self.ui.obj_combo.currentText()

        # Get source object.
        try:
            self.paint_obj = self.app.collection.get_by_name(str(self.obj_name))
        except Exception as e:
            self.app.log.error("ToolPaint.on_paint_button_click() --> %s" % str(e))
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.obj_name))
            return

        if self.paint_obj is None:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Object not found"), self.paint_obj))
            return

        # test if the Geometry Object is multigeo with more than one tool and return Fail if True because
        # for now Paint don't work on MultiGeo with more than one tools
        if self.paint_obj.kind == 'geometry' and self.paint_obj.multigeo is True and len(self.paint_obj.tools) > 1:
            self.app.inform.emit('[ERROR_NOTCL] %s...' % _("Can't do Paint on MultiGeo geometries"))
            return 'Fail'

        self.o_name = '%s_mt_paint' % self.obj_name

        # use the selected tools in the tool table; get diameters
        self.tooldia_list = []
        table_items = self.ui.tools_table.selectedItems()
        sel_rows = {t.row() for t in table_items}
        if len(sel_rows) > 0:
            for row in sel_rows:
                try:
                    self.tooldia = float(self.ui.tools_table.item(row, 1).text())
                except ValueError:
                    # try to convert comma to decimal point. if it's still not working error message and return
                    try:
                        self.tooldia = float(self.ui.tools_table.item(row, 1).text().replace(',', '.'))
                    except ValueError:
                        self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                        continue
                self.tooldia_list.append(self.tooldia)
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("There are no tools selected in the Tool Table."))
            return

        self.select_method = self.ui.select_method_combo.get_value()
        if self.select_method == 0:  # _("All")
            self.paint_poly_all(self.paint_obj, tooldia=self.tooldia_list, outname=self.o_name)

        elif self.select_method == 1:   # _("Polygon Selection")
            self._paint_poly_single()

        elif self.select_method == 2:   # _("Area Selection")
            self._paint_poly_area()

        elif self.select_method == 3:   # _("Reference Object")
            self._paint_poly_reference()

    def paint_area_selection_option(self, areas_to_paint_list: list[Polygon | MultiPolygon]):
        self.app.log.info("PaintGen.paint_area_selection_option() --> Painting the designated areas(s).")

        areas_to_paint_list = unary_union(areas_to_paint_list)
        if isinstance(areas_to_paint_list, MultiPolygon):
            areas_to_paint_list = list(areas_to_paint_list.geoms)
        elif isinstance(areas_to_paint_list, Polygon):
            areas_to_paint_list = [areas_to_paint_list]

        self.paint_poly_area_worker(
            painted_object=self.paint_obj,
            tooldia=self.tooldia_list,
            areas_to_paint=areas_to_paint_list,
            outname=self.o_name
        )

    def paint_polygon_worker(
            self,
            poly_g,
            tool_diameter,
            paint_method,
            over,
            conn,
            cont,
            prog_plot,
            obj,
    ):

        p_poly: AppRTreeStorage | None = None

        if paint_method == 0:   # _("Standard")
            try:
                # Type(cp) == AppRTreeStorage | None
                p_poly = self.parent_tool.clear_polygon_shrink(
                    poly_g,
                    tooldia=tool_diameter,
                    steps_per_circle=self.circle_steps,
                    overlap=over,
                    contour=cont,
                    connect=conn,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Standard --> %s" % str(ee))
        elif paint_method == 1:  # _("Seed")
            try:
                # Type(cp) == AppRTreeStorage | None
                p_poly = self.parent_tool.clear_polygon_seed(
                    poly_g,
                    tooldia=tool_diameter,
                    steps_per_circle=self.circle_steps,
                    overlap=over,
                    contour=cont,
                    connect=conn,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Seed --> %s" % str(ee))
        elif paint_method == 2:  # _("Lines")
            try:
                # Type(cp) == AppRTreeStorage | None
                p_poly = self.parent_tool.clear_polygon_lines(
                    poly_g,
                    tooldia=tool_diameter,
                    steps_per_circle=self.circle_steps,
                    overlap=over,
                    contour=cont,
                    connect=conn,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Lines --> %s" % str(ee))
        elif paint_method == 3:  # _("Laser_lines")
            # line = None
            # aperture_size = None

            # the key is the aperture type and the val is a list of geo elements
            flash_el_dict = {}
            # the key is the aperture size, the val is a list of geo elements
            traces_el_dict = {}

            try:
                # find the flashes and the lines that are in the selected polygon and store them separately
                for apid, ap_val in obj.tools.items():
                    for geo_el in ap_val['geometry']:
                        if "size" in ap_val and ap_val["size"] == 0.0:
                            if ap_val["size"] in traces_el_dict:
                                traces_el_dict[ap_val["size"]].append(geo_el)
                            else:
                                traces_el_dict[ap_val["size"]] = [geo_el]

                        if 'follow' in geo_el and geo_el['follow'].within(poly_g):
                            if isinstance(geo_el['follow'], Point):
                                if ap_val["type"] == 'C':
                                    if 'C' in flash_el_dict:
                                        flash_el_dict['C'].append(geo_el)
                                    else:
                                        flash_el_dict['C'] = [geo_el]
                                elif ap_val["type"] == 'O':
                                    if 'O' in flash_el_dict:
                                        flash_el_dict['O'].append(geo_el)
                                    else:
                                        flash_el_dict['O'] = [geo_el]
                                elif ap_val["type"] == 'R':
                                    if 'R' in flash_el_dict:
                                        flash_el_dict['R'].append(geo_el)
                                    else:
                                        flash_el_dict['R'] = [geo_el]
                            else:
                                aperture_size = ap_val['size']

                                if aperture_size in traces_el_dict:
                                    traces_el_dict[aperture_size].append(geo_el)
                                else:
                                    traces_el_dict[aperture_size] = [geo_el]
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error(
                    "ToolPaint.paint_polygon_worker() Laser Lines -> Identify flashes/traces--> %s" % str(ee))

            p_poly = AppRTreeStorage()
            pads_lines_list = []

            # process the flashes found in the selected polygon with the 'lines' method for rectangular
            # flashes and with _("Seed") for oblong and circular flashes
            # and pads (flashes) need the contour therefore I override the GUI settings with always True
            try:
                for ap_type in flash_el_dict:
                    for elem in flash_el_dict[ap_type]:
                        if 'solid' in elem:
                            if ap_type == 'C':
                                f_o = self.parent_tool.clear_polygon_seed(
                                    elem['solid'],
                                    tooldia=tool_diameter,
                                    steps_per_circle=self.circle_steps,
                                    overlap=over,
                                    contour=True,
                                    connect=conn,
                                    prog_plot=prog_plot)
                                pads_lines_list += [p for p in f_o.get_objects() if p]
                            # this is the same as above but I keep it in case I will modify something in the future
                            elif ap_type == 'O':
                                f_o = self.parent_tool.clear_polygon_seed(
                                    elem['solid'],
                                    tooldia=tool_diameter,
                                    steps_per_circle=self.app.options.get("geometry_circle_steps", 64),
                                    overlap=over,
                                    contour=True,
                                    connect=conn,
                                    prog_plot=prog_plot,
                                )
                                pads_lines_list += [p for p in f_o.get_objects() if p]

                            elif ap_type == 'R':
                                f_o = self.parent_tool.clear_polygon_lines(
                                    elem['solid'],
                                    tooldia=tool_diameter,
                                    steps_per_circle=self.app.options.get("geometry_circle_steps", 64),
                                    overlap=over,
                                    contour=True,
                                    connect=conn,
                                    prog_plot=prog_plot,
                                )

                                pads_lines_list += [p for p in f_o.get_objects() if p]
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Laser Lines -> Process flashes--> %s" % str(ee))

            # add the lines from pads to the storage
            try:
                for lin in pads_lines_list:
                    if lin:
                        p_poly.insert(lin)
            except TypeError:
                p_poly.insert(pads_lines_list)

            copper_lines_list = []
            # process the traces found in the selected polygon using the 'laser_lines' method,
            # method which will follow the 'follow' line therefore use the longer path possible for the
            # laser, therefore the acceleration will play a smaller factor
            try:
                for aperture_size in traces_el_dict:
                    for elem in traces_el_dict[aperture_size]:
                        line = elem['follow']

                        if line and isinstance(line, (LineString, MultiLineString)):
                            t_o = self.parent_tool.fill_with_lines(
                                line,
                                aperture_size,
                                tooldia=tool_diameter,
                                steps_per_circle=self.app.options.get("geometry_circle_steps", 64),
                                overlap=over,
                                contour=cont,
                                connect=conn,
                                prog_plot=prog_plot,
                            )

                            copper_lines_list += [p for p in t_o.get_objects() if p]
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Laser Lines -> Process traces--> %s" % str(ee))

            # add the lines from copper features to storage but first try to make as few lines as possible
            # by trying to fuse them
            lines_union = linemerge(unary_union(copper_lines_list))     # noqa
            lines_geoms = lines_union.geoms if isinstance(lines_union, MultiLineString) else [lines_union]
            try:
                for lin in lines_geoms:
                    if lin:
                        p_poly.insert(lin)
            except TypeError:
                p_poly.insert(lines_geoms)

        elif paint_method == 4:  # _("Combo")
            try:
                self.app.inform.emit(_("Painting polygon with method: lines."))
                p_poly = self.parent_tool.clear_polygon_lines(
                    poly_g,
                    tooldia=tool_diameter,
                    steps_per_circle=self.circle_steps,
                    overlap=over,
                    contour=cont,
                    connect=conn,
                    prog_plot=prog_plot,
                )

                if p_poly and p_poly.objects:
                    pass
                else:
                    self.app.inform.emit(_("Failed. Painting polygon with method: seed."))
                    p_poly = self.parent_tool.clear_polygon_seed(
                        poly_g,
                        tooldia=tool_diameter,
                        steps_per_circle=self.circle_steps,
                        overlap=over,
                        contour=cont,
                        connect=conn,
                        prog_plot=prog_plot,
                    )
                    if p_poly and p_poly.objects:
                        pass
                    else:
                        self.app.inform.emit(_("Failed. Painting polygon with method: standard."))
                        p_poly = self.parent_tool.clear_polygon_shrink(
                            poly_g,
                            tooldia=tool_diameter,
                            steps_per_circle=self.circle_steps,
                            overlap=over,
                            contour=cont,
                            connect=conn,
                            prog_plot=prog_plot,
                        )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_polygon_worker() Combo --> %s" % str(ee))

        if p_poly and p_poly.objects:
            return p_poly
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _('Geometry could not be painted completely'))
            return None

    def paint_handler(
            self,
            painted_object: Union["GeometryObject", "GerberObject"],
            geometry,
            tooldia=None,
            order=None,
            method=None,
            outname=None,
            tools_storage=None,
            plot=True,
            rest=None,
            run_threaded=True,
    ):
        """
        Paints a given geometry.

        :param painted_object:             painted object
        :param geometry:        geometry to Paint
        :param tooldia:         Diameter of the painting tool
        :param order:           if the tools are ordered and how
        :param outname:         Name of the resulting Geometry Object.
        :param method:          choice out of _("Seed"), 'normal', 'lines'
        :param tools_storage:   whether to use the current tools_storage self.paints_tools or a different one.
                                Usage of the different one is related to when this function is called
                                from a TcL command.
        :param plot:            if the geometry is plotted; bool
        :param rest:            if rest machining apply here; bool
        :param run_threaded:
        :return: None
        """

        if run_threaded:
            proc = self.app.proc_container.new('%s...' % _("Working"))
        else:
            self.app.proc_container.view.set_busy('%s...' % _("Working"))
            QtWidgets.QApplication.processEvents()

        params = self._create_params(
            order=order,
            method=method,
            rest=rest,
            outname=outname,
            tools_storage=tools_storage,
            run_threaded=run_threaded
        )

        sorted_paint_tools = self._parse_tool_diameters(tooldia)
        if sorted_paint_tools == 'fail':
            return 'fail'

        def job_thread(app_instance, proc):
            ret = None
            try:
                if params.rest_machining_choice:
                    ret = app_instance.app_obj.new_object(
                        "geometry",
                        params.output_object_name,
                        lambda o, a: self._generate_rest_paint_worker(
                            o,
                            a,
                            params,
                            sorted_paint_tools,
                            geometry,
                            painted_object,
                            plot,
                        ),
                        plot=plot,
                        autoselected=False,
                    )
                else:
                    ret = app_instance.app_obj.new_object(
                        "geometry",
                        params.output_object_name,
                        lambda o, a: self._generate_paint_worker(
                            o, a, params, sorted_paint_tools, geometry, painted_object, plot),
                        plot=plot,
                        autoselected=False,
                    )
            except grace:
                app_instance.log.debug("PaintGen.paint_handler.job_thread() -> Graceful exit.")
            except Exception as err:
                app_instance.log.debug(f"PaintGen.paint_handler.job_thread() -> Exception: {str(err)}")
                traceback.print_stack()
                ret = 'fail'
            finally:
                proc.done()

            if ret == 'fail':
                self.app.inform.emit('[ERROR] %s' % _("Failed."))
                return

            self.app.inform.emit('[success] %s' % _("Done."))

        if run_threaded:
            self.app.collection.promise(params.output_object_name)
            self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app, proc]})
        else:
            job_thread(app_instance=self.app, proc=proc)

    def _create_params(self, order, method, rest, outname, tools_storage, run_threaded):
        return Params(
            units=self.app.units,
            tool_ordering=order if order is not None else self.ui.order_combo.get_value(),
            paint_method=method if method is not None else self.ui.method_combo.get_value(),
            rest_machining_choice=rest if rest is not None else self.ui.rest_cb.get_value(),
            simplification_value=0.01,
            prog_plot=self.app.options.get("tools_paint_plotting") == 'progressive',
            tools_storage=self.paint_tools if tools_storage is None else tools_storage,
            output_object_name=outname if outname is not None else self.obj_name + "_paint",
            run_threaded=run_threaded
        )

    def _parse_tool_diameters(self, tooldia):
        sorted_paint_tools = []
        if tooldia is not None:
            try:
                sorted_paint_tools = [float(eval(dia)) for dia in tooldia.split(",") if dia != '']
            except AttributeError:
                if not isinstance(tooldia, list):
                    sorted_paint_tools = [float(tooldia)]
                else:
                    sorted_paint_tools = tooldia
        else:
            table_items = self.ui.tools_table.selectedItems()
            sel_rows = {t.row() for t in table_items}
            for row in sel_rows:
                try:
                    self.tooldia = float(self.ui.tools_table.item(row, 1).text())
                except ValueError:
                    try:
                        self.tooldia = float(self.ui.tools_table.item(row, 1).text().replace(',', '.'))
                    except ValueError:
                        self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                        continue
                sorted_paint_tools.append(self.tooldia)
            if not sorted_paint_tools:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("There are no tools selected in the Tool Table."))
                return 'fail'
        return sorted_paint_tools

    def _find_tool_uid(self, tool_dia, tools_storage):
        for k, v in tools_storage.items():
            if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool_dia)):
                return int(k)
        return None

    def _get_tool_params(self, tool_uid, tools_storage):
        return {
            'over': float(tools_storage[tool_uid]['data']['tools_paint_overlap']) / 100.0,
            'conn': tools_storage[tool_uid]['data']['tools_paint_connect'],
            'cont': tools_storage[tool_uid]['data']['tools_paint_contour'],
            'offset': float(tools_storage[tool_uid]['data']['tools_paint_offset'])
        }

    def _buffer_geometry(self, geometry, offset):
        poly_buf = []
        for pol in flatten_shapely_geometry(geometry):
            buffered_pol = pol.buffer(-offset)
            if buffered_pol and not buffered_pol.is_empty:
                poly_buf.append(buffered_pol)
        return poly_buf

    def _process_polygon(self, polygon, tool_dia, tool_params, params, painted_object):
        return self.paint_polygon_worker(
            polygon,
            tool_diameter=tool_dia,
            over=tool_params['over'],
            conn=tool_params['conn'],
            cont=tool_params['cont'],
            paint_method=params.paint_method,
            obj=painted_object,
            prog_plot=params.prog_plot,
        )

    def _simplify_geometry(self, geometry_list, simplification_value):
        if simplification_value > 0.0:
            return [x.simplify(simplification_value) for x in geometry_list]
        return list(geometry_list)

    def _update_progress(self, current, total, old_disp_number):
        disp_number = int(np.interp(current, [0, total], [0, 100]))
        if old_disp_number < disp_number <= 100:
            self.app.proc_container.update_view_text(' %d%%' % disp_number)
            return disp_number
        return old_disp_number

    def _cleanup_progressive_plotting(self):
        if self.app.options["tools_paint_plotting"] == 'progressive':
            self.temp_shapes.clear(update=True)

    def _remove_empty_tools(self, tools_storage):
        for uid in list(tools_storage.keys()):
            if not tools_storage[uid]['solid_geometry']:
                tools_storage.pop(uid, None)

    def _set_output_bounds(self, output_obj, solid_geometry):
        try:
            a, b, c, d = unary_union(solid_geometry).bounds
            output_obj.obj_options['xmin'] = a
            output_obj.obj_options['ymin'] = b
            output_obj.obj_options['xmax'] = c
            output_obj.obj_options['ymax'] = d
        except Exception as ee:
            self.app.log.error("ToolPaint.paint_poly.job_init() bounds error --> %s" % str(ee))
            return False
        return True

    def _validate_output_geometry(self, output_obj):
        has_solid_geo = sum(1 for uid in output_obj.tools if output_obj.tools[uid]['solid_geometry'])
        if has_solid_geo == 0:
            self.app.log.error(
                "There is no Painting Geometry in the file.\n"
                "Usually it means that the tool diameter is too big for the painted geometry.\n"
                "Change the painting parameters and try again."
            )
            return False
        return True

    def _generate_paint_worker(self, output_geo_object, app_obj, params, sorted_paint_tools, geometry, painted_object, plot):
        tool_dia = None
        current_uid = None
        final_solid_geometry = []
        old_disp_number = 0

        if params.tool_ordering == 1:
            sorted_paint_tools.sort(reverse=False)
        elif params.tool_ordering == 2:
            sorted_paint_tools.sort(reverse=True)

        for tool_dia in sorted_paint_tools:
            self.app.log.debug("Starting geometry processing for tool: %s" % str(tool_dia))
            msg = '[success] %s %s%s %s' % (_('Painting with tool diameter = '),
                                            str(tool_dia),
                                            self.units.lower(),
                                            _('started'))
            self.app.inform.emit(msg)
            self.app.proc_container.update_view_text(' %d%%' % 0)

            current_uid = self._find_tool_uid(tool_dia, params.tools_storage)
            if not current_uid:
                return "fail"

            tool_params = self._get_tool_params(current_uid, params.tools_storage)

            poly_buf = self._buffer_geometry(geometry, tool_params['offset'])
            if not poly_buf:
                self.app.inform.emit(
                    '[ERROR_NOTCL] %s' % _("There is no geometry to process or the tool diameter is too big."))
                continue

            geo_len = len(poly_buf)
            self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

            pol_nr = 0
            cp_list = []

            try:
                for pp in poly_buf:
                    QtWidgets.QApplication.processEvents()
                    if self.app.abort_flag:
                        raise grace

                    geo_res = self._process_polygon(pp, tool_dia, tool_params, params, painted_object)
                    if geo_res:
                        cp_list.append(geo_res)

                    pol_nr += 1
                    old_disp_number = self._update_progress(pol_nr, geo_len, old_disp_number)

                total_geometry = []
                if cp_list:
                    for cp in cp_list:
                        total_geometry += self._simplify_geometry(cp.get_objects(), params.simplification_value)
                    total_geometry = [g for g in total_geometry if g and not g.is_empty]
            except grace:
                return "fail"
            except Exception as e:
                self.app.log.error(
                    f'"Could not do Paint. Try a different combination of parameters. '
                    f'Or a different method of Paint" {str(e)}'
                )
                self.app.inform.emit(_("Failed."))
                continue

            params.tools_storage[current_uid]['solid_geometry'] = deepcopy(total_geometry)
            params.tools_storage[current_uid]['data']['output_object_name'] = params.output_object_name
            final_solid_geometry += total_geometry

        self._cleanup_progressive_plotting()
        self._remove_empty_tools(params.tools_storage)

        if not params.tools_storage:
            return 'fail'

        output_geo_object.obj_options["tools_mill_tooldia"] = str(tool_dia)
        output_geo_object.multigeo = True
        output_geo_object.multitool = True
        output_geo_object.tools.clear()
        output_geo_object.tools = dict(params.tools_storage)
        output_geo_object.solid_geometry = flatten_shapely_geometry(unary_union(final_solid_geometry))

        if not self._set_output_bounds(output_geo_object, output_geo_object.solid_geometry):
            return

        if not self._validate_output_geometry(output_geo_object):
            app_obj.inform.emit(_("Failed."))
            return "fail"

    def _generate_rest_paint_worker(self, output_geo_object, app_obj, params, sorted_paint_tools, geometry, painted_object, plot):
        current_uid = None
        final_solid_geometry = []
        old_disp_number = 0

        sorted_paint_tools.sort(reverse=True)
        paint_offset = self.ui.rest_offset_entry.get_value()

        poly_buf = []
        for pol in geometry:
            buffered_pol = pol.buffer(-paint_offset)
            if buffered_pol and not buffered_pol.is_empty:
                try:
                    for x in buffered_pol:
                        poly_buf.append(x)
                except TypeError:
                    poly_buf.append(buffered_pol)

        poly_buf = unary_union(poly_buf)
        poly_buf = flatten_shapely_geometry(poly_buf)

        if not poly_buf:
            self.app.inform.emit(
                '[ERROR_NOTCL] %s' % _("There is no geometry to process or the tool diameter is too big."))
            return 'fail'

        geo_len = len(poly_buf)
        self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

        for tool_dia in sorted_paint_tools:
            self.app.log.debug("Starting geometry processing for tool: %s" % str(tool_dia))
            msg = '[success] %s %s%s %s' % (_('Painting with tool diameter = '),
                                            str(tool_dia),
                                            self.units.lower(),
                                            _('started'))
            self.app.inform.emit(msg)
            self.app.proc_container.update_view_text(' %d%%' % 0)

            current_uid = self._find_tool_uid(tool_dia, params.tools_storage)
            if not current_uid:
                return "fail"

            tool_params = self._get_tool_params(current_uid, params.tools_storage)
            rest_list = []
            cleared_geo = []
            pol_nr = 0

            try:
                for pp in poly_buf:
                    QtWidgets.QApplication.processEvents()
                    if self.app.abort_flag:
                        raise grace

                    check_dist = -tool_dia / 2.0
                    check_buff = pp.buffer(check_dist)
                    if not check_buff or check_buff.is_empty:
                        continue

                    geo_res = self._process_polygon(pp, tool_dia, tool_params, params, painted_object)
                    geo_elems = self._simplify_geometry(geo_res.get_objects(), params.simplification_value)

                    pp_cleared = unary_union(geo_elems).buffer(tool_dia / 2.0)
                    rest_geo = pp.difference(pp_cleared)
                    if rest_geo:
                        rest_geo = flatten_shapely_geometry(rest_geo)
                        for r in rest_geo:
                            if r.is_valid and not r.is_empty:
                                rest_list.append(r)

                    if geo_res:
                        cleared_geo += geo_elems

                    pol_nr += 1
                    old_disp_number = self._update_progress(pol_nr, geo_len, old_disp_number)
            except grace:
                return "fail"
            except Exception as e:
                self.app.log.error("Could not Paint the polygons. %s" % str(e))
                msg = '[ERROR] %s\n%s' % (_("Could not do Paint. Try a different combination of parameters. "
                                            "Or a different method of Paint"), str(e))
                self.app.inform.emit(msg)
                continue

            if cleared_geo:
                final_solid_geometry += cleared_geo
                params.tools_storage[current_uid]['solid_geometry'] = deepcopy(cleared_geo)
                params.tools_storage[current_uid]['data']['output_object_name'] = params.output_object_name
                output_geo_object.tools[current_uid] = dict(params.tools_storage[current_uid])
            else:
                self.app.log.debug("There are no geometries in the cleared polygon.")

            self.app.log.debug("Generating rest geometry for the next tool.")

            buffered_cleared = unary_union(cleared_geo)
            buffered_cleared = buffered_cleared.buffer(tool_dia / 2.0)
            poly_buf = MultiPolygon(poly_buf).difference(buffered_cleared)
            poly_buf = flatten_shapely_geometry(poly_buf)

            tmp = [p for p in poly_buf if p.is_valid]
            tmp += rest_list

            print(tmp)
            poly_buf = MultiPolygon(tmp)
            if not poly_buf.is_valid:
                poly_buf = unary_union(tmp)
            if not poly_buf or poly_buf.is_empty or not poly_buf.is_valid:
                app_obj.log.debug("Rest geometry empty. Breaking.")
                break
            poly_buf = flatten_shapely_geometry(poly_buf)

        output_geo_object.multigeo = True
        output_geo_object.obj_options["tools_mill_tooldia"] = '0.0'

        self._cleanup_progressive_plotting()
        self._remove_empty_tools(params.tools_storage)

        if not params.tools_storage:
            return 'fail'

        output_geo_object.multitool = True

        if not output_geo_object.tools:
            return "fail"

        if not self._validate_output_geometry(output_geo_object):
            app_obj.inform.emit(
                '[ERROR] %s' %
                _("There is no Painting Geometry in the file.\n"
                  "Usually it means that the tool diameter is too big for the painted geometry.\n"
                  "Change the painting parameters and try again.")
            )
            return "fail"

        output_geo_object.solid_geometry = flatten_shapely_geometry(unary_union(final_solid_geometry))

        if not self._set_output_bounds(output_geo_object, output_geo_object.solid_geometry):
            return

    def paint_poly(
            self,
            obj: Union["GeometryObject", "GerberObject"],
            inside_pt=None,
            poly_list=None,
            tooldia=None,
            order=None,
            method=None,
            outname=None,
            tools_storage=None,
            plot=True,
            run_threaded=True,
    ):
        """
        Paints a polygon selected by clicking on its interior or by having a point coordinates given

        Note:
            * The margin is taken directly from the form.

        :param run_threaded:
        :param plot:
        :param poly_list:
        :param obj:             painted object
        :param inside_pt:       [x, y]
        :param tooldia:         Diameter of the painting tool
        :param order:           if the tools are ordered and how
        :param outname:         Name of the resulting Geometry Object.
        :param method:          choice out of _("Seed"), 'normal', 'lines'
        :param tools_storage:   whether to use the current tools_storage self.paints_tools or a different one.
                                Usage of the different one is related to when this function is called
                                from a TcL command.
        :return: None
        """

        if obj.kind == 'gerber':
            # I don't do anything here, like buffering when the Gerber is loaded without buffering????!!!!
            if self.app.options["gerber_buffering"] == 'no':
                msg = '%s %s %s' % (_("Paint Plugin."),
                                    _("Normal painting polygon task started."),
                                    _("Buffering geometry..."))
                self.app.inform.emit(msg)
            else:
                self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Normal painting polygon task started.")))

            if self.app.options["tools_paint_plotting"] == 'progressive':
                if isinstance(obj.solid_geometry, list):
                    obj.solid_geometry = MultiPolygon(obj.solid_geometry).buffer(0)
                else:
                    obj.solid_geometry = obj.solid_geometry.buffer(0)
        else:
            self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Normal painting polygon task started.")))

        if inside_pt and poly_list is None:
            polygon_list = self.parent_tool.find_polygon(point=inside_pt, geoset=obj.solid_geometry)
            if polygon_list:
                polygon_list = [polygon_list]
        elif (inside_pt is None and poly_list) or (inside_pt and poly_list):
            polygon_list = poly_list
        else:
            return

        # No polygon?
        if polygon_list is None:
            self.app.log.warning('No polygon found.')
            self.app.inform.emit('[WARNING] %s' % _('No polygon found.'))
            return "fail"

        self.paint_handler(
            obj,
            polygon_list,
            tooldia=tooldia,
            order=order,
            method=method,
            outname=outname,
            tools_storage=tools_storage,
            plot=plot,
            run_threaded=run_threaded,
        )

    def paint_poly_all(
            self,
            obj: Union["GeometryObject", "GerberObject"],
            tooldia=None,
            order=None,
            method=None,
            outname=None,
            tools_storage=None,
            plot=True,
            run_threaded=True,
    ):
        """
        Paints all polygons in this object.

        :param obj:             painted object
        :param tooldia:         a tuple or single element made out of diameters of the tools to be used
        :param order:           if the tools are ordered and how
        :param outname:         name of the resulting object
        :param method:          choice out of _("Seed"), 'normal', 'lines'
        :param tools_storage:   whether to use the current tools_storage self.paints_tools or a different one.
                                Usage of the different one is related to when this function is called from
                                a TcL command.
        :param run_threaded:
        :param plot:
        :return:
        """

        def recurse(geometry, reset=True):
            """
            Creates a list of non-iterable linear geometry objects.
            Results are placed in self.flat_geometry

            :param geometry: Shapely type, list or list of lists of such.
            :param reset: Clears the contents of self.flat_geometry.
            """
            if self.app.abort_flag:
                # graceful abort requested by the user
                raise grace

            if geometry is None:
                return

            if reset:
                self.flat_geometry = []

            # ## If iterable, expand recursively.
            try:
                for geo in geometry:
                    if geo and not geo.is_empty:
                        recurse(geometry=geo, reset=False)
            # ## Not iterable, do the actual indexing and add.
            except TypeError:
                if isinstance(geometry, LinearRing):
                    g = Polygon(geometry)
                    self.flat_geometry.append(g)
                else:
                    self.flat_geometry.append(geometry)

            return self.flat_geometry

        if obj.kind == 'gerber':
            # I don't do anything here, like buffering when the Gerber is loaded without buffering????!!!!
            if self.app.options["gerber_buffering"] == 'no':
                msg = '%s %s %s' % (_("Paint Plugin."), _("Paint all polygons task started."),
                                    _("Buffering geometry..."))
                self.app.inform.emit(msg)
            else:
                self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Paint all polygons task started.")))

            if self.app.options["tools_paint_plotting"] == 'progressive':
                if isinstance(obj.solid_geometry, list):
                    obj.solid_geometry = MultiPolygon(obj.solid_geometry).buffer(0)
                else:
                    obj.solid_geometry = obj.solid_geometry.buffer(0)
        else:
            self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Paint all polygons task started.")))

        painted_area = recurse(obj.solid_geometry)

        # No polygon?
        if not painted_area:
            self.app.log.warning('No polygon found.')
            self.app.inform.emit('[WARNING] %s' % _('No polygon found.'))
            return

        self.paint_handler(
            obj,
            painted_area,
            tooldia=tooldia,
            order=order,
            method=method,
            outname=outname,
            tools_storage=tools_storage,
            plot=plot,
            run_threaded=run_threaded,
        )

    def _paint_poly_single(self):
        # disengage the grid snapping since it may be hard to click on polygons with grid snapping on
        if self.app.ui.grid_snap_btn.isChecked():
            self.grid_status_memory = True
            self.app.ui.grid_snap_btn.trigger()
        else:
            self.grid_status_memory = False

        self.app.inform.emit('[WARNING_NOTCL] %s' % _("Click on a polygon to paint it."))

        self.mr = self.app.plotcanvas.graph_event_connect(
            'mouse_release',
            self.parent_tool.on_single_poly_mouse_release,
        )
        self.kp = self.app.plotcanvas.graph_event_connect(
            'key_press',
            self.parent_tool.on_key_press,
        )

        if self.app.use_3d_engine:
            self.app.plotcanvas.graph_event_disconnect(
                'mouse_release',
                self.app.on_mouse_click_release_over_plot,
            )
            self.app.plotcanvas.graph_event_disconnect(
                'mouse_press',
                self.app.on_mouse_click_over_plot,
            )
        else:
            self.app.plotcanvas.graph_event_disconnect(self.app.mr)
            self.app.plotcanvas.graph_event_disconnect(self.app.mp)

        # disconnect flags
        self.poly_sel_disconnect_flag = True

    def _paint_poly_area(self):
        self.app.inform.emit('[WARNING_NOTCL] %s' % _("Click the start point of the area."))

        if self.app.use_3d_engine:
            self.app.plotcanvas.graph_event_disconnect(
                'mouse_press',
                self.app.on_mouse_click_over_plot,
            )
            self.app.plotcanvas.graph_event_disconnect(
                'mouse_move',
                self.app.on_mouse_move_over_plot,
            )
            self.app.plotcanvas.graph_event_disconnect(
                'mouse_release',
                self.app.on_mouse_click_release_over_plot,
            )
        else:
            self.app.plotcanvas.graph_event_disconnect(self.app.mp)
            self.app.plotcanvas.graph_event_disconnect(self.app.mm)
            self.app.plotcanvas.graph_event_disconnect(self.app.mr)

        self.mr = self.app.plotcanvas.graph_event_connect(
            'mouse_release',
            self.parent_tool.on_mouse_release,
        )
        self.mm = self.app.plotcanvas.graph_event_connect(
            'mouse_move',
            self.parent_tool.on_mouse_move,
        )
        self.kp = self.app.plotcanvas.graph_event_connect(
            'key_press',
            self.parent_tool.on_key_press,
        )

        # disconnect flags
        self.area_sel_disconnect_flag = True
        # disable the "notebook" until the process is finished
        self.app.ui.notebook.setDisabled(True)

    def _paint_poly_reference(self):
        self.bound_obj_name = self.ui.reference_combo.currentText()
        # Get source object.
        try:
            self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
        except Exception:
            self.app.inform.emit(
                '[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.obj_name)
            )
            return "Could not retrieve object: %s" % self.obj_name

        self.paint_poly_ref(
            obj=self.paint_obj,
            sel_obj=self.bound_obj,
            tooldia=self.tooldia_list,
            outname=self.o_name,
        )

    def paint_poly_ref(
            self,
            obj,
            sel_obj,
            tooldia=None,
            order=None,
            method=None,
            outname=None,
            tools_storage=None,
            plot=True,
            run_threaded=True,
    ):
        """
        Paints all polygons in this object that are within the areas_to_paint object

        :param obj: painted object
        :param sel_obj: paint only what is inside this object bounds
        :param tooldia: a tuple or single element made out of diameters of the tools to be used
        :param order: if the tools are ordered and how
        :param outname: name of the resulting object
        :param method: choice out of _("Seed"), 'normal', 'lines'
        :param tools_storage: whether to use the current tools_storage self.paints_tools or a different one.
        Usage of the different one is related to when this function is called from a TcL command.
        :param run_threaded:
        :param plot:
        :return:
        """
        geo = sel_obj.solid_geometry
        try:
            if isinstance(geo, MultiPolygon):
                env_obj = geo.convex_hull
            elif (isinstance(geo, MultiPolygon) and len(geo.geoms) == 1) or \
                    (isinstance(geo, list) and len(geo) == 1) and isinstance(geo[0], Polygon):
                env_obj = unary_union(self.bound_obj.solid_geometry)
            else:
                env_obj = unary_union(self.bound_obj.solid_geometry)
                env_obj = env_obj.convex_hull
            sel_rect = env_obj.buffer(distance=0.0000001, join_style=base.JOIN_STYLE.mitre)
        except Exception as e:
            self.app.log.error("ToolPaint.paint_poly_ref() --> %s" % str(e))
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
            return

        self.paint_poly_area_worker(
            painted_object=obj,
            areas_to_paint=sel_rect,
            tooldia=tooldia,
            order=order,
            method=method,
            outname=outname,
            tools_storage=tools_storage,
            plot=plot,
            run_threaded=run_threaded,
        )

    def paint_poly_area_worker(
            self,
            painted_object: Union["GeometryObject", "GerberObject"],
            areas_to_paint: Union[Polygon, MultiPolygon] | list[Polygon | MultiPolygon],
            tooldia=None,
            order=None,
            method=None,
            outname=None,
            tools_storage=None,
            plot=True,
            run_threaded=True,
    ):
        """
        Paints all polygons in this object that are within the sel_obj object

        :param painted_object: painted object
        :param areas_to_paint: paint only what is inside this object bounds
        :param tooldia: a tuple or single element made out of diameters of the tools to be used
        :param order: if the tools are ordered and how
        :param outname: name of the resulting object
        :param method: choice out of _("Seed"), 'normal', 'lines'
        :param tools_storage: whether to use the current tools_storage self.paints_tools or a different one.
        Usage of the different one is related to when this function is called from a TcL command.
        :param run_threaded:
        :param plot:
        :return:
        """

        def recurse(geometry: BaseGeometry, reset=True):
            """
            Creates a list of non-iterable linear geometry objects.
            Results are placed in self.flat_geometry

            :param geometry: Shapely type, list or list of lists of such.
            :param reset: Clears the contents of self.flat_geometry.
            """
            if self.app.abort_flag:
                # graceful abort requested by the user
                raise grace

            if geometry is None:
                return

            if reset:
                self.flat_geometry = []

            # ## If iterable, expand recursively.
            try:
                multigeo = geometry.geoms if isinstance(geometry, (MultiPolygon, MultiLineString)) else geometry
                for geo in multigeo:
                    if geo and not geo.is_empty:
                        recurse(geometry=geo, reset=False)
            # ## Not iterable, do the actual indexing and add.
            except TypeError:
                if isinstance(geometry, LinearRing):
                    g = Polygon(geometry)
                    self.flat_geometry.append(g)
                else:
                    self.flat_geometry.append(geometry)

            return self.flat_geometry

        # this is where heavy lifting is done and creating the geometry to be painted
        target_geo = unary_union(painted_object.solid_geometry)

        p_msg = f'{_("Paint Plugin.")} {_("Painting area task started.")}'
        if painted_object.kind == 'gerber':
            # I don't do anything here, like buffering when the Gerber is loaded without buffering????!!!!
            if self.app.options["gerber_buffering"] == 'no':
                msg = '%s %s %s' % (_("Paint Plugin."),
                                    _("Painting area task started."),
                                    _("Buffering geometry..."))
                self.app.inform.emit(msg)
            else:
                self.app.inform.emit(p_msg)

            if painted_object.kind == 'gerber':
                if self.app.options.get("tools_paint_plotting") == 'progressive':
                    target_geo = target_geo.buffer(0)
        else:
            self.app.inform.emit(p_msg)

        if isinstance(areas_to_paint, list):
            areas_to_paint = unary_union(areas_to_paint)
        geo_to_paint = target_geo.intersection(areas_to_paint)
        painted_area = recurse(geo_to_paint, reset=True)
        try:
            painted_area = linemerge(painted_area)
        except Exception:
            pass

        if isinstance(painted_area, (MultiPolygon, MultiLineString)):
            painted_area = painted_area.geoms

        p_geo_list = []
        try:
            for paint_g_elem in painted_area:
                if isinstance(paint_g_elem, Polygon):
                    p_geo_list.append(paint_g_elem)
                elif isinstance(paint_g_elem, (LinearRing, LineString)):
                    if paint_g_elem.is_closed:
                        p_geo_list.append(Polygon(paint_g_elem.coords))
                    else:
                        coords = list(paint_g_elem.coords)
                        coords.append(coords[0])
                        p_geo_list.append(Polygon(coords))
        except TypeError:
            if isinstance(painted_area, Polygon):
                p_geo_list.append(painted_area)
            elif isinstance(painted_area, (LinearRing, LineString)):
                if painted_area.is_closed:
                    p_geo_list.append(Polygon(painted_area.coords))
                else:
                    coords = list(painted_area.coords)
                    coords.append(coords[0])
                    p_geo_list.append(Polygon(coords))

        # No polygon?
        if not p_geo_list:
            self.app.log.warning('ToolPaint.paint_poly_Area(). No geometry or the found geometry could not be painted.')
            self.app.inform.emit('[WARNING] %s' % _('No polygon found.'))
            return

        self.paint_handler(
            painted_object,
            p_geo_list,
            tooldia=tooldia,
            order=order,
            method=method,
            outname=outname,
            tools_storage=tools_storage,
            plot=plot,
            run_threaded=run_threaded,
        )

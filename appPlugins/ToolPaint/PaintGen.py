
from PyQt6 import QtWidgets     # noqa

import logging
from copy import deepcopy
import numpy as np
import traceback

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

log = logging.getLogger('base')


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
        self.sel_rect = tool.sel_rect
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

        self.sel_rect = []

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

        self.select_method = self.ui.selectmethod_combo.get_value()
        if self.select_method == 0:  # _("All")
            self.paint_poly_all(self.paint_obj, tooldia=self.tooldia_list, outname=self.o_name)

        elif self.select_method == 1:   # _("Polygon Selection")
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

        elif self.select_method == 2:   # _("Area Selection")
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

        elif self.select_method == 3:   # _("Reference Object")
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

    def paint_polygon_worker(self, polyg, tooldiameter, paint_method, over, conn, cont, prog_plot, obj):

        cpoly = None

        if paint_method == 0:   # _("Standard")
            try:
                # Type(cp) == AppRTreeStorage | None
                cpoly = self.parent_tool.clear_polygon_shrink(
                    polyg,
                    tooldia=tooldiameter,
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
                cpoly = self.parent_tool.clear_polygon_seed(
                    polyg,
                    tooldia=tooldiameter,
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
                cpoly = self.parent_tool.clear_polygon_lines(
                    polyg,
                    tooldia=tooldiameter,
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
                for apid, apval in obj.tools.items():
                    for geo_el in apval['geometry']:
                        if "size" in apval and apval["size"] == 0.0:
                            if apval["size"] in traces_el_dict:
                                traces_el_dict[apval["size"]].append(geo_el)
                            else:
                                traces_el_dict[apval["size"]] = [geo_el]

                        if 'follow' in geo_el and geo_el['follow'].within(polyg):
                            if isinstance(geo_el['follow'], Point):
                                if apval["type"] == 'C':
                                    if 'C' in flash_el_dict:
                                        flash_el_dict['C'].append(geo_el)
                                    else:
                                        flash_el_dict['C'] = [geo_el]
                                elif apval["type"] == 'O':
                                    if 'O' in flash_el_dict:
                                        flash_el_dict['O'].append(geo_el)
                                    else:
                                        flash_el_dict['O'] = [geo_el]
                                elif apval["type"] == 'R':
                                    if 'R' in flash_el_dict:
                                        flash_el_dict['R'].append(geo_el)
                                    else:
                                        flash_el_dict['R'] = [geo_el]
                            else:
                                aperture_size = apval['size']

                                if aperture_size in traces_el_dict:
                                    traces_el_dict[aperture_size].append(geo_el)
                                else:
                                    traces_el_dict[aperture_size] = [geo_el]
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error(
                    "ToolPaint.paint_polygon_worker() Laser Lines -> Identify flashes/traces--> %s" % str(ee))

            cpoly = AppRTreeStorage()
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
                                    tooldia=tooldiameter,
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
                                    tooldia=tooldiameter,
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
                                    tooldia=tooldiameter,
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
                        cpoly.insert(lin)
            except TypeError:
                cpoly.insert(pads_lines_list)

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
                                tooldia=tooldiameter,
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
                        cpoly.insert(lin)
            except TypeError:
                cpoly.insert(lines_geoms)

        elif paint_method == 4:  # _("Combo")
            try:
                self.app.inform.emit(_("Painting polygon with method: lines."))
                cpoly = self.parent_tool.clear_polygon_lines(
                    polyg,
                    tooldia=tooldiameter,
                    steps_per_circle=self.circle_steps,
                    overlap=over,
                    contour=cont,
                    connect=conn,
                    prog_plot=prog_plot,
                )

                if cpoly and cpoly.objects:
                    pass
                else:
                    self.app.inform.emit(_("Failed. Painting polygon with method: seed."))
                    cpoly = self.parent_tool.clear_polygon_seed(
                        polyg,
                        tooldia=tooldiameter,
                        steps_per_circle=self.circle_steps,
                        overlap=over,
                        contour=cont,
                        connect=conn,
                        prog_plot=prog_plot,
                    )
                    if cpoly and cpoly.objects:
                        pass
                    else:
                        self.app.inform.emit(_("Failed. Painting polygon with method: standard."))
                        cpoly = self.parent_tool.clear_polygon_shrink(
                            polyg,
                            tooldia=tooldiameter,
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

        if cpoly and cpoly.objects:
            return cpoly
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _('Geometry could not be painted completely'))
            return None

    def paint_geo(self, obj, geometry, tooldia=None, order=None, method=None, outname=None,
                  tools_storage=None, plot=True, rest=None, run_threaded=True):
        """
        Paints a given geometry.

        :param obj:             painted object
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

        paint_method = method if method is not None else self.ui.paintmethod_combo.get_value()
        # determine if to use the progressive plotting
        prog_plot = True if self.app.options["tools_paint_plotting"] == 'progressive' else False

        name = outname if outname is not None else self.obj_name + "_paint"
        order = order if order is not None else self.ui.paint_order_combo.get_value()
        tools_storage = self.paint_tools if tools_storage is None else tools_storage
        use_rest_strategy = rest if rest is not None else self.ui.rest_cb.get_value()

        # TODO this should be in preferences and in the UI
        simplification_value = 0.01

        sorted_tools = []
        if tooldia is not None:
            try:
                sorted_tools = [float(eval(dia)) for dia in tooldia.split(",") if dia != '']
            except AttributeError:
                if not isinstance(tooldia, list):
                    sorted_tools = [float(tooldia)]
                else:
                    sorted_tools = tooldia
        else:
            table_items = self.ui.tools_table.selectedItems()
            sel_rows = {t.row() for t in table_items}
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
                sorted_tools.append(self.tooldia)
            if not sorted_tools:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("There are no tools selected in the Tool Table."))
                return 'fail'

        # Initializes the new geometry object
        def job_normal_clear(geo_obj, app_obj):
            tool_dia = None
            current_uid = None
            final_solid_geometry = []
            old_disp_number = 0

            # sort the tools if we have an order selected in the UI
            if order == 1:  # Forward
                sorted_tools.sort(reverse=False)
            elif order == 2:    # Reverse
                sorted_tools.sort(reverse=True)
            else:
                pass

            for tool_dia in sorted_tools:
                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool_dia))
                msg = '[success] %s %s%s %s' % (_('Painting with tool diameter = '),
                                                str(tool_dia),
                                                self.units.lower(),
                                                _('started'))
                self.app.inform.emit(msg)
                self.app.proc_container.update_view_text(' %d%%' % 0)

                # find the tooluid associated with the current tool_dia, so we know what tool to use
                for k, v in tools_storage.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool_dia)):
                        current_uid = int(k)

                if not current_uid:
                    return "fail"

                # determine the tool parameters to use
                over = float(tools_storage[current_uid]['data']['tools_paint_overlap']) / 100.0
                conn = tools_storage[current_uid]['data']['tools_paint_connect']
                cont = tools_storage[current_uid]['data']['tools_paint_contour']

                paint_offset = float(tools_storage[current_uid]['data']['tools_paint_offset'])

                poly_buf = []
                for pol in flatten_shapely_geometry(geometry):
                    buffered_pol = pol.buffer(-paint_offset)
                    if buffered_pol and not buffered_pol.is_empty:
                        poly_buf.append(buffered_pol)

                if not poly_buf:
                    self.app.inform.emit(
                        '[ERROR_NOTCL] %s' % _("There is no geometry to process or the tool diameter is too big."))
                    continue

                # variables to display the percentage of work done
                geo_len = len(poly_buf)

                self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                pol_nr = 0

                # -----------------------------
                # effective polygon clearing job
                # -----------------------------
                try:
                    cp_list = []
                    for pp in poly_buf:
                        # provide the app with a way to process the GUI events when in a blocking loop
                        QtWidgets.QApplication.processEvents()
                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise grace
                        geo_res = self.paint_polygon_worker(pp, tooldiameter=tool_dia, over=over, conn=conn,
                                                            cont=cont, paint_method=paint_method, obj=obj,
                                                            prog_plot=prog_plot)
                        if geo_res:
                            cp_list.append(geo_res)
                        pol_nr += 1
                        disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                        # log.debug("Polygons cleared: %d" % pol_nr)

                        if old_disp_number < disp_number <= 100:
                            self.app.proc_container.update_view_text(' %d%%' % disp_number)
                            old_disp_number = disp_number

                    total_geometry = []
                    if cp_list:
                        for cp in cp_list:
                            if simplification_value > 0.0:
                                total_geometry += [x.simplify(simplification_value) for x in cp.get_objects()]
                            else:
                                total_geometry += [x for x in cp.get_objects()]

                        # clean the geometry
                        total_geometry = [g for g in total_geometry if g and not g.is_empty]
                except grace:
                    return "fail"
                except Exception as e:
                    self.app.log.error("Could not Paint the polygons. %s" % str(e))
                    mssg = '[ERROR] %s\n%s' % (_("Could not do Paint. Try a different combination of parameters. "
                                                 "Or a different method of Paint"), str(e))
                    self.app.inform.emit(mssg)
                    continue

                # add the solid_geometry to the current too in self.paint_tools (tools_storage)
                # dictionary and then reset the temporary list that stored that solid_geometry
                tools_storage[current_uid]['solid_geometry'] = deepcopy(total_geometry)
                tools_storage[current_uid]['data']['name'] = name
                final_solid_geometry += total_geometry

            # clean the progressive plotted shapes if it was used
            if self.app.options["tools_paint_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # delete tools with empty geometry
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid in list(tools_storage.keys()):
                # if the solid_geometry (type=list) is empty
                if not tools_storage[uid]['solid_geometry']:
                    tools_storage.pop(uid, None)

            if not tools_storage:
                return 'fail'

            geo_obj.obj_options["tools_mill_tooldia"] = str(tool_dia)
            # this will turn on the FlatCAMCNCJob plot for multiple tools
            geo_obj.multigeo = True
            geo_obj.multitool = True
            geo_obj.tools.clear()
            geo_obj.tools = dict(tools_storage)

            geo_obj.solid_geometry = flatten_shapely_geometry(unary_union(final_solid_geometry))

            try:
                a, b, c, d = unary_union(geo_obj.solid_geometry).bounds

                geo_obj.obj_options['xmin'] = a
                geo_obj.obj_options['ymin'] = b
                geo_obj.obj_options['xmax'] = c
                geo_obj.obj_options['ymax'] = d
            except Exception as ee:
                self.app.log.error("ToolPaint.paint_poly.job_init() bounds error --> %s" % str(ee))
                return

            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            has_solid_geo = 0
            for tooluid in geo_obj.tools:
                if geo_obj.tools[tooluid]['solid_geometry']:
                    has_solid_geo += 1

            if has_solid_geo == 0:
                app_obj.inform.emit('[ERROR] %s' %
                                    _("There is no Painting Geometry in the file.\n"
                                      "Usually it means that the tool diameter is too big for the painted geometry.\n"
                                      "Change the painting parameters and try again."))
                return "fail"

            # Experimental...
            # print("Indexing...", end=' ')
            # geo_obj.make_index()

        # Initializes the new geometry object
        def job_rest_clear(geo_obj, app_obj):
            current_uid = None
            final_solid_geometry = []
            old_disp_number = 0

            # sort the tools reversed for the rest machining
            sorted_tools.sort(reverse=True)

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

            # variables to display the percentage of work done
            geo_len = len(poly_buf)

            self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

            for tool_dia in sorted_tools:
                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool_dia))
                msg = '[success] %s %s%s %s' % (_('Painting with tool diameter = '),
                                                str(tool_dia),
                                                self.units.lower(),
                                                _('started'))
                self.app.inform.emit(msg)
                self.app.proc_container.update_view_text(' %d%%' % 0)

                # find the tooluid associated with the current tool_dia, so we know what tool to use
                for k, v in tools_storage.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool_dia)):
                        current_uid = int(k)

                if not current_uid:
                    return "fail"

                # store here the cleared geometry
                # cleared_geo = []

                # determine the tool parameters to use
                over = float(tools_storage[current_uid]['data']['tools_paint_overlap']) / 100.0
                conn = tools_storage[current_uid]['data']['tools_paint_connect']
                cont = tools_storage[current_uid]['data']['tools_paint_contour']

                pol_nr = 0

                # store here the parts of polygons that could not be cleared; actually those are parts of polygons
                rest_list = []

                # -----------------------------
                # effective polygon clearing job
                # -----------------------------
                try:
                    cleared_geo = []
                    for pp in poly_buf:
                        # provide the app with a way to process the GUI events when in a blocking loop
                        QtWidgets.QApplication.processEvents()
                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise grace

                        # speedup the clearing by not trying to clear polygons that is clear they can't be
                        # cleared with the current tool. this tremendously reduce the clearing time
                        check_dist = -tool_dia / 2.0
                        check_buff = pp.buffer(check_dist)
                        if not check_buff or check_buff.is_empty:
                            continue

                        geo_res = self.paint_polygon_worker(pp, tooldiameter=tool_dia, over=over, conn=conn,
                                                            cont=cont, paint_method=paint_method, obj=obj,
                                                            prog_plot=prog_plot)

                        if simplification_value > 0.0:
                            geo_elems = [x.simplify(simplification_value) for x in geo_res.get_objects()]
                        else:
                            geo_elems = [x for x in geo_res.get_objects()]

                        # See if the polygon was completely cleared
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
                        disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                        # log.debug("Polygons cleared: %d" % pol_nr)

                        if old_disp_number < disp_number <= 100:
                            self.app.proc_container.update_view_text(' %d%%' % disp_number)
                            old_disp_number = disp_number
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

                    # add the solid_geometry to the current too in self.paint_tools (tools_storage)
                    # dictionary and then reset the temporary list that stored that solid_geometry
                    tools_storage[current_uid]['solid_geometry'] = deepcopy(cleared_geo)
                    tools_storage[current_uid]['data']['name'] = name
                    geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                else:
                    self.app.log.debug("There are no geometries in the cleared polygon.")

                # Area to clear next
                self.app.log.debug("Generating rest geometry for the next tool.")

                buffered_cleared = unary_union(cleared_geo)
                buffered_cleared = buffered_cleared.buffer(tool_dia / 2.0)
                poly_buf = MultiPolygon(poly_buf).difference(buffered_cleared)
                poly_buf = flatten_shapely_geometry(poly_buf)

                tmp = []
                for p in poly_buf:
                    if p.is_valid:
                        tmp.append(p)
                tmp += rest_list

                print(tmp)
                poly_buf = MultiPolygon(tmp)
                if not poly_buf.is_valid:
                    poly_buf = unary_union(tmp)
                if not poly_buf or poly_buf.is_empty or not poly_buf.is_valid:
                    app_obj.log.debug("Rest geometry empty. Breaking.")
                    break
                poly_buf = flatten_shapely_geometry(poly_buf)

            geo_obj.multigeo = True
            geo_obj.obj_options["tools_mill_tooldia"] = '0.0'

            # clean the progressive plotted shapes if it was used
            if self.app.options["tools_paint_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # delete tools with empty geometry
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid in list(tools_storage.keys()):
                # if the solid_geometry (type=list) is empty
                if not tools_storage[uid]['solid_geometry']:
                    tools_storage.pop(uid, None)

            if not tools_storage:
                return 'fail'

            geo_obj.multitool = True

            if not geo_obj.tools:
                return "fail"

            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            has_solid_geo = 0
            for tooluid in geo_obj.tools:
                if geo_obj.tools[tooluid]['solid_geometry']:
                    has_solid_geo += 1

            if has_solid_geo == 0:
                app_obj.inform.emit(
                    '[ERROR] %s' %
                    _("There is no Painting Geometry in the file.\n"
                      "Usually it means that the tool diameter is too big for the painted geometry.\n"
                      "Change the painting parameters and try again.")
                )
                return "fail"
            geo_obj.solid_geometry = flatten_shapely_geometry(unary_union(final_solid_geometry))

            try:
                a, b, c, d = unary_union(geo_obj.solid_geometry).bounds

                geo_obj.obj_options['xmin'] = a
                geo_obj.obj_options['ymin'] = b
                geo_obj.obj_options['xmax'] = c
                geo_obj.obj_options['ymax'] = d
            except Exception as ee:
                app_obj.log.error("ToolPaint.paint_poly.job_init() bounds error --> %s" % str(ee))
                return

            # Experimental...
            # print("Indexing...", end=' ')
            # geo_obj.make_index()

        def job_thread(app_obj):
            try:
                if use_rest_strategy:
                    ret = app_obj.app_obj.new_object("geometry", name, job_rest_clear, plot=plot, autoselected=False)
                else:
                    ret = app_obj.app_obj.new_object("geometry", name, job_normal_clear, plot=plot, autoselected=False)
            except grace:
                proc.done()
                return
            except Exception as er:
                proc.done()
                app_obj.inform.emit('[ERROR] %s --> %s' % ('PaintTool.paint_geo()', str(er)))
                traceback.print_stack()
                return
            proc.done()

            if ret == 'fail':
                self.app.inform.emit('[ERROR] %s' % _("Failed."))
                return

            # focus on Properties Tab
            # self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)

            self.app.inform.emit('[success] %s' % _("Done."))

        # Promise object with the new name
        self.app.collection.promise(name)

        proc = self.app.proc_container.new(_("Painting ..."))

        if run_threaded:
            # Background
            self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})
        else:
            job_thread(app_obj=self.app)

    def paint_poly(self, obj, inside_pt=None, poly_list=None, tooldia=None, order=None, method=None, outname=None,
                   tools_storage=None, plot=True, run_threaded=True):
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

        self.paint_geo(obj, polygon_list, tooldia=tooldia, order=order, method=method, outname=outname,
                       tools_storage=tools_storage, plot=plot, run_threaded=run_threaded)

    def paint_poly_all(self, obj, tooldia=None, order=None, method=None, outname=None, tools_storage=None, plot=True,
                       run_threaded=True):
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

        # This is a recursive generator of individual Polygons.
        # Note: Double check correct implementation. Might exit
        #       early if it finds something that is not a Polygon?
        # def recurse(geo):
        #     try:
        #         for subg in geo:
        #             for subsubg in recurse(subg):
        #                 yield subsubg
        #     except TypeError:
        #         if isinstance(geo, Polygon):
        #             yield geo
        #
        #     raise StopIteration

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

        self.paint_geo(obj, painted_area, tooldia=tooldia, order=order, method=method, outname=outname,
                       tools_storage=tools_storage, plot=plot, run_threaded=run_threaded)

    def paint_poly_area(self, obj, sel_obj, tooldia=None, order=None, method=None, outname=None,
                        tools_storage=None, plot=True, run_threaded=True):
        """
        Paints all polygons in this object that are within the sel_obj object

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
        target_geo = unary_union(obj.solid_geometry)

        if obj.kind == 'gerber':
            # I don't do anything here, like buffering when the Gerber is loaded without buffering????!!!!
            if self.app.options["gerber_buffering"] == 'no':
                msg = '%s %s %s' % (_("Paint Plugin."),
                                    _("Painting area task started."),
                                    _("Buffering geometry..."))
                self.app.inform.emit(msg)
            else:
                self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Painting area task started.")))

            if obj.kind == 'gerber':
                if self.app.options["tools_paint_plotting"] == 'progressive':
                    target_geo = target_geo.buffer(0)
        else:
            self.app.inform.emit('%s %s' % (_("Paint Plugin."), _("Painting area task started.")))

        geo_to_paint = target_geo.intersection(sel_obj)
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

        self.paint_geo(obj, p_geo_list, tooldia=tooldia, order=order, method=method, outname=outname,
                       tools_storage=tools_storage, plot=plot, run_threaded=run_threaded)

    def paint_poly_ref(self, obj, sel_obj, tooldia=None, order=None, method=None, outname=None,
                       tools_storage=None, plot=True, run_threaded=True):
        """
        Paints all polygons in this object that are within the sel_obj object

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

        self.paint_poly_area(obj=obj,
                             sel_obj=sel_rect,
                             tooldia=tooldia,
                             order=order,
                             method=method,
                             outname=outname,
                             tools_storage=tools_storage,
                             plot=plot,
                             run_threaded=run_threaded)

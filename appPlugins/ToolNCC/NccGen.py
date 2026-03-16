
from PyQt6 import QtWidgets     # noqa

import logging
from copy import deepcopy
import numpy as np

import traceback

from shapely import (
    LineString,
    Polygon,
    MultiPolygon,
    MultiLineString,
    LinearRing,
)
from shapely.geometry import base
from shapely.ops import unary_union

import gettext
import appTranslation as fcTranslate
import builtins

from camlib import grace, flatten_shapely_geometry

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class NccGen:
    def __init__(self, tool):
        self.app = tool.app
        self.parent_tool = tool

        self.ui = tool.ui

        self.mm = tool.mm
        self.mr = tool.mr
        self.kp = tool.kp

        self.decimals = tool.app.decimals
        self.temp_shapes = tool.temp_shapes

        self.first_click = tool.first_click
        self.cursor_pos = tool.cursor_pos
        self.mouse_is_dragging = tool.mouse_is_dragging
        self.area_sel_disconnect_flag = tool.area_sel_disconnect_flag
        self.sel_rect = tool.sel_rect

        self.circle_steps = tool.circle_steps

        self.obj_name = tool.obj_name
        self.select_method = tool.select_method
        self.bound_obj_name = tool.bound_obj_name
        self.bound_obj = tool.bound_obj

        self.o_name = tool.o_name

        self.ncc_obj = tool.ncc_obj

        self.ncc_dia_list = tool.ncc_dia_list
        self.iso_dia_list = tool.iso_dia_list
        self.tooldia = tool.tooldia
        self.ncc_tools = tool.ncc_tools

        self.solid_geometry = tool.solid_geometry

    def on_ncc_click(self):
        """
        Slot for clicking signal
        :return: None
        """

        self.app.defaults.report_usage("on_ncc_click")

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False
        should_check_validity = self.ui.valid_cb.get_value()

        prog_plot = True if self.app.options["tools_ncc_plotting"] == 'progressive' else False
        if prog_plot:
            self.temp_shapes.clear(update=True)

        self.sel_rect = []

        obj_type = self.ui.type_obj_radio.get_value
        geo_steps = self.app.options.get("geometry_circle_steps", 64)
        gerber_steps = self.app.options.get("gerber_circle_steps", 64)
        self.circle_steps = int(gerber_steps) if obj_type == 'gerber' else int(geo_steps)
        self.obj_name = self.ui.object_combo.currentText()

        # Get source object.
        try:
            self.ncc_obj = self.app.collection.get_by_name(self.obj_name)
        except Exception as e:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"),  str(self.obj_name)))
            return "Could not retrieve object: %s with error: %s" % (self.obj_name, str(e))

        if self.ncc_obj is None:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Object not found"), str(self.obj_name)))
            return

        # Check tool validity
        if should_check_validity is True:
            # this is done in another Process
            self.parent_tool.find_safe_tooldia_multiprocessing()

        # use the selected tools in the tool table; get diameters for isolation
        self.iso_dia_list = []
        # use the selected tools in the tool table; get diameters for non-copper clear
        self.ncc_dia_list = []

        table_items = self.ui.tools_table.selectedItems()
        sel_rows = {t.row() for t in table_items}
        if len(sel_rows) > 0:
            for row in sel_rows:
                # try to convert comma to decimal point. if it's still not working error message and return
                try:
                    self.tooldia = float(self.ui.tools_table.item(row, 1).text().replace(',', '.'))
                except ValueError:
                    self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                    continue

                # find out which tools are for isolation and which are for copper clearing
                for uid_k, uid_v in self.ncc_tools.items():
                    if round(uid_v['tooldia'], self.decimals) == round(self.tooldia, self.decimals):
                        if uid_v['data']['tools_ncc_operation'] == "iso":
                            self.iso_dia_list.append(self.tooldia)
                        else:
                            self.ncc_dia_list.append(self.tooldia)
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("There are no tools selected in the Tool Table."))
            return

        self.o_name = '%s_ncc' % self.obj_name

        self.select_method = self.ui.select_combo.get_value()
        if self.select_method == 0:   # Itself
            self.bound_obj_name = self.ui.object_combo.currentText()
            # Get source object.
            try:
                self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.bound_obj_name))
                return "Could not retrieve object: %s with error: %s" % (self.bound_obj_name, str(e))

            self.ncc_handler(ncc_obj=self.ncc_obj,
                             ncctd_list=self.ncc_dia_list,
                             isotd_list=self.iso_dia_list,
                             outname=self.o_name,
                             tools_storage=self.ncc_tools)
        elif self.select_method == 1:   # Area Selection
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
            # disable the "notebook UI" until finished
            self.app.ui.notebook.setDisabled(True)
        elif self.select_method == 2:   # Reference Object
            self.bound_obj_name = self.ui.reference_combo.currentText()
            # Get source object.
            try:
                self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.bound_obj_name))
                return "Could not retrieve object: %s. Error: %s" % (self.bound_obj_name, str(e))

            self.ncc_handler(
                ncc_obj=self.ncc_obj,
                sel_obj=self.bound_obj,
                ncctd_list=self.ncc_dia_list,
                isotd_list=self.iso_dia_list,
                outname=self.o_name,
            )

    def calculate_bounding_box(self, ncc_obj, ncc_select, box_obj=None):
        """
        Will return a geometry that dictate the total extent of the area to be copper cleared

        :param ncc_obj:     The object to be copper cleared
        :param box_obj:     The object whose geometry will be used as delimitation for copper clearing - if selected
        :param ncc_select:  String that choose what kind of reference to be used for copper clearing extent
        :return:            The geometry that surrounds the area to be cleared and the kind of object from which the
                            geometry originated (string: "gerber", "geometry" or None)
        """
        box_kind = box_obj.kind if box_obj is not None else None

        env_obj = None
        if ncc_select == 0:     # _('Itself')
            geo_n = ncc_obj.solid_geometry

            try:
                if isinstance(geo_n, MultiPolygon):
                    env_obj = geo_n.convex_hull
                elif (isinstance(geo_n, MultiPolygon) and len(geo_n.geoms) == 1) or \
                        (isinstance(geo_n, list) and len(geo_n) == 1) and isinstance(geo_n[0], Polygon):
                    env_obj = unary_union(geo_n)
                else:
                    env_obj = unary_union(geo_n)
                    env_obj = env_obj.convex_hull
            except Exception as e:
                self.app.log.error("ToolNcc.calculate_bounding_box() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return None
        elif ncc_select == 1:   # _("Area Selection")
            env_obj = unary_union(self.sel_rect)
            env_obj = flatten_shapely_geometry(env_obj)
        elif ncc_select == 2:   # _("Reference Object")
            if box_obj is None:
                return None, None

            box_geo = box_obj.solid_geometry
            if box_kind == 'geometry':
                env_obj = flatten_shapely_geometry(box_geo)
            elif box_kind == 'gerber':
                box_geo = unary_union(box_obj.solid_geometry).convex_hull
                ncc_geo = unary_union(ncc_obj.solid_geometry).convex_hull
                env_obj = ncc_geo.intersection(box_geo)
                env_obj = flatten_shapely_geometry(env_obj)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        return env_obj, box_kind

    def apply_margin_to_bounding_box(self, bbox, box_kind, ncc_select, ncc_margin):
        """
        Prepare non-copper polygons.
        Apply a margin to  the bounding box area from which the copper features will be subtracted

        :param bbox:        the Geometry to be used as bounding box after applying the ncc_margin
        :param box_kind:    "geometry" or "gerber"
        :param ncc_select:  the kind of area to be copper cleared
        :param ncc_margin:  the margin around the area to be copper cleared
        :return:            a geometric element (Polygon or MultiPolygon) that specify the area to be copper cleared
        """

        self.app.log.debug("NCC Tool. Preparing non-copper polygons.")
        self.app.inform.emit(_("NCC Tool. Preparing non-copper polygons."))

        if bbox is None:
            self.app.log.debug("ToolNcc.apply_margin_to_bounding_box() --> The object is None")
            return 'fail'

        new_bounding_box = None
        if ncc_select == 0:     # _('Itself')
            try:
                new_bounding_box = bbox.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            except Exception as e:
                self.app.log.error("ToolNcc.apply_margin_to_bounding_box() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return 'fail'
        elif ncc_select == 1:   # _("Area Selection")
            geo_buff_list = []
            for poly in bbox:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace
                geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))
            new_bounding_box = unary_union(geo_buff_list)
        elif ncc_select == 2:   # _("Reference Object")
            if box_kind == 'geometry':
                geo_buff_list = []
                for poly in bbox:
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

                new_bounding_box = unary_union(geo_buff_list)
            elif box_kind == 'gerber':
                new_bounding_box = bbox.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        self.app.log.debug("NCC Tool. Finished non-copper polygons.")
        return new_bounding_box

    def get_tool_empty_area(self, name, ncc_obj, geo_obj, isotooldia, has_offset, ncc_offset, ncc_margin,
                            bounding_box, tools_storage, work_geo=None):
        """
        Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry.

        :param name:
        :param ncc_obj:
        :param geo_obj:
        :param isotooldia:
        :param has_offset:
        :param ncc_offset:
        :param ncc_margin:
        :param bounding_box:    only this area is kept
        :param tools_storage:
        :param work_geo:        if provided use this geometry to generate the empty area
        :return:
        """

        self.app.log.debug("NCC Tool. Calculate 'empty' area.")
        self.app.inform.emit(_("NCC Tool. Calculate 'empty' area."))

        # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
        # will store the number of tools for which the isolation is broken
        warning_flag = 0

        if work_geo:
            sol_geo = work_geo
            if has_offset is True:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s ...' % _("Buffering")
                )
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit(
                    '[success] %s ...' % _("Buffering finished")
                )
            empty = self.get_ncc_empty_area(
                target=sol_geo,
                boundary=bounding_box,
            )

            if empty == 'fail' or empty.is_empty:
                msg = '[ERROR_NOTCL] %s' % _("Could not get the extent of the area to be non copper cleared.")
                self.app.inform.emit(msg)
                return 'fail', 0

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            self.app.log.debug(
                "NCC Tool. Finished calculation of 'empty' area."
            )
            self.app.inform.emit(
                _("NCC Tool. Finished calculation of 'empty' area.")
            )

            return empty, warning_flag

        if ncc_obj.kind == 'gerber' and not isotooldia:
            # unfortunately for this function to work time efficient,
            # if the Gerber was loaded without buffering then it require the buffering now.
            fused_solid_geometry = unary_union(ncc_obj.solid_geometry)
            if self.app.options.get("gerber_buffering", "no") == 'no':
                sol_geo = fused_solid_geometry.buffer(0)
            else:
                sol_geo = fused_solid_geometry

            if has_offset is True:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s ...' % _("Buffering")
                )
                if isinstance(sol_geo, list):
                    sol_geo = MultiPolygon(sol_geo)
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit(
                    '[success] %s ...' % _("Buffering finished")
                )

            empty = self.get_ncc_empty_area(
                target=sol_geo,     # noqa
                boundary=bounding_box,
            )
            if empty == 'fail' or empty.is_empty:
                msg = '[ERROR_NOTCL] %s' % _("Could not get the extent of the area to be non copper cleared.")
                self.app.inform.emit(msg)
                return 'fail', 0

        elif ncc_obj.kind == 'gerber' and isotooldia:
            isolated_geo = []

            # unfortunately for this function to work time efficient,
            # if the Gerber was loaded without buffering then it require the buffering now.
            fused_solid_geometry = unary_union(ncc_obj.solid_geometry)
            # TODO 'buffering status' should be a property of the object not the project property
            if self.app.options['gerber_buffering'] == 'no':
                self.solid_geometry = fused_solid_geometry.buffer(0)
            else:
                self.solid_geometry = fused_solid_geometry

            # if milling type is climb then the move is counter-clockwise around features
            milling_type = self.ui.milling_type_radio.get_value()

            for tool_iso in isotooldia:
                new_geometry = []

                if milling_type == 'cl':
                    isolated_geo = self.generate_envelope(tool_iso/2, 1)
                else:
                    isolated_geo = self.generate_envelope(tool_iso/2, 0)

                if isolated_geo == 'fail' or isolated_geo.is_empty:
                    self.app.inform.emit('[ERROR_NOTCL] %s %s' %
                                         (_("Isolation geometry could not be generated."), str(tool_iso)))
                    continue

                if ncc_margin < tool_iso:
                    self.app.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                  "than isolation tool diameter."))

                w_isolated_geo = flatten_shapely_geometry(isolated_geo)
                for geo_elem in w_isolated_geo:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace

                    if isinstance(geo_elem, Polygon):
                        for ring in self.poly2rings(geo_elem):
                            new_geo = ring.intersection(bounding_box)
                            if new_geo and not new_geo.is_empty:
                                new_geometry.append(new_geo)
                    elif isinstance(geo_elem, LineString):
                        new_geo = geo_elem.intersection(bounding_box)
                        if new_geo:
                            if not new_geo.is_empty:
                                new_geometry.append(new_geo)

                # a MultiLineString geometry element will show that the isolation is broken for this tool
                for geo_e in new_geometry:
                    if type(geo_e) == MultiLineString:
                        warning_flag += 1
                        break

                for k, v in tools_storage.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                        tool_iso)):
                        current_uid = int(k)
                        # add the solid_geometry to the current too in self.paint_tools dictionary
                        # and then reset the temporary list that stored that solid_geometry
                        v['solid_geometry'] = flatten_shapely_geometry(new_geometry)
                        v['data']['name'] = name
                        geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                        break

            if isolated_geo == "fail":
                self.app.log.error(
                    "ToolNcc.get_tool_empty_area() -> The isolation failed for tool: %s" % str(isotooldia)
                )
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("Failed."))
                return 'fail', 0

            sol_geo = unary_union(isolated_geo)
            if has_offset is True:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s ...' % _("Buffering")
                )
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit(
                    '[success] %s ...' % _("Buffering finished")
                )

            empty = self.get_ncc_empty_area(
                target=sol_geo,     # noqa
                boundary=bounding_box,
            )
            if empty == 'fail' or empty.is_empty:
                msg = '[ERROR_NOTCL] %s' % _("Could not get the extent of the area to be non copper cleared.")
                self.app.inform.emit(msg)
                return 'fail', 0

        elif ncc_obj.kind == 'geometry':
            sol_geo = unary_union(ncc_obj.solid_geometry)
            if has_offset is True:
                self.app.inform.emit(
                    '[WARNING_NOTCL] %s ...' % _("Buffering")
                )
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit(
                    '[success] %s ...' % _("Buffering finished")
                )
            empty = self.get_ncc_empty_area(
                target=sol_geo,     # noqa
                boundary=bounding_box,
            )
            if empty == 'fail' or empty.is_empty:
                msg = '[ERROR_NOTCL] %s' % _("Could not get the extent of the area to be non copper cleared.")
                self.app.inform.emit(msg)
                return 'fail', 0
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.'))
            return 'fail', 0

        if type(empty) is Polygon:
            empty = MultiPolygon([empty])

        self.app.log.debug("NCC Tool. Finished calculation of 'empty' area.")
        self.app.inform.emit(_("NCC Tool. Finished calculation of 'empty' area."))

        return empty, warning_flag

    def clear_polygon_worker(self, pol, tooldia, ncc_method, ncc_overlap, ncc_connect, ncc_contour, prog_plot,
                             simplify_tol=0.0):

        cp = None

        if ncc_method == 0:     # standard
            try:
                cp = self.parent_tool.clear_polygon_shrink(
                    pol,
                    tooldia,
                    steps_per_circle=self.circle_steps,
                    overlap=ncc_overlap, contour=ncc_contour,
                    connect=ncc_connect,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolNcc.clear_polygon_worker() Standard --> %s" % str(ee))
        elif ncc_method == 1:   # seed
            try:
                cp = self.parent_tool.clear_polygon_seed(
                    pol,
                    tooldia,
                    steps_per_circle=self.circle_steps,
                    overlap=ncc_overlap, contour=ncc_contour,
                    connect=ncc_connect,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolNcc.clear_polygon_worker() Seed --> %s" % str(ee))
        elif ncc_method == 2:   # Lines
            try:
                cp = self.parent_tool.clear_polygon_lines(
                    pol,
                    tooldia,
                    steps_per_circle=self.circle_steps,
                    overlap=ncc_overlap, contour=ncc_contour,
                    connect=ncc_connect,
                    prog_plot=prog_plot,
                )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolNcc.clear_polygon_worker() Lines --> %s" % str(ee))
        elif ncc_method == 3:   # Combo
            try:
                self.app.inform.emit(_("Clearing the polygon with the method: lines."))
                cp = self.parent_tool.clear_polygon_lines(
                    pol, tooldia,
                    steps_per_circle=self.circle_steps,
                    overlap=ncc_overlap, contour=ncc_contour,
                    connect=ncc_connect,
                    prog_plot=prog_plot,
                )

                if cp and cp.objects:
                    pass
                else:
                    self.app.inform.emit(_("Failed. Clearing the polygon with the method: seed."))
                    cp = self.parent_tool.clear_polygon_seed(
                        pol,
                        tooldia,
                        steps_per_circle=self.circle_steps,
                        overlap=ncc_overlap, contour=ncc_contour,
                        connect=ncc_connect,
                        prog_plot=prog_plot,
                    )
                    if cp and cp.objects:
                        pass
                    else:
                        self.app.inform.emit(_("Failed. Clearing the polygon with the method: standard."))
                        cp = self.parent_tool.clear_polygon_shrink(
                            pol,
                            tooldia,
                            steps_per_circle=self.circle_steps,
                            overlap=ncc_overlap, contour=ncc_contour,
                            connect=ncc_connect,
                            prog_plot=prog_plot,
                        )
            except grace:
                return "fail"
            except Exception as ee:
                self.app.log.error("ToolNcc.clear_polygon_worker() Combo --> %s" % str(ee))

        if cp and cp.objects:
            if simplify_tol > 0.0:
                return [x.simplify(simplify_tol) for x in cp.get_objects()]
            else:
                return [x for x in cp.get_objects()]
        else:
            pt = pol.representative_point()
            coords = (pt.x, pt.y)
            self.app.inform_shell.emit('%s %s' % (_('Polygon could not be cleared. Location:'), str(coords)))
            return None

    def ncc_handler(
            self,
            ncc_obj,
            ncctd_list,
            isotd_list,
            sel_obj=None,
            outname=None,
            order=None,
            tools_storage=None,
            run_threaded=True,
    ):
        """
        Clear the excess copper from the entire object.

        :param ncc_obj:         ncc cleared object
        :type ncc_obj:          appObjects.GerberObject.GerberObject
        :param ncctd_list:      a list of diameters of the tools to be used to ncc clear
        :type ncctd_list:       list
        :param isotd_list:      a list of diameters of the tools to be used for isolation
        :type isotd_list:       list
        :param sel_obj:
        :type sel_obj:
        :param outname:         name of the resulting object
        :type outname:          str
        :param order:           Tools order
        :param tools_storage:   whether to use the current tools_storage self.ncc_tools or a different one.
                                Usage of the different one is related to when this function is called
                                from a TcL command.
        :type tools_storage:    dict

        :param run_threaded:    If True the method will be run in a threaded way suitable for GUI usage; if False
                                it will run non-threaded for TclShell usage
        :type run_threaded:     bool
        :return:
        """
        self.app.log.debug("Executing the ncc_handler() ...")

        if run_threaded:
            proc = self.app.proc_container.new('%s...' % _("Working"))
        else:
            self.app.proc_container.view.set_busy('%s...' % _("Working"))
            QtWidgets.QApplication.processEvents()

        # ######################################################################################################
        # ######################### Read the parameters ########################################################
        # ######################################################################################################

        units = self.app.app_units
        order = order if order else self.ui.ncc_order_combo.get_value()
        ncc_select = self.ui.select_combo.get_value()
        rest_machining_choice = self.ui.ncc_rest_cb.get_value()

        # TODO this should be in preferences and in the UI
        simplification_value = 0.01

        # determine if to use the progressive plotting
        prog_plot = True if self.app.options["tools_ncc_plotting"] == 'progressive' else False

        tools_storage = tools_storage if tools_storage is not None else self.ncc_tools
        sorted_clear_tools = ncctd_list

        if not sorted_clear_tools:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("There is no copper clearing tool in the selection "
                                                        "and at least one is needed."))
            return 'fail'

        # ########################################################################################################
        # set the name for the future Geometry object
        # I do it here because it is also stored inside the gen_clear_area() and gen_clear_area_rest() methods
        # ########################################################################################################
        name = outname if outname is not None else self.obj_name + "_ncc"

        # ########################################################################################################
        # ######### #####Initializes the new geometry object #####################################################
        # ########################################################################################################
        def gen_clear_area(geo_obj, app_obj):
            app_obj.log.debug("NCC Tool. Normal copper clearing task started.")
            self.app.inform.emit(_("NCC Tool. Finished non-copper polygons. Normal copper clearing task started."))

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
            # will store the number of tools for which the isolation is broken
            warning_flag = 0

            tool = None

            if order == 1:  # "Forward"
                sorted_clear_tools.sort(reverse=False)
            elif order == 2:    # "Reverse"
                sorted_clear_tools.sort(reverse=True)
            else:
                pass

            app_obj.poly_not_cleared = False    # flag for polygons not cleared

            if ncc_select == 2:     # Reference Object
                bbox_geo, bbox_kind = self.calculate_bounding_box(
                    ncc_obj=ncc_obj, box_obj=sel_obj, ncc_select=ncc_select)
            else:
                bbox_geo, bbox_kind = self.calculate_bounding_box(ncc_obj=ncc_obj, ncc_select=ncc_select)

            if bbox_geo is None and bbox_kind is None:
                self.app.inform.emit("[ERROR_NOTCL] %s" % _("NCC Tool failed creating bounding box."))
                return "fail"

            # Bounding box for current tool
            ncc_margin = self.ui.ncc_margin_entry.get_value()
            bbox = self.apply_margin_to_bounding_box(bbox=bbox_geo, box_kind=bbox_kind,
                                                     ncc_select=ncc_select, ncc_margin=ncc_margin)

            # ----------------------------------------------------
            # COPPER CLEARING with tools marked for CLEAR#
            # ----------------------------------------------------
            for tool in sorted_clear_tools:
                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                if not run_threaded:
                    QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                                    )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                # ----------------------------------------------------
                # store here the geometry generated by clear operation
                # ----------------------------------------------------
                cleared_geo = []

                # ----------------------------------------------------
                # find the current tool_uid
                # ----------------------------------------------------
                tool_uid = 0
                for k, v in self.ncc_tools.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool)):
                        tool_uid = int(k)
                        break

                # ----------------------------------------------------
                # parameters that are particular to the current tool
                # ----------------------------------------------------
                ncc_overlap = float(self.ncc_tools[tool_uid]["data"]["tools_ncc_overlap"]) / 100.0
                ncc_method = self.ncc_tools[tool_uid]["data"]["tools_ncc_method"]
                ncc_connect = self.ncc_tools[tool_uid]["data"]["tools_ncc_connect"]
                ncc_contour = self.ncc_tools[tool_uid]["data"]["tools_ncc_contour"]
                has_offset = self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_choice"]
                ncc_offset = float(self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_value"])

                # ----------------------------------------------------
                # Area to clear
                # ----------------------------------------------------
                result = self.get_tool_empty_area(name=name, ncc_obj=ncc_obj, geo_obj=geo_obj, isotooldia=isotd_list,
                                                  ncc_margin=ncc_margin, has_offset=has_offset, ncc_offset=ncc_offset,
                                                  tools_storage=tools_storage, bounding_box=bbox)
                area, warning_flag = result

                if area == "fail":
                    self.app.log.debug("Failed to create empty area for this tool.")
                    continue

                tool_empty_area = flatten_shapely_geometry(area)
                if not tool_empty_area:
                    continue

                # variables to display the percentage of work done
                old_disp_number = 0
                geo_len = len(tool_empty_area)
                self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                # ----------------------------------------------------
                # Copper-clear the Polygons in the non-copper-area
                # Iterate over them
                # ----------------------------------------------------
                pol_nr = 0
                for p in tool_empty_area:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    if not run_threaded:
                        QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace

                    # ----------------------------------------------------
                    # attempt to fix possible problems with the polygon
                    # ----------------------------------------------------
                    p = p.buffer(0.0000001)
                    p = flatten_shapely_geometry(p, simplify_tolerance=simplification_value)

                    poly_failed = 0
                    for pol in p:
                        # provide the app with a way to process the GUI events when in a blocking loop
                        QtWidgets.QApplication.processEvents()

                        if pol is not None and pol.is_valid and isinstance(pol, Polygon):
                            # ----------------------------------------------------
                            # This is where copper clearing is happening
                            # ----------------------------------------------------
                            res = self.clear_polygon_worker(pol=pol, tooldia=tool,
                                                            ncc_method=ncc_method,
                                                            ncc_overlap=ncc_overlap,
                                                            ncc_connect=ncc_connect,
                                                            ncc_contour=ncc_contour,
                                                            simplify_tol=simplification_value,
                                                            prog_plot=prog_plot)
                            if res is not None:
                                cleared_geo += res
                            else:
                                poly_failed += 1
                        else:
                            self.app.log.warning(
                                "Expected geo is a Polygon. Instead got a %s" % str(type(pol)))

                        pol_nr += 1
                        disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                        if old_disp_number < disp_number <= 100:
                            self.app.proc_container.update_view_text(' %d%%' % disp_number)
                            old_disp_number = disp_number

                    if poly_failed > 0:
                        app_obj.poly_not_cleared = True

                # ---------------------------------------------------------
                # Debug message regarding how many points are in the result
                # ---------------------------------------------------------
                l_coords = 0
                for i in range(len(cleared_geo)):
                    l_coords += len(cleared_geo[i].coords)
                self.app.log.debug(
                    "NCC Tool.ncc_handler.gen_clear_area() -> Number of cleared geo coords: %s" % str(l_coords))

                # -----------------------------------------------------------
                # check if there is a geometry at all in the cleared geometry
                # -----------------------------------------------------------
                if cleared_geo:
                    formatted_tool = self.app.dec_format(tool, self.decimals)
                    # find the tooluid associated with the current tool_dia so we know where to add the tool
                    # solid_geometry
                    for k, v in tools_storage.items():
                        if self.app.dec_format(v['tooldia'], self.decimals) == formatted_tool:
                            current_uid = int(k)

                            # add the solid_geometry to the current too in self.paint_tools dictionary
                            # and then reset the temporary list that stored that solid_geometry
                            v['solid_geometry'] = deepcopy(cleared_geo)
                            v['data']['name'] = name
                            geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                            break
                else:
                    self.app.log.debug("There are no geometries in the cleared polygon.")

            # ----------------------------------------------------
            # clean the progressive plotted shapes if it was used
            # ----------------------------------------------------
            if self.app.options["tools_ncc_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # ----------------------------------------------------
            # delete tools with empty geometry
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            # ----------------------------------------------------
            for uid, uid_val in list(tools_storage.items()):
                try:
                    # if the solid_geometry (type=list) is empty
                    if not uid_val['solid_geometry']:
                        msg = '%s %s: %s %s: %s' % (
                            _("Could not use the tool for copper clear."),
                            _("Tool"),
                            str(uid),
                            _("with diameter"),
                            str(uid_val['tooldia']))
                        self.app.inform.emit(msg)
                        self.app.log.debug(
                            "Empty geometry for tool: %s with diameter: %s" % (str(uid), str(uid_val['tooldia'])))
                        tools_storage.pop(uid, None)
                except KeyError:
                    tools_storage.pop(uid, None)

            geo_obj.obj_options["tools_mill_tooldia"] = str(tool)

            geo_obj.multigeo = True
            geo_obj.tools = dict(tools_storage)

            # make sure to use the default tool cut depth from the NCC parameters as milling tool cut depth
            for k, v in geo_obj.tools.items():
                v["data"]["tools_mill_cutz"] = app_obj.options["tools_ncc_cutz"]

            # -------------------------------------------------------------------------------------------------
            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            # -------------------------------------------------------------------------------------------------
            has_solid_geo = 0
            for tid in geo_obj.tools:
                if geo_obj.tools[tid]['solid_geometry']:
                    has_solid_geo += 1
            if has_solid_geo == 0:
                msg = '[ERROR] %s' % _("There is no NCC Geometry in the file.\n"
                                       "Usually it means that the tool diameter is too big for the painted geometry.\n"
                                       "Change the painting parameters and try again.")
                app_obj.inform.emit(msg)
                return 'fail'

            # ----------------------------------------------------------------
            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            # ----------------------------------------------------------------
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool clear all done."))
                else:
                    self.app.inform.emit('[WARNING] %s: %s %s.' % (
                        _("NCC Tool clear all done but the copper features isolation is broken for"),
                        str(warning_flag),
                        _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tool_id in geo_obj.tools:
                    if geo_obj.tools[tool_id]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tool_id]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tool_id]['solid_geometry'])
            else:
                # I will use this variable for this purpose, although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

            # # Experimental...
            # # print("Indexing...", end=' ')
            # # geo_obj.make_index()

        # ###########################################################################################
        # Initializes the new geometry object for the case of the rest-machining ####################
        # ###########################################################################################
        def gen_clear_area_rest(geo_obj, app_obj):
            app_obj.log.debug("NCC Tool. Rest machining copper clearing task started.")
            app_obj.inform.emit(_("NCC Tool. Rest machining copper clearing task started."))

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            sorted_clear_tools.sort(reverse=True)

            # re purposed flag for final object, geo_obj. True if it has any solid_geometry, False if not.
            app_obj.poly_not_cleared = True

            if ncc_select == 2:     # Reference Object
                env_obj, box_obj_kind = self.calculate_bounding_box(
                    ncc_obj=ncc_obj, box_obj=sel_obj, ncc_select=ncc_select)
            else:
                env_obj, box_obj_kind = self.calculate_bounding_box(ncc_obj=ncc_obj, ncc_select=ncc_select)

            if env_obj is None and box_obj_kind is None:
                self.app.inform.emit("[ERROR_NOTCL] %s" % _("NCC Tool failed creating bounding box."))
                return "fail"

            # log.debug("NCC Tool. Calculate 'empty' area.")
            # app_obj.inform.emit("NCC Tool. Calculate 'empty' area.")

            # Bounding box for current tool
            ncc_margin = self.ui.ncc_margin_entry.get_value()
            bbox = self.apply_margin_to_bounding_box(bbox=env_obj, box_kind=box_obj_kind,
                                                     ncc_select=ncc_select, ncc_margin=ncc_margin)

            ncc_connect = self.ui.rest_ncc_connect_cb.get_value()
            ncc_contour = self.ui.rest_ncc_contour_cb.get_value()
            has_offset = self.ui.rest_ncc_choice_offset_cb.get_value()
            ncc_offset = self.ui.rest_ncc_offset_spinner.get_value()

            # Area to clear
            area, warning_flag = self.get_tool_empty_area(name=name, ncc_obj=ncc_obj, geo_obj=geo_obj,
                                                          isotooldia=isotd_list,
                                                          has_offset=has_offset, ncc_offset=ncc_offset,
                                                          ncc_margin=ncc_margin, tools_storage=tools_storage,
                                                          bounding_box=bbox)

            # for testing purposes ----------------------------------
            # for po in area.geoms:
            #     self.app.tool_shapes.add(po, color=self.app.options['global_sel_line'],
            #                              face_color=self.app.options['global_sel_line'],
            #                              update=True, layer=0, tolerance=None)
            # -------------------------------------------------------

            # Generate area for each tool
            while sorted_clear_tools:
                tool = sorted_clear_tools.pop(0)

                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                                    )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool_uid = 0    # find the current tool_uid
                for k, v in self.ncc_tools.items():
                    if self.app.dec_format(v['tooldia'], self.decimals) == self.app.dec_format(tool, self.decimals):
                        tool_uid = int(k)
                        break

                tool_data_dict = self.ncc_tools[tool_uid]["data"]

                # parameters that are particular to the current tool
                ncc_overlap = float(tool_data_dict["tools_ncc_overlap"]) / 100.0
                ncc_method = tool_data_dict["tools_ncc_method"]

                # variables to display the percentage of work done
                geo_len = len(area.geoms)
                old_disp_number = 0
                self.app.log.warning("Total number of polygons to be cleared: %s" % str(geo_len))

                # def random_color():
                #     r_color = np.random.rand(4)
                #     r_color[3] = 0.5
                #     return r_color

                # store here the geometry generated by clear operation
                cleared_geo = []

                tool_empty_area = []
                if area.geoms:
                    tool_empty_area = flatten_shapely_geometry(area.geoms)

                if tool_empty_area:
                    poly_failed = 0
                    pol_nr = 0
                    for p in tool_empty_area:
                        # provide the app with a way to process the GUI events when in a blocking loop
                        if not run_threaded:
                            QtWidgets.QApplication.processEvents()

                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise grace

                        if p is not None and p.is_valid and not p.is_empty:
                            # provide the app with a way to process the GUI events when in a blocking loop
                            QtWidgets.QApplication.processEvents()

                            # speedup the clearing by not trying to clear polygons that is obvious they can't be
                            # cleared with the current tool. this tremendously reduce the clearing time
                            check_dist = -tool / 2
                            check_buff = p.buffer(check_dist, self.circle_steps)
                            check_buff = flatten_shapely_geometry(check_buff, simplify_tolerance=simplification_value)
                            if not check_buff:
                                continue

                            # if self.app.dec_format(float(tool), self.decimals) == 0.15:
                            #     # for testing purposes ----------------------------------
                            #     self.app.tool_shapes.add(p, color=self.app.options['global_sel_line'],
                            #                              face_color=random_color(),
                            #                              update=True, layer=0, tolerance=None)
                            #     self.app.tool_shapes.add(check_buff, color=self.app.options['global_sel_line'],
                            #                              face_color='#FFFFFFFF',
                            #                              update=True, layer=0, tolerance=None)
                            #     # -------------------------------------------------------

                            # actual copper clearing is done here
                            if isinstance(p, Polygon):
                                res = self.clear_polygon_worker(pol=p, tooldia=tool,
                                                                ncc_method=ncc_method,
                                                                ncc_overlap=ncc_overlap,
                                                                ncc_connect=ncc_connect,
                                                                ncc_contour=ncc_contour,
                                                                simplify_tol=simplification_value,
                                                                prog_plot=prog_plot)

                                if res is not None:
                                    cleared_geo += res
                                else:
                                    poly_failed += 1
                            else:
                                self.app.log.warning("Expected geo is a Polygon. Instead got a %s" % str(type(p)))

                            if poly_failed > 0:
                                app_obj.poly_not_cleared = True

                            pol_nr += 1
                            disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                            # log.debug("Polygons cleared: %d" % pol_nr)

                            if old_disp_number < disp_number <= 100:
                                self.app.proc_container.update_view_text(' %d%%' % disp_number)
                                old_disp_number = disp_number
                                # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                    if self.app.abort_flag:
                        raise grace     # graceful abort requested by the user

                    # check if there is a geometry at all in the cleared geometry
                    if cleared_geo:
                        tools_storage[tool_uid]["solid_geometry"] = deepcopy(cleared_geo)
                        tools_storage[tool_uid]["data"]["name"] = name + '_' + str(tool)
                        geo_obj.tools[tool_uid] = dict(tools_storage[tool_uid])
                    else:
                        app_obj.log.debug("There are no geometries in the cleared polygon.")

                    app_obj.log.warning("Total number of polygons failed to be cleared: %s" % str(poly_failed))
                else:
                    app_obj.log.warning("The area to be cleared has no polygons.")

                l_coords = 0
                for i in range(len(cleared_geo)):
                    l_coords += len(cleared_geo[i].coords)
                self.app.log.debug(
                    "NCC Tool.ncc_handler.gen_clear_area_rest() -> Number of cleared geo coords: %s" % str(l_coords))

                # # Area to clear next
                # try:
                #     # buffered_cleared = unary_union(cleared_geo).buffer(tool / 2.0)
                #     # area = area.difference(buffered_cleared)
                #     area = area.difference(unary_union(cleared_geo))
                # except Exception as e:
                #     self.app.log.error("Creating new area failed due of: %s" % str(e))

                if not cleared_geo:
                    break
                buffered_cleared_geo = [line.buffer(tool / 2) for line in cleared_geo]
                buffered_cleared_geo = flatten_shapely_geometry(buffered_cleared_geo)
                if not buffered_cleared_geo:
                    break
                try:
                    new_area = MultiPolygon(buffered_cleared_geo)
                except Exception as err:
                    self.app.log.error("ToolNcc.ncc_handler.gen_clear_area_rest() Buffering -> %s" % str(err))
                    self.app.log.debug(
                        "ToolNcc.ncc_handler.gen_clear_area_rest() Buffering -> %s" % str(traceback.format_exc())
                    )
                    return
                new_area = new_area.buffer(0.0000001)

                area = area.difference(new_area)
                area = flatten_shapely_geometry(area, simplify_tolerance=simplification_value)

                new_area = [pol for pol in area if pol.is_valid and not pol.is_empty]
                area = MultiPolygon(new_area)

                # speedup the clearing by not trying to clear polygons that is clear they can't be
                # cleared with any tool. this tremendously reduce the clearing time
                # found_poly_to_clear = False
                # for t in sorted_clear_tools:
                #     check_dist = -t / 2.000000001
                #     for pl in area:
                #         check_buff = pl.buffer(check_dist)
                #         if not check_buff or check_buff.is_empty or not check_buff.is_valid:
                #             continue
                #         else:
                #             found_poly_to_clear = True
                #             break
                #     if found_poly_to_clear is True:
                #         break
                #
                # if found_poly_to_clear is False:
                #     log.warning("The area to be cleared no longer has polygons. Finishing.")
                #     break

                if not area or area.is_empty:
                    break

                # # try to clear the polygons
                # buff_distance = 0.0
                # try:
                #     new_area = [p.buffer(buff_distance) for p in area if not p.is_empty]
                # except TypeError:
                #     new_area = [area.buffer(tool * ncc_overlap)]
                # area = unary_union(area)

            geo_obj.multigeo = True
            geo_obj.obj_options["tools_mill_tooldia"] = '0.0'

            # make sure to use the default tool cut depth from the NCC parameters as milling tool cut depth
            for k, v in geo_obj.tools.items():
                v["data"]["tools_mill_cutz"] = app_obj.options["tools_ncc_cutz"]

            # clean the progressive plotted shapes if it was used
            if self.app.options["tools_ncc_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool Rest Machining clear all done."))
                else:
                    self.app.inform.emit(
                        '[WARNING] %s: %s %s.' % (_("NCC Tool Rest Machining clear all done but the copper features "
                                                    "isolation is broken for"), str(warning_flag), _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tool_uid in geo_obj.tools:
                    if geo_obj.tools[tool_uid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tool_uid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tool_uid]['solid_geometry'])
            else:
                # I will use this variable for this purpose, although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

        # ###########################################################################################
        # Create the Job function and send it to the worker to be processed in another thread #######
        # ###########################################################################################
        def job_thread(a_obj):
            try:
                if rest_machining_choice is True:
                    a_obj.app_obj.new_object("geometry", name, gen_clear_area_rest, autoselected=False)
                else:
                    a_obj.app_obj.new_object("geometry", name, gen_clear_area, autoselected=False)
            except grace:
                if run_threaded:
                    proc.done()
                return
            except Exception:
                if run_threaded:
                    proc.done()
                traceback.print_stack()
                return

            if run_threaded:
                proc.done()
            else:
                a_obj.proc_container.view.set_idle()

            # focus on Properties Tab
            # self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)

        if run_threaded:
            # Promise object with the new name
            self.app.collection.promise(name)

            # Background
            self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})
        else:
            job_thread(a_obj=self.app)

    def clear_copper_tcl(
            self,
            ncc_obj,
            sel_obj=None,
            ncc_tooldia=None,
            iso_tooldia=None,
            margin=None,
            has_offset=None,
            offset=None,
            select_method=None,
            outname=None,
            overlap=None,
            connect=None,
            contour=None,
            order=None,
            method=None,
            rest=None,
            tools_storage=None,
            plot=True,
            run_threaded=False,
    ):
        """
        Clear the excess copper from the entire object. To be used only in a TCL command.

        :param ncc_obj:         ncc cleared object
        :param sel_obj:
        :param ncc_tooldia:     a tuple or single element made out of diameters of the tools to be used to ncc clear
        :param iso_tooldia:     a tuple or single element made out of diameters of the tools to be used for isolation
        :param overlap:         value by which the paths will overlap
        :param order:           if the tools are ordered and how
        :param select_method:   if to do ncc on the whole object, on a defined area or on an area defined by
                                another object
        :param has_offset:      True if an offset is needed
        :param offset:          distance from the copper features where the copper clearing is stopping
        :param margin:          a border around cleared area
        :param outname:         name of the resulting object
        :param connect:         Connect lines to avoid tool lifts.
        :param contour:         Clear around the edges.
        :param method:          choice out of 'seed', 'normal', 'lines'
        :param rest:            True if to use rest-machining
        :param tools_storage:   whether to use the current tools_storage self.ncc_tools or a different one.
                                Usage of the different one is related to when this function is called from a
                                TcL command.
        :param plot:            if True after the job is finished the result will be plotted, else it will not.
        :param run_threaded:    If True the method will be run in a threaded way suitable for GUI usage;
                                if False it will run non-threaded for TclShell usage
        :return:
        """
        if run_threaded:
            proc = self.app.proc_container.new('%s...' % _("Working"))
        else:
            self.app.proc_container.view.set_busy('%s...' % _("Working"))
            QtWidgets.QApplication.processEvents()

        # #####################################################################
        # ####### Read the parameters #########################################
        # #####################################################################

        units = self.app.app_units

        self.app.log.debug("NCC Tool started. Reading parameters.")
        self.app.inform.emit(_("NCC Tool started. Reading parameters."))

        ncc_method = method
        ncc_margin = margin
        ncc_select = select_method
        overlap = overlap

        connect = connect
        contour = contour
        order = order

        if tools_storage is not None:
            tools_storage = tools_storage
        else:
            tools_storage = self.ncc_tools

        ncc_offset = 0.0
        if has_offset is True:
            ncc_offset = offset

        # ######################################################################################################
        # # Read the tooldia parameter and create a sorted list out them - they may be more than one diameter ##
        # ######################################################################################################
        sorted_tools = []
        try:
            sorted_tools = [float(eval(dia)) for dia in ncc_tooldia.split(",") if dia != '']
        except AttributeError:
            if not isinstance(ncc_tooldia, list):
                sorted_tools = [float(ncc_tooldia)]
            else:
                sorted_tools = ncc_tooldia

        if not sorted_tools:
            return 'fail'

        # ##############################################################################################################
        # Prepare non-copper polygons. Create the bounding box area from which the copper features will be subtracted ##
        # ##############################################################################################################
        self.app.log.debug("NCC Tool. Preparing non-copper polygons.")
        self.app.inform.emit(_("NCC Tool. Preparing non-copper polygons."))

        try:
            if sel_obj is None or sel_obj == 0:     # sel_obj == 'itself'
                ncc_sel_obj = ncc_obj
            else:
                ncc_sel_obj = sel_obj
        except Exception as e:
            self.app.log.error("ToolNcc.ncc_handler() --> %s" % str(e))
            return 'fail'

        bounding_box = None
        if ncc_select == 0:     # itself
            geo_n = flatten_shapely_geometry(ncc_sel_obj.solid_geometry)

            try:
                if len(geo_n) == 1:
                    env_obj = unary_union(geo_n)
                else:
                    env_obj = unary_union(geo_n)
                    env_obj = env_obj.convex_hull
                bounding_box = env_obj.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            except Exception as e:
                self.app.log.error("ToolNcc.ncc_handler() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return 'fail'

        elif ncc_select == 1:   # area
            geo_n = unary_union(self.sel_rect)
            geo_n = flatten_shapely_geometry(geo_n)

            geo_buff_list = []
            for poly in geo_n:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace
                geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

            bounding_box = unary_union(geo_buff_list)

        elif ncc_select == 2:   # Reference Object
            geo_n = ncc_sel_obj.solid_geometry
            if ncc_sel_obj.kind == 'geometry':
                geo_buff_list = []
                geo_n = flatten_shapely_geometry(geo_n)
                for poly in geo_n:
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

                bounding_box = unary_union(geo_buff_list)
            elif ncc_sel_obj.kind == 'gerber':
                geo_n = unary_union(geo_n).convex_hull
                bounding_box = unary_union(ncc_sel_obj.solid_geometry).convex_hull.intersection(geo_n)
                bounding_box = bounding_box.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        self.app.log.debug("NCC Tool. Finished non-copper polygons.")
        # ########################################################################################################
        # set the name for the future Geometry object
        # I do it here because it is also stored inside the gen_clear_area() and gen_clear_area_rest() methods
        # ########################################################################################################
        rest_machining_choice = rest
        if rest_machining_choice is True:
            name = outname if outname is not None else self.obj_name + "_ncc_rm"
        else:
            name = outname if outname is not None else self.obj_name + "_ncc"

        # ##########################################################################################
        # Initializes the new geometry object ######################################################
        # ##########################################################################################
        def gen_clear_area(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            self.app.log.debug("NCC Tool. Normal copper clearing task started.")
            self.app.inform.emit(_("NCC Tool. Finished non-copper polygons. Normal copper clearing task started."))

            # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
            # will store the number of tools for which the isolation is broken
            warning_flag = 0

            if order == 1:  # "Forward"
                sorted_tools.sort(reverse=False)
            elif order == 2:    # "Reverse"
                sorted_tools.sort(reverse=True)
            else:
                pass

            cleared_geo = []
            # Already cleared area
            cleared = MultiPolygon()

            # flag for polygons not cleared
            app_obj.poly_not_cleared = False

            # Generate area for each tool
            offset_a = sum(sorted_tools)
            current_uid = int(1)
            # try:
            #     tool = eval(self.app.options["tools_ncc_tools"])[0]
            # except TypeError:
            #     tool = eval(self.app.options["tools_ncc_tools"])

            # ###################################################################################################
            # Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry ##
            # ###################################################################################################
            self.app.log.debug("NCC Tool. Calculate 'empty' area.")
            self.app.inform.emit(_("NCC Tool. Calculate 'empty' area."))

            if ncc_obj.kind == 'gerber' and not iso_tooldia:
                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.options['gerber_buffering'] == 'no':
                    sol_geo = ncc_obj.solid_geometry.buffer(0)
                else:
                    sol_geo = ncc_obj.solid_geometry
                    if isinstance(sol_geo, list):
                        sol_geo = unary_union(sol_geo)

                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))

                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            elif ncc_obj.kind == 'gerber' and iso_tooldia:
                isolated_geo = []

                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.options['gerber_buffering'] == 'no':
                    self.solid_geometry = ncc_obj.solid_geometry.buffer(0)
                else:
                    self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.app.options["tools_ncc_milling_type"]

                for tool_iso in iso_tooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso / 2, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso / 2, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        if ncc_margin < tool_iso:
                            app_obj.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                         "than isolation tool diameter."))
                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for a_poly in geo_elem.geoms:
                                        for ring in self.poly2rings(a_poly):
                                            new_geo = ring.intersection(bounding_box)
                                            if new_geo and not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(geo_elem, LineString):
                                    new_geo = geo_elem.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiLineString):
                                    for line_elem in geo_elem.geoms:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                        except TypeError:
                            if isinstance(isolated_geo, Polygon):
                                for ring in self.poly2rings(isolated_geo):
                                    new_geo = ring.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                            elif isinstance(isolated_geo, LineString):
                                new_geo = isolated_geo.intersection(bounding_box)
                                if new_geo and not new_geo.is_empty:
                                    new_geometry.append(new_geo)
                            elif isinstance(isolated_geo, MultiLineString):
                                for line_elem in isolated_geo.geoms:
                                    new_geo = line_elem.intersection(bounding_box)
                                    if new_geo and not new_geo.is_empty:
                                        new_geometry.append(new_geo)

                        # a MultiLineString geometry element will show that the isolation is broken for this tool
                        for geo_e in new_geometry:
                            if type(geo_e) == MultiLineString:
                                warning_flag += 1
                                break

                        for k, v in tools_storage.items():
                            if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                tool_iso)):
                                current_uid = int(k)
                                # add the solid_geometry to the current too in self.paint_tools dictionary
                                # and then reset the temporary list that stored that solid_geometry
                                v['solid_geometry'] = deepcopy(new_geometry)
                                v['data']['name'] = name
                                break
                        geo_obj.tools[current_uid] = dict(tools_storage[current_uid])

                sol_geo = unary_union(isolated_geo)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(
                    target=sol_geo,     # noqa
                    boundary=bounding_box,
                )
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Isolation geometry is broken. Margin is less than isolation tool diameter."))
                    return 'fail'

            elif ncc_obj.kind == 'geometry':
                sol_geo = unary_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit(
                        '[success] %s ...' % _("Buffering finished")
                    )
                empty = self.get_ncc_empty_area(
                    target=sol_geo,     # noqa
                    boundary=bounding_box,
                )
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit(
                        '[ERROR_NOTCL] %s' % _("Could not get the extent of the area to be non copper cleared.")
                    )
                    return 'fail'

            else:
                app_obj.inform.emit(
                    '[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.')
                )
                return 'fail'

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            self.app.log.debug("NCC Tool. Finished calculation of 'empty' area.")
            self.app.inform.emit(_("NCC Tool. Finished calculation of 'empty' area."))

            tool = 1
            # COPPER CLEARING #
            for tool in sorted_tools:
                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                                    )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                cleared_geo[:] = []

                # Get remaining tools offset
                offset_a -= (tool - 1e-12)

                # Area to clear
                area = empty.buffer(-offset_a)
                try:
                    area = area.difference(cleared)
                except Exception:
                    continue

                area = flatten_shapely_geometry(area)

                # variables to display the percentage of work done
                geo_len = len(area)

                old_disp_number = 0
                self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if not area:
                    continue

                pol_nr = 0
                for p in area:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace

                    # clean the polygon
                    p = p.buffer(0)

                    if p and p.is_valid:
                        poly_processed = []
                        if isinstance(p, Polygon):
                            if ncc_method == 0:  # standard
                                cp = self.parent_tool.clear_polygon_shrink(
                                    p,
                                    tool,
                                    self.circle_steps,
                                    overlap=overlap,
                                    contour=contour,
                                    connect=connect,
                                    prog_plot=False,
                                )
                            elif ncc_method == 1:  # seed
                                cp = self.parent_tool.clear_polygon_seed(
                                    p, tool, self.circle_steps,
                                    overlap=overlap,
                                    contour=contour,
                                    connect=connect,
                                    prog_plot=False,
                                )
                            else:
                                cp = self.parent_tool.clear_polygon_lines(
                                    p, tool, self.circle_steps,
                                    overlap=overlap,
                                    contour=contour,
                                    connect=connect,
                                    prog_plot=False,
                                )
                            if cp:
                                cleared_geo += list(cp.get_objects())
                                poly_processed.append(True)
                            else:
                                poly_processed.append(False)
                                self.app.log.warning("Polygon can not be cleared.")
                        else:
                            self.app.log.warning("Geo can not be cleared because it is: %s" % str(type(p)))

                        p_cleared = poly_processed.count(True)
                        p_not_cleared = poly_processed.count(False)

                        if p_not_cleared:
                            app_obj.poly_not_cleared = True

                        if p_cleared == 0:
                            continue

                        pol_nr += 1
                        disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                        # log.debug("Polygons cleared: %d" % pol_nr)

                        if old_disp_number < disp_number <= 100:
                            self.app.proc_container.update_view_text(' %d%%' % disp_number)
                            old_disp_number = disp_number
                            # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                    # check if there is a geometry at all in the cleared geometry
                if cleared_geo:
                    # Overall cleared area
                    cleared = empty.buffer(-offset_a * (1 + overlap)).buffer(-tool / 1.999999).buffer(
                        tool / 1.999999)

                    # clean-up cleared geo
                    cleared = cleared.buffer(0)

                    # find the tooluid associated with the current tool_dia so we know where to add the tool
                    # solid_geometry
                    for k, v in tools_storage.items():
                        if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                            tool)):
                            current_uid = int(k)

                            # add the solid_geometry to the current too in self.paint_tools dictionary
                            # and then reset the temporary list that stored that solid_geometry
                            v['solid_geometry'] = flatten_shapely_geometry(cleared_geo)
                            v['data']['name'] = name
                            break
                    geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                else:
                    app_obj.log.debug("There are no geometries in the cleared polygon.")

            # delete tools with empty geometry
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid, uid_val in list(tools_storage.items()):
                try:
                    # if the solid_geometry (type=list) is empty
                    if not uid_val['solid_geometry']:
                        tools_storage.pop(uid, None)
                except KeyError:
                    tools_storage.pop(uid, None)

            geo_obj.obj_options["tools_mill_tooldia"] = str(tool)

            geo_obj.multigeo = True
            geo_obj.tools.clear()
            geo_obj.tools = dict(tools_storage)

            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            has_solid_geo = 0
            for tooluid in geo_obj.tools:
                if geo_obj.tools[tooluid]['solid_geometry']:
                    has_solid_geo += 1
            if has_solid_geo == 0:
                app_obj.inform.emit('[ERROR] %s' %
                                    _("There is no NCC Geometry in the file.\n"
                                      "Usually it means that the tool diameter is too big for the painted geometry.\n"
                                      "Change the painting parameters and try again."))
                return 'fail'

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool clear all done."))
                else:
                    self.app.inform.emit('[WARNING] %s: %s %s.' % (
                        _("NCC Tool clear all done but the copper features isolation is broken for"),
                        str(warning_flag),
                        _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tooluid in geo_obj.tools:
                    if geo_obj.tools[tooluid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tooluid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tooluid]['solid_geometry'])
            else:
                # I will use this variable for this purpose, although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

        # ###########################################################################################
        # Initializes the new geometry object for the case of the rest-machining ####################
        # ###########################################################################################
        def gen_clear_area_rest(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

            app_obj.log.debug("NCC Tool. Rest machining copper clearing task started.")
            app_obj.inform.emit('_(NCC Tool. Rest machining copper clearing task started.')

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
            # will store the number of tools for which the isolation is broken
            warning_flag = 0

            sorted_tools.sort(reverse=True)

            cleared_geo = []
            cleared_by_last_tool = []
            rest_geo = []
            current_uid = 1
            try:
                tool = eval(str(self.app.options["tools_ncc_tools"]))[0]
            except TypeError:
                tool = eval(self.app.options["tools_ncc_tools"])

            # repurposed flag for final object, geo_obj. True if it has any solid_geometry, False if not.
            app_obj.poly_not_cleared = True
            app_obj.log.debug("NCC Tool. Calculate 'empty' area.")
            app_obj.inform.emit("NCC Tool. Calculate 'empty' area.")

            # ###################################################################################################
            # Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry ##
            # ###################################################################################################
            if ncc_obj.kind == 'gerber' and not iso_tooldia:
                sol_geo = ncc_obj.solid_geometry
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            elif ncc_obj.kind == 'gerber' and iso_tooldia:
                isolated_geo = []
                self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.app.options["tools_ncc_milling_type"]

                for tool_iso in iso_tooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        app_obj.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                     "than isolation tool diameter."))

                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for poly_g in geo_elem.geoms:
                                        for ring in self.poly2rings(poly_g):
                                            new_geo = ring.intersection(bounding_box)
                                            if new_geo and not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(geo_elem, LineString):
                                    new_geo = geo_elem.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiLineString):
                                    for line_elem in geo_elem.geoms:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                        except TypeError:
                            try:
                                if isinstance(isolated_geo, Polygon):
                                    for ring in self.poly2rings(isolated_geo):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo:
                                            if not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(isolated_geo, LineString):
                                    new_geo = isolated_geo.intersection(bounding_box)
                                    if new_geo and not new_geo.is_empty:
                                        new_geometry.append(new_geo)
                                elif isinstance(isolated_geo, MultiLineString):
                                    for line_elem in isolated_geo.geoms:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                            except Exception:
                                pass

                        # a MultiLineString geometry element will show that the isolation is broken for this tool
                        for geo_e in new_geometry:
                            if type(geo_e) == MultiLineString:
                                warning_flag += 1
                                break

                        for k, v in tools_storage.items():
                            if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                tool_iso)):
                                current_uid = int(k)
                                # add the solid_geometry to the current too in self.paint_tools dictionary
                                # and then reset the temporary list that stored that solid_geometry
                                v['solid_geometry'] = deepcopy(new_geometry)
                                v['data']['name'] = name
                                break
                        geo_obj.tools[current_uid] = dict(tools_storage[current_uid])

                sol_geo = unary_union(isolated_geo)
                if has_offset is True:
                    app_obj.inform.emit(
                        '[WARNING_NOTCL] %s ...' % _("Buffering")
                    )
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit(
                        '[success] %s ...' % _("Buffering finished")
                    )
                empty = self.get_ncc_empty_area(
                    target=sol_geo,     # noqa
                    boundary=bounding_box
                )
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit(
                        '[ERROR_NOTCL] %s' % _("Isolation geometry is broken. "
                                               "Margin is less than isolation tool diameter.")
                    )
                    return 'fail'

            elif ncc_obj.kind == 'geometry':
                sol_geo = unary_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(
                    target=sol_geo,     # noqa
                    boundary=bounding_box,
                )
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            else:
                app_obj.inform.emit('[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.'))
                return

            if self.app.abort_flag:
                # graceful abort requested by the user
                raise grace

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            area = empty.buffer(0)

            app_obj.log.debug("NCC Tool. Finished calculation of 'empty' area.")
            app_obj.inform.emit("NCC Tool. Finished calculation of 'empty' area.")

            # Generate area for each tool
            while sorted_tools:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                tool = sorted_tools.pop(0)
                self.app.log.debug("Starting geometry processing for tool: %s" % str(tool))

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                                    )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool_used = tool - 1e-12
                cleared_geo[:] = []

                # Area to clear
                for poly_r in cleared_by_last_tool:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    try:
                        area = area.difference(poly_r)
                    except Exception:
                        pass
                cleared_by_last_tool[:] = []

                # Transform area to MultiPolygon
                if type(area) is Polygon:
                    area = MultiPolygon([area])

                # add the rest that was not cleared previously; area is a MultyPolygon
                # and rest_geo it's a list
                allparts = [p.buffer(0) for p in area.geoms]
                allparts += deepcopy(rest_geo)
                rest_geo[:] = []
                area = MultiPolygon(deepcopy(allparts))
                allparts[:] = []

                # variables to display the percentage of work done
                geo_len = len(area.geoms)
                old_disp_number = 0
                self.app.log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if area.geoms:
                    if len(area.geoms) > 0:
                        pol_nr = 0
                        for p in area.geoms:
                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise grace

                            # clean the polygon
                            p = p.buffer(0)

                            if p is not None and p.is_valid:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if isinstance(p, Polygon):
                                    try:
                                        if ncc_method == 0:     # standard
                                            cp = self.parent_tool.clear_polygon_shrink(
                                                p,
                                                tool_used,
                                                self.circle_steps,
                                                overlap=overlap,
                                                contour=contour,
                                                connect=connect,
                                                prog_plot=False,
                                            )
                                        elif ncc_method == 1:   # seed
                                            cp = self.parent_tool.clear_polygon_seed(
                                                p,
                                                tool_used,
                                                self.circle_steps,
                                                overlap=overlap,
                                                contour=contour,
                                                connect=connect,
                                                prog_plot=False,
                                            )
                                        else:
                                            cp = self.parent_tool.clear_polygon_lines(
                                                p,
                                                tool_used,
                                                self.circle_steps,
                                                overlap=overlap,
                                                contour=contour,
                                                connect=connect,
                                                prog_plot=False,
                                            )
                                        cleared_geo.append(list(cp.get_objects()))
                                    except Exception as ee:
                                        self.app.log.error("Polygon can't be cleared. %s" % str(ee))
                                        # this polygon should be added to a list and then try clear it with
                                        # a smaller tool
                                        rest_geo.append(p)
                                elif isinstance(p, MultiPolygon):
                                    for poly_p in p.geoms:
                                        if poly_p is not None:
                                            # provide the app with a way to process the GUI events when
                                            # in a blocking loop
                                            QtWidgets.QApplication.processEvents()

                                            try:
                                                if ncc_method == 0:     # 'standard'
                                                    cp = self.parent_tool.clear_polygon_shrink(
                                                        poly_p,
                                                        tool_used,
                                                        self.circle_steps,
                                                        overlap=overlap, contour=contour,
                                                        connect=connect,
                                                        prog_plot=False,
                                                    )
                                                elif ncc_method == 1:   # 'seed'
                                                    cp = self.parent_tool.clear_polygon_seed(
                                                        poly_p,
                                                        tool_used,
                                                        self.circle_steps,
                                                        overlap=overlap, contour=contour,
                                                        connect=connect,
                                                        prog_plot=False,
                                                    )
                                                else:
                                                    cp = self.parent_tool.clear_polygon_lines(
                                                        poly_p,
                                                        tool_used,
                                                        self.circle_steps,
                                                        overlap=overlap, contour=contour,
                                                        connect=connect,
                                                        prog_plot=False,
                                                    )
                                                cleared_geo.append(list(cp.get_objects()))
                                            except Exception as eee:
                                                self.app.log.error("Polygon can't be cleared. %s" % str(eee))
                                                # this polygon should be added to a list and then try clear it with
                                                # a smaller tool
                                                rest_geo.append(poly_p)

                                pol_nr += 1
                                disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                                # log.debug("Polygons cleared: %d" % pol_nr)

                                if old_disp_number < disp_number <= 100:
                                    self.app.proc_container.update_view_text(' %d%%' % disp_number)
                                    old_disp_number = disp_number
                                    # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise grace

                        # check if there is a geometry at all in the cleared geometry
                        if cleared_geo:
                            # Overall cleared area
                            cleared_area = list(self.parent_tool.flatten_list(cleared_geo))

                            # cleared = MultiPolygon([p.buffer(tool_used / 2).buffer(-tool_used / 2)
                            #                         for p in cleared_area])

                            # here we store the poly's already processed in the original geometry by the current tool
                            # into cleared_by_last_tool list
                            # this will be sutracted from the original geometry_to_be_cleared and make data for
                            # the next tool
                            buffer_value = tool_used / 2
                            for p in cleared_area:
                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                r_poly = p.buffer(buffer_value)
                                cleared_by_last_tool.append(r_poly)

                            # find the tooluid associated with the current tool_dia so we know
                            # where to add the tool solid_geometry
                            for k, v in tools_storage.items():
                                if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                    tool)):
                                    current_uid = int(k)

                                    # add the solid_geometry to the current too in self.paint_tools dictionary
                                    # and then reset the temporary list that stored that solid_geometry
                                    v['solid_geometry'] = flatten_shapely_geometry(cleared_area)
                                    v['data']['name'] = name
                                    cleared_area[:] = []
                                    break

                            geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                        else:
                            app_obj.log.debug("There are no geometries in the cleared polygon.")

            geo_obj.multigeo = True
            geo_obj.obj_options["tools_mill_tooldia"] = str(tool)

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool Rest Machining clear all done."))
                else:
                    self.app.inform.emit(
                        '[WARNING] %s: %s %s.' % (_("NCC Tool Rest Machining clear all done but the copper features "
                                                    "isolation is broken for"), str(warning_flag), _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tooluid in geo_obj.tools:
                    if geo_obj.tools[tooluid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tooluid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tooluid]['solid_geometry'])
            else:
                # I will use this variable for this purpose, although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

        # ###########################################################################################
        # Create the Job function and send it to the worker to be processed in another thread #######
        # ###########################################################################################
        def job_thread(app_obj):
            try:
                if rest_machining_choice is True:
                    app_obj.app_obj.new_object("geometry", name, gen_clear_area_rest, plot=plot)
                else:
                    app_obj.app_obj.new_object("geometry", name, gen_clear_area, plot=plot)
            except grace:
                if run_threaded:
                    proc.done()
                return
            except Exception:
                if run_threaded:
                    proc.done()
                traceback.print_stack()
                return

            if run_threaded:
                proc.done()
            else:
                app_obj.proc_container.view.set_idle()

            # focus on Properties Tab
            self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)

        if run_threaded:
            # Promise object with the new name
            self.app.collection.promise(name)

            # Background
            self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})
        else:
            job_thread(app_obj=self.app)

    def get_ncc_empty_area(self, target, boundary=None):
        """
        Returns the complement of target geometry within
        the given boundary polygon. If not specified, it defaults to
        the rectangular bounding box of target geometry.

        :param target:      The geometry that is to be 'inverted'
        :param boundary:    A polygon that surrounds the entire solid geometry and from which we subtract in order to
                            create a "negative" geometry (geometry to be emptied of copper)
        :return:
        """
        if isinstance(target, (LineString, LinearRing, Polygon)):
            geo_len = 1
        elif isinstance(target, (MultiPolygon, MultiLineString)):
            geo_len = len(target.geoms)
        else:
            geo_len = len(target)

        if isinstance(target, list):
            target = MultiPolygon(target)

        pol_nr = 0
        old_disp_number = 0

        if boundary is None:
            boundary = target.envelope
        else:
            boundary = boundary

        try:
            ret_val = boundary.difference(target)
        except Exception:
            try:
                target_geoms = target.geoms if isinstance(target, MultiPolygon) else target
                for el in target_geoms:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace

                    boundary = boundary.difference(el)
                    pol_nr += 1
                    disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))

                    if old_disp_number < disp_number <= 100:
                        self.app.proc_container.update_view_text(' %d%%' % disp_number)
                        old_disp_number = disp_number
                return boundary
            except Exception:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Try to use the Buffering Type = Full in Preferences -> Gerber General. "
                                       "Reload the Gerber file after this change."))
                return 'fail'

        return ret_val

    @staticmethod
    def poly2rings(poly):
        return [poly.exterior] + [interior for interior in poly.interiors]

    def generate_envelope(
            self,
            offset,
            invert,
            envelope_iso_type=2,
    ):
        # isolation_geometry produces an envelope that is going on the left of the geometry
        # (the copper features). To leave the least amount of burrs on the features
        # the tool needs to travel on the right side of the features (this is called conventional milling)
        # the first pass is the one cutting all the features, so it needs to be reversed
        # the other passes overlap preceding ones and cut the leftover copper. It is better for them
        # to cut on the right side of the leftover copper i.e. on the left side of the features.
        try:
            geom = self.parent_tool.isolation_geometry(offset, iso_type=envelope_iso_type)
        except Exception as e:
            self.app.log.error('ToolNcc.generate_envelope() --> %s' % str(e))
            return 'fail'

        if invert:
            try:
                pl = []
                for p in geom:
                    if p is not None:
                        if isinstance(p, Polygon):
                            pl.append(Polygon(p.exterior.coords[::-1], p.interiors))
                        elif isinstance(p, LinearRing):
                            pl.append(Polygon(p.coords[::-1]))
                geom = MultiPolygon(pl)
            except TypeError:
                if isinstance(geom, Polygon) and geom is not None:
                    geom = Polygon(geom.exterior.coords[::-1], geom.interiors)
                elif isinstance(geom, LinearRing) and geom is not None:
                    geom = Polygon(geom.coords[::-1])
                else:
                    self.app.log.debug(
                        f"ToolNcc.generate_envelope() Error --> Unexpected Geometry {type(geom)}")
            except Exception as e:
                self.app.log.error(
                    f"ToolNcc.generate_envelope() Error --> {str(e)}"
                )
                return 'fail'
        return geom



from tclCommands.TclCommand import TclCommandSignaled

import collections

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class TclCommandOpenDXF(TclCommandSignaled):
    """
    Tcl shell command to open an DXF file as a Geometry/Gerber Object.
    """

    # array of all command aliases, to be able use  old names for backward compatibility (add_poly, add_polygon)
    aliases = ['open_dxf']

    description = '%s %s' % ("--", "Open a DXF file as a Geometry (or Gerber) Object.")

    # dictionary of types from Tcl command, needs to be ordered
    arg_names = collections.OrderedDict([
        ('filename', str)
    ])

    # dictionary of types from Tcl command, needs to be ordered , this  is  for options  like -optionname value
    option_types = collections.OrderedDict([
        ('type', str),
        ('outname', str),
        ('text_mode', str)  # NEW: Add text_mode option
    ])

    # array of mandatory options for current Tcl command: required = {'name','outname'}
    required = ['filename']

    # structured help for current command, args needs to be ordered
    help = {
        'main': "Open a DXF file as a Geometry (or Gerber) Object.",
        'args':  collections.OrderedDict([
            ('filename', 'Absolute path to file to open. Required.\n'
                         'WARNING: no spaces are allowed. If unsure enclose the entire path with quotes.'),
            ('type', 'Open as a Gerber or Geometry (default) object. Values can be: "geometry" or "gerber"'),
            ('outname', 'Name of the resulting Geometry object.'),
            ('text_mode', 'Text conversion mode: "stroke" (default, CNC paths), '
                          '"outline" (filled shapes), or "none" (skip text)')
        ]),
        'examples': [
            'open_dxf /path/to/file.DXF',
            'open_dxf /path/to/file.DXF -type gerber',
            'open_dxf /path/to/file.DXF -text_mode outline',
            'open_dxf /path/to/file.DXF -text_mode none  # Skip text, import geometry only'
        ]
    }

    def execute(self, args, unnamed_args):
        """
        execute current TCL shell command

        :param args: array of known named arguments and options
        :param unnamed_args: array of other values which were passed into command
            without -somename and  we do not have them in known arg_names
        :return: None or exception
        """

        # How the object should be initialized
        def obj_init(geo_obj, app_obj):

            if obj_type == "geometry":
                geo_obj.import_dxf_as_geo(filename, units=units, text_mode=text_mode)
            elif obj_type == "gerber":
                geo_obj.import_dxf_as_gerber(filename, units=units, text_mode=text_mode)
            else:
                return "fail"

        filename = args['filename']

        if 'outname' in args:
            outname = args['outname']
        else:
            outname = filename.split('/')[-1].split('\\')[-1]

        if 'type' in args:
            obj_type = str(args['type']).lower()
        else:
            obj_type = 'geometry'

        if obj_type != "geometry" and obj_type != "gerber":
            self.raise_tcl_error("Option type can be 'geometry' or 'gerber' only, got '%s'." % obj_type)
            return "fail"

        # Get text_mode option with default 'stroke'
        if 'text_mode' in args:
            text_mode = str(args['text_mode']).lower()
            # Validate text_mode value
            if text_mode not in ('stroke', 'outline', 'none'):
                self.raise_tcl_error("Option text_mode must be 'stroke', 'outline', or 'none', got '%s'." % text_mode)
                return "fail"
        else:
            text_mode = 'stroke'

        units = self.app.app_units.upper()

        with self.app.proc_container.new('%s...' % _("Opening")):

            # Object creation
            ret_val = self.app.app_obj.new_object(obj_type, outname, obj_init, plot=False)
            if ret_val == 'fail':
                filename = self.app.options['global_tcl_path'] + '/' + outname
                ret_val = self.app.app_obj.new_object(obj_type, outname, obj_init, plot=False)

                if ret_val == 'fail':
                    self.app.log.error("Failed. The OpenDXF command was used but could not open the DXF file")
                    return "fail"

            # Register recent file
            self.app.file_opened.emit("dxf", filename)

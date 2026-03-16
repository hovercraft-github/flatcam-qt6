# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Author: Marius Adrian Stanciu (c)                   #
# Date: 3/10/2019                                          #
# MIT Licence                                              #
# ##########################################################

# ######################################################################
# ## Borrowed code from 'https://github.com/gddc/ttfquery/blob/master/ #
# ## and made it work with Python 3                                    #
# ######################################################################

import re
import os
import sys
import glob

from shapely import Polygon, MultiPolygon
from shapely.affinity import translate, scale
from shapely.ops import unary_union

import freetype as ft
from fontTools import ttLib

import logging

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base2')


class ParseFont:

    # FreeType uses 26.6 fixed-point (units of 1/64 point).
    # These factors convert from FreeType units to real-world coordinates.
    # MM:   (1/64) * (25.4/49.6) — 26.6 fixed-point to millimeters
    # INCH: (1/64) * (1/49.6)    — 26.6 fixed-point to inches
    SCALE_MM = 0.0080187969924812
    SCALE_INCH = 0.00031570066

    FONT_SPECIFIER_NAME_ID = 4
    FONT_SPECIFIER_FAMILY_ID = 1

    @staticmethod
    def get_win32_font_path():
        """Get User-specific font directory on Win32"""
        try:
            import winreg
        except ImportError:
            return os.path.join(os.environ['WINDIR'], 'Fonts')
        else:
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            try:
                # should check that k is valid? How?
                return winreg.QueryValueEx(k, "Fonts")[0]
            finally:
                winreg.CloseKey(k)

    @staticmethod
    def get_linux_font_paths():
        """Get system font directories on Linux/Unix

        Uses /usr/sbin/chkfontpath to get the list
        of system-font directories, note that many
        of these will *not* be truetype font directories.

        If /usr/sbin/chkfontpath isn't available, uses
        returns a set of common Linux/Unix paths
        """
        executable = '/usr/sbin/chkfontpath'
        if os.path.isfile(executable):
            data = os.popen(executable).readlines()
            match = re.compile(r'\d+: (.+)')
            set_lst = []
            for line in data:
                result = match.match(line)
                if result:
                    set_lst.append(result.group(1))
            return set_lst
        else:
            directories = [
                # what seems to be the standard installation point
                "/usr/X11R6/lib/X11/fonts/TTF/",
                # common application, not really useful
                "/usr/lib/openoffice/share/fonts/truetype/",
                # documented as a good place to install new fonts...
                "/usr/share/fonts",
                "/usr/local/share/fonts",
                # seems to be where fonts are installed for an individual user?
                "~/.fonts",
            ]

            dir_set = []

            for directory in directories:
                directory = os.path.expanduser(os.path.expandvars(directory))
                try:
                    if os.path.isdir(directory):
                        for path, children, files in os.walk(directory):
                            dir_set.append(path)
                except (IOError, OSError, TypeError, ValueError):
                    pass
            return dir_set

    @staticmethod
    def get_mac_font_paths():
        """Get system font directories on MacOS
        """
        directories = [
            # okay, now the OS X variants...
            "~/Library/Fonts/",
            "/Library/Fonts/",
            "/Network/Library/Fonts/",
            "/System/Library/Fonts/",
            "System Folder:Fonts:",
        ]

        dir_set = []

        for directory in directories:
            directory = os.path.expanduser(os.path.expandvars(directory))
            try:
                if os.path.isdir(directory):
                    for path, children, files in os.walk(directory):
                        dir_set.append(path)
            except (IOError, OSError, TypeError, ValueError):
                pass
        return dir_set

    @staticmethod
    def get_win32_fonts(font_directory=None):
        """Get list of explicitly *installed* font names"""

        import winreg
        if font_directory is None:
            font_directory = ParseFont.get_win32_font_path()
        k = None

        items = {}
        for keyName in (
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts",
        ):
            try:
                k = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    keyName
                )
            except OSError:
                pass

        if not k:
            # couldn't open either WinNT or Win98 key???
            return glob.glob(os.path.join(font_directory, '*.ttf'))

        try:
            # should check that k is valid? How?
            for index in range(winreg.QueryInfoKey(k)[1]):
                key, value, _ = winreg.EnumValue(k, index)
                if not os.path.dirname(value):
                    value = os.path.join(font_directory, value)
                value = os.path.abspath(value).lower()
                if value.endswith(('.ttf', '.otf')):
                    items[value] = 1
            return list(items.keys())
        finally:
            winreg.CloseKey(k)

    @staticmethod
    def get_font_name(font_path):
        """
        Get the short name from the font's names table
        From 'https://github.com/gddc/ttfquery/blob/master/ttfquery/describe.py'
        and
        http://www.starrhorne.com/2012/01/18/
        how-to-extract-font-names-from-ttf-files-using-python-and-our-old-friend-the-command-line.html
        ported to Python 3 here: https://gist.github.com/pklaus/dce37521579513c574d0
        """
        name = ""
        family = ""

        with ttLib.TTFont(font_path) as font:
            for record in font['name'].names:
                try:
                    name_str = record.toUnicode()
                except (UnicodeDecodeError, AttributeError):
                    continue

                if record.nameID == ParseFont.FONT_SPECIFIER_NAME_ID and not name:
                    name = name_str
                elif record.nameID == ParseFont.FONT_SPECIFIER_FAMILY_ID and not family:
                    family = name_str

                if name and family:
                    break
        return name, family

    def __init__(self, app):
        self.app = app

        # regular fonts
        self.regular_f = {}
        # bold fonts
        self.bold_f = {}
        # italic fonts
        self.italic_f = {}
        # bold and italic fonts
        self.bold_italic_f = {}

    def get_fonts(self, paths=None):
        """
        Find fonts in paths, or the system paths if not given
        """
        files = {}
        if paths is None:
            if sys.platform == 'win32':
                font_directory = ParseFont.get_win32_font_path()
                paths = [font_directory, ]

                # now get all installed fonts directly...
                for f in self.get_win32_fonts(font_directory):
                    files[f] = 1
            elif sys.platform == 'linux':
                paths = ParseFont.get_linux_font_paths()
            else:
                paths = ParseFont.get_mac_font_paths()
        elif isinstance(paths, str):
            paths = [paths]

        for path in paths:
            for ext in ('*.ttf', '*.otf'):
                for file in glob.glob(os.path.join(path, ext)):
                    files[os.path.abspath(file)] = 1

        return list(files.keys())

    def get_fonts_by_types(self):

        system_fonts = self.get_fonts()

        # split the installed fonts by type: regular, bold, italic (oblique), bold-italic and
        # store them in separate dictionaries {name: file_path/filename.ttf}
        for font in system_fonts:
            try:
                name, family = ParseFont.get_font_name(font)
            except Exception as e:
                log.error("ParseFont.get_fonts_by_types() --> Could not get the font name. %s" % str(e))
                continue

            if 'Bold' in name and 'Italic' in name:
                name = name.replace(" Bold Italic", '')
                self.bold_italic_f.update({name: font})
            elif 'Bold' in name and 'Oblique' in name:
                name = name.replace(" Bold Oblique", '')
                self.bold_italic_f.update({name: font})
            elif 'Bold' in name:
                name = name.replace(" Bold", '')
                self.bold_f.update({name: font})
            elif 'SemiBold' in name:
                name = name.replace(" SemiBold", '')
                self.bold_f.update({name: font})
            elif 'DemiBold' in name:
                name = name.replace(" DemiBold", '')
                self.bold_f.update({name: font})
            elif 'Demi' in name:
                name = name.replace(" Demi", '')
                self.bold_f.update({name: font})
            elif 'Italic' in name:
                name = name.replace(" Italic", '')
                self.italic_f.update({name: font})
            elif 'Oblique' in name:
                name = name.replace(" Oblique", '')
                self.italic_f.update({name: font})
            else:
                try:
                    name = name.replace(" Regular", '')
                except Exception:
                    pass
                self.regular_f.update({name: font})
        log.debug("Font parsing is finished.")

    @staticmethod
    def _interpolate_contour(points, tags, segments=8):
        """Convert a FreeType contour to line vertices by interpolating quadratic Bezier curves.

        FreeType tags bit 0: 1 = on-curve, 0 = off-curve (quadratic control point).
        TrueType rule: two consecutive off-curve points have an implied on-curve midpoint.

        Args:
            points: list of (x, y) from outline.points
            tags: list of int from outline.tags
            segments: line segments per Bezier curve (higher = smoother)
        Returns:
            list of (x, y) suitable for Polygon(), or empty list on failure
        """
        if len(points) < 2:
            return []

        result = []
        n = len(points)

        # Find the first on-curve point to start from, or compute implied midpoint
        first_on = None
        for k in range(n):
            if tags[k] & 1:
                first_on = k
                break

        if first_on is None:
            # All off-curve: start from implied midpoint between last and first
            start_pt = ((points[-1][0] + points[0][0]) / 2,
                        (points[-1][1] + points[0][1]) / 2)
            result.append(start_pt)
            first_on = 0  # process from index 0
        else:
            result.append(points[first_on])
            first_on = (first_on + 1) % n

        # Walk all points starting after the first on-curve
        i = first_on
        visited = 0
        while visited < n:
            idx = i % n
            visited += 1

            if tags[idx] & 1:
                # On-curve: straight line
                result.append(points[idx])
            else:
                # Off-curve control point — start collecting Bezier sequence
                p0 = result[-1]

                while visited <= n:
                    ctrl = points[idx]
                    next_idx = (idx + 1) % n

                    if visited >= n:
                        # Wrap: endpoint is start of contour
                        p2 = result[0]
                    elif tags[next_idx] & 1:
                        # Next is on-curve: endpoint
                        p2 = points[next_idx]
                        i = (idx + 1) % n
                        visited += 1
                    else:
                        # Next is also off-curve: implied midpoint
                        p2 = ((ctrl[0] + points[next_idx][0]) / 2,
                              (ctrl[1] + points[next_idx][1]) / 2)

                    # Interpolate quadratic Bezier: B(t) = (1-t)²·p0 + 2(1-t)t·ctrl + t²·p2
                    for s in range(1, segments + 1):
                        t = s / segments
                        mt = 1 - t
                        x = mt * mt * p0[0] + 2 * mt * t * ctrl[0] + t * t * p2[0]
                        y = mt * mt * p0[1] + 2 * mt * t * ctrl[1] + t * t * p2[1]
                        result.append((x, y))

                    p0 = p2

                    if visited >= n or (tags[next_idx] & 1):
                        break
                    idx = next_idx
                    visited += 1

            i = (i + 1) % n

        # Close contour
        if result and result[0] != result[-1]:
            result.append(result[0])

        return result

    def font_to_geometry(self, char_string, font_name, font_type, font_size, units='MM', coordx=0, coordy=0):
        path = []
        path_filename = ""

        regular_dict = self.regular_f
        bold_dict = self.bold_f
        italic_dict = self.italic_f
        bold_italic_dict = self.bold_italic_f

        try:
            if font_type == 'bi':
                path_filename = bold_italic_dict[font_name]
            elif font_type == 'bold':
                path_filename = bold_dict[font_name]
            elif font_type == 'italic':
                path_filename = italic_dict[font_name]
            elif font_type == 'regular':
                path_filename = regular_dict[font_name]
        except Exception as e:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Font not supported, try another one."))
            log.error("[ERROR_NOTCL] Font Loading: %s" % str(e))
            return "flatcam font parse failed"

        face = ft.Face(path_filename)
        try:
            face.set_char_size(int(round(float(font_size) * 64)))

            pen_x = coordx
            previous = 0

            # done as here: https://www.freetype.org/freetype2/docs/tutorial/step2.html
            for char in char_string:
                glyph_index = face.get_char_index(char)

                try:
                    if previous > 0 and glyph_index > 0:
                        delta = face.get_kerning(previous, glyph_index)
                        pen_x += delta.x
                except Exception:
                    pass

                face.load_glyph(glyph_index)
                # face.load_char(char, flags=8)

                slot = face.glyph
                outline = slot.outline

                start, end = 0, 0
                for i in range(len(outline.contours)):
                    end = outline.contours[i]
                    points = outline.points[start:end + 1]
                    tags = outline.tags[start:end + 1]

                    interp_points = ParseFont._interpolate_contour(points, tags)
                    if len(interp_points) >= 4:  # minimum 3 unique points + closing
                        try:
                            char_geo = Polygon(interp_points)
                            if char_geo.is_valid and not char_geo.is_empty:
                                char_geo = translate(char_geo, xoff=pen_x, yoff=coordy)
                                path.append(char_geo)
                        except Exception:
                            # Fallback: use raw points as straight lines (original behavior)
                            points_list = list(points)
                            points_list.append(points_list[0])
                            char_geo = Polygon(points_list)
                            if not char_geo.is_empty:
                                char_geo = translate(char_geo, xoff=pen_x, yoff=coordy)
                                path.append(char_geo)

                    start = end + 1

                pen_x += slot.advance.x
                previous = glyph_index
        finally:
            del face

        # --- Hole detection on unscaled geometry ---
        n = len(path)
        if n == 0:
            return MultiPolygon()

        if n == 1:
            ret_geo = path[0]
        else:
            # Classify contours: a contour is a hole if it's contained within another
            is_hole = [False] * n
            for i in range(n):
                for j in range(n):
                    if i != j and path[i].within(path[j]):
                        is_hole[i] = True
                        break

            shells = [path[i] for i in range(n) if not is_hole[i]]
            holes = [path[i] for i in range(n) if is_hole[i]]

            if holes:
                ret_geo = unary_union(shells).difference(unary_union(holes))
            else:
                ret_geo = unary_union(shells)

        # --- Single scale operation on final geometry ---
        s = ParseFont.SCALE_MM if units == 'MM' else ParseFont.SCALE_INCH
        ret_geo = scale(ret_geo, s, s, origin=(coordx, coordy))

        return ret_geo

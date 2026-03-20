# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
python flatcam.py
```

Requires Python 3.11+ and PyQt6. Dependencies managed via `requirements.txt` or `environment.yml` (conda/mamba).

## Running Tests

Tests use `unittest` (no pytest configuration). Run individually:

```bash
python tests/test_gerber_parser.py
python tests/test_vispy_batch.py
python tests/test_pdf_hole_detection.py
```

## Architecture

FlatCAM EVO is a PyQt6-based CAM application for PCB manufacturing (Gerber to G-Code). The codebase follows a hub-and-spoke architecture centered on the `App` class.

### Core Flow

```
flatcam.py (entry) → App (appMain.py) → MainGUI + Objects + Editors + Plugins + Parsers
```

**`App` (appMain.py)** — Central orchestrator (~154 methods). Holds references to GUI, object collection, editors, tools, parsers, handlers, preferences. All components receive an `app` reference.

**`camlib.py`** — Core geometry and CNC library (~8500 LOC). Contains base classes `Gerber`, `Excellon`, `Geometry`, `CNCjob` that app objects inherit from, plus geometry utilities (`AppRTree`, flatten, bounds, translate).

### Object Model

```
FlatCAMObj (appObjects/AppObjectTemplate.py)  — base for all project objects
  ├── GerberObject    (+ Gerber from camlib)
  ├── ExcellonObject  (+ Excellon from camlib)
  ├── GeometryObject  (+ Geometry from camlib)
  ├── CNCJobObject    (+ CNCjob from camlib)
  ├── ScriptObject
  └── DocumentObject
```

Objects are created via `AppObject.new_object()` factory, registered in `ObjectCollection` (project tree), and plotted via VisPy canvas.

### Plugin System (appPlugins/)

All tools inherit from `AppTool` (appTool.py). Two patterns exist:

1. **Single-file plugins** (legacy): `ToolName.py` with `ToolX` class + `XUI` class in one file
2. **MVC plugins** (current direction): Separate folder with:
   - `Tool.py` — Controller (orchestration, signals, state)
   - `ToolUI.py` — View (UI building/layout)
   - `ToolGen.py` — Model (algorithms, generation logic)

ToolPaint and ToolNCC are refactored to MVC. Other tools (ToolIsolation, ToolDrilling, ToolMilling, etc.) still use single-file pattern.

Plugin lifecycle: `__init__(app)` → `install()` → `run()` → `connect_signals()` / `set_tool_ui()`

Signal management uses `ui_connect()` / `ui_disconnect()` pairs to prevent duplicate connections.

### Editor System (appEditors/)

Three main editors with plugin sub-architecture:
- `appGerberEditor.py` + `grb_plugins/`
- `appGeoEditor.py` + `geo_plugins/`
- `appExcEditor.py` + `exc_plugins/`

Editor plugins inherit from `AppToolEditor` and follow `EditorTool` + `EditorUI` pattern.

### Parsers (appParsers/)

Format-specific parsers: `ParseGerber`, `ParseExcellon`, `ParseDXF`, `ParseSVG`, `ParsePDF`, `ParseFont`, `ParseHPGL2`. Each implements `parse()` and `build_geometry()`.

### Preprocessors (preprocessors/)

G-Code post-processors for specific CNC machines (GRBL, Marlin, Roland, etc.). Auto-registered via `ABCPreProcRegister` metaclass. Each implements `start_code()`, `rapid_code()`, `linear_code()`, `toolchange_code()`, etc.

### Preferences

- `defaults.py` — `AppDefaults` holds all default values; `AppOptions` for runtime
- `appGUI/preferences/` — UI panels organized by section (general, gerber, excellon, geometry, cncjob, tools)
- `PreferencesUIManager.py` — Master handler, persists via QSettings
- Tools sync with preferences via `storage_to_form()` / `form_to_storage()`

### I/O

`appHandlers/appIO.py` (~140 methods) handles all file import/export operations, delegating parsing to appParsers/ and creating objects via AppObject factory.

### Tcl Commands (tclCommands/)

76 command classes for scripting. Base: `TclCommand` with argument parsing. `TclCommandSignaled` subclass adds async execution with signal-based blocking.

### Key Dependencies

- **GUI**: PyQt6, VisPy (2D/3D canvas)
- **Geometry**: Shapely, numpy, rtree
- **File formats**: ezdxf, lxml, svglib, reportlab
- **Internationalization**: `appTranslation.py` (imported by 174 files — most-imported module)

### Signal/Event Pattern

Components communicate via Qt signals and `FCSignal` wrapper (appCommon/Common.py). Tools connect to app-level signals in `connect_signals()` and disconnect on deactivation.

# GUI Workbench

MyGUI uses one native desktop window with a full-width application command bar, a resizable workbench, and a full-width message/state bar. The workbench keeps the table and figure-inspector tools on the left and the matplotlib figure workspace on the right.

## Window and workbench layout

- The application starts maximized and uses the operating system title bar, resize borders, minimize/maximize controls, and snap behavior.
- The command bar spans the window. Its first row selects `style`, `layout`, `chart`, or `element`; the second row contains the corresponding action gallery.
- `workspace_splitter` divides the left workspace from the figure workspace. Its first-run ratio is approximately 45/55 and the figure workspace keeps at least 400 logical pixels when space permits.
- `explorer_control_splitter` divides the active Explorer page from the
  figure inspector. Its first-run sizes are 420/240 logical pixels.
- The activity rails are 44 logical pixels wide. The bottom Message/State Bar is 28 logical pixels high.
- Table and Components buttons switch the shared Explorer page. Clicking the
  active button again hides the Explorer; opening either page restores its
  last visible width.
- Inspector sections remain independently scrollable when a restored or narrow window cannot show the complete form. TeX and MATLAB pages use the same bounded-scroll behavior, so switching tools does not resize the shell.
- Component editing uses one profile-driven Inspector shell. Line charts share the same appearance groups; Text, Title, and Axis Labels share the same text sections; Legend keeps its Controller-specific layout and frame sections.

## Persisted application settings

Workbench preferences are stored in the versioned `workspaceLayout` `QSettings` group:

- `version`: layout settings version; currently `2`.
- `outerSplitterSizes`: left-workspace and figure-workspace sizes.
- `innerSplitterSizes`: Explorer and Inspector sizes.
- `explorerMode`: last visible page, `table` or `components`.
- `explorerVisible`: whether the Explorer is expanded.

Window geometry is not stored because every application launch starts maximized. Missing, malformed, obsolete, or unusable layout values fall back to the first-run sizes. The Settings dialog's reset action clears this group and reapplies the defaults.
Version-1 `tableVisible` is migrated to the Table page and the equivalent
Explorer visibility.

These settings are application preferences. They are not written to `.mygui.json` project files, and opening a project does not replace them.

## Empty states and command galleries

- With no project, the figure workspace explains that a style must be selected to create a project; the existing Style workflow remains the creation path.
- With a project but no Axes, the Figure root Inspector remains available.
- Style, Layout, Chart, and Element use action toolbars. Qt moves actions that do not fit into the toolbar overflow menu.
- Style, Layout, Text, and Settings dialogs are created on first use, parented to the main window, and reused. Chart dialogs are recreated so their data choices reflect the current project.
- The Components tree is the only Component navigation. It opens one exact
  stable-ID Inspector at a time; every Inspector binds its Controller
  directly.
- Chart creation dialogs reuse controller-free line appearance, data reference, and interpolation-option inputs. Accepting a dialog still delegates component creation to the active canvas.

## Project tab close and application exit

The canvas tab bar resolves context menus with `tabAt(position)`. `Rename
Project` and `Close Project` therefore operate on the clicked tab without
switching a background project.

Each project has a runtime clean fingerprint made from its full typed Table
snapshot and normalized schema-v7 component tree. A new project has no clean
baseline and is dirty. Loading or completing an atomic save establishes the
baseline. Table edits, project rename, Component changes, Undo, and
Matplotlib toolbar view changes are detected by comparing a fresh snapshot;
fingerprint errors are treated as dirty.

Closing a dirty tab offers Save, Discard, and Cancel:

- Save writes to `canvas.project_path`, or opens Save As when no path exists.
  Cancelling Save As or a failed write leaves the project open.
- Discard closes without writing.
- Cancel leaves every project object unchanged.
- A clean project closes without a prompt.

Closing removes the matching project ID from the Canvas map, Figure
Inspector, Table stack, `TableRepository`, and Undo stack, then disposes
Registry, repository, TeX, MATLAB, fitting, and redraw callbacks
idempotently. Closing the final project shows the Canvas, Table, and Inspector
empty states. Application exit runs the same checks for every project before
disposing any of them; a Cancel or failed save aborts exit, while projects
saved earlier in that pass remain clean.

## Figure DPI

`PyFigureCanvas.document_dpi` is the project and default-export DPI. Qt's device pixel ratio may change the renderer DPI used for display, but it does not change `document_dpi`, project `figure.dpi`, figure size in inches, or default export dimensions.

For example, a 6.4 x 4.8 inch figure at 100 document DPI exports to 640 x 480 pixels by default on 100%, 125%, 150%, and 200% displays. Passing an explicit DPI to `save()` overrides the default export DPI.

## Message and state semantics

- Message levels are `info`, `success`, `warning`, and `error`.
- Success is green, warnings are yellow, and errors are red. The level is also exposed as a widget property for styling and testing.
- Optional integrations use `● Name On` for enabled and `○ Name Off` for disabled. Off is neutral rather than an error state.
- Icon-only activity and command buttons provide tooltips, accessible names, and visible keyboard focus.

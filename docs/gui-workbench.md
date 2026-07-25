# GUI Workbench

MyGUI uses one native desktop window with a full-width application command bar, a resizable workbench, and a full-width message/state bar. The workbench keeps the table and figure-inspector tools on the left and the matplotlib figure workspace on the right.

## Window and workbench layout

- The application starts maximized and uses the operating system title bar, resize borders, minimize/maximize controls, and snap behavior.
- The command bar spans the window. Its first row selects `style`, `layout`, `chart`, or `element`; the second row contains the corresponding action gallery.
- `workspace_splitter` divides the left workspace from the figure workspace. Its first-run ratio is approximately 45/55 and the figure workspace keeps at least 400 logical pixels when space permits.
- `table_control_splitter` divides the project table from the figure inspector. Its first-run sizes are 420/240 logical pixels.
- The activity rails are 44 logical pixels wide. The bottom Message/State Bar is 28 logical pixels high.
- The table activity button hides or restores the table without collapsing the inspector or figure workspace.
- Inspector sections remain independently scrollable when a restored or narrow window cannot show the complete form. TeX and MATLAB pages use the same bounded-scroll behavior, so switching tools does not resize the shell.

## Persisted application settings

Workbench preferences are stored in the versioned `workspaceLayout` `QSettings` group:

- `version`: layout settings version; currently `1`.
- `outerSplitterSizes`: left-workspace and figure-workspace sizes.
- `innerSplitterSizes`: table and inspector sizes.
- `tableVisible`: table activity-button state.

Window geometry is not stored because every application launch starts maximized. Missing, malformed, obsolete, or unusable layout values fall back to the first-run sizes. The Settings dialog's reset action clears this group and reapplies the defaults.

These settings are application preferences. They are not written to `.mygui.json` project files, and opening a project does not replace them.

## Empty states and command galleries

- With no project, the figure workspace explains that a style must be selected to create a project; the existing Style workflow remains the creation path.
- Empty inspector states explain when a project, axes, or editable object is required.
- Style, Layout, Chart, and Element use action toolbars. Qt moves actions that do not fit into the toolbar overflow menu.
- Style, Layout, Text, and Settings dialogs are created on first use, parented to the main window, and reused. Chart dialogs are recreated so their data choices reflect the current project.

## Figure DPI

`PyFigureCanvas.document_dpi` is the project and default-export DPI. Qt's device pixel ratio may change the renderer DPI used for display, but it does not change `document_dpi`, project `figure.dpi`, figure size in inches, or default export dimensions.

For example, a 6.4 x 4.8 inch figure at 100 document DPI exports to 640 x 480 pixels by default on 100%, 125%, 150%, and 200% displays. Passing an explicit DPI to `save()` overrides the default export DPI.

## Message and state semantics

- Message levels are `info`, `success`, `warning`, and `error`.
- Success is green, warnings are yellow, and errors are red. The level is also exposed as a widget property for styling and testing.
- Optional integrations use `● Name On` for enabled and `○ Name Off` for disabled. Off is neutral rather than an error state.
- Icon-only activity and command buttons provide tooltips, accessible names, and visible keyboard focus.

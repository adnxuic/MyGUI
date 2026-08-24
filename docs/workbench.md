# GUI Workbench

MyGUI uses one native desktop window with a full-width application command bar, a resizable workbench, and a full-width message/state bar. The workbench keeps the table and figure-inspector tools on the left and the matplotlib figure workspace on the right.

## Window and workbench layout

- The application starts maximized and uses the operating system title bar, resize borders, minimize/maximize controls, and snap behavior.
- The command bar spans the window. Its first row selects style, layout, chart, or element; the second row shows the corresponding action gallery.
- workspace_splitter divides the left workspace from the figure workspace. Its first-run ratio is approximately 45/55 and the figure workspace keeps at least 400 logical pixels when space permits.
- explorer_control_splitter divides the active Explorer page from the figure inspector. Its first-run sizes are 420/240 logical pixels.
- The activity rails are 44 logical pixels wide. The bottom Message/State Bar is 28 logical pixels high.
- Table and Components buttons switch the shared Explorer page. Clicking the active button again hides the Explorer; opening either page restores its last visible width.
- Inspector sections remain independently scrollable when a restored or narrow window cannot show the complete form. TeX and MATLAB pages use the same bounded-scroll behavior, so switching tools does not resize the shell.
- Every project tab shows a matplotlib navigation toolbar (Home, Back, Forward, Pan, Zoom, Subplots, Save) plus the project's shared Undo/Redo actions above its canvas. The rightmost Canvas Window button moves the same live canvas into a maximized, non-modal window containing only the canvas viewport; the project tab shows a placeholder until the window closes, and closing the window with its system close button or Esc returns the canvas with its scroll position and focus. Because that window hosts the one live canvas, edits made in the main window appear in it immediately. The view keeps the project's fixed Figure size and uses scroll bars when needed instead of scaling or changing its document DPI. Each project can have one such window, so canvases from different projects can be viewed together. Toolbar buttons, mouse pan/zoom, and keyboard shortcuts are listed in [Keyboard and Mouse Reference](keyboard-and-mouse-reference.md), [Project Undo and Redo](undo-redo.md), and the [matplotlib navigation guide](https://matplotlib.org/3.9.0/users/explain/figure/interactive.html).
- Component editing uses one profile-driven Inspector shell. Line charts share the same appearance groups; Text, Title, and Axis Labels share the same text sections; Legend keeps its Controller-specific layout and frame sections.

## Command bar and menus

The dark command row offers the File menu:

- 打开 Excel... opens an Excel workbook through the import preview. See [Excel Import](excel-import.md).
- 打开文本数据... opens a text file through the content-based text importer. See [Text Data Import](text-data-import.md).
- 打开项目... opens a saved .mygui.json project file.
- 保存项目... saves the current project to its project path, or asks for a path.
- Project Save As... saves the current project under a new path.
- 导出当前图片... exports the current Figure canvas as a PNG, PDF, or SVG image.
- 导出数据... exports the current project's table data as a JSON snapshot.

Save, open, restore, and export semantics are documented in [Project Files](project-files.md).

## Activity rails

- The left activity rail toggles the Table and Components Explorer pages and opens the Settings dialog.
- The right activity rail opens the TeX and MATLAB panels; the two panels share one page and opening one deselects the other. See [TeX Rendering Integration](tex-integration.md) and [Fitting](fitting.md).

## Empty states and command galleries

- With no project, the figure workspace explains that a style must be selected to create a project; the Style workflow remains the creation path.
- With a project but no Axes, the Figure root Inspector remains available.
- Style, Layout, Chart, and Element use action toolbars. Qt moves actions that do not fit into the toolbar overflow menu.
- Style and Settings dialogs are created on first use, parented to the main window, and reused. Layout, Chart, and Element creation dialogs are recreated so their Figure, Axes, and data choices reflect the current project.
- The Components tree is the only Component navigation. It opens one exact stable-ID Inspector at a time; every Inspector binds its Controller directly.
- Chart creation dialogs reuse controller-free line appearance, data reference, and interpolation-option inputs. Plot, Scatter, and Interpolation use a compact shared-X/multi-Y dropdown with visible X/Y preprocessing expressions and publish all selected curves through one Canvas registration transaction. Fit retains its single-pair input. Accepting a dialog still delegates component creation to the active canvas.

## Persisted application settings

Workbench preferences are stored in the versioned workspaceLayout QSettings group:

- version: layout settings version; currently 2.
- outerSplitterSizes: left-workspace and figure-workspace sizes.
- innerSplitterSizes: Explorer and Inspector sizes.
- explorerMode: last visible page, table or components.
- explorerVisible: whether the Explorer is expanded.

Window geometry is not stored because every application launch starts maximized. Missing, malformed, obsolete, or unusable layout values fall back to the first-run sizes. The Settings dialog's reset action clears this group and reapplies the defaults. Version-1 tableVisible is migrated to the Table page and the equivalent Explorer visibility.

These settings are application preferences. They are not written to .mygui.json project files, and opening a project does not replace them.

## Project tabs, closing, and exit

The canvas tab bar resolves context menus with tabAt(position). Rename Project and Close Project therefore operate on the clicked tab without switching a background project.

Each project has a runtime clean fingerprint made from its full typed Table snapshot and normalized schema-v14 component tree. A new project has no clean baseline and is dirty. Loading or completing an atomic save establishes the baseline. Table edits, project rename, Component changes, Undo, and Matplotlib toolbar view changes are detected by comparing a fresh snapshot; fingerprint errors are treated as dirty. Undoing exactly to the latest successful load/save fingerprint returns the project to clean state, while Redo makes it dirty again.

Closing a dirty tab offers Save, Discard, and Cancel:

- Save writes to canvas.project_path, or opens Save As when no path exists. Cancelling Save As or a failed write leaves the project open.
- Discard closes without writing.
- Cancel leaves every project object unchanged.
- A clean project closes without a prompt.

Closing removes the matching project ID from the Canvas map, Figure Inspector, Table stack, TableRepository, and shared project Undo stack, then disposes Registry, history, repository, TeX, MATLAB, fitting, and redraw callbacks idempotently. Closing the final project shows the Canvas, Table, and Inspector empty states. Application exit runs the same checks for every project before disposing any of them; a Cancel or failed save aborts exit, while projects saved earlier in that pass remain clean.

## Application icon and taskbar identity

MyGUI uses pictures/icons/app_icon.ico for the native main-window icon, the Windows taskbar icon, and the default icon inherited by application windows. Dialogs that explicitly select a feature-specific icon keep their own icon.

main.WINDOWS_APP_USER_MODEL_ID is the stable MyGUI.Desktop identity that keeps a source launch from being grouped under the Python interpreter. main.configure_windows_taskbar_identity() assigns it through the Windows Shell before QApplication is created and returns whether it was applied; unsupported platforms leave startup unchanged.

main.APP_ICON_PATH resolves the icon asset through the package resource locator, so icon loading does not depend on the process working directory. main.configure_application_icon(application) assigns the loaded QIcon to the application and returns it; MainWindow also assigns the icon explicitly so directly constructed main windows keep the application branding outside the normal startup path.

## See also

- Message and State Bar semantics: [Bottom Bar](bottom-bar.md).
- Project save/open format, export, and DPI: [Project Files](project-files.md).
- Available styles and the project creation dialog: [Style Creation Defaults](style-creation-defaults.md).

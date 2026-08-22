# Keyboard and Mouse Reference

Keyboard shortcuts and mouse interactions for MyGUI controls. Shortcuts apply to the widget that currently has focus; the same key can mean different things in different widgets.

## Project history

| Key | Action |
| --- | --- |
| Ctrl+Z | Undoes the latest committed Table or Figure command in the active project. Uncommitted text in a text or cell editor uses native text Undo first. |
| Ctrl+Y | Redoes the next committed command in the active project. Uncommitted text uses native text Redo first. |
| Ctrl+Shift+Z | Redoes the next committed command in the active project. |

The Table and Figure toolbar actions use the same per-project timeline. See
[Project Undo and Redo](undo-redo.md).

## Table view

| Key or mouse action | Action |
| --- | --- |
| Ctrl+C | Copies the selected cells to the clipboard as TSV text. |
| Ctrl+V | Pastes TSV text at the current selection. All locked column types are validated before any change; missing rows or columns are added automatically; the complete paste is one undo command. |
| Delete | Clears the selected cells, setting them to missing values. |
| Double-click, F2, or typing | Starts editing the current cell. |
| Enter | Commits the cell edit. |
| Esc | Cancels the cell edit. |
| Arrow keys / Tab | Move between cells (standard Qt navigation). |
| Click | Boolean columns toggle their checkbox state; when editing, a Boolean cell offers the choices true, false, and empty. |
| Calendar button | Datetime cells edit with a calendar popup; committed values are stored as ISO 8601 local date/time text. |
| Double-click a Sheet tab | Renames the Sheet. |
| Click the + tab | Creates a new Sheet with an automatically unique default name. |

Right-click menus: the column header offers Rename Column, Change Type, Add Column Right, Delete Column, Move Left, Move Right, Sort Rows Ascending, and Sort Rows Descending. The row header offers Insert Row Above, Delete Row, Move Up, and Move Down. A Sheet tab offers Rename Sheet and Delete Sheet. See [Table Data](table-data.md).

## Multi-select Y dropdown

Plot, Scatter, and Interpolation creation dialogs use a checkable multi-select dropdown for the Y columns:

| Key or mouse action | Action |
| --- | --- |
| Space / Enter / Return | Toggles the check state of the highlighted column without closing the dropdown. |
| Click | Toggles the check state of the clicked column. |

See [Multi-Series Chart Creation](multi-series-charts.md).

## Figure canvas

Every project tab contains one matplotlib navigation toolbar above its canvas:

| Button | Action |
| --- | --- |
| Home | Resets the view to the stored home limits. |
| Back / Forward | Steps backward and forward through the view history. |
| Pan | Toggles pan/zoom mode: dragging with the left button pans, dragging with the right button zooms. |
| Zoom | Toggles zoom-to-rectangle mode: drag a rectangle to zoom into it. |
| Subplots | Opens the subplot configuration dialog, whose sliders set the Figure margins (left, right, bottom, top) and the horizontal and vertical spacing between Axes. |
| Save | Opens the image save dialog (PNG by default). |
| Undo / Redo | Steps through committed Table and Figure commands for this project. |

### Keyboard shortcuts

Matplotlib's default key bindings are active while the canvas has focus:

| Key | Action |
| --- | --- |
| h / r / home | Home: reset the view. |
| left arrow / backspace / c | Back: previous view. |
| right arrow / v | Forward: next view. |
| p | Toggle pan/zoom mode. |
| o | Toggle zoom-to-rectangle mode. |
| s / Ctrl+S | Save the figure as an image. |
| g | Cycles the major grid visibility of the Axes under the pointer. |
| G | Cycles the major and minor grid visibility of the Axes under the pointer. |
| k / L | Toggles the X-axis scale of the Axes under the pointer between linear and log. |
| l | Toggles the Y-axis scale of the Axes under the pointer between linear and log. |

The default Matplotlib bindings f and Ctrl+F (fullscreen) and Ctrl+W and q (close figure) are accepted by the default handler but have no effect on MyGUI's embedded project canvas.

## Components tree

- Typing in the search box filters the tree by component name; the clear button restores the full tree.
- Clicking a component selects it and opens its Inspector.
- Right-clicking a removable component offers Delete and Batch Delete Same Type. See [Components Tree](components-tree.md).

## Color and palette pickers

- Arrow keys move the highlight; Enter or double-click activates the highlighted color or palette. See [Color Picker](color-picker.md).

## Fit coefficient table

- Double-click or F2 edits a coefficient constraint cell (Lower or Upper) in the fit advanced options. See [Fitting](fitting.md).

## Matplotlib reference

- [Interactive navigation](https://matplotlib.org/3.9.0/users/explain/figure/interactive.html): toolbar buttons, mouse pan/zoom, and the default keyboard bindings MyGUI uses.
- [NavigationToolbar2](https://matplotlib.org/3.9.0/api/backend_bases_api.html#matplotlib.backend_bases.NavigationToolbar2): the toolbar class behind the canvas controls.

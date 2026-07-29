# Manual Smoke Test

Run these checks from the repository root after GUI-facing changes.

## Start

```powershell
python main.py
```

Expected result: the main PySide6 window opens without requiring MATLAB or LaTeX.

## Window and Responsive Layout

1. Confirm the application starts maximized with the native Windows title bar and only one taskbar window.
2. Confirm the dark command bar and bottom Message/State Bar span the full window width.
3. Confirm the left workspace and right figure workspace touch through a visible splitter with no desktop showing between them.
4. Drag both workbench splitters, hide and restore the table, restart the application, and confirm the splitter/table preferences restore.
5. Use Settings > `Reset workspace layout` and confirm the default proportions return and the Message Bar reports success in green.
6. With no project, confirm the figure empty state directs the user to Style; create a project and confirm the empty state is replaced by its canvas tab.
7. Resize a restored window through 960x600, 1280x720, 1366x768, and 1920x1080; confirm the command gallery uses overflow instead of clipping and the canvas remains visible.
8. Switch repeatedly between the figure inspector, TeX, and MATLAB pages; confirm the main layout does not jump or grow.
9. On available 100%, 125%, 150%, and 200% displays, confirm text/icons remain clear and menus/dialogs stay on the active screen.
10. Move the window between monitors with different scaling and verify native maximize/restore, resize, and snap behavior.

For a 6.4 x 4.8 inch, 100 DPI test figure, a default PNG export must be 640 x 480 pixels at every display scale. Save and reopen the project and confirm its recorded DPI remains 100.

## Core Workflow

1. Create a new project from the style toolbar and enter a unique project name.
2. Confirm the table area shows only that project's table and a `Sheet1` sheet.
3. Add axes from the layout toolbar.
4. Import an Excel workbook through the file menu and confirm data lands in the current project table.
5. Save table data to the in-memory database from the sheet/table workflow if needed.
6. Create a plot using two saved data columns. Confirm the line-style control
   initially reads `Solid`, selecting `Dashed` creates a dashed line, and the
   Inspector shows the same style.
7. Create a scatter chart using two saved data columns.
8. Create an interpolation curve from saved data, change its method, set `Samples`, and confirm the curve redraws.
9. Change method-specific interpolation options and confirm the curve redraws.
10. Change interpolation X/Y data sources from the right-side panel and confirm only current-project data is listed.
11. Create a SciPy fitting curve, run `poly2`, and confirm the result area shows coefficients and goodness metrics.
12. Switch between Function Curve, Data Plot, Fit Curve, and Interpolation. Confirm each Inspector uses the same Basic, Marker, and Advanced line appearance fields in the same order, including line style and marker fields for Interpolation.
13. In Fit Curve, confirm Data Source, Fit Operations, Fit Result, Display Range, and Appearance are separate sections. Changing X/Y must request a manual refit rather than silently recomputing.
14. Edit Title, X Label, Y Label, and free Text. Confirm they show the same Content, Typography, Rotation and Alignment, Position, and Rendering sections; only free Text offers deletion.
15. Open Legend with no plotted handles, then with plotted handles. Switch between a preset and a custom coordinate location, change columns and frame properties, and confirm rebuilding the legend keeps its title, font size, location, columns, and frame state.
16. Add a curve that expands the canvas range and confirm the Common Inspector
    updates immediately. Then modify axis range, axis labels, label font size,
    bottom spine state, and legend position; the Bottom Spine action must
    replace the previous Message Bar text with one green success message.
17. Narrow the Inspector until vertical scrolling is required. Visit all six Axes pages and confirm controls remain reachable without expanding the main window.
18. Add a text element and edit its content, font, size, and position.
19. Save the current project, open it in a fresh workspace, and confirm plot, scatter, interpolation, fitting result, axes state, text, and Inspector values restore.
20. Right-click the canvas tab, rename the project, and confirm existing charts and fitting data references still redraw.
21. Right-click the sheet tab, rename the sheet, and confirm existing charts and fitting data references still redraw.
22. Create a second project and confirm switching canvas tabs switches the visible table.
23. Open a second different project and confirm it coexists with the current project.
24. Try opening the same project twice and confirm the second open is rejected without changing the workspace.
25. Enter invalid expression, data reference, color, range, and interpolation values. Confirm each failed operation restores the last valid control and artist state and reports exactly one red Message Bar error.

## Matplotlib Style Creation Defaults

1. Create a `fivethirtyeight` project and add Axes. Open Curve, Plot, Scatter,
   Fit, and Interpolation dialogs; confirm their first color is `#008FD5` and
   the Plot line width is `4`.
2. Create charts successfully one at a time and confirm their default colors
   advance through the style cycle. Cancel a dialog and confirm the next color
   is unchanged.
3. Create a `seaborn-v0_8-poster` project and confirm the Scatter size is
   `125.44`, including its decimal value and range.
4. Create a `dark_background` project, add free Text, and confirm the new text
   is white. Switch back to another canvas and reopen Text; confirm its font
   and size follow that canvas rather than the previous dialog.
5. Open the Axes Palette section and confirm it shows `Style default`, the
   Figure style name, and its color strip. Switch to a named built-in or
   custom palette and confirm the name and colors are shown and applied to
   existing and later charts. Cancel the chooser and confirm the source rolls
   back.
6. Switch the Palette source back to `Style default` and confirm the current
   Figure style colors are reapplied. Change the Figure style in the
   Inspector and confirm existing artists do not change until this explicit
   Palette switch, while later Style-default creations use the new style.
7. Save and reopen the project. Confirm existing component properties, Figure
   style, active palette source, and next color position are restored.

## Optional Local Integrations

These checks depend on local system setup and should not block baseline GUI maintenance.

1. Enable TeX rendering and update the TeX preamble.
2. Open the MATLAB panel and click `Connect Matlab`.
3. Load metadata for at least `poly2` and `gauss1`; confirm their advanced option controls differ by model.
4. With advanced options disabled, fit `poly2` and confirm the curve redraws.
5. With advanced options disabled, fit a nonlinear model such as `gauss1`; confirm the curve redraws instead of leaving a previous polynomial line in place.
6. Enable advanced options, set valid numeric bounds or start points, fit once, and confirm the result area shows coefficient values, 95% bounds, and goodness-of-fit metrics.
7. Enter an invalid advanced numeric value and confirm the GUI warns locally without starting a MATLAB fitting request.

## Notes

- If MATLAB or LaTeX is unavailable, record that as an environment limitation rather than a baseline GUI failure.
- If a smoke step fails, capture the exact action, visible error, and whether the Python process stayed alive.
- Fitting engines, options, and MATLAB runtime settings are documented in `docs/fitting.md`.
- Interpolation methods and parameters are documented in `docs/interpolation.md`.

# Manual Smoke Test

Run these checks from the repository root after GUI-facing changes.

## Start

```powershell
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe main.py
```

Expected result: the main PySide6 window opens without requiring MATLAB or LaTeX.

## Window and Responsive Layout

1. Confirm the application starts maximized with the native Windows title bar and only one taskbar window.
2. Confirm the dark command bar and bottom Message/State Bar span the full window width.
3. Confirm the left workspace and right figure workspace touch through a visible splitter with no desktop showing between them.
4. Drag both workbench splitters. Switch between Table and Components,
   click the active page again to hide the Explorer, restart, and confirm the
   splitter, page, and visibility preferences restore.
5. Use Settings > `Reset workspace layout` and confirm the default proportions return and the Message Bar reports success in green.
6. With no project, confirm the figure empty state directs the user to Style; create a project and confirm the empty state is replaced by its canvas tab.
7. Resize a restored window through 960x600, 1280x720, 1366x768, and 1920x1080; confirm the command gallery uses overflow instead of clipping and the canvas remains visible.
8. Switch repeatedly between the figure inspector, TeX, and MATLAB pages; confirm the main layout does not jump or grow.
9. On available 100%, 125%, 150%, and 200% displays, confirm text/icons remain clear and menus/dialogs stay on the active screen.
10. Move the window between monitors with different scaling and verify native maximize/restore, resize, and snap behavior.
11. In a project with at least one chart, click the rightmost Canvas Window
    toolbar button. Confirm a maximized, non-modal native window immediately
    renders the canvas content and contains only that viewport, while the
    original tab shows its placeholder. Pan or zoom in the separate window and
    edit a Component from the main window; confirm every edit appears there at
    once and neither view changes the document size or DPI. Click the button
    again and confirm no duplicate window is created. Close the window with its
    system close button, reopen it, and close it again with Esc; confirm both
    paths return the canvas, its scroll position, and the focus to the project
    tab.
12. Open Canvas Windows for two projects, switch tabs, and move the windows
    between monitors. Confirm both stay usable and independently maximized.
    Rename one project and confirm its window title updates. Close one project,
    clear all projects, and exit the application with a window open; confirm no
    orphan Canvas window or taskbar entry remains.

For a 6.4 x 4.8 inch, 100 DPI test figure, a default PNG export must be 640 x 480 pixels at every display scale. Save and reopen the project and confirm its recorded DPI remains 100.

## Core Workflow

1. Create a new project from the style toolbar and enter a unique project name.
2. Confirm the table area shows only that project's table and a `Sheet1` sheet.
3. Add axes from the layout toolbar.
4. Import an Excel workbook through the file menu and confirm data lands in the current project table.
5. Save table data to the in-memory database from the sheet/table workflow if needed.
6. Create a plot using two saved data columns. Confirm the line-style control
   initially reads `Solid`, selecting `Dashed` creates a dashed line, and the
   Inspector shows the same style. Reopen Plot, select one shared X and at
   least three Y columns from the checkable dropdown, and confirm the compact
   field reports the selected count. Confirm the X/Y `fx` expression inputs
   remain visible beside their data selectors. Create the batch and confirm
   the curves receive distinct palette colors and Y-column legend labels.
7. Create a scatter chart using two saved data columns.
   Select multiple Y columns and confirm one Scatter component is created per
   Y with shared marker/size settings; edit one afterward and confirm the
   other Scatter components remain unchanged.
   In Plot and Scatter, set X `fx` to `1/x` and Y `fx` to `y`; confirm the
   reciprocal-X data is drawn. Enter an unsafe or malformed expression and
   confirm all four source/formula controls and the artist roll back with one
   red result. Include X = 0 and confirm one yellow filtered-row warning.
8. Create interpolation curves from one shared X and multiple Y columns,
   change their shared method and `Samples`, and confirm each resulting curve
   redraws independently. Include one Y column that cannot satisfy the method
   and confirm the complete batch is rejected with one red result, no palette
   advance, and no partial component.
9. Change method-specific interpolation options and confirm the curve redraws.
10. Change interpolation X/Y data sources from the right-side panel and confirm only current-project data is listed.
11. Create a SciPy fitting curve, run `poly2`, and confirm the result area shows coefficients and goodness metrics.
    Change a Fit preprocessing expression while a fit is running; confirm the
    old request cannot overwrite the changed source state, the previous curve
    remains, and one yellow message requests a new fit. Refit and confirm its
    displayed range follows transformed X.
12. Select Function Curve, Data Plot, Fit Curve, and Interpolation nodes in
    the Components tree. Confirm exactly one Inspector is visible and each
    uses the same Basic, Marker, and Advanced line appearance fields in the
    same order, including line style and marker fields for Interpolation.
13. In Fit Curve, confirm Data Source, Fit Operations, Fit Result, Display Range, and Appearance are separate sections. Changing X/Y must request a manual refit rather than silently recomputing.
14. Edit Title, X Label, Y Label, and free Text. Confirm they show the same Content, Typography, Rotation and Alignment, Position, and Rendering sections; only free Text offers deletion.
15. Open Legend with no plotted handles, then with plotted handles. Switch between a preset and a custom coordinate location, change columns and frame properties, and confirm rebuilding the legend keeps its title, font size, location, columns, and frame state.
16. Add a curve that expands the canvas range and confirm the Common Inspector
    updates immediately. Then modify axis range, axis labels, label font size,
    bottom spine state, and legend position; the Bottom Spine action must
    replace the previous Message Bar text with one green success message.
17. Narrow the Inspector until vertical scrolling is required. Select Axes,
    Axis, Spine, Tick, Grid, Title, Label, and Legend tree nodes and confirm
    each exact Inspector remains reachable without expanding the main window.
18. Add a text element and edit its content, font, size, and position.
19. Save the current project, open it in a fresh workspace, and confirm plot, scatter, interpolation, fitting result, preprocessing expressions, axes state, text, and Inspector values restore. Fit must restore its saved result without running an engine.
20. Right-click the canvas tab, rename the project, and confirm existing charts and fitting data references still redraw.
21. Right-click the sheet tab, rename the sheet, and confirm existing charts and fitting data references still redraw.
22. Create a second project and confirm switching canvas tabs switches the visible table.
23. Open a second different project and confirm it coexists with the current project.
24. Try opening the same project twice and confirm the second open is rejected without changing the workspace.
25. Enter invalid expression, data reference, color, range, and interpolation values. Confirm each failed operation restores the last valid control and artist state and reports exactly one red Message Bar error.
26. Add two Function Curves. Right-click the first tree node while the second
    is selected and delete it; confirm the lightweight dialog names the first
    curve and its stable ID, defaults to Cancel, and only that clicked curve,
    Inspector, and artist disappear after confirmation with one green result.
27. Right-click a Function Curve tree node and choose
    `Batch Delete Same Type...`. Confirm the batch dialog
    starts fully selected, `Clear All` disables `Delete (0)`, partial
    selection deletes only checked instances, and deleting all removes the
    corresponding tree nodes. Give multiple curves the same preview and
    confirm their numbered labels remain distinct. Filter to one curve and
    confirm the dialog still lists the complete same-parent/type cohort and
    states that search does not narrow deletion scope.
    With a color palette active, delete the middle of three palette-colored
    charts and confirm the next creation previews the released middle color;
    surviving chart colors must not change.
    Repeat with an injected or otherwise reproducible failure and confirm the
    original artists, tree selection/expansion, callbacks, and Inspector objects
    and palette cursor remain in place; only one red result is shown.
28. Create a 2x2 Axes layout and delete the first, middle, and last Axes in
    separate runs. Confirm the deleted cell remains empty; every surviving
    Axes keeps its original position and subplot slot without overlap or
    expansion. Confirm the dialog reports the cascade count, stable surviving
    IDs and subplot slots persist after save/open, labels remain
    `Axes 1...Axes N`, and deleting the final remaining Axes shows the Figure
    root Inspector. On a forced failure, confirm the Figure Axes order,
    current Axes, shared/twinned links, Axes Panel, tree selection, and layout
    do not change and no intermediate removal is visible.
    Add a Figure-level free Text before deleting the final Axes and confirm
    fallback still selects the Figure root rather than crossing to Text.
29. Confirm Layout shows Single Axes, Horizontal Comparison, Vertical Stack,
    2 × 2 Grid, 3 × 3 Grid, Primary + Right Y, and Main Plot + Residual with
    their matching icons. Create each template and confirm its dialog does not
    repeat the template, row/column, or occupied-cell choices. For Horizontal
    Comparison, disable and re-enable Share Y axis; repeat with Share X axis in
    Vertical Stack. Confirm independent/shared behavior and label visibility
    follow the switch. Confirm 2 × 2 and 3 × 3 remain independent.
30. Open `Edit layout geometry…`, change ratios, margins, and spacing, and
    confirm Axes artists and Component IDs remain unchanged. Confirm the edit
    dialog shows a persisted relationship summary without creation-only Axes,
    template, occupancy, sharing, or twin controls.
31. Save one of two projects while its tab is in the background and confirm
    the file contains that project. Modify a saved project through the Table,
    Component Inspector, and toolbar zoom, then close its tab and verify
    Save/Discard/Cancel, Save As cancellation, and save failure behavior.
32. Exit with multiple dirty projects. Confirm any Cancel or failed save
    aborts exit without closing a project, while an earlier successful save
    remains clean.

## Keyboard Shortcuts

1. In the table, select several cells, press Ctrl+C, move the selection, and press Ctrl+V. Confirm the pasted TSV block lands as one undo command, then press Delete and confirm the cleared cells become missing values.
2. Focus a project canvas and press p; drag with the left button to pan and the right button to zoom. Press o and drag a rectangle to zoom. Press h to reset the view, and press s to open the image save dialog.
3. Open the Plot creation dialog, open the Y dropdown, move the highlight with the arrow keys, and press Space. Confirm the highlighted column toggles without closing the dropdown, and the Create button count follows.

See [Keyboard and Mouse Reference](keyboard-and-mouse-reference.md) for the complete lists.

## In-Axes Elements

1. With no project and then with a project but no selected Axes, click
   Elements > `in_axes`. Confirm creation is intercepted with one useful
   warning and no child Axes is left behind.
2. Create Line and Scatter charts, open `in_axes`, choose Zoom, enter X/Y
   ranges and normalized bounds, and create it. Confirm the Figure still has
   the same number of main Axes and the new node appears under `Zoom Insets`
   in the selected parent Axes.
3. Modify source data, color, marker, line style, visibility, scale, and axis
   direction; then create and delete another source chart. Confirm the inset
   refreshes all visible Line/Scatter mirrors, never shows Text or Legend, and
   does not advance the Axes palette.
4. Edit Layout, Frame, Zoom Range, and Indicator Inspector sections. Confirm
   the position, size, range, ticks, region rectangle, and connector styling
   update without canvas dragging or a second Component state model.
5. Create an empty Zoom inset under an Axes with no supported visible chart.
   Confirm it remains editable and one yellow Message Bar warning explains
   that it is empty.
6. Open `in_axes` again, choose Image, preview PNG, JPEG, BMP, and TIFF files,
   and exercise transparent PNG and EXIF-rotated JPEG inputs. Confirm invalid,
   damaged, mismatched, or oversized payloads leave the dialog open.
7. For an Image inset, edit opacity, `contain`/`stretch`, interpolation,
   layout, and frame. Replace the image from its Image Inspector section and
   confirm the tree preview shows the new base filename.
8. Save the project, move or delete the source image, and reopen it. Confirm
   the embedded image, stable inset IDs, Zoom sources, ranges, and styles are
   restored. Export the Figure and confirm both inset modes are present.
9. In a multi-Figure, multi-Axes workspace, create insets under different
   parents. Confirm selection never changes the current main Axes or subplot
   numbering and each Zoom mirrors only its own parent.
10. Delete one inset, batch-delete same-role insets, then delete their parent
    Axes. Confirm child Axes, image/mirror artists, zoom rectangle, connectors,
    Inspector, and tree nodes disappear atomically and one result is shown.
    On an injected failure, confirm all original object identities, selection,
    listeners, and visible artists remain.

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

## Reference Marks

1. With no selected Axes, choose Elements > `Reflection Positions`. Confirm
   creation is intercepted with one warning and no Component or collection is
   left behind.
2. Select an ordinary Axes, enter `15.2, 15.2, 22.9`, label it `YBCO`, and
   create it. Confirm one `Reflection Positions — YBCO` node appears in the
   Components tree and one Inspector opens.
3. Change Baseline, Height, Color, Line width, Line style, Alpha, Z order, and
   Clip on. Confirm the same collection updates, the marks remain at normalized
   Axes Y positions when Y limits change, and X zoom/pan moves or clips them
   with the data coordinates.
4. Replace Positions with an empty value and apply. Confirm the component and
   Inspector remain and no marks draw. Restore the duplicate sequence and
   confirm input order and duplicates remain.
5. Choose a Number column in the Table column selector, apply, and confirm the
   marks append those values after the manual positions. Edit the column and
   confirm the marks refresh without a new Undo command. Delete that column,
   confirm the component is removed after the dependency prompt, then Undo and
   confirm the original ID, reference, and selection return.
6. Enter malformed or non-finite positions and geometry where
   `baseline + height > 1`. Confirm the input, Controller state, collection,
   and tree preview return to their last valid values with one red result.
7. Save, close, and reopen the project. Confirm the stable ID, exact ordered
   positions, optional column reference, appearance, and one collection restore. Undo/Redo data and style
   edits and confirm clean/dirty state follows the latest saved fingerprint.
8. Delete the component from the tree, Undo, and Redo. Confirm the tree node,
   Inspector, collection, selection, and stable state disappear and return
   atomically with one result per action.

## Reference Guides

1. With no selected ordinary Axes, choose Elements > `Add Reference Line` and
   then `Add Reference Band`. Confirm each action is intercepted with one
   warning and no collection, Component, Inspector, or history command remains.
2. Select an ordinary Axes and add a vertical Reference Line at `2.5` with span
   `0.2` to `0.8`. Add a horizontal Reference Band from `-0.5` to `0.5` with
   span `0.1` to `0.9`. Confirm both appear under one **Reference Guides** tree
   group with formula previews and exact Inspector profiles.
3. Pan, zoom, switch the applicable data axis to logarithmic scale, and change
   both Axes limits. Confirm each guide follows its data-coordinate value or
   bounds, retains its normalized Axes span, and does not expand `dataLim`,
   relimit, or autoscale limits.
4. Edit orientation, value/bounds, span, label, visibility, colors, line style,
   line width, alpha, z order, and clipping. Confirm the same LineCollection or
   PolyCollection updates and one user action creates one history command.
5. Enter a non-finite value, equal/reversed band bounds, an out-of-range span,
   or `span_start >= span_end`. Confirm UI, Controller state, collection,
   selection, tree preview, and dirty state return atomically to their last
   valid values with one red result.
6. Create guides on separate ordinary Axes and on a right-Y Axes. Confirm each
   guide belongs to the selected Axes and uses that Axes' blended transform.
   Delete multiple Reference Lines together, then Undo/Redo; repeat by deleting
   their owning Axes and confirm the full subtree restores with stable IDs.
7. Save, close, and reopen the schema-v15 project. Confirm orientation,
   position/bounds, spans, appearance, stable IDs, order, empty `data`, one
   runtime collection per guide, selection/Inspector behavior, and clean/dirty
   fingerprints survive the round trip. Close the project and confirm no
   project, tree, Inspector, callback, or history resource remains active.

## FullProf XRD Refinement Import

Use `tests/test_datas/XRD/YBCO.prf` as the representative v1 input.

1. Open or create a project and select **Main Plot + Residual**.
2. Leave **Import XRD refinement result** off, create the layout, and confirm
   the ordinary 2 × 1, 3:1, shared-X layout still works without new Sheets.
3. Open **Main Plot + Residual** again, select the **XRD Refinement** tab, and
   enable the import checkbox.
4. Browse for `YBCO.prf`. Confirm the filter reads `FullProf PRF (*.prf)` and
   the preview shows YBCO, χ² `2.3177`, 3,803 profile points, 338 reflections,
   and the 2θ range.
5. Select a nonexistent or malformed `.prf` and confirm inline validation
   disables **Create**. Restore the valid fixture.
6. Toggle the Observed, Calculated, Reflection positions, and Residual legend
   checkboxes, then create the result.
7. In the Table Explorer, confirm `<source> Profile` contains `2Theta`, `Yobs`,
   `Ycal`, `Yobs-Ycal (PRF)`, `Residual`, and `Backg`; confirm `<source>
   Reflections` contains `2Theta`, `h`, `k`, and `l` with duplicate positions
   preserved.
8. Confirm the Main Axes contains one Observed Scatter, one Calculated Data
   Plot, and one editable Reflection Positions component whose data is an empty
   manual sequence plus the Reflections/`2Theta` column. Confirm the main Y
   range keeps ordinary autoscale content in the upper 90% and the reflection
   marks sit in the lower 10% band. Confirm Backg is not plotted and no extra
   vertical-line artists exist.
9. Confirm the lower Axes contains one Residual Data Plot whose first value is
   `Yobs - Ycal`, not the offset `Yobs-Ycal (PRF)` value, and that Residual
   Axes Y reserve stays at `0`.
10. Open the four XRD property buttons, confirm the default styles, Cancel
    without changing the request, then override colors/sizes and create.
11. Change the X limits and confirm both Axes move together. Change either Y
    limit and confirm reflection marks keep their normalized Axes height.
12. Confirm each selected Main legend entry appears, each excluded entry is
    absent, the lower legend contains only Residual when selected, and an empty
    selection hides its corresponding legend.
13. Save the project and close it. Temporarily move or rename `YBCO.prf`, then
    reopen the project and confirm both imported Sheets, all four components,
    the shared layout, Axes `y_lower_reserve`, and the legends remain complete
    without a file prompt.
14. In a fresh import, Undo once and confirm only the Figure setup disappears
    while both Sheets remain. Undo again and confirm both imported Sheets are
    removed. Redo twice and confirm the Sheets return before the data-backed
    Figure components.

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

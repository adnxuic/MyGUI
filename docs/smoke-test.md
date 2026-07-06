# Manual Smoke Test

Run these checks from the repository root after GUI-facing changes.

## Start

```powershell
python main.py
```

Expected result: the main PySide6 window opens without requiring MATLAB or LaTeX.

## Core Workflow

1. Create a new project from the style toolbar and enter a unique project name.
2. Confirm the table area shows only that project's table and a `Sheet1` sheet.
3. Add axes from the layout toolbar.
4. Import an Excel workbook through the file menu and confirm data lands in the current project table.
5. Save table data to the in-memory database from the sheet/table workflow if needed.
6. Create a plot using two saved data columns.
7. Create a scatter chart using two saved data columns.
8. Create an interpolation curve from saved data, change its method, set `Samples`, and confirm the curve redraws.
9. Change method-specific interpolation options and confirm the curve redraws.
10. Change interpolation X/Y data sources from the right-side panel and confirm only current-project data is listed.
11. Create a SciPy fitting curve, run `poly2`, and confirm the result area shows coefficients and goodness metrics.
12. Modify axis range, axis labels, label font size, bottom spine state, and legend position.
13. Add a text element and edit its content, font, size, and position.
14. Save the current project, open it in a fresh workspace, and confirm plot, scatter, interpolation, fitting result, axes state, and text restore.
15. Right-click the canvas tab, rename the project, and confirm existing charts and fitting data references still redraw.
16. Right-click the sheet tab, rename the sheet, and confirm existing charts and fitting data references still redraw.
17. Create a second project and confirm switching canvas tabs switches the visible table.
18. Open a second different project and confirm it coexists with the current project.
19. Try opening the same project twice and confirm the second open is rejected without changing the workspace.
20. Enter invalid interpolation input such as duplicate X values and confirm the Message Bar shows a red error while the app stays open.

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

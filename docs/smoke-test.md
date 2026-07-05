# Manual Smoke Test

Run these checks from the repository root after GUI-facing changes.

## Start

```powershell
python main.py
```

Expected result: the main PySide6 window opens without requiring MATLAB or LaTeX.

## Core Workflow

1. Create a new figure from the style toolbar.
2. Add axes from the layout toolbar.
3. Import an Excel workbook through the file menu.
4. Save table data to the in-memory database from the sheet/table workflow.
5. Create a plot using two saved data columns.
6. Create a scatter chart using two saved data columns.
7. Create an interpolation curve from saved data.
8. Modify axis range, axis labels, and legend position.
9. Add a text element and edit its content, font, size, and position.

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

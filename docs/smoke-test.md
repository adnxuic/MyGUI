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
2. Open the MATLAB panel, connect MATLAB, and run a fitting workflow.

## Notes

- If MATLAB or LaTeX is unavailable, record that as an environment limitation rather than a baseline GUI failure.
- If a smoke step fails, capture the exact action, visible error, and whether the Python process stayed alive.

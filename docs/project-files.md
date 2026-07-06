# Project Files

MyGUI project files use schema version 3. A project is exactly one canvas and one
table with the same name. The table contains all sheets that belong to that
canvas.

## Contents

- `name`: project, canvas, and table name. It must be non-empty and cannot
  contain `/` or `\`.
- `table`: the single bound table. `table.name` must match `name`.
- `table.sheets`: all sheets in the bound table. Sheet names must be non-empty
  and cannot contain `/` or `\`.
- `figure`: the single canvas snapshot. `figure.name` must match `name`.
- `figure.fits`: fitting curves. Each record stores the source X/Y data names,
  engine, selected fit type/options, saved fit result, final drawing expression,
  style, color, label, and X range.
- `figure.axes`: per-axes view and label state, including limits, labels, label
  font, label positions, axis visibility, spine state, and legend position.

Data references still use `ProjectName/SheetName/Column`. Plot, scatter,
interpolation, and fitting inputs must reference the current project's table.
Cross-project table references are invalid in project files.

## Workflow

- Creating a canvas from Style creates a same-name table with `Sheet1`.
- Switching canvases switches the visible table to that canvas's bound table.
- Renaming a canvas tab renames the project and its bound table, and rewrites
  chart data references.
- Renaming a sheet tab rewrites chart data references for that sheet.
- Saving writes only the current canvas and its bound table.
- Opening a project appends it beside existing projects. If a project with the
  same name already exists, opening is rejected.
- Opening restores saved fitting curves without rerunning the fitting engine.
- Opening applies saved axes state after recreating charts, so saved ranges and
  labels are not replaced by autoscaling.

Schema v3 intentionally does not load old workspace-level project files.

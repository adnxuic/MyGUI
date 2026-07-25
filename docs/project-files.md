# MyGUI Project Files

Project files use JSON schema version 4. A file contains one project, its typed Table document, and one matplotlib canvas.

## Root fields

- `schema`: always `mygui-project`.
- `schema_version`: always `4`.
- `project`: stable project `id` and editable `name`.
- `table`: project table document.
- `figure`: canvas, axes, chart, fitting, interpolation, and text records.

Window geometry, splitter sizes, table visibility, command selection, and optional-integration runtime state are application preferences. They are not project fields and opening a project does not change them.

## Table fields

`table.id` and `table.name` match the project. `table.sheets` is an ordered array. Each Sheet stores:

- `id`: stable UUID.
- `name`: unique display name.
- `row_count`: logical number of stored rows.
- `columns`: ordered typed columns documented in `table-driven-chart-refresh.md`.

Missing cells are JSON `null`; number, text, Boolean, and ISO 8601 date/time values retain their types.

## Data-source fields

Plot, Scatter, Interpolation, and Fit records contain a stable `object_id` plus `x_ref` and `y_ref` objects. Each reference contains `project_id`, `sheet_id`, and `column_id`. Every referenced column must exist in the same project.

## Figure size and DPI

`figure.size_inches` stores the document width and height in inches. `figure.dpi` stores the document/export DPI. Display scaling and the active screen's device pixel ratio do not change these fields. A default figure export uses `figure.dpi`; an explicit export DPI only changes that export.

Project writes use a temporary file followed by replacement, with a direct-write fallback for Windows permission behavior. The loader validates the complete v4 structure before mutating the application.

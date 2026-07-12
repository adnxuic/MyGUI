# MyGUI Project Files

Project files use JSON schema version 4. A file contains one project, its typed Table document, and one matplotlib canvas.

## Root fields

- `schema`: always `mygui-project`.
- `schema_version`: always `4`.
- `project`: stable project `id` and editable `name`.
- `table`: project table document.
- `figure`: canvas, axes, chart, fitting, interpolation, and text records.

## Table fields

`table.id` and `table.name` match the project. `table.sheets` is an ordered array. Each Sheet stores:

- `id`: stable UUID.
- `name`: unique display name.
- `row_count`: logical number of stored rows.
- `columns`: ordered typed columns documented in `table-driven-chart-refresh.md`.

Missing cells are JSON `null`; number, text, Boolean, and ISO 8601 date/time values retain their types.

## Data-source fields

Plot, Scatter, Interpolation, and Fit records contain a stable `object_id` plus `x_ref` and `y_ref` objects. Each reference contains `project_id`, `sheet_id`, and `column_id`. Every referenced column must exist in the same project.

Project writes use a temporary file followed by replacement, with a direct-write fallback for Windows permission behavior. The loader validates the complete v4 structure before mutating the application.

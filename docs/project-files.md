# MyGUI Project Files

Project files use JSON schema version 5. A file contains one project, its typed Table document, and one matplotlib canvas. Schema-v4 files migrate in memory to v5 with an empty color-cycle state and are written as v5 on their next save.

## Root fields

- `schema`: always `mygui-project`.
- `schema_version`: always `5` after loading or saving.
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

Curve, Plot, Scatter, Interpolation, and Fit records also contain `color_order`, a non-negative unique integer used to restore cross-type creation order. Their `color` fields are validated before the project mutates application state and normalized to uppercase `#RRGGBB` or `#RRGGBBAA`.

## Axes color-cycle fields

Each `figure.axes[]` record contains `color_cycle`. It is `null` when no palette is active. Otherwise it contains:

- `palette.id`: stable built-in or custom palette identifier.
- `palette.name`, `palette.category`, and `palette.source`: display and provenance metadata.
- `palette.colors`: the complete ordered normalized color snapshot.
- `next_index`: the next palette position, from zero through `colors.length - 1`.

The embedded snapshot keeps a project's palette usable when its custom application-library entry has been changed or deleted.

## Figure size and DPI

`figure.size_inches` stores the document width and height in inches. `figure.dpi` stores the document/export DPI. Display scaling and the active screen's device pixel ratio do not change these fields. A default figure export uses `figure.dpi`; an explicit export DPI only changes that export.

Project writes use a temporary file followed by replacement, with a direct-write fallback for Windows permission behavior. The loader migrates v4 when needed, then validates the complete v5 structure, data references, colors, and palette cursor before mutating the application.

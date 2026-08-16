# MyGUI Project Files

MyGUI project files use strict JSON schema version 10. One file contains one project, its typed Table document, and one Matplotlib Figure component tree. The loader accepts only the exact integer version `10`; schema v4-v9 and unknown versions are intentionally unsupported and are not migrated in-process.

## Root structure

```json
{
  "schema": "mygui-project",
  "schema_version": 10,
  "project": {"id": "project-id", "name": "Project name"},
  "table": {},
  "figure": {
    "root_component_id": "figure-component-id",
    "components": []
  }
}
```

- `schema` is always `mygui-project`.
- `schema_version` is always the integer `10`.
- `project.id` is stable and must match `table.id`.
- `project.name` is editable and must match `table.name`.
- `table` is the typed table document.
- `figure` contains only `root_component_id` and `components`; legacy axes/chart arrays are not written alongside the tree.

Window geometry, splitter sizes, table visibility, command selection, and optional-integration runtime state are application preferences rather than project fields.

## Table document

`table.sheets` is an ordered array. Each Sheet stores:

- `id`: stable UUID.
- `name`: case-insensitively unique display name.
- `row_count`: logical row count.
- `columns`: ordered typed columns.

Each column stores `id`, `name`, `type`, `width`, and `values`. Missing cells are JSON `null`; number, text, Boolean, and ISO 8601 date/time values retain their types. See `table-driven-chart-refresh.md` for the table and reference model.

## Component record

Every entry in `figure.components` has exactly these fields:

```json
{
  "id": "stable-component-id",
  "kind": "line",
  "role": "data_plot",
  "parent_id": "axes-component-id",
  "order": 3,
  "selector": {"object_id": "stable-component-id"},
  "properties": {},
  "data": {}
}
```

- `id`: non-empty stable identifier, unique in the Figure.
- `kind`: controlled component family.
- `role`: controlled specialization valid for the selected `kind`.
- `parent_id`: parent component ID, or JSON `null` only for the Figure root.
- `order`: non-negative sibling/runtime ordering value. Chart component orders are unique across Line and Scatter records so color sequencing remains stable.
- `selector`: semantic identity used to resolve dynamic Matplotlib objects. Examples are `{"index": 0}` for an Axes, `{"axis": "x", "level": "major"}` for an axis group, and `{"object_id": "..."}` for a stable artist.
- `properties`: visual and editable state using Controller property names.
- `data`: non-visual, role-specific source data.

The controlled kind/role combinations are:

| Kind | Roles |
| --- | --- |
| `figure` | `figure` |
| `axes` | `axes` |
| `axis` | `x_axis`, `y_axis` |
| `spine` | `spine` |
| `tick_group` | `major_tick`, `minor_tick` |
| `tick_label_group` | `major_tick_label`, `minor_tick_label` |
| `grid` | `grid` |
| `text` | `title`, `x_label`, `y_label`, `text` |
| `legend` | `legend` |
| `line` | `line`, `function_curve`, `data_plot`, `fit_curve`, `interpolation` |
| `scatter` | `scatter` |
| `in_axes` | `in_axes_zoom`, `in_axes_image` |

## Figure hierarchy and fixed components

`figure.root_component_id` identifies the sole parentless `figure/figure` record. Its properties include `name`, `style`, `size_inches`, `dpi`, face/edge/frame appearance, linewidth/alpha, and tagged `layout_engine`. The saved `style` supplies defaults only for components created later; every existing component restores from its concrete saved properties.

The Figure root stores `data.layouts`. Each record contains a stable `id`, grid dimensions, positive row/column ratios, normalized margins, and non-negative horizontal/vertical spacing.

Each `axes/axes` child stores:

- `properties.xlim` and `properties.ylim`: two-number ranges.
- `properties.aspect`, margins, box aspect, anchor/adjustable, `facecolor`, `visible`, `autoscalex_on`, and `autoscaley_on`.
- `properties.color_cycle`: JSON `null` or a complete color-cycle snapshot.
- `data.subplot`: stable `layout_id`, zero-based `row`/`column`, `layer` (`primary` or `right_y`), and nullable `share_x_group` / `share_y_group` identifiers.

Axes position is derived from its Figure layout rather than persisted as an independently editable property. Each X/Y Axis owns its tagged scale, locator, and formatter configuration. Ordered Axes limits are the sole inversion authority.

Every Axes contains fixed semantic children:

- one X Axis and one Y Axis;
- left, right, bottom, and top Spines;
- Major and Minor Tick groups for both axes;
- one Tick Label group for each Tick group;
- Major and Minor Grid groups for both axes;
- Title, X Label, Y Label, and Legend components.

Tick, Tick Label, Grid, and Legend targets may be recreated by Matplotlib. Their selectors identify the semantic group rather than a transient artist instance.

## Artist properties and role data

Line visual properties include tagged line/marker/markevery values, draw style, gap color, marker fill and alternate face color, cap/join/antialias controls, and safe advanced Artist fields.

Scatter visual properties include uniform face/edge appearance, tagged marker and line pattern, hatch/cap/join/antialias controls, and tagged color/size mapping specifications. See `matplotlib-component-properties-v10.md` for the complete property matrix and composite formats.

Role-specific `data` fields are:

| Role | Data fields |
| --- | --- |
| `line` | finite, equal-length `x` and `y` arrays |
| `function_curve` | `expression`, `x_start`, `x_stop` |
| `data_plot` | `x_ref`, `y_ref`, `preprocess` |
| `scatter` | `x_ref`, `y_ref`, optional `color_ref`, optional `size_ref`, `preprocess` |
| `interpolation` | `x_ref`, `y_ref`, `preprocess`, `method`, `k`, `samples`, `lam`, `lam_auto` |
| `fit_curve` | `x_ref`, `y_ref`, `preprocess`, `engine`, `fit_type`, `fit_options`, `fit_result`, `expression`, `x_start`, `x_stop` |
| `in_axes_zoom` | no persisted data; mirrors are derived at runtime |
| `in_axes_image` | `filename`, detected `mime_type`, original `payload_base64` bytes |

Free Text, Title, and Axis Label records share the safe Text typography, alignment, bbox, math/TeX, z-order, and export contract. Only Free Text persists a selectable data/axes/figure coordinate system.

Legend properties use tagged location and anchor records, complete entry/title fonts, columns/layout, points/scaling, spacing/padding, frame appearance, dragging, z-order/export fields, and `entry_scope` (`axes` or `twin_pair`).

An `in_axes` record is a removable child of a main Axes and uses
`selector: {"object_id": component_id}`. Both roles persist normalized parent
Axes `bounds`, `visible`, `zorder`, `facecolor`, `frameon`, `edgecolor`, and
`linewidth`. Zoom additionally stores `xlim`, `ylim`, tick/region/connector
visibility and indicator appearance. Image additionally stores `opacity`,
`fit_mode` (`contain` or `stretch`), all Matplotlib 3.9 image interpolation
values, origin/extent and resampling/filter/export fields. Image filenames cannot contain a path, the MIME type must match
the decoded PNG/JPEG/BMP/TIFF payload, and decode safety is checked before any
application state changes.

## Data references, colors, and palette cursor

`x_ref`, `y_ref`, and optional Scatter `color_ref`/`size_ref` contain `project_id`, `sheet_id`, and `column_id`. The reference must resolve inside the same project. X accepts Number or Datetime columns; Y and mapping columns accept Number columns.

`preprocess` contains exactly `x_expression` and `y_expression`. Both are
validated element-wise mathematical expressions over the fixed variables
`x` and `y`; identity values are `x` and `y`. Date/time X references require
the identity X expression and prohibit using `x` in the Y expression. See
`data-preprocessing.md` for the expression and row-validity contract.

Color properties are normalized to uppercase `#RRGGBB` or `#RRGGBBAA`. An Axes color-cycle snapshot is JSON `null` when no palette is active; otherwise it stores:

- `palette.id`, `name`, `category`, and `source`;
- the complete ordered `palette.colors` snapshot;
- `next_index`, the next palette position.

Embedding the palette keeps a project reproducible if a custom application palette later changes or is deleted. A palette derived from `axes.prop_cycle` uses `source: "matplotlib-style"` and is stored after the first successful palette-backed chart creation. Older or untouched Axes may retain `color_cycle: null`; their next creation position is derived from the next persisted chart order.

The Axes Palette panel treats a `matplotlib-style` snapshot (or `null`) as
`Style default`. Any other palette source is `User-selected`; the embedded
palette name is displayed even when its application-level custom palette has
later been renamed or deleted. Switching sources updates this existing
snapshot only and does not change schema v10.

## Stable IDs and compatibility

Component, project, Sheet, column, layout, and data-reference IDs are persisted unchanged and must remain stable across every schema-v10 save/open round trip. Schema versions v4 through v9, non-integer versions, and unknown versions are rejected before Table or Figure state is published. A future format change must use a new schema version rather than silently normalizing an older file.

After validation, restore materializes Figure, Axes/layout groups, fixed semantic
children and source chart/Text artists first, then `in_axes` Elements and
Legend directly from the v10 tree. Zoom mirrors receive one final batch refresh
after their sources exist. Restore does not
create legacy chart arrays or Modifier records as an intermediate runtime
format. The Registry tree is subsequently the source for every save.

Component-level fallback messages accumulated while materializing a complete
tree are discarded at the restore transaction boundary. A successful open
therefore reports one final `Project opened: ...` result instead of exposing
internal messages such as `Legend updated.`; a failed open reports its single
final error or warning. Direct environment warnings that are meaningful to the
user, such as unavailable TeX support, remain visible.

## Validation and writes

Before Table or Figure application state changes, the loader validates:

- exactly one Figure root matching `root_component_id`;
- unique component IDs, known kind/role pairs, existing parents, an acyclic connected hierarchy, and unique semantic selectors;
- required fixed Axes children, valid layout cells, twin pairs, and consistent shared-axis groups;
- property/data JSON types, finite numbers, normalized colors, and unique chart order values;
- data references, compatible column types, preprocessing expressions,
  interpolation methods, and fitting engines.

Project writes use a temporary file followed by atomic replacement. If the operating system blocks replacement, saving fails and leaves the previous project file unchanged. `size_inches` and `dpi` remain document/export values; display device-pixel ratio does not alter them.

The file byte count, decoded JSON depth/value count, and Figure component count
are checked before project state is materialized. Embedded images have encoded
byte, dimension, and decoded-pixel budgets. Defaults and supported environment
overrides are listed in `resource-and-process-limits.md`.

`project_snapshot(figure_window, canvas=...)` and
`save_project_snapshot(path, figure_window, canvas=...)` accept an explicit
target Canvas, so saving a background tab cannot serialize the current tab by
mistake. A successful save returns the written snapshot, updates that Canvas
path, and establishes its runtime clean fingerprint. Dirty fingerprints,
selected tabs, Inspector state, and close-dialog choices are runtime-only and
are not added to schema v10.

Component selection, Components-tree search/expansion, Inspector switching,
and Inspector scroll position do not alter the project fingerprint. A clean
schema-v10 project stays clean through those UI-only interactions, and a
save-open-save round trip preserves the same persisted snapshot.

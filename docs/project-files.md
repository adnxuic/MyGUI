# MyGUI Project Files

MyGUI project files use JSON schema version 8. One file contains one project, its typed Table document, and one Matplotlib Figure component tree. Loading migrates supported older files to v8 in memory, and every subsequent save writes v8.

## Root structure

```json
{
  "schema": "mygui-project",
  "schema_version": 8,
  "project": {"id": "project-id", "name": "Project name"},
  "table": {},
  "figure": {
    "root_component_id": "figure-component-id",
    "components": []
  }
}
```

- `schema` is always `mygui-project`.
- `schema_version` is always `8` after migration, loading, or saving.
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

`figure.root_component_id` identifies the sole parentless `figure/figure` record. Its properties include `name`, `style`, `size_inches`, `dpi`, `facecolor`, `edgecolor`, `frameon`, and `constrained_layout`. The saved `style` supplies defaults only for components created later; every existing component restores from its concrete saved properties.

Each `axes/axes` child stores:

- `properties.position`: `[left, bottom, width, height]`.
- `properties.xlim` and `properties.ylim`: two-number ranges.
- `properties.xscale` and `properties.yscale`: Matplotlib scale names.
- `properties.aspect`, `facecolor`, `visible`, and `autoscale_on`.
- `properties.color_cycle`: JSON `null` or a complete color-cycle snapshot.
- `data.subplot`: `layout_group`, positive `nrows`/`ncols`, and one-based `slot`.

Every Axes contains fixed semantic children:

- one X Axis and one Y Axis;
- left, right, bottom, and top Spines;
- Major and Minor Tick groups for both axes;
- one Tick Label group for each Tick group;
- Major and Minor Grid groups for both axes;
- Title, X Label, Y Label, and Legend components.

Tick, Tick Label, Grid, and Legend targets may be recreated by Matplotlib. Their selectors identify the semantic group rather than a transient artist instance.

## Artist properties and role data

Line visual properties use Controller names: `label`, `color`, `linestyle`, `linewidth`, `marker`, `markersize`, `markerfacecolor`, `markeredgecolor`, `markeredgewidth`, `alpha`, `visible`, and `zorder`.

Scatter visual properties use `label`, `color`, `edgecolor`, `size`, `marker`, `linewidth`, `alpha`, `visible`, and `zorder`.

Role-specific `data` fields are:

| Role | Data fields |
| --- | --- |
| `line` | finite, equal-length `x` and `y` arrays |
| `function_curve` | `expression`, `x_start`, `x_stop` |
| `data_plot` | `x_ref`, `y_ref`, `preprocess` |
| `scatter` | `x_ref`, `y_ref`, `preprocess` |
| `interpolation` | `x_ref`, `y_ref`, `preprocess`, `method`, `k`, `samples`, `lam`, `lam_auto` |
| `fit_curve` | `x_ref`, `y_ref`, `preprocess`, `engine`, `fit_type`, `fit_options`, `fit_result`, `expression`, `x_start`, `x_stop` |
| `in_axes_zoom` | no persisted data; mirrors are derived at runtime |
| `in_axes_image` | `filename`, detected `mime_type`, original `payload_base64` bytes |

Free Text, Title, and Axis Label records share Text properties: `text`, `position`, `color`, `fontsize`, `fontfamily`, `fontweight`, `fontstyle`, `rotation`, horizontal/vertical alignment, `usetex`, `alpha`, and `visible`.

Legend properties use `location`, `ncols`, `fontsize`, frame colors/state, `framealpha`, `title`, and `visible`.

An `in_axes` record is a removable child of a main Axes and uses
`selector: {"object_id": component_id}`. Both roles persist normalized parent
Axes `bounds`, `visible`, `zorder`, `facecolor`, `frameon`, `edgecolor`, and
`linewidth`. Zoom additionally stores `xlim`, `ylim`, tick/region/connector
visibility and indicator appearance. Image additionally stores `opacity`,
`fit_mode` (`contain` or `stretch`), and `interpolation` (`nearest`, `bilinear`,
or `bicubic`). Image filenames cannot contain a path, the MIME type must match
the decoded PNG/JPEG/BMP/TIFF payload, and decode safety is checked before any
application state changes.

## Data references, colors, and palette cursor

`x_ref` and `y_ref` contain `project_id`, `sheet_id`, and `column_id`. The reference must resolve inside the same project. X accepts Number or Datetime columns; Y accepts Number columns.

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
snapshot only and does not change schema v8.

## Stable IDs and migration

Existing Plot, Scatter, Fit, and Interpolation `object_id` values are retained. Curve and Text IDs are also retained when present. Older records without IDs receive deterministic UUID5 values derived from the project ID and their legacy semantic path; repeating the same migration therefore produces identical IDs.

- v4 is migrated to v5 first, adding missing color-cycle and color-order state.
- v5 is then converted to the v6 component tree.
- v6 is strictly normalized and migrated without loss to v7.
- v7 is migrated to v8 by adding identity preprocessing to every Plot,
  Scatter, Interpolation, and Fit component.
- v8 is normalized and validated directly, including embedded inset images
  and preprocessing expressions.
- v1-v3 and unknown versions are rejected.

Migration functions operate on deep copies and do not modify the supplied dictionary.

After validation, restore materializes Figure, Axes/layout groups, fixed semantic
children and source chart/Text artists first, then `in_axes` Elements and
Legend directly from the v8 tree. Zoom mirrors receive one final batch refresh
after their sources exist. Restore does not
create legacy chart arrays or Modifier records as an intermediate runtime
format. The Registry tree is subsequently the source for every save.

## Validation and writes

Before Table or Figure application state changes, the loader validates:

- exactly one Figure root matching `root_component_id`;
- unique component IDs, known kind/role pairs, existing parents, an acyclic connected hierarchy, and unique semantic selectors;
- required fixed Axes children and valid subplot groups;
- property/data JSON types, finite numbers, normalized colors, and unique chart order values;
- data references, compatible column types, preprocessing expressions,
  interpolation methods, and fitting engines.

Project writes use a temporary file followed by atomic replacement. If the operating system blocks replacement, saving fails and leaves the previous project file unchanged. `size_inches` and `dpi` remain document/export values; display device-pixel ratio does not alter them.

`project_snapshot(figure_window, canvas=...)` and
`save_project_snapshot(path, figure_window, canvas=...)` accept an explicit
target Canvas, so saving a background tab cannot serialize the current tab by
mistake. A successful save returns the written snapshot, updates that Canvas
path, and establishes its runtime clean fingerprint. Dirty fingerprints,
selected tabs, Inspector state, and close-dialog choices are runtime-only and
are not added to schema v8.

# Project Files

MyGUI project files use strict JSON schema version 17. One file contains one
project, its typed Table document, and one Matplotlib Figure component tree.
The loader accepts exact integer v17. Strict v16 input migrates directly to
v17, while v10–v15 migrate through every intervening version. Schema v4–v9,
non-integer values, and unknown versions are rejected before application state
is published.

Reusable chart templates are deliberately separate from project files. They
use strict `mygui-template` schema version 1, do not contain a Table document,
and never change project schema version 17. See [Chart Templates](chart-templates.md).

## Root structure

```json
{
  "schema": "mygui-project",
  "schema_version": 17,
  "project": {"id": "project-id", "name": "Project name"},
  "table": {},
  "figure": {
    "root_component_id": "figure-component-id",
    "components": []
  }
}
```

- `schema` is always `mygui-project`.
- Newly saved `schema_version` is always the integer `17`.
- `project.id` is stable and must match `table.id`.
- `project.name` is editable and must match `table.name`.
- `table` is the typed table document.
- `figure` contains only `root_component_id` and `components`; legacy axes/chart arrays are not written alongside the tree.

Window geometry, splitter sizes, table visibility, Undo/Redo commands and stack
cursor, command selection, component selection, and optional-integration
runtime state are not project fields. A restored project therefore starts with
an empty history while preserving the exact saved Table and Figure state.

## Table document

`table.sheets` is an ordered array. Each Sheet stores:

- `id`: stable UUID.
- `name`: case-insensitively unique display name.
- `row_count`: logical row count.
- `columns`: ordered typed columns.

Each column stores `id`, `name`, `type`, `width`, and `values`. Missing cells are JSON `null`; number, text, Boolean, and ISO 8601 date/time values retain their types. See [Table Data](table-data.md) for the table and reference model.

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
- `order`: non-negative sibling/runtime ordering value. Chart component orders are unique across Line, Scatter, and FIELD_2D records so color sequencing remains stable. FIELD_2D charts participate in that order but do not consume the Axes color cycle.
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
| `annotation` | `annotation` |
| `legend` | `legend` |
| `line` | `line`, `function_curve`, `data_plot`, `fit_curve`, `interpolation` |
| `scatter` | `scatter` |
| `field_2d` | `pseudocolor`, `heatmap`, `contour` |
| `reference_marks` | `reflection_positions` |
| `reference_guide` | `reference_line`, `reference_band` |
| `colorbar` | `colorbar` |
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

Each Tick Label Group persists `fontfamily` as one non-empty primary-family
string. X/Y Label `position` values use normalized `Axes.transAxes`
coordinates, so their placement scales with the Axes instead of the canvas
pixel coordinate system.

Every Axes contains fixed semantic children:

- one X Axis and one Y Axis;
- left, right, bottom, and top Spines;
- Major and Minor Tick groups for both axes;
- one Tick Label group for each Tick group;
- Major and Minor Grid groups for both axes;
- Title, X Label, Y Label, and Legend components.

Tick, Tick Label, Grid, and Legend targets may be recreated by Matplotlib. Their selectors identify the semantic group rather than a transient artist instance.

Minor visibility and the owning Axis locator are restored together. For
schema-v13 files produced before this behavior was enforced, loading silently
installs the scale-appropriate minor locator only when the file contains an
explicit non-default request: a visible Minor Grid or visible secondary Minor
Ticks/Tick Labels. Default primary visibility alone does not enable minor
ticks. This compatibility repair changes neither the schema version nor the
component wire shape.

## Artist properties and role data

Line visual properties include tagged line/marker/markevery values, draw style, gap color, marker fill and alternate face color, cap/join/antialias controls, and safe advanced Artist fields.

Scatter visual properties include uniform face/edge appearance, tagged marker and line pattern, hatch/cap/join/antialias controls, and tagged color/size mapping specifications. FIELD_2D visual properties include a closed `ColorMapSpec` plus role-specific mesh, image, or contour fields. See [Component Properties (schema v17)](component-properties-v17.md) for the complete property ownership matrix and composite formats.

Role-specific `data` fields are:

| Role | Data fields |
| --- | --- |
| `line` | finite, equal-length `x` and `y` arrays |
| `function_curve` | `expression`, `x_start`, `x_stop` |
| `data_plot` | `x_ref`, `y_ref`, `preprocess` |
| `scatter` | `x_ref`, `y_ref`, optional `color_ref`, optional `size_ref`, `preprocess` |
| `pseudocolor` | `x_ref`, `y_ref`, `z_ref` |
| `heatmap` | `x_ref`, `y_ref`, `z_ref` |
| `contour` | `x_ref`, `y_ref`, `z_ref` |
| `reflection_positions` | ordered finite manual `positions`, nullable Number-column `position_ref`, and tagged `placement`; empty cells are skipped, duplicates remain valid |
| `reference_line` | exactly `{}`; constant geometry is owned by `properties` |
| `reference_band` | exactly `{}`; constant geometry is owned by `properties` |
| `annotation` | exactly `{}`; target, text placement, arrow, typography, and box state are owned by `properties` |
| `colorbar` | `source_component_id` |
| `interpolation` | `x_ref`, `y_ref`, `preprocess`, `method`, `k`, `samples`, `lam`, `lam_auto` |
| `fit_curve` | `x_ref`, `y_ref`, `preprocess`, `engine`, `fit_type`, `fit_options`, `fit_result`, `expression`, `x_start`, `x_stop` |
| `in_axes_zoom` | no persisted data; mirrors are derived at runtime |
| `in_axes_image` | `filename`, detected `mime_type`, original `payload_base64` bytes |

Free Text, Title, and Axis Label records share the safe Text typography, alignment, bbox, math/TeX, z-order, and export contract. Only Free Text persists a selectable data/axes/figure coordinate system.

An `annotation/annotation` record is a removable child of an ordinary Axes.
Its selector is exactly `{"object_id": component_id}` and its `data` object is
exactly empty. `xy` plus `xycoords` own the pointed target; `xytext` plus
`textcoords` own the text anchor. Arrow, typography, alignment, simple box,
TeX request, overall alpha, z-order, and clipping are concrete properties.
Only `data` and `axes_fraction` are valid target systems; text placement also
accepts `offset_points`. See [Annotation Component](editing-components/elements/annotation.md).

Legend properties use tagged location and anchor records, complete entry/title fonts, columns/layout, points/scaling, spacing/padding, frame appearance, dragging, z-order/export fields, and `entry_scope` (`axes` or `twin_pair`).

A `colorbar/colorbar` record is a removable child of its owner Axes. Its
selector contains the Colorbar stable object ID, and `data` contains only the
stable `source_component_id`. The source must be a scalar-mapped Scatter in the
same Axes, with a valid `color_ref`, and may be referenced by only one
Colorbar. Placement, label/ticker/font, outline, extend, spacing, and edge
settings are Colorbar properties. Colormap, norm, limits, and scalar values
remain owned only by the Scatter. See [Colorbar Component](colorbar-component.md).

A `reference_marks/reflection_positions` record is a removable child of an
ordinary Axes. Its selector contains only the stable component object ID, and
its data contains exactly `positions` (manual finite numbers), nullable
`position_ref` (a current-project Number column), and tagged `placement`.
`placement` is either `{"kind": "fixed"}` or
`{"kind": "between_table_ranges", "lower_ref": ColumnRef, "upper_refs": [ColumnRef, ColumnRef]}`.
Effective X coordinates
merge the manual sequence first, then the column values in row order, skipping
empty cells. Automatic placement recomputes the Axes-fraction baseline after
ordinary autoscale so the marks sit between the lower and upper Table ranges.
One `LineCollection` renders the merged positions using data X
coordinates and normalized Axes Y coordinates. The ten exact
appearance/geometry properties and validation rules are documented in
[Reference Marks Component](reference-marks-component.md).

A `reference_guide/reference_line` or `reference_guide/reference_band` record
is a removable child of an ordinary Axes. Its selector contains only the
stable component object ID and its `data` object is exactly empty. Line
properties own orientation, value, Axes-fraction span, and line appearance;
Band properties own orientation, lower/upper bounds, Axes-fraction span, and
fill/border appearance. Their `LineCollection` and `PolyCollection` runtimes
use blended transforms and are attached with `autolim=False`, so they never
expand data limits. See [Reference Guides](reference-guides-component.md).

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
snapshot only and does not change schema v17.

## Stable IDs and compatibility

Component, project, Sheet, column, layout, and data-reference IDs are persisted
unchanged across every schema-v17 save/open round trip. Strict v16 input is
validated completely, deep-copied, and migrated in memory to v17 by advancing
the version only. Strict v15 input migrates through v16 to v17; older accepted
inputs migrate through every intervening version. Tick Label
`fontfamily` string values remain unchanged; non-empty string lists become only
their first string during the v13→v14 step. No other component or Table field
is rewritten. v10 cannot
contain Colorbar; v10/v11 cannot contain Reference Marks; v10-v12 cannot
contain Reference Guides; v10–v15 cannot contain FIELD_2D; and every
predecessor v10–v16 rejects Annotation. Malformed predecessors and versions v4 through v9
are rejected before Table or Figure state is published.

After validation, restore enters `PyFigureCanvas.restore_component_tree` on
the target Canvas. Handlers live in `canvas_materialize_handlers.py`; after
Matplotlib targets exist, `CanvasSnapshotApplier` applies the saved property
tree. Restore materializes Figure, Axes/layout groups, fixed semantic
children and source chart/Text artists first, then dynamic Annotation,
Reference Marks, Reference Guides, `in_axes` Elements, and
Colorbar after its source, with Legend restored from the component tree.
After those Matplotlib targets exist, the Canvas
applies the saved property tree and publishes one final selection. Zoom
mirrors receive one final batch refresh after their sources exist. Restore
does not create legacy chart arrays or Modifier records as an intermediate
runtime format. The Registry tree is subsequently the source for every save.

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
- Colorbar source existence, Scatter role, shared owner Axes, active scalar
  mapping and `color_ref`, and one-Colorbar-per-source cardinality;
- Reference Marks ownership by an ordinary Axes, exact selector/property/data
  keys, finite ordered positions, and normalized baseline/height geometry;
- Reference Guide ownership by an ordinary Axes, exact selector/property keys,
  empty data, finite values/bounds, orientation, and normalized spans;
- Annotation ownership by an ordinary Axes, exact object selector and empty
  data, complete property keys, finite coordinate pairs, closed coordinate,
  arrow, connection, color, and box values;
- property/data JSON types, finite numbers, normalized colors, unique chart order values, and one non-empty string `fontfamily` for every Tick Label Group;
- data references, compatible column types, preprocessing expressions,
  interpolation methods, and fitting engines.

Project writes use a temporary file followed by atomic replacement. If the operating system blocks replacement, saving fails and leaves the previous project file unchanged. `size_inches` and `dpi` remain document/export values; display device-pixel ratio does not alter them.

The file byte count, decoded JSON depth/value count, and Figure component count
are checked before project state is materialized. Embedded images have encoded
byte, dimension, and decoded-pixel budgets. Defaults and supported environment
overrides are listed in [Resource and Process Limits](resource-limits.md).

`project_snapshot(figure_window, canvas=...)` and
`save_project_snapshot(path, figure_window, canvas=...)` accept an explicit
target Canvas, so saving a background tab cannot serialize the current tab by
mistake. A successful save returns the written snapshot, updates that Canvas
path, and establishes its runtime clean fingerprint. Dirty fingerprints,
selected tabs, Inspector state, and close-dialog choices are runtime-only and
are not added to schema v17.

Component selection, Components-tree search/expansion, Inspector switching,
and Inspector scroll position do not alter the project fingerprint. A clean
schema-v17 project stays clean through those UI-only interactions, and a
save-open-save round trip preserves the same persisted snapshot.

## Figure and data export

- 导出当前图片... (File menu) and the canvas toolbar Save button open the same modal [Figure Export](figure-export.md) window for the explicit Canvas that requested it. PNG, JPEG, TIFF, WebP, PDF, and SVG are supported. The export does not change Figure size, document DPI, Undo/Redo, dirty state, or schema v17.
- 导出数据... (File menu) writes the current project's table data as a pretty-printed JSON snapshot.
- PyFigureCanvas.document_dpi is the project and default-export DPI. Qt's device pixel ratio may change the renderer DPI used for display, but it does not change document_dpi, project figure.dpi, figure size in inches, or default export dimensions. For example, a 6.4 x 4.8 inch figure at 100 document DPI exports to 640 x 480 pixels by default on 100%, 125%, 150%, and 200% displays. Passing an explicit DPI to save() overrides the default export DPI.

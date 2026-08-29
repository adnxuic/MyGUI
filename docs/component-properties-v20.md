# Component Properties (schema v20)

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v20 retains the exact eight-field `ComponentState` record:

```text
id, kind, role, parent_id, order, selector, properties, data
```

Profiles, Sections, Qt widgets, callbacks, tree grouping/search/expansion,
selection, and other runtime projection state are never serialized.

## Property ownership

| Component | Owned persistent state |
| --- | --- |
| Figure | name/style, size/DPI, face/edge/frame, linewidth/alpha, tagged layout engine, layout records |
| Axes | ordered limits/autoscale, lower-Y visual reserve ratio, aspect/box geometry, margins, adjustable/anchor, visibility/frame/layering, palette, layout/export fields, plus required data: `subplot` and `geometry` (`{"mode": "grid"}` or `{"mode": "manual", "bounds": [left, bottom, width, height]}`) |
| X/Y Axis | tagged scale, major/minor locator and formatter, label/offset placement, offset text style, overlap policy |
| Spine, Tick, Tick Label, Grid | Their explicit visibility, geometry, line/text appearance, layering, clipping, raster, and export contracts; each Tick Label `fontfamily` is one non-empty primary-family string |
| Text | content/position, safe typography, alignment/rotation, bbox/wrap/math/TeX, coordinate system, layering/export fields |
| Annotation | content/name/visibility, target/text coordinates and coordinate systems, arrow style/color/width/connection, typography, alignment/rotation, bbox, alpha, TeX, z-order, clipping; data is exactly `{}` |
| Legend | tagged location/anchor, layout/entry scope, fonts, marker/point settings, spacing, frame, dragging, layering/export fields |
| Line roles (Data Plot, Function Curve, Inset Indicator) | label/visibility/color, tagged line/marker/markevery, draw/fill style, cap/join/gap, layering/export fields, plus role data |
| Line role (Fit Curve) | Line appearance properties plus required data keys: `x_ref`, `y_ref`, `preprocess`, `engine`, `fit_type`, `fit_options`, `fit_result`, `expression`, `x_start`, `x_stop`, and `fit_input_range` (`{"kind": "all"}` or `{"kind": "bounded", "minimum": float, "maximum": float}`) |
| Scatter | uniform appearance, tagged marker/line, authoritative `ScatterColorMapSpec` and `ScatterSizeMapSpec`, mapping references, layering/export fields |
| Error Bar | data line and marker appearance (`label`, `color`, tagged `linestyle`/`marker`, `linewidth`, `markersize`, `markerfacecolor`, `markeredgecolor`), error appearance (`ecolor`, `elinewidth`, `capsize`, `capthick`, `barsabove`), `alpha`, `visible`, `zorder`, `clip_on`, plus exact data: `x_ref`, `y_ref`, tagged `xerr`, tagged `yerr`, `preprocess` |
| FIELD_2D (Pseudocolor, Heatmap, Contour) | closed `ColorMapSpec`, role-specific mesh/image/contour properties, layering/export fields, and exact `x_ref`/`y_ref`/`z_ref` |
| Reference Marks | manual finite reflection positions, optional Number-column `position_ref`, tagged `placement`, plus label, visibility, Axes-relative baseline/height, line appearance, alpha, z-order, and clipping |
| Reference Line | constant orientation/value, Axes-fraction span, line appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Reference Band | constant orientation/lower/upper bounds, Axes-fraction span, fill/border appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Colorbar | placement, label/ticks/fonts/outline and advanced display properties; stable source ID only, never source cmap/norm/clim/data |
| Zoom/Image Inset | child-Axes placement/appearance and role-specific indicator or embedded-image data |

Single-owner rules prevent duplicate state: Axis owns scale; ordered Axes
limits own inversion; Axes owns `y_lower_reserve`; Tick/Label groups own their
sides and label padding; Axes owns grid layering; Scatter and FIELD_2D own
Colorbar colormap, norm, limits, and scalar data. Reference Marks owns the merged
`positions` + `position_ref` + tagged `placement` data and one `LineCollection`; Reference Guides
and Annotation own their complete constant geometry in `properties` and keep `data` empty.
Fit Curve owns its `fit_input_range` specification for custom data subsetting.
Error Bar owns its tagged `xerr`/`yerr` magnitude specifications and one
composite `ErrorbarContainer`; its runtime is a stable wrapper, never an
individual child artist, and Error Bar is not a ScalarMappable so it can never
source a Colorbar.
Axes owns individual `geometry` mode (`grid` vs `manual`) and explicit normalized bounds.
Runtime Artists are never authoritative.

Minor Tick, Tick Label, and Grid visibility remains owned by those semantic
components. When visible minor output is requested and the owning Axis has a
null minor locator, one Controller transaction installs the Matplotlib 3.9
scale default in the Axis `minor_locator` and applies the visibility change.
This coordination changes no schema-v20 field or record shape.

The exact Fit Curve field matrix, range controls, defaults, transforms, and pinned
Matplotlib links are in [Fit Curve](editing-components/charts/fit-curve.md).
The exact Annotation field matrix, controls, defaults, transforms, and pinned
Matplotlib links are in [Annotation](editing-components/elements/annotation.md).
Reference Guide fields are in [Reference Guides](reference-guides-component.md).
Reference Marks fields are in
[Reference Marks Component](reference-marks-component.md). Colorbar fields are
in [Colorbar Component](colorbar-component.md). FIELD_2D fields are in
[Pseudocolor](editing-components/charts/pseudocolor.md),
[Heatmap](editing-components/charts/heatmap.md), and
[Contour](editing-components/charts/contour.md). Error Bar fields are in
[Error Bar](editing-components/charts/errorbar.md). Modular component fields across
all 32 profiles are documented in [Figure](editing-components/fixed-semantics/figure.md),
[Axes](editing-components/fixed-semantics/axes.md), and child component guides.

## Upstream migration notes

Schema v20 extends schema v19 by introducing the Error Bar component
(`kind: "errorbar"`, `role: "error_bar"`). When saving, projects record
`schema_version: 20`. Existing strictly valid schema-v19 files migrate
directly into schema v20 by advancing the version only; v19 validation rejects
Error Bar records, so no component rewrite occurs. Stepwise migrations from
v10–v18 promote through every intervening version into v20. Schema v19 and
older reject `errorbar` components.

## Referenced Matplotlib 3.9.0 URLs

- [Line2D API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html)
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html)
- [Step demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/step_demo.html)
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html)
- [Marker fillstyle reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html)
- [Axes errorbar](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.errorbar.html)
- [ErrorbarContainer API](https://matplotlib.org/3.9.0/api/container_api.html#matplotlib.container.ErrorbarContainer)
- [Annotation API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Annotation)
- [Axes.annotate](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.annotate.html)
- [FancyArrowPatch API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.FancyArrowPatch.html)
- [BoxStyle API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.BoxStyle.html)
- [Axes API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.html)
- [SubplotSpec API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.gridspec.SubplotSpec.html)

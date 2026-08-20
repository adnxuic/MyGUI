# Component Properties (schema v11)

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v11 retains the exact eight-field `ComponentState` record:

```text
id, kind, role, parent_id, order, selector, properties, data
```

Profiles, Sections, Qt widgets, callbacks, tree grouping/search/expansion,
selection, and other runtime projection state are never serialized.

## Property ownership

| Component | Owned persistent state |
| --- | --- |
| Figure | name/style, size/DPI, face/edge/frame, linewidth/alpha, tagged layout engine, layout records |
| Axes | ordered limits/autoscale, aspect/box geometry, margins, adjustable/anchor, visibility/frame/layering, palette, layout/export fields |
| X/Y Axis | tagged scale, major/minor locator and formatter, label/offset placement, offset text style, overlap policy |
| Spine, Tick, Tick Label, Grid | Their explicit visibility, geometry, line/text appearance, layering, clipping, raster, and export contracts |
| Text | content/position, safe typography, alignment/rotation, bbox/wrap/math/TeX, coordinate system, layering/export fields |
| Legend | tagged location/anchor, layout/entry scope, fonts, marker/point settings, spacing, frame, dragging, layering/export fields |
| Line roles | label/visibility/color, tagged line/marker/markevery, draw/fill style, cap/join/gap, layering/export fields, plus role data |
| Scatter | uniform appearance, tagged marker/line, authoritative `ScatterColorMapSpec` and `ScatterSizeMapSpec`, mapping references, layering/export fields |
| Colorbar | placement, label/ticks/fonts/outline and advanced display properties; stable source ID only, never source cmap/norm/clim/data |
| Zoom/Image Inset | child-Axes placement/appearance and role-specific indicator or embedded-image data |

Single-owner rules prevent duplicate state: Axis owns scale; ordered Axes
limits own inversion; Tick/Label groups own their sides and label padding;
Axes owns grid layering; Scatter owns Colorbar colormap, norm, limits, and
scalar data. Colorbar orientation is derived from `location` and is not a
second property.

The complete Colorbar field matrix, controls, defaults, and pinned Matplotlib
links are in [Colorbar Component](colorbar-component.md). Chart fields are in
[Chart Component Parameters](chart-component-parameters.md), and Figure/Axes
fields are in [Axes and Figure Component Parameters](axes-component-parameters.md).

## Closed tagged values

Composite values persist as closed tagged objects and reject unknown keys,
non-finite values, and invalid kind/parameter combinations. Production never
uses editable JSON. The supported families are:

- `ScaleSpec`, `LocatorSpec`, and `FormatterSpec`;
- `FontSpec`, `TextBoxSpec`, legend location/anchor, and Axes anchor;
- line pattern, marker, mark-every, optional color, and named number;
- `FigureLayoutSpec`, rectangles/ranges/positions/sequences;
- `ScatterColorMapSpec` with tagged `NormSpec`, and `ScatterSizeMapSpec`;
- Zoom connector records and Image Inset interpolation/extent fields.

Fixed formatters require a fixed locator with the same number of locations.
Arbitrary callables, `FuncFormatter`, `FuncNorm`, Matplotlib objects, NumPy
arrays, and QWidget instances are rejected from project state.

## Schema v11 and migration

Saving writes exact integer `schema_version: 11`. The v11 validator accepts
Colorbar records only when the source is a scalar-mapped `scatter/scatter` in
the same owner Axes and no other Colorbar uses that source.

Loading exact integer v10 first runs the strict v10 validator. A valid v10
component tree migrates without component rewrites because v10 cannot contain
Colorbar; only the root schema version changes to 11, followed by complete v11
validation. Malformed v10 is rejected before migration. Versions v4-v9,
booleans, floats, strings, and unknown versions remain unsupported.

See [Project Files](project-files.md) for the file graph and restore order, and
[Component Controllers](component-controllers.md) for runtime mutation and
rollback contracts.

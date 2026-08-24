# Component Properties (schema v14)

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v14 retains the exact eight-field `ComponentState` record:

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
| Spine, Tick, Tick Label, Grid | Their explicit visibility, geometry, line/text appearance, layering, clipping, raster, and export contracts; each Tick Label `fontfamily` is one non-empty primary-family string |
| Text | content/position, safe typography, alignment/rotation, bbox/wrap/math/TeX, coordinate system, layering/export fields |
| Legend | tagged location/anchor, layout/entry scope, fonts, marker/point settings, spacing, frame, dragging, layering/export fields |
| Line roles | label/visibility/color, tagged line/marker/markevery, draw/fill style, cap/join/gap, layering/export fields, plus role data |
| Scatter | uniform appearance, tagged marker/line, authoritative `ScatterColorMapSpec` and `ScatterSizeMapSpec`, mapping references, layering/export fields |
| Reference Marks | ordered finite reflection positions plus label, visibility, Axes-relative baseline/height, line appearance, alpha, z-order, and clipping |
| Reference Line | constant orientation/value, Axes-fraction span, line appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Reference Band | constant orientation/lower/upper bounds, Axes-fraction span, fill/border appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Colorbar | placement, label/ticks/fonts/outline and advanced display properties; stable source ID only, never source cmap/norm/clim/data |
| Zoom/Image Inset | child-Axes placement/appearance and role-specific indicator or embedded-image data |

Single-owner rules prevent duplicate state: Axis owns scale; ordered Axes
limits own inversion; Tick/Label groups own their sides and label padding;
Axes owns grid layering; Scatter owns Colorbar colormap, norm, limits, and
scalar data. Reference Marks owns one ordered `positions` sequence and one
`LineCollection`; Reference Guides own their complete constant geometry in
`properties` and keep `data` empty. Runtime Artists are never authoritative.

Minor Tick, Tick Label, and Grid visibility remains owned by those semantic
components. When visible minor output is requested and the owning Axis has a
null minor locator, one Controller transaction installs the Matplotlib 3.9
scale default in the Axis `minor_locator` and applies the visibility change.
This coordination changes no schema-v14 field or record shape.

The exact Reference Guide field matrices, controls, defaults, transforms, and
pinned Matplotlib links are in [Reference Guides](reference-guides-component.md).
Reference Marks fields are in
[Reference Marks Component](reference-marks-component.md). Colorbar fields are
in [Colorbar Component](colorbar-component.md). Chart fields are in
[Chart Component Parameters](chart-component-parameters.md), and Figure/Axes
fields are in
[Axes and Figure Component Parameters](axes-component-parameters.md).

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
The Logit locator `nbins` value accepts either a positive integer or `auto`;
runtime automatic `AutoMinorLocator` subdivisions serialize canonically as a
null `n` parameter. Arbitrary callables, `FuncFormatter`, `FuncNorm`,
Matplotlib objects, NumPy arrays, and QWidget instances are rejected from
project state.

## Schema v14 and migration

Saving writes exact integer `schema_version: 14`. Schema v14 requires every
`tick_label_group.properties.fontfamily` value to be a non-empty string. A v14
file containing a list, an empty string, `null`, or another type is rejected at
that exact field path.

Loading exact integer v13 first runs the strict v13 root, Table, component-graph,
and property validator. The validated snapshot is deep-copied. Existing
non-empty string font families remain unchanged; a non-empty string list is
replaced only by its first item. Empty lists and lists containing a non-string
or empty member are rejected. The root version then advances to 14 and the
complete v14 snapshot is validated before any Table or Figure is published.

Exact integer v12 migrates through v13 to v14, v11 migrates through v12 and
v13, and v10 migrates through every intervening version. Component IDs,
hierarchy, order, selectors, data, Table state, and every property other than
the v13 Tick Label font representation remain unchanged. Versions v4-v9,
booleans, floats, strings, and unknown versions remain unsupported.

See [Project Files](project-files.md) for the file graph and restore order, and
[Component Controllers](component-controllers.md) for runtime mutation and
rollback contracts. [Component Properties (schema v13)](component-properties-v13.md)
documents the immediate migration source.

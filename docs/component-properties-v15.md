# Component Properties (schema v15)

Schema v15 is retained as the strict immediate migration source for current
[schema v16](component-properties-v16.md) files. New saves no longer emit v15.

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v15 retains the exact eight-field `ComponentState` record:

```text
id, kind, role, parent_id, order, selector, properties, data
```

Profiles, Sections, Qt widgets, callbacks, tree grouping/search/expansion,
selection, and other runtime projection state are never serialized.

## Property ownership

| Component | Owned persistent state |
| --- | --- |
| Figure | name/style, size/DPI, face/edge/frame, linewidth/alpha, tagged layout engine, layout records |
| Axes | ordered limits/autoscale, lower-Y visual reserve ratio, aspect/box geometry, margins, adjustable/anchor, visibility/frame/layering, palette, layout/export fields |
| X/Y Axis | tagged scale, major/minor locator and formatter, label/offset placement, offset text style, overlap policy |
| Spine, Tick, Tick Label, Grid | Their explicit visibility, geometry, line/text appearance, layering, clipping, raster, and export contracts; each Tick Label `fontfamily` is one non-empty primary-family string |
| Text | content/position, safe typography, alignment/rotation, bbox/wrap/math/TeX, coordinate system, layering/export fields |
| Legend | tagged location/anchor, layout/entry scope, fonts, marker/point settings, spacing, frame, dragging, layering/export fields |
| Line roles | label/visibility/color, tagged line/marker/markevery, draw/fill style, cap/join/gap, layering/export fields, plus role data |
| Scatter | uniform appearance, tagged marker/line, authoritative `ScatterColorMapSpec` and `ScatterSizeMapSpec`, mapping references, layering/export fields |
| Reference Marks | manual finite reflection positions, optional Number-column `position_ref`, tagged `placement`, plus label, visibility, Axes-relative baseline/height, line appearance, alpha, z-order, and clipping |
| Reference Line | constant orientation/value, Axes-fraction span, line appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Reference Band | constant orientation/lower/upper bounds, Axes-fraction span, fill/border appearance, visibility, label, z-order, and clipping; data is exactly `{}` |
| Colorbar | placement, label/ticks/fonts/outline and advanced display properties; stable source ID only, never source cmap/norm/clim/data |
| Zoom/Image Inset | child-Axes placement/appearance and role-specific indicator or embedded-image data |

Single-owner rules prevent duplicate state: Axis owns scale; ordered Axes
limits own inversion; Axes owns `y_lower_reserve`; Tick/Label groups own their
sides and label padding; Axes owns grid layering; Scatter owns Colorbar
colormap, norm, limits, and scalar data. Reference Marks owns the merged
`positions` + `position_ref` + tagged `placement` data and one `LineCollection`; Reference Guides
own their complete constant geometry in `properties` and keep `data` empty.
Runtime Artists are never authoritative.

FIELD_2D (Pseudocolor, Heatmap, Contour) records are not part of schema v15
and are rejected by the v15 validator.

Minor Tick, Tick Label, and Grid visibility remains owned by those semantic
components. When visible minor output is requested and the owning Axis has a
null minor locator, one Controller transaction installs the Matplotlib 3.9
scale default in the Axis `minor_locator` and applies the visibility change.
This coordination changes no schema-v15 field or record shape.

The exact Reference Guide field matrices, controls, defaults, transforms, and
pinned Matplotlib links are in [Reference Guides](reference-guides-component.md).
Reference Marks fields are in
[Reference Marks Component](reference-marks-component.md). Colorbar fields are
in [Colorbar Component](colorbar-component.md). Modular component fields across
the 27 v15 profiles are documented in [Figure](editing-components/fixed-semantics/figure.md),
[Axes](editing-components/fixed-semantics/axes.md), and child component guides.

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

## Schema v15 and migration

Schema v15 is no longer written by the saver. Exact integer v15 input is
validated completely, deep-copied, and advanced to 16 without rewriting
component records. FIELD_2D records are not accepted in v15.

Loading exact integer v14 first runs the independent strict v14 root, Table,
component-graph, and property validator, including the v14 Reference Marks
`positions`-only data contract and Axes property set without
`y_lower_reserve`. The validated snapshot is deep-copied. Every Reference
Marks record receives `position_ref: null` and `placement: {"kind": "fixed"}`,
and every Axes record receives
`y_lower_reserve: 0.0`. Old projects are not inferred as XRD plots; IDs,
order, hierarchy, ranges, and rendering stay unchanged. The root version then
advances to 15 and the complete v15 snapshot is validated before the v15-to-v16
version bump.

Exact integer v13 migrates through v14 to v15, v12 through v13/v14, v11
through v12–v14, and v10 through every intervening version, then to v16.
Versions v4-v9, booleans, floats, strings, and unknown versions remain
unsupported.

See [Project Files](project-files.md) and
[Component Properties (schema v16)](component-properties-v16.md).
[Component Properties (schema v14)](component-properties-v14.md)
documents the previous migration source.

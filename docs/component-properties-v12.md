# Legacy Component Properties (schema v12)

This page documents the strict v12 migration-source contract. New projects use
[Component Properties (schema v16)](component-properties-v16.md). MyGUI
targets Matplotlib 3.9.0. Every v12 production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v12 retains the exact eight-field `ComponentState` record:

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
| Reference Marks | ordered finite reflection positions plus label, visibility, Axes-relative baseline/height, line appearance, alpha, z-order, and clipping |
| Colorbar | placement, label/ticks/fonts/outline and advanced display properties; stable source ID only, never source cmap/norm/clim/data |
| Zoom/Image Inset | child-Axes placement/appearance and role-specific indicator or embedded-image data |

Single-owner rules prevent duplicate state: Axis owns scale; ordered Axes
limits own inversion; Tick/Label groups own their sides and label padding;
Axes owns grid layering; Scatter owns Colorbar colormap, norm, limits, and
scalar data. Reference Marks owns one ordered `positions` sequence and one
`LineCollection`; duplicate positions are meaningful and are never deduplicated.

The complete Reference Marks field matrix, controls, defaults, and pinned
Matplotlib links are in [Reference Marks Component](reference-marks-component.md).
Colorbar fields are in [Colorbar Component](colorbar-component.md). Chart fields
are in [Plot](editing-components/charts/plot.md) and the other
[Editing Components](components-tree.md) chart pages, and Figure/Axes fields
are in [Axes](editing-components/fixed-semantics/axes.md).

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

## Schema v12 migration source

A schema-v12 file uses exact integer `schema_version: 12`. The v12 validator
adds the
`reference_marks/reflection_positions` record while retaining the exact
eight-field record shape used by v11.

Loading exact integer v11 first runs the strict v11 validator, changes only the
root schema version, and then validates the complete v12 graph. Exact integer
v10 is validated as v10 and migrates through v11 to v12. Because Reference
Marks did not exist in either predecessor, v10 and v11 explicitly reject its
kind/role. Existing component records and stable IDs are not rewritten.
Malformed predecessors are rejected before migration. Current MyGUI then
deep-copies the strictly validated v12 snapshot, changes only its root version
to v13, strictly validates v13, and then applies the v13-to-v14 Tick Label
font-family migration before validating v14. The validated v14 snapshot then
migrates in memory to v15 before Table or Figure publication. Other component
and Table state is not rewritten.
Reference Guides are therefore not valid in v12. Versions v4-v9, booleans,
floats, strings, and unknown versions remain unsupported.

See [Project Files](project-files.md) for the file graph and restore order, and
[Component Controllers](component-controllers.md) for runtime mutation and
rollback contracts.

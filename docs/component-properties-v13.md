# Component Properties (schema v13)

Schema v13 is retained as a strict chained migration source for current
[schema v15](component-properties-v15.md) files. Valid v13 snapshots migrate
through v14 to v15. New saves no longer emit v13.

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v13 retains the exact eight-field `ComponentState` record:

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
This coordination changes no schema-v13 field or record shape.

The exact Reference Guide field matrices, controls, defaults, transforms, and
pinned Matplotlib links are in [Reference Guides](reference-guides-component.md).
Reference Marks fields are in
[Reference Marks Component](reference-marks-component.md). Colorbar fields are
in [Colorbar Component](colorbar-component.md). Chart fields are in
[Plot](editing-components/charts/plot.md) and the other
[Editing Components](components-tree.md) chart pages, and Figure/Axes
fields are in
[Axes](editing-components/fixed-semantics/axes.md).

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
null `n` parameter.
Arbitrary callables, `FuncFormatter`, `FuncNorm`, Matplotlib objects, NumPy
arrays, and QWidget instances are rejected from project state.

## Schema v13 predecessor contract

Saving writes exact integer `schema_version: 13`. The v13 validator adds the
`reference_guide/reference_line` and `reference_guide/reference_band` records
while retaining the exact eight-field record shape used by v12.

Loading exact integer v12 first runs the strict v12 validator, deep-copies the
validated snapshot, changes only the root schema version to 13, and then runs
the strict v13 validator. Exact integer v11 migrates through v12 to v13. Exact
integer v10 migrates through v11 and v12 to v13. Reference Guides did not exist
in any predecessor, so v10, v11, and v12 explicitly reject their kind/roles.
Existing component IDs, order, selectors, properties, data, table IDs, and
table values are not rewritten. Reference Marks remain valid from v12 onward.
Malformed predecessors are rejected before migration. Versions v4-v9,
booleans, floats, strings, and unknown versions remain unsupported.

Current loading then validates the complete v13 snapshot, deep-copies it,
canonicalizes Tick Label `fontfamily` from a non-empty string list to its first
string, changes the root version to 14, and strictly validates schema v14.
The validated v14 snapshot then migrates in memory to v15 before
publication. Non-empty v13 string values remain unchanged; invalid or empty
font lists are rejected.

See [Project Files](project-files.md) for the file graph and restore order, and
[Component Controllers](component-controllers.md) for runtime mutation and
rollback contracts.

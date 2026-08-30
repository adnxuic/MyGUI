# Component Properties (schema v22)

MyGUI targets Matplotlib 3.9.0. Every production `(ComponentKind,
ComponentRole)` has one Controller and one exact Inspector profile. Persistent
properties are edited only through Controllers or domain Services, and every
property/data key is exposed exactly once or explicitly hidden by its profile.

Schema v22 retains the exact eight-field `ComponentState` record:

```text
id, kind, role, parent_id, order, selector, properties, data
```

Profiles, Sections, Qt widgets, callbacks, preview images, selection, shared-
axis projections, and Undo/Redo state are never serialized.

## Property ownership

| Component | Owned persistent state |
| --- | --- |
| Figure | name/style, size/DPI, face/edge/frame, linewidth/alpha, tagged layout engine, layout records |
| Axes | ordered limits/autoscale, lower-Y reserve, aspect/box geometry, margins, adjustable/anchor, visibility/frame/layering, palette, layout/export fields, plus required `subplot` and `geometry` data |
| X/Y Axis | tagged scale; major/minor Locator and Formatter; label/offset placement; offset text style; overlap policy |
| Spine, Tick, Tick Label, Grid | Explicit visibility, geometry, line/text appearance, layering, clipping, raster, and export contracts |
| Text and Annotation | Safe content, positions/transforms, typography, alignment/rotation, box/math/TeX, and role-specific arrow/coordinate fields |
| Legend | Tagged location/anchor, entry scope, fonts, marker/point settings, spacing, frame, dragging, layering/export fields |
| Line roles | Line/marker appearance and the closed data contract for the selected Line role |
| Scatter | Uniform appearance, tagged marker/line, color/size mapping specifications and references |
| Error Bar | Data-line, marker, error-line/cap/sampling/limit-arrow appearance plus exact X/Y/error/preprocess data |
| FIELD_2D | Closed color-map specification, role-specific mesh/image/contour fields, and exact X/Y/Z references |
| Reference Marks / Guides | Closed position, placement, data-reference, line/fill, label, and clipping contracts |
| Colorbar | Placement, label/ticks/fonts/outline and stable source ID; never source cmap/norm/clim/data |
| Zoom/Image Inset | Child-Axes placement/appearance and role-specific indicator or embedded-image data |

Axis owns Locator and Formatter specifications. Tick Group owns tick-line
appearance, while Tick Label Group owns text appearance and side visibility.
The unified **Ticks & Labels** dialog submits those existing owners in one
Registry transaction; it does not create an alternate component record.
Locator/Formatter changes synchronize across the selected `sharex` or
`sharey` group, while appearance remains local to the selected Axes.

## Schema-v22 ticker extension

All schema-v21 Locator and Formatter kinds remain valid. Schema v22 adds two
closed, non-executable wire types:

```json
{"kind": "index", "params": {"base": 1.0, "offset": 0.0}}
```

`base` must be positive and finite; `offset` must be finite. It constructs a
fresh `matplotlib.ticker.IndexLocator` and is intended for regularly spaced
index data.

```json
{"kind": "format_str", "params": {"format": "%1.2f"}}
```

The format must contain exactly one safe percent value conversion. Literal
`%%` is allowed. Mapping keys, dynamic `*` width or precision, multiple or
invalid conversions, callables, expressions, and `FuncFormatter` are rejected.
It constructs a fresh `matplotlib.ticker.FormatStrFormatter`.

A `fixed` Formatter is valid only with a `fixed` Locator whose location count
equals its label count. Every ticker object is reconstructed from its tagged
specification during restore; Matplotlib objects and functions are never read
from project JSON.

## Upstream migration notes

New saves record exact integer `schema_version: 22`. A v21 input is first
validated by the strict v21 whitelist, which rejects `index` and `format_str`,
and is then deep-copied with only the root version advanced to v22. Component
IDs, parent relationships, order, selectors, properties, and data remain
unchanged. Versions v10–v20 continue through their existing migration chain
before the v21→v22 step; v4–v9 remain unsupported.

Chart templates use independent schema v6. A strict template-v5 record first
validates its schema-v21 Figure blueprint and then advances without Figure
content changes to template v6 / Figure schema v22.

The historical schema-v21 property contract remains available at
[Component Properties (schema v21)](component-properties-v21.md).

## Referenced Matplotlib 3.9.0 URLs

- [Axis ticks guide](https://matplotlib.org/3.9.0/users/explain/axes/axes_ticks.html)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)
- [IndexLocator](https://matplotlib.org/3.9.0/api/ticker_api.html#matplotlib.ticker.IndexLocator)
- [FormatStrFormatter](https://matplotlib.org/3.9.0/api/ticker_api.html#matplotlib.ticker.FormatStrFormatter)

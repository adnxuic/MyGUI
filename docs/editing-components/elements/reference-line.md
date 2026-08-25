# Reference Line Component

The **Reference Line** component draws a constant coordinate guideline across the plotting area (`LineCollection`) with a constant X or Y data value and an orthogonal fractional span.

For conceptual overview and usage guides, see [Reference Guides](../../reference-guides-component.md).

## General

--8<-- "_snippets/components/reference_guides/reference-guide-general.md"

## Position

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Orientation | Dropdown | Line orientation: `vertical` (`x = value`) or `horizontal` (`y = value`). | `vertical` or `horizontal`; default `vertical` | `properties.orientation` |
| Value | Number | Constant data coordinate value. | Finite number; default `0.0` | `properties.value` |

## Line

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Color | Color choice | Line stroke color using Matplotlib color contract. | Hex color; default `#000000` | `properties.color` |
| Linewidth | Number | Line stroke width in points. | Finite number `>= 0`; default `0.8` | `properties.linewidth` |
| Linestyle | Line-style choice | Line stroke dash pattern. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Alpha | Number | Line opacity factor from 0 to 1. | Finite `0 <= alpha <= 1`; default `1.0` | `properties.alpha` |

## Advanced

--8<-- "_snippets/components/reference_guides/reference-guide-advanced.md"

## Project record

Schema v15 persists Reference Line as `kind: "reference_guide"`, `role: "reference_line"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object is `{}`.

## Referenced Matplotlib 3.9.0 URLs

- [LineCollection API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection)
- [Artist set_alpha](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html)
- [Artist set_zorder](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html)
- [Artist set_clip_on](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html)

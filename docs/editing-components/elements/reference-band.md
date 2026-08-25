# Reference Band Component

The **Reference Band** component draws a highlighted coordinate band spanning across the plotting area (`PolyCollection`) with constant lower and upper data boundaries and an orthogonal fractional span.

For conceptual overview and usage guides, see [Reference Guides](../../reference-guides-component.md).

## General

--8<-- "_snippets/components/reference_guides/reference-guide-general.md"

## Position

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Orientation | Dropdown | Band orientation: `vertical` (bounds X data) or `horizontal` (bounds Y data). | `vertical` or `horizontal`; default `vertical` | `properties.orientation` |
| Lower | Number | Lower data-coordinate boundary of the band. | Finite number; default `0.0`; must be less than Upper | `properties.lower` |
| Upper | Number | Upper data-coordinate boundary of the band. | Finite number; default `1.0`; must be greater than Lower | `properties.upper` |

## Fill

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Facecolor | Color choice | Band background fill color using Matplotlib color contract. | Hex color; default `#b0b0b0` | `properties.facecolor` |
| Alpha | Number | Opacity of the band fill and borders from 0 to 1. | Finite `0 <= alpha <= 1`; default `0.25` | `properties.alpha` |

## Border

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Edgecolor | Color choice | Stroke color of the bounding polygon borders. | Hex color; default `#000000` | `properties.edgecolor` |
| Linewidth | Number | Stroke width of the bounding polygon borders in points. | Finite number `>= 0`; default `0.8` | `properties.linewidth` |
| Linestyle | Line-style choice | Stroke dash pattern of the bounding polygon borders. | Preset or dash tuple; default `-` | `properties.linestyle` |

## Advanced

--8<-- "_snippets/components/reference_guides/reference-guide-advanced.md"

## Project record

Schema v15 persists Reference Band as `kind: "reference_guide"`, `role: "reference_band"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object is `{}`.

## Referenced Matplotlib 3.9.0 URLs

- [PolyCollection API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.PolyCollection)
- [Artist set_alpha](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html)
- [Artist set_zorder](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html)
- [Artist set_clip_on](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html)

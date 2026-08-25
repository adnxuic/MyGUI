# Spine Component

The **Spine** component represents one of the boundary lines of an Axes (`top`, `bottom`, `left`, `right`). It provides boundary geometry, line style, color, tick positioning reference, and data bounding limits.

## Properties

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides this spine line. | `true` or `false`; default `true` | `properties.visible` |
| Color | Color choice | Spine line stroke color. | Hex color; default `#000000` | `properties.color` |
| Linewidth | Number | Spine line stroke thickness in points. | Finite number `>= 0`; default `0.8` | `properties.linewidth` |
| Linestyle | Line-style choice | Spine line dash pattern. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Position | Position editor | Spine placement specification: `center`, `zero`, or explicit coordinate tuple. | Position spec; default `('outward', 0.0)` | `properties.position` |
| Bounds | Bounds editor | Restricts spine drawing to data limit bounds `[min, max]`. | Tuple or None; default None | `properties.bounds` |
| Alpha | Number | Spine line opacity from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Capstyle | Dropdown | Cap style of line endings. | `butt`, `projecting`, `round`; default `butt` | `properties.capstyle` |
| Joinstyle | Dropdown | Join style of corner vertices. | `miter`, `round`, `bevel`; default `miter` | `properties.joinstyle` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Antialiased | Checkbox | Enables antialiased line rendering for the spine. | `true` or `false`; default `true` | `properties.antialiased` |
| Zorder | Number | Stacking order of the spine relative to other artists. | Finite number; default `2.5` | `properties.zorder` |
| Clip On | Checkbox | Clips spine to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes spine in tight-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel grid snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

## Project record

Schema v15 persists each Spine as `kind: "spine"`, `role: "spine"`, with `selector: {"spine_id": "<top|bottom|left|right>"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Spines API](https://matplotlib.org/3.9.0/api/spines_api.html#matplotlib.spines.Spine)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

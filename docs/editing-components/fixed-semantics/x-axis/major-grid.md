# Major Grid Component

The **Major Grid** component manages the grid lines associated with the major tick locations of an axis.

## Properties

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides major grid lines. | `true` or `false`; default `false` (or style default) | `properties.visible` |
| Color | Color choice | Grid line stroke color. | Hex color; default `#b0b0b0` | `properties.color` |
| Linestyle | Line-style choice | Grid line dash pattern. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Linewidth | Number | Grid line stroke width in points. | Finite number `>= 0`; default `0.8` | `properties.linewidth` |
| Alpha | Number | Grid line opacity from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Gapcolor | Optional color | Alternating color shown inside dashed gaps. | Hex color or none; default none | `properties.gapcolor` |
| Dash Capstyle | Dropdown | Cap style of dash segments. | `butt`, `projecting`, `round`; default `butt` | `properties.dash_capstyle` |
| Dash Joinstyle | Dropdown | Join style of dash segments. | `miter`, `round`, `bevel`; default `round` | `properties.dash_joinstyle` |
| Solid Capstyle | Dropdown | Cap style of solid segments. | `butt`, `projecting`, `round`; default `projecting` | `properties.solid_capstyle` |
| Solid Joinstyle | Dropdown | Join style of solid segments. | `miter`, `round`, `bevel`; default `round` | `properties.solid_joinstyle` |

## Advanced

--8<-- "_snippets/components/ticks/tick-advanced.md"

## Project record

Schema v15 persists Major Grid as `kind: "grid"`, `role: "grid"`, with `selector: {"axis_name": "x", "grid_type": "major"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Axes grid](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.grid.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

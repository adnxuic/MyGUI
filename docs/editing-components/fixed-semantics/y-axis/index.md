# Y Axis Component

The **Y Axis** component represents the vertical coordinate dimension of an Axes. It owns coordinate scaling (`linear`, `log`, `symlog`, `logit`, `asinh`), major and minor tick locators and formatters, label placement, and offset exponent notation.

## Properties

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the Y Axis and its associated tick marks and labels. | `true` or `false`; default `true` | `properties.visible` |
| Scale | Scale dialog | Coordinate scaling model: `linear`, `log`, `symlog`, `logit`, `asinh`. | Scale spec; default `{'kind': 'linear'}` | `properties.scale` |
| Major Locator | Locator dialog | Rule determining where major tick marks are placed along the Y axis. | Locator spec; default `{'kind': 'auto'}` | `properties.major_locator` |
| Major Formatter | Formatter dialog | Rule converting major tick numeric positions into formatted label strings. | Formatter spec; default `{'kind': 'scalar'}` | `properties.major_formatter` |
| Minor Locator | Locator dialog | Rule determining where minor tick marks are placed. Enabling minor elements installs the scale default if null. | Locator spec or None; default `{'kind': 'null'}` | `properties.minor_locator` |
| Minor Formatter | Formatter dialog | Rule converting minor tick numeric positions into formatted label strings. | Formatter spec or None; default `{'kind': 'null'}` | `properties.minor_formatter` |
| Label Position | Dropdown | Placement side for tick labels: `left` or `right`. | `left` or `right`; default `left` | `properties.label_position` |
| Remove Overlapping Locs | Checkbox | Automatically suppresses overlapping tick label display. | `true` or `false`; default `true` | `properties.remove_overlapping_locs` |
| Offset Font | Font chooser | Font styling for numeric exponent offset notation (e.g. `x10^3`). | Font spec; default sans-serif 10 | `properties.offset_font` |
| Offset Visible | Checkbox | Shows or hides the exponent offset notation. | `true` or `false`; default `true` | `properties.offset_visible` |
| Offset Position | Dropdown | Placement side for exponent offset notation on the Y axis: `left` or `right`. | `left` or `right`; default `left` | `properties.offset_position` |

## Advanced

--8<-- "_snippets/components/common/axis-advanced.md"

## Project record

Schema v15 persists the Y Axis as `kind: "axis"`, `role: "y_axis"`, with `selector: {"axis_name": "y"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [YAxis API](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.YAxis)
- [Axes scales explainer](https://matplotlib.org/3.9.0/users/explain/axes/axes_scales.html)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

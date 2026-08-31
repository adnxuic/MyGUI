# Y Axis Component

The **Y Axis** component represents the vertical coordinate dimension of an Axes. It owns coordinate scaling (`linear`, `log`, `symlog`, `logit`, `asinh`), major and minor tick locators and formatters, label placement, and offset exponent notation.

## Properties

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the Y Axis and its associated tick marks and labels. | `true` or `false`; default `true` | `properties.visible` |
| Scale | Scale dialog | Coordinate scaling model: `linear`, `log`, `symlog`, `logit`, `asinh`. | Scale spec; default `{'kind': 'linear'}` | `properties.scale` |
| Ticks & Labels — Major Positions | Unified dialog | Selects the Locator that determines major tick positions; the same dialog also edits major tick-line and label appearance. | Locator spec; default `auto` | `properties.major_locator` |
| Ticks & Labels — Major Label Format | Unified dialog | Selects the Formatter that generates major tick-label text. | Formatter spec; default `scalar` | `properties.major_formatter` |
| Ticks & Labels — Minor Positions | Unified dialog | Selects the Locator that determines minor tick positions; the same dialog also edits minor tick-line and label appearance. | Locator spec; default `null` | `properties.minor_locator` |
| Ticks & Labels — Minor Label Format | Unified dialog | Selects the Formatter that generates minor tick-label text. | Formatter spec; default `null` | `properties.minor_formatter` |
| Label Position | Dropdown | Placement side for tick labels: `left` or `right`. | `left` or `right`; default `left` | `properties.label_position` |
| Remove Overlapping Locs | Checkbox | Automatically suppresses overlapping tick label display. | `true` or `false`; default `true` | `properties.remove_overlapping_locs` |
| Offset Font | Font chooser | Font styling for numeric exponent offset notation (e.g. `x10^3`). | Font spec; default sans-serif 10 | `properties.offset_font` |
| Offset Visible | Checkbox | Shows or hides the exponent offset notation. | `true` or `false`; default `true` | `properties.offset_visible` |
| Offset Position | Dropdown | Placement side for exponent offset notation on the Y axis: `left` or `right`. | `left` or `right`; default `left` | `properties.offset_position` |

## Advanced

--8<-- "_snippets/components/common/axis-advanced.md"

## Unified Ticks & Labels

Locator determines tick positions; Formatter generates their label strings.
The Major and Minor tabs expose the complete existing Tick and Tick Label
properties while their child components remain independently editable. Fixed
ticks use a position/label table with add, remove, and reorder controls. A
Fixed Formatter requires an equal-length Fixed Locator. Major↔Minor copy,
opening-snapshot restore, and current-scale defaults change only the temporary
draft. Preview, Cancel, and an unchanged OK do not alter project state.

Ticker specifications synchronize across the current `sharey` group;
tick-line and label appearance remains local to the selected Axes. Schema v23
also supports Index Locator for index data and one-conversion Percent Format
Formatter. Date/category ticker and executable formatter types are excluded.

## Project record

Schema v23 persists the Y Axis as `kind: "axis"`, `role: "y_axis"`, with `selector: {"axis": "y"}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [YAxis API](https://matplotlib.org/3.9.0/api/axis_api.html#matplotlib.axis.YAxis)
- [Axes scales explainer](https://matplotlib.org/3.9.0/users/explain/axes/axes_scales.html)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)
- [Axis ticks guide](https://matplotlib.org/3.9.0/users/explain/axes/axes_ticks.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

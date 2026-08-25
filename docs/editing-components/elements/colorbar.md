# Colorbar Component

The **Colorbar** component provides a visual color scale for colormapped chart series (such as Scatter plots). It owns placement, axis orientation, scalar formatting, custom locators, and bounding outline frame styling.

For color selection and colormap configuration, see [Colorbar Component Guide](../../colorbar-component.md) and [Color Picker](../../color-picker.md).

## Source

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Source Component ID | Component chooser | Target mappable chart component (e.g. Scatter) providing the authoritative colormap and data limits. | Stable component ID | `data.source_component_id` |

## Placement

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Location | Dropdown | Placement edge relative to the parent Axes: `left`, `right`, `top`, `bottom`. | `left`, `right`, `top`, `bottom`; default `right` | `properties.location` |
| Fraction | Number | Fraction of original Axes dimensions reserved for colorbar insertion. | Positive number; default `0.15` | `properties.fraction` |
| Shrink | Number | Fraction by which to multiply the length of the colorbar. | Positive number; default `1.0` | `properties.shrink` |
| Aspect | Number | Ratio of long to short dimensions of the colorbar box. | Positive number; default `20.0` | `properties.aspect` |
| Pad | Number | Fraction of original Axes dimensions between colorbar and chart Axes. | Positive number; default `0.05` | `properties.pad` |

## Scale & Ticks

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Locator | Locator dialog | Rule determining where ticks are placed on the colorbar axis. | Locator spec or None; default None | `properties.locator` |
| Formatter | Formatter dialog | Rule converting colorbar tick values into numeric label strings. | Formatter spec or None; default None | `properties.formatter` |
| Minor Ticks | Checkbox | Enables minor tick mark generation on the colorbar. | `true` or `false`; default `false` | `properties.minor_ticks` |
| Ticklocation | Dropdown | Side of the colorbar where ticks and labels are rendered. | `auto`, `left`, `right`, `top`, `bottom`; default `auto` | `properties.ticklocation` |

## Label

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label | Text | Descriptive title label string rendered alongside the colorbar. | Text; default empty | `properties.label` |
| Label Font | Font chooser | Font configuration for the colorbar label text. | Font spec; default sans-serif 10 | `properties.label_font` |

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the colorbar component and its auxiliary axes. | `true` or `false`; default `true` | `properties.visible` |
| Tick Font | Font chooser | Font configuration for colorbar tick label text. | Font spec; default sans-serif 10 | `properties.tick_font` |
| Outline Visible | Checkbox | Draws the bounding box outline frame around the color gradient. | `true` or `false`; default `true` | `properties.outline_visible` |
| Outline Color | Color choice | Stroke color of the bounding box outline frame. | Hex color; default `#000000` | `properties.outline_color` |
| Outline Linewidth | Number | Stroke thickness of the bounding box outline frame in points. | Finite number `>= 0`; default `0.8` | `properties.outline_linewidth` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Extend | Dropdown | Displays pointed arrow extensions for out-of-range values: `neither`, `both`, `min`, `max`. | `neither`, `both`, `min`, `max`; default `neither` | `properties.extend` |
| Spacing | Dropdown | Spacing of colorbar color patches: `uniform` or `proportional`. | `uniform` or `proportional`; default `uniform` | `properties.spacing` |
| Drawedges | Checkbox | Draws divider lines between adjacent discrete color patches. | `true` or `false`; default `false` | `properties.drawedges` |

## Project record

Schema v15 persists Colorbar as `kind: "colorbar"`, `role: "colorbar"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object contains `source_component_id`.

## Referenced Matplotlib 3.9.0 URLs

- [Colorbar API](https://matplotlib.org/3.9.0/api/colorbar_api.html#matplotlib.colorbar.Colorbar)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)

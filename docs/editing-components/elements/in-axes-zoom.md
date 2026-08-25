# Zoom Inset Component

The **Zoom Inset** component provides a magnified detail view of a sub-region within the parent Axes, complete with optional indicator rectangles and connecting corner lines.

For high-level guides on in-axes overlays, see [In-Axes Elements](../../in-axes.md).

## Layout

--8<-- "_snippets/components/in_axes/in-axes-layout.md"

## Frame

--8<-- "_snippets/components/in_axes/in-axes-frame.md"

## Zoom range

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Xlim | Range editor | Magnified sub-region X data limits `[min, max]`. | Tuple of 2 numbers; default `[0.2, 0.4]` | `properties.xlim` |
| Ylim | Range editor | Magnified sub-region Y data limits `[min, max]`. | Tuple of 2 numbers; default `[0.2, 0.4]` | `properties.ylim` |
| Ticks Visible | Checkbox | Shows or hides coordinate tick marks along the inset border. | `true` or `false`; default `true` | `properties.ticks_visible` |

## Indicator

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Region Visible | Checkbox | Draws the indicator bounding box over the zoomed region in the parent Axes. | `true` or `false`; default `true` | `properties.region_visible` |
| Region Color | Color choice | Outline stroke color of the zoomed region indicator box. | Hex color; default `#808080` | `properties.region_color` |
| Region Linestyle | Line-style choice | Outline dash pattern of the zoomed region indicator box. | Preset or dash tuple; default `-` | `properties.region_linestyle` |
| Region Linewidth | Number | Outline stroke width of the zoomed region indicator box in points. | Finite number `>= 0`; default `1.0` | `properties.region_linewidth` |
| Region Alpha | Number | Opacity of the zoomed region indicator box from 0 to 1. | Finite `0 <= alpha <= 1`; default `0.5` | `properties.region_alpha` |
| Region Facecolor | Color choice | Background fill color inside the zoomed region indicator box. | Hex color; default `#00000000` | `properties.region_facecolor` |
| Region Fill | Checkbox | Enables background fill painting inside the indicator box. | `true` or `false`; default `false` | `properties.region_fill` |
| Region Hatch | Text | Hatch fill pattern inside the indicator box. | Hatch string or None; default None | `properties.region_hatch` |
| Region Zorder | Number | Stacking order of the indicator box in the parent Axes. | Finite number; default `4.99` | `properties.region_zorder` |
| Connectors | Dropdown | Draws connecting line segments between the indicator box and inset corners: `all`, `pair1`, `pair2`, `none`. | `all`, `pair1`, `pair2`, `none`; default `all` | `properties.connectors` |

## Project record

Schema v15 persists Zoom Inset as `kind: "in_axes"`, `role: "in_axes_zoom"`, with `selector: {"object_id": component_id}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [indicate_inset_zoom](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.indicate_inset_zoom.html)
- [Rectangle patch](https://matplotlib.org/3.9.0/api/patches_api.html#matplotlib.patches.Rectangle)

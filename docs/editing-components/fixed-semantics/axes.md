# Axes Component

The **Axes** component represents an individual Cartesian plotting area inside a Figure. It owns the coordinate system, limits, autoscaling parameters, visual lower-Y reserve margin, background patch styling, aspect ratio constraints, and the categorical color cycle palette.

In the Components tree, each Axes owns a fixed semantic subtree comprising its structural elements (Spines, Title, Legend) and dimensional axes (X Axis, Y Axis).

!!! note "Title and Axis Labels"
    The Axes Title, X Label, and Y Label are separate semantic Text components owned within the Axes hierarchy. For their configuration parameters, see [Title](axes-structure/title.md), [X Label](x-axis/x-label.md), and [Y Label](y-axis/y-label.md).

## Layout relationship

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Position | Position rectangle | Axes position rectangle `[left, bottom, width, height]` in normalized figure coordinates. Configured via the Edit layout geometry dialog. | Tuple of 4 floats `[0..1]`; default `[0.125, 0.11, 0.775, 0.77]` | `properties.position` |

For multi-axes arrangement and layout templates, see [Axes Layout Templates](../../axes-layouts.md).

## Limits and autoscale

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Xlim | Range editor | X axis data coordinate boundaries `[min, max]`. | Tuple of 2 numbers; default `[0.0, 1.0]` | `properties.xlim` |
| Ylim | Range editor | Y axis data coordinate boundaries `[min, max]`. | Tuple of 2 numbers; default `[0.0, 1.0]` | `properties.ylim` |
| Autoscalex On | Checkbox | Enables automatic X axis data limit fitting based on active data series. | `true` or `false`; default `true` | `properties.autoscalex_on` |
| Autoscaley On | Checkbox | Enables automatic Y axis data limit fitting based on active data series. | `true` or `false`; default `true` | `properties.autoscaley_on` |
| Y Lower Reserve | Number | Extra visual reserve space added below the ordinary autoscale interval as a fraction of total Axes height. | Finite `0.0 <= r < 0.9`; default `0.0` | `properties.y_lower_reserve` |
| X Inverted | Checkbox (proxy) | Reverses the direction of X data coordinates by swapping limit ordering. | `true` or `false`; default `false` | `runtime.x_inverted` |
| Y Inverted | Checkbox (proxy) | Reverses the direction of Y data coordinates by swapping limit ordering. | `true` or `false`; default `false` | `runtime.y_inverted` |

### Lower Y Reserve Guidance

The `y_lower_reserve` property adds extra visual clearance at the bottom of the Axes plotting area after ordinary autoscale. When autoscale runs, the autoscale range expands downward in coordinate transform space by `S * r / (1 - r)`, ensuring data occupies the upper `1 - r` portion of the Axes height:

- **Ordinary Plots**: Default `0.0` (standard full-height data range).
- **XRD Main Plot + Residual & Single without residual**: Default `0.1` (10% lower clearance to accommodate baseline reflection markers).
- **Single with Residual Overlay**: Default `0.0` (residual occupies separate data baseline).

## Palette

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Color Cycle | Color palette chooser | Ordered categorical color cycle dictionary applied to newly created chart series. | Palette dict or None; default None | `properties.color_cycle` |

For details on color choice workflows, see [Color Picker](../../color-picker.md).

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Aspect | Aspect editor | Aspect ratio of coordinate scaling: `auto`, `equal`, or numeric ratio. | `auto`, `equal`, or positive number; default `auto` | `properties.aspect` |
| Facecolor | Color choice | Background fill color of the Axes plotting rectangle. | Hex color; default `#ffffff` | `properties.facecolor` |
| Visible | Checkbox | Shows or hides the entire Axes and its children. | `true` or `false`; default `true` | `properties.visible` |
| Xmargin | Number | Automatic padding fraction added to each side of X data limits during autoscale. When `0`, autoscale X uses the data interval with no locator expansion. XRD Single and Main Plot + Residual set this to `0`. | Finite `-0.5 <= margin <= 10.0`; default `0.05` | `properties.xmargin` |
| Ymargin | Number | Automatic padding fraction added to each side of Y data limits during autoscale. | Finite `-0.5 <= margin <= 10.0`; default `0.05` | `properties.ymargin` |
| Adjustable | Dropdown | Defines whether the physical `box` or data limits `datalim` adjust to satisfy aspect ratio. | `box` or `datalim`; default `box` | `properties.adjustable` |
| Anchor | Anchor editor | Alignment anchor of the Axes box within its available bounding space. | Compass string (`C`, `SW`, `NE`, etc.); default `C` | `properties.anchor` |
| Box Aspect | Number | Fixed physical box aspect ratio (height / width), or None for unconstrained. | Positive number or None; default None | `properties.box_aspect` |
| Axisbelow | Dropdown | Layering of grid lines and tick marks relative to chart data artists. | `true` (below), `false` (above), `line` (grid below, ticks above); default `line` | `properties.axisbelow` |
| Frameon | Checkbox | Enables drawing of the background patch and bounding spines. | `true` or `false`; default `true` | `properties.frameon` |
| Zorder | Number | Stacking order of the Axes background patch. | Finite number; default `0.0` | `properties.zorder` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Rasterization Zorder | Number | Z-order threshold below which artists are automatically rasterized in vector export. | Finite number or None; default None | `properties.rasterization_zorder` |
| Alpha | Number | Axes background patch opacity from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Label | Text | Display and lookup label for the Axes artist. | Text; default empty | `properties.label` |
| Clip On | Checkbox | Clips child artists to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes the Axes in tight-layout and auto-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export (PDF/SVG). | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel grid snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

## Project record

Schema v15 persists Axes as `kind: "axes"`, `role: "axes"`, with `selector: {"object_id": component_id}`. Its parent is the Figure root.

## Referenced Matplotlib 3.9.0 URLs

- [Axes set_anchor](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.set_anchor.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

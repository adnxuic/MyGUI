# Contour Component

The **Contour** component draws isolines and/or filled regions from a table-driven 2D scalar field using Matplotlib [`Axes.contour`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contour.html) and [`Axes.contourf`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contourf.html). It is `kind: "field_2d"` with `role: "contour"`. A drawable contour requires at least a 2×2 grid; smaller inputs remain a valid empty component.

Mode `filled` (default) uses a filled set as the ScalarMappable. Mode `lines` uses line contours only. Mode `overlay` draws both and uses the filled set as the Colorbar source. Labels default to off. Enabling labels in filled mode creates a hidden auxiliary line set used only to place labels. The component does not consume the Axes color cycle. Create a [Colorbar](../../colorbar-component.md) separately when a color scale is required.

## Data source

--8<-- "_snippets/components/charts/field-2d-data.md"

## Color mapping

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Colormap | Color map editor | Closed colormap name, tagged `NormSpec`, and optional bad/under/over colors. See [colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html) and [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize). | `ColorMapSpec`; default from Figure style `image.cmap` | `properties.colormap` |

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the contour artists. | `true` or `false`; default `true` | `properties.visible` |
| Alpha | Number | Opacity from 0 to 1, or None to inherit. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order relative to other Axes artists. | Finite number; default `1.0` | `properties.zorder` |
| Mode | Dropdown | Drawing mode for the QuadContourSet. | `lines`, `filled`, `overlay`; default `filled` | `properties.mode` |
| Levels | Contour levels editor | Automatic count (2–256) or strictly increasing explicit values (2–256). See [`contour`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contour.html). | `{"kind": "count", "count": 8}` or `{"kind": "values", "values": [...]}` | `properties.levels` |
| Corner Mask | Checkbox | Masks triangles with masked corners. See [QuadContourSet](https://matplotlib.org/3.9.0/api/contour_api.html#matplotlib.contour.QuadContourSet). | `true` or `false`; default `true` | `properties.corner_mask` |
| Extend | Dropdown | Out-of-range filled extensions. See [`contourf`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contourf.html). | `neither`, `both`, `min`, `max`; default `neither` | `properties.extend` |
| Algorithm | Dropdown | Contour generation algorithm. | `mpl2014`, `serial`, `threaded`; default `mpl2014` | `properties.algorithm` |
| Nchunk | Integer | Chunk size for contour generation; `0` disables chunking. | Integer `>= 0`; default `0` | `properties.nchunk` |
| Antialiased | Checkbox | Enables antialiased contour rendering. | `true` or `false`; default `true` | `properties.antialiased` |
| Linewidth | Number | Contour line width in points. | Finite number `>= 0`; default `1.0` | `properties.linewidth` |
| Linestyle | Line-style choice | Positive contour dash pattern. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Negative Linestyle | Line-style choice | Dash pattern for negative contours, seeded from Figure style `contour.negative_linestyle`. | Preset or dash tuple; default `dashed` | `properties.negative_linestyle` |
| Labels | Contour label editor | Closed label contract: enable, numeric format, fontsize, color, inline, and spacing. See [`clabel`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.clabel.html). Default off. | `ContourLabelSpec`; default disabled | `properties.labels` |

## Export

--8<-- "_snippets/components/charts/field-2d-export.md"

## Project record

Schema v16 persists Contour as `kind: "field_2d"`, `role: "contour"`, with `selector: {"object_id": component_id}` under its parent Axes. `data` is exactly `x_ref`, `y_ref`, and `z_ref`.

## Referenced Matplotlib 3.9.0 URLs

- [Axes contour](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contour.html)
- [Axes contourf](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contourf.html)
- [Axes clabel](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.clabel.html)
- [QuadContourSet API](https://matplotlib.org/3.9.0/api/contour_api.html#matplotlib.contour.QuadContourSet)
- [Colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html)
- [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
- [Artist rasterized](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_rasterized)

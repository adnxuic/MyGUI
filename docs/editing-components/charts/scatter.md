# Scatter Component

The **Scatter** component represents a 2D point collection (`PathCollection`) where marker colors and sizes can either be uniform or dynamically mapped to table data columns via colormaps and size interpolation functions.

For multi-series workflows and color mapping integration, see [Multi-Series Chart Creation](../../multi-series-charts.md) and [Colorbar Component](../../colorbar-component.md).

## Data source

--8<-- "_snippets/components/charts/data-source.md"

## Color and size mapping

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Color Mapping | Scatter color map editor | Authoritative color mapping specification: colormap name, normalization interval, and out-of-range clamping. | ScatterColorMapSpec; default disabled | `properties.color_mapping` |
| Size Mapping | Scatter size map editor | Authoritative marker size mapping specification: output point area range and clamp mode. | ScatterSizeMapSpec; default disabled | `properties.size_mapping` |
| Color Column | Column selector | Table column providing numeric values for continuous colormap lookups. | Number column or None; default None | `data.color_ref` |
| Size Column | Column selector | Table column providing numeric values for marker size scaling. | Number column or None; default None | `data.size_ref` |

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the scatter collection artist. | `true` or `false`; default `true` | `properties.visible` |
| Color | Color choice | Uniform marker fill color (active when color mapping is disabled). | Hex color; default `#1f77b4` | `properties.color` |
| Marker | Marker choice | Marker symbol shape. | Marker spec; default `{'kind': 'symbol', 'value': 'o'}` | `properties.marker` |
| Size | Number | Uniform marker area in points-squared (active when size mapping is disabled). | Finite number `>= 0`; default `36.0` | `properties.size` |
| Edgecolor | Color choice | Uniform marker outline stroke color. | Hex color; default `#1f77b4` | `properties.edgecolor` |
| Linewidth | Number | Marker outline stroke thickness in points. | Finite number `>= 0`; default `1.0` | `properties.linewidth` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label | Text | Legend entry label for the scatter collection. | Text; default empty | `properties.label` |
| Linestyle | Line-style choice | Marker outline dash pattern. | Preset or dash tuple; default `none` | `properties.linestyle` |
| Hatch | Text | Hatch fill pattern across scatter markers (e.g. `/`, `x`, `o`). | Hatch string or None; default None | `properties.hatch` |
| Capstyle | Dropdown | Cap style of marker outlines. | `butt`, `projecting`, `round` or None; default None | `properties.capstyle` |
| Joinstyle | Dropdown | Join style of marker corners. | `miter`, `round`, `bevel` or None; default None | `properties.joinstyle` |
| Alpha | Number | Opacity factor for scatter markers from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order relative to other Axes artists. | Finite number; default `1.0` | `properties.zorder` |
| Antialiased | Checkbox | Enables antialiased rendering of marker geometry. | `true` or `false`; default `true` | `properties.antialiased` |
| Clip On | Checkbox | Clips markers to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes scatter artist in tight-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL attached to the entire collection in SVG export. | Valid URL string or none; default none | `properties.url` |
| Urls | String list | Per-point hyperlink URLs for interactive SVG exports. | List of URL strings; default empty | `properties.urls` |

## Project record

Schema v15 persists Scatter as `kind: "scatter"`, `role: "scatter"`, with `selector: {"object_id": component_id}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Axes scatter](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.scatter.html)
- [PathCollection API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.PathCollection)
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html)
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html)
- [Hatch style reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html)
- [Cap and join styles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

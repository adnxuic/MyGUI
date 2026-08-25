# Legend Component

The **Legend** component manages the explanatory key for chart series and collections inside an Axes. It automatically aggregates labeled artists, formats symbol handles, controls multi-column layouts, and configures background box frame styling.

## Title

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Title | Text | Optional title string displayed at the top of the legend box. | Text; default empty | `properties.title` |

## Typography

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label Font | Font chooser | Font configuration for legend item labels. | Font spec; default sans-serif 10 | `properties.label_font` |
| Title Font | Font chooser | Font configuration for the legend title text. | Font spec; default sans-serif 10 | `properties.title_font` |

## Layout

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the entire legend box. | `true` or `false`; default `true` | `properties.visible` |
| Location | Dropdown | Placement anchor position inside or outside the Axes. | Matplotlib legend location code; default `best` | `properties.location` |
| Ncols | Number | Number of columns used to arrange legend entries. | Positive integer; default `1` | `properties.ncols` |
| Entry Scope | Dropdown | Filters which chart series enter the legend: `axes` (owning Axes only) or `all` (all artists across figure). | `axes` or `all`; default `axes` | `properties.entry_scope` |

## Layout details

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Bbox To Anchor | Position / Box dialog | Explicit bounding box anchor `(x, y, width, height)` in figure or axes coordinates. | Tuple or None; default None | `properties.bbox_to_anchor` |
| Mode | Dropdown | Expansion mode: `expand` (expands legend horizontally) or None. | `expand` or None; default None | `properties.mode` |
| Alignment | Dropdown | Horizontal alignment of title and entries inside legend: `left`, `center`, `right`. | `left`, `center`, `right`; default `center` | `properties.alignment` |
| Reverse | Checkbox | Reverses the display order of legend entries. | `true` or `false`; default `false` | `properties.reverse` |
| Markerfirst | Checkbox | Places legend marker handles to the left of labels (`true`) or right (`false`). | `true` or `false`; default `true` | `properties.markerfirst` |
| Draggable | Checkbox | Enables interactive mouse drag repositioning on the canvas. | `true` or `false`; default `false` | `properties.draggable` |
| Draggable Update | Dropdown | Coordinate update mode when dragged: `loc` or `bbox`. | `loc` or `bbox`; default `loc` | `properties.draggable_update` |
| Numpoints | Number | Number of marker points shown on line handles. | Positive integer; default `1` | `properties.numpoints` |
| Scatterpoints | Number | Number of marker points shown on scatter handles. | Positive integer; default `1` | `properties.scatterpoints` |
| Scatteryoffsets | Number sequence | Vertical marker offsets for multi-point scatter handles. | List of numbers; default `[0.375, 0.5, 0.3125]` | `properties.scatteryoffsets` |
| Markerscale | Number | Relative scaling factor for marker symbols inside legend handles. | Positive number; default `1.0` | `properties.markerscale` |
| Borderpad | Number | Fractional whitespace padding inside the legend border box. | Positive number; default `0.4` | `properties.borderpad` |
| Labelspacing | Number | Vertical spacing between successive legend entries. | Positive number; default `0.5` | `properties.labelspacing` |
| Handlelength | Number | Length of line and patch handles in font-size units. | Positive number; default `2.0` | `properties.handlelength` |
| Handleheight | Number | Height of line and patch handles in font-size units. | Positive number; default `0.7` | `properties.handleheight` |
| Handletextpad | Number | Padding between handle symbols and entry labels. | Positive number; default `0.8` | `properties.handletextpad` |
| Borderaxespad | Number | Padding between the legend border and the Axes bounding box. | Positive number; default `0.5` | `properties.borderaxespad` |
| Columnspacing | Number | Spacing between adjacent columns in multi-column layouts. | Positive number; default `2.0` | `properties.columnspacing` |

## Frame

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Frameon | Checkbox | Draws the background rectangle patch behind legend items. | `true` or `false`; default `true` | `properties.frameon` |
| Facecolor | Color choice | Background fill color of the legend frame. | Hex color; default `#ffffff` | `properties.facecolor` |
| Edgecolor | Color choice | Border outline stroke color of the legend frame. | Hex color; default `#e0e0e0` | `properties.edgecolor` |
| Framealpha | Number | Opacity of the background frame patch from 0 to 1. | Finite `0 <= alpha <= 1` or None; default `0.8` | `properties.framealpha` |
| Fancybox | Checkbox | Enables rounded corners on the background frame patch. | `true` or `false`; default `true` | `properties.fancybox` |
| Shadow | Checkbox | Draws a drop shadow behind the legend box. | `true` or `false`; default `false` | `properties.shadow` |
| Frame Linewidth | Number | Border stroke outline width in points. | Finite number `>= 0`; default `0.8` | `properties.frame_linewidth` |
| Frame Linestyle | Line-style choice | Border outline dash pattern. | Preset or dash tuple; default `-` | `properties.frame_linestyle` |
| Frame Hatch | Text | Hatch fill pattern for the background box. | Hatch pattern or None; default None | `properties.frame_hatch` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Zorder | Number | Stacking order of the legend relative to other Axes artists. | Finite number; default `5.0` | `properties.zorder` |
| Alpha | Number | Overall legend opacity factor. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Label | Text | Display label for lookup and debugging. | Text; default empty | `properties.label` |
| Clip On | Checkbox | Clips legend to Axes boundaries. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier for vector export. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes legend in tight-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel grid snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

## Project record

Schema v15 persists the Legend as `kind: "legend"`, `role: "legend"`, with `selector: {"object_id": component_id}` under its parent Axes.

## Referenced Matplotlib 3.9.0 URLs

- [Legend API](https://matplotlib.org/3.9.0/api/legend_api.html#matplotlib.legend.Legend)
- [Axes legend](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.legend.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

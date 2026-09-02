# Figure Component

The **Figure** component represents the top-level canvas root of a MyGUI visualization project. It owns global canvas properties such as physical dimensions, display and export DPI resolution, background face and edge styling, and the layout management engine.

In the Components tree, the Figure root sits at the top of the hierarchy and cannot be deleted. Selecting the Figure root activates the Figure Inspector profile.

## Basic

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Name | Text | Project and figure title name. Synchronized with project tab and table document title. | Text string; default empty | `properties.name` |
| Style | Text | Active Matplotlib style sheet applied during figure creation. | Style name; default `default` | `properties.style` |
| Size | Size editor | Physical figure canvas dimensions `(width, height)` in inches. | Positive tuple `(width, height)`; default `[6.4, 4.8]` | `properties.size_inches` |
| DPI | Number | Canvas resolution in dots per inch for rendering and image/PDF export. | Positive number; default `100.0` | `properties.dpi` |
| Background | Color choice | Figure background canvas fill color. | Hex color; default `#ffffff` | `properties.facecolor` |
| Layout Engine | Layout engine dialog | Tagged layout engine specification (`none`, `tight`, `constrained`, `compressed`). | Tagged dict; default `{'kind': 'none'}` | `properties.layout_engine` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Border | Color choice | Figure border stroke outline color. | Hex color; default `#ffffff` | `properties.edgecolor` |
| Frame | Checkbox | Enables drawing of the background figure canvas rectangle patch. | `true` or `false`; default `true` | `properties.frameon` |
| Line Width | Number | Stroke width of the figure border outline in points. | Finite number `>= 0`; default `0.0` | `properties.linewidth` |
| Alpha | Number | Background canvas opacity from 0 (transparent) to 1 (opaque). | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Label | Text | Display and lookup label for the Figure artist. | Text; default empty | `properties.label` |
| Visible | Checkbox | Shows or hides the complete figure canvas rendering. | `true` or `false`; default `true` | `properties.visible` |
| Zorder | Number | Drawing stacking order of the figure canvas relative to parent container. | Finite number; default `0.0` | `properties.zorder` |
| Clip On | Checkbox | Clips figure artists to canvas bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes figure artist in layout engine calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export (PDF/SVG). | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel grid snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

## Project record

Schema v15 persists the figure root as `kind: "figure"`, `role: "figure"`, with `selector: null` and parent `null`. Its `properties` record contains exact scalar and composite values matching the Inspector fields above.

## Referenced Matplotlib 3.9.0 URLs

- [Figure API](https://matplotlib.org/3.9.0/api/figure_api.html#matplotlib.figure.Figure)
- [Layout Engine API](https://matplotlib.org/3.9.0/api/layout_engine_api.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Antialiased | Checkbox | Enables antialiased rendering for tick lines. | `true` or `false`; default `true` | `properties.antialiased` |
| Clip On | Checkbox | Clips tick lines to the Axes boundaries. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier for vector export. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes artist in layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces raster bitmap rendering for vector exports. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel snapping behavior: auto (`None`), `True`, or `False`. | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

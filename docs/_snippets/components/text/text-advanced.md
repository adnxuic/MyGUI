| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Bbox | Text box editor | Bounding background box and frame styling behind text. | Bbox spec; default `{'enabled': False}` | `properties.bbox` |
| Antialiased | Checkbox | Enables antialiased text rendering. | `true` or `false`; default `true` | `properties.antialiased` |
| Label | Text | Display and lookup label for the text artist. | Text; default empty | `properties.label` |
| Clip On | Checkbox | Clips text rendering to the parent Axes boundary. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier for vector export. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes text artist in tight-layout and auto-constrained calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces raster bitmap rendering for vector exports. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel snapping behavior: auto (`None`), `True`, or `False`. | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Zorder | Number | Stacking order of axis elements relative to other artists. | Finite number; default `2.5` | `properties.zorder` |
| Alpha | Number | Opacity factor for axis elements from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Clip On | Checkbox | Enables Axes clipping for axis tick lines and labels. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier for vector export. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes axis artists in tight-layout calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization in vector exports. | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel snapping behavior: auto (`None`), `True`, or `False`. | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.url` |

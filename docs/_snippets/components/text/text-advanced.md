| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Fontweight | Named number | Font weight (stroke thickness). | `normal`, `bold`, `heavy`, `light`, or 100-900; default `normal` | `properties.fontweight` |
| Fontstyle | Dropdown | Font posture / slant style. | `normal`, `italic`, `oblique`; default `normal` | `properties.fontstyle` |
| Fontstretch | Named number | Horizontal character condensation or expansion. | `normal`, `condensed`, `expanded`, etc.; default `normal` | `properties.fontstretch` |
| Fontvariant | Dropdown | Font capitalization variant. | `normal`, `small-caps`; default `normal` | `properties.fontvariant` |
| Math Fontfamily | Text | Math font family used for Mathtext equations (`$...$`). | `dejavusans`, `dejavuserif`, `cm`, `stix`; default `dejavusans` | `properties.math_fontfamily` |
| Parse Math | Checkbox | Enables Matplotlib Mathtext equation parser for dollar expressions. | `true` or `false`; default `true` | `properties.parse_math` |
| Alpha | Number | Text opacity from 0 (transparent) to 1 (opaque). | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order of the text artist. | Finite number; default `3.0` | `properties.zorder` |
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

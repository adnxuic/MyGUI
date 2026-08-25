| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label | Text | Legend entry label. Empty labels do not create legend entries. | Text; default empty | `properties.label` |
| Visible | Checkbox | Shows or hides the line artist. | `true` or `false`; default `true` | `properties.visible` |
| Color | Color choice | Uniform line color using Matplotlib color contract. | Hex color; default `#1f77b4` | `properties.color` |
| Linestyle | Line-style choice | Line pattern: solid, dashed, dashdot, dotted, none, or custom dash sequence. | Preset or dash tuple; default `-` | `properties.linestyle` |
| Linewidth | Number | Line thickness in points. | Finite number `>= 0`; default `1.5` | `properties.linewidth` |
| Drawstyle | Dropdown | Point connection style: `default` (straight), `steps`, `steps-pre`, `steps-mid`, `steps-post`. | Matplotlib drawstyle; default `default` | `properties.drawstyle` |
| Gapcolor | Optional color | Alternating color shown inside dashed gaps. | Hex color or none; default none | `properties.gapcolor` |
| Marker | Marker choice | Marker symbol shape: none, symbol (`o`, `s`, `^`, etc.), or regular polygon. | Marker spec; default `None` | `properties.marker` |
| Markersize | Number | Marker diameter in points. | Finite number `>= 0`; default `6.0` | `properties.markersize` |
| Markerfacecolor | Color choice | Marker fill color. | Hex color; default `#1f77b4` | `properties.markerfacecolor` |
| Markerfacecoloralt | Optional color | Alternate fill color for half-fill marker styles. | Hex color or none; default `none` | `properties.markerfacecoloralt` |
| Markeredgecolor | Color choice | Marker outline color. | Hex color; default `#1f77b4` | `properties.markeredgecolor` |
| Markeredgewidth | Number | Marker outline width in points. | Finite number `>= 0`; default `1.0` | `properties.markeredgewidth` |
| Fillstyle | Dropdown | Marker fill coverage: `full`, `left`, `right`, `bottom`, `top`, `none`. | Matplotlib fillstyle; default `full` | `properties.fillstyle` |
| Markevery | Structured editor | Subsampling for marker display: all, stride, slice, indices, or spacing. | Markevery spec; default `{'kind': 'all'}` | `properties.markevery` |
| Alpha | Number | Opacity from 0 (transparent) to 1 (opaque), or None to inherit. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order among artists in the Axes; higher values draw on top. | Finite number; default `2.0` | `properties.zorder` |
| Dash Capstyle | Dropdown | Cap style of dash segments: `butt`, `projecting`, `round`. | `butt`, `projecting`, `round`; default `butt` | `properties.dash_capstyle` |
| Dash Joinstyle | Dropdown | Join style of dash segments: `miter`, `round`, `bevel`. | `miter`, `round`, `bevel`; default `round` | `properties.dash_joinstyle` |
| Solid Capstyle | Dropdown | Cap style of solid segments: `butt`, `projecting`, `round`. | `butt`, `projecting`, `round`; default `projecting` | `properties.solid_capstyle` |
| Solid Joinstyle | Dropdown | Join style of solid segments: `miter`, `round`, `bevel`. | `miter`, `round`, `bevel`; default `round` | `properties.solid_joinstyle` |
| Antialiased | Checkbox | Enables antialiased line rendering. | `true` or `false`; default `true` | `properties.antialiased` |
| Clip On | Checkbox | Clips the line artist to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |
| Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.gid` |
| In Layout | Checkbox | Includes the artist in tight-layout and auto-constrained calculations. | `true` or `false`; default `true` | `properties.in_layout` |
| Rasterized | Checkbox | Forces bitmap rasterization during vector export (PDF/SVG). | `true` or `false`; default `false` | `properties.rasterized` |
| Sketch Params | Triplet editor | Hand-drawn stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.sketch_params` |
| Snap | Dropdown | Pixel grid alignment: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.snap` |
| Url | Text | Hyperlink URL attached to the line in SVG exports. | Valid URL string or none; default none | `properties.url` |

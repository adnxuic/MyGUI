| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Primary Visible | Checkbox | Shows or hides tick labels on the primary spine (bottom / left). | `true` or `false`; default `true` | `properties.primary_visible` |
| Secondary Visible | Checkbox | Shows or hides tick labels on the secondary spine (top / right). | `true` or `false`; default `false` | `properties.secondary_visible` |
| Color | Color choice | Tick label font color. | Hex color; default `#000000` | `properties.color` |
| Fontsize | Number | Font size in points. | Positive number; default `10.0` | `properties.fontsize` |
| Rotation | Number | Label rotation angle in degrees. | Finite angle in degrees; default `0.0` | `properties.rotation` |
| Fontfamily | Font chooser | Primary font family for tick labels. | Family name; default `sans-serif` | `properties.fontfamily` |
| Pad | Number | Distance between tick marks and tick labels in points. | Finite number; default `3.5` | `properties.pad` |
| Fontweight | Named number | Font weight (stroke thickness). | `normal`, `bold`, `heavy`, `light`, or numeric; default `normal` | `properties.fontweight` |
| Fontstyle | Dropdown | Font posture / slant style. | `normal`, `italic`, `oblique`; default `normal` | `properties.fontstyle` |
| Fontstretch | Named number | Horizontal condensation or expansion. | `normal`, `condensed`, `expanded`, etc.; default `normal` | `properties.fontstretch` |
| Fontvariant | Dropdown | Font capitalization variant. | `normal`, `small-caps`; default `normal` | `properties.fontvariant` |
| Alpha | Number | Text opacity from 0 to 1. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Rotation Mode | Dropdown | Coordinate anchor rotation mode. | `default` or `anchor`; default `default` | `properties.rotation_mode` |
| Horizontalalignment | Dropdown | Horizontal text alignment relative to anchor. | `left`, `center`, `right`; default `center` | `properties.horizontalalignment` |
| Verticalalignment | Dropdown | Vertical text alignment relative to anchor. | `top`, `center`, `bottom`, `baseline`, `center_baseline`; default `baseline` | `properties.verticalalignment` |
| Multialignment | Dropdown | Alignment of multi-line tick label text. | `left`, `center`, `right`, or None; default None | `properties.multialignment` |
| Wrap | Checkbox | Enables line wrapping for tick labels. | `true` or `false`; default `false` | `properties.wrap` |
| Linespacing | Number | Line spacing factor for multi-line labels. | Finite number `>= 0`; default `1.2` | `properties.linespacing` |
| Math Fontfamily | Text | Math font family used for Mathtext equations (`$...$`). | `dejavusans`, `cm`, `stix`; default `dejavusans` | `properties.math_fontfamily` |
| Parse Math | Checkbox | Enables Matplotlib Mathtext equation parser. | `true` or `false`; default `true` | `properties.parse_math` |
| Usetex | Checkbox | Enables LaTeX typesetting for tick labels. | `true` or `false`; default `false` | `properties.usetex` |
| Bbox | Text box editor | Bounding background box styling behind tick labels. | Bbox spec; default `{'enabled': False}` | `properties.bbox` |
| Zorder | Number | Stacking order of tick labels. | Finite number; default `3.0` | `properties.zorder` |

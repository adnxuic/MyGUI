| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Fontfamily | Font chooser | Primary font family name for text rendering. | Family name; default `sans-serif` | `properties.fontfamily` |
| Fontsize | Number | Font size in points. | Positive number; default `10.0` | `properties.fontsize` |
| Fontweight | Named number | Font weight (stroke thickness). | `normal`, `bold`, `heavy`, `light`, or 100-900; default `normal` | `properties.fontweight` |
| Fontstyle | Dropdown | Font posture / slant style. | `normal`, `italic`, `oblique`; default `normal` | `properties.fontstyle` |
| Fontstretch | Named number | Horizontal character condensation or expansion. | `normal`, `condensed`, `expanded`, etc.; default `normal` | `properties.fontstretch` |
| Fontvariant | Dropdown | Font capitalization variant. | `normal`, `small-caps`; default `normal` | `properties.fontvariant` |
| Math Fontfamily | Text | Math font family used for Mathtext equations (`$...$`). | `dejavusans`, `dejavuserif`, `cm`, `stix`; default `dejavusans` | `properties.math_fontfamily` |
| Parse Math | Checkbox | Enables Matplotlib Mathtext equation parser for dollar expressions. | `true` or `false`; default `true` | `properties.parse_math` |
| Color | Color choice | Text font color using Matplotlib color contract. | Hex color; default `#000000` | `properties.color` |
| Alpha | Number | Text opacity from 0 (transparent) to 1 (opaque). | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |

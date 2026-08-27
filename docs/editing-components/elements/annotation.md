# Annotation Component

The **Annotation** component represents an anchored text label pointing to a target data point or coordinate location via an optional arrow patch (`matplotlib.text.Annotation`).

For creation workflows, coordinate behavior, tree lifecycle, and component
boundaries, see [Annotation Component](../../annotation-component.md). For
general unanchored text element creation, see [Text Element](../../text-element.md).

## Content

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Text | Multi-line text input | Text displayed by the annotation. | String; default `""` | `properties.text` |
| Name | Text input | User-defined label shown in the Components Tree. | String; default `""` | `properties.label` |
| Visible | Checkbox | Shows or hides the annotation text and arrow. | `true` or `false`; default `true` | `properties.visible` |

## Target

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Target coordinate system | Dropdown | Coordinate system for the pointed target position. | `data`, `axes_fraction`; default `data` | `properties.xycoords` |
| Target position | Position editor | Target coordinates `(x, y)` pointed to by the arrow. | Tuple of 2 finite numbers; default `[0.0, 0.0]` | `properties.xy` |

## Text position

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Text coordinate system | Dropdown | Coordinate system for the text label position. | `offset_points`, `data`, `axes_fraction`; default `offset_points` | `properties.textcoords` |
| Text position | Position editor | Text anchor coordinates `(x, y)` in the selected coordinate system. | Tuple of 2 finite numbers; default `[20.0, 20.0]` | `properties.xytext` |

**Placement preset** is a UI-only dropdown below these two persisted fields.
It offers Custom, Above, Below, Left, Right, Upper Left, Upper Right, Lower
Left, and Lower Right. Choosing a direction writes `textcoords=offset_points`
and the matching 20-point `xytext` offset in one transaction, then returns the
dropdown to Custom.

## Arrow

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Show arrow | Checkbox | Toggles arrow visibility while preserving style settings. | `true` or `false`; default `true` | `properties.arrow_enabled` |
| Arrow style | Dropdown | Arrowhead style: line, arrow, filled arrow, or double arrow. | `line`, `arrow`, `filled_arrow`, `double_arrow`; default `arrow` | `properties.arrow_style` |
| Arrow color | Color choice | Arrow stroke color. | Hex color; default `#000000` | `properties.arrow_color` |
| Arrow linewidth | Number | Arrow stroke width in points. | Finite number `>= 0`; default `1.5` | `properties.arrow_linewidth` |
| Connection style | Dropdown | Connection routing: `straight` (`arc3,rad=0`), `angle` (`angle3,angleA=0,angleB=90`), or `arc` (`arc3,rad=0.2`). | `straight`, `angle`, `arc`; default `straight` | `properties.connection_style` |

## Text style

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Font family | Font dropdown | Primary font family used for the text label. | String; default `sans-serif` | `properties.fontfamily` |
| Font size | Number | Font size in points. | Finite number `> 0`; default `10.0` | `properties.fontsize` |
| Font weight | Dropdown / Number | Font weight boldness. | Named weight or number; default `normal` | `properties.fontweight` |
| Font style | Dropdown | Font slant style: normal, italic, or oblique. | `normal`, `italic`, `oblique`; default `normal` | `properties.fontstyle` |
| Color | Color choice | Text font fill color. | Hex color; default `#000000` | `properties.color` |

## Rotation and alignment

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Rotation | Rotation editor | Text orientation angle in degrees counter-clockwise. | Finite number in degrees; default `0.0` | `properties.rotation` |
| Horizontal alignment | Dropdown | Horizontal text anchor alignment. | `left`, `center`, `right`; default `left` | `properties.horizontalalignment` |
| Vertical alignment | Dropdown | Vertical text anchor alignment. | `top`, `center`, `bottom`, `baseline`, `center_baseline`; default `baseline` | `properties.verticalalignment` |

## Box

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Show box, Box style, Background, Border, Border width, Opacity, Padding | Checkbox, dropdown, two color choices, and four numbers | Edits one closed box record. The box-only opacity is independent of the Annotation overall Alpha. | Disabled by default; style Rounded (`rounded`), background `#ffffff`, border `#000000`, width `1.0`, opacity `1.0`, padding `0.3`. Enabled style may be Square or Rounded; width/padding are finite and non-negative; opacity is `0`–`1` or automatic. | `properties.bbox` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Use TeX | Checkbox | Enables TeX rendering for mathematical formulas when LaTeX is available. | `true` or `false`; default `false` | `properties.usetex` |
| Alpha | Number | Overall opacity factor for text and arrow from 0 to 1. | Finite `0 <= alpha <= 1` or `null`; default `null` | `properties.alpha` |
| Zorder | Number | Stacking order of the annotation artist. | Finite number; default `3.0` | `properties.zorder` |
| Clip | Checkbox | Clips the annotation to the Axes boundary. | `true` or `false`; default `true` | `properties.clip_on` |

## Project record

Schema v17 persists Annotation as `kind: "annotation"`, `role: "annotation"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object is `{}`.

## Referenced Matplotlib 3.9.0 URLs

- [Annotation API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Annotation)
- [Axes.annotate](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.annotate.html)
- [Annotations Guide](https://matplotlib.org/3.9.0/users/explain/text/annotations.html)
- [FancyArrowPatch API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.FancyArrowPatch.html)
- [BoxStyle API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.BoxStyle.html)

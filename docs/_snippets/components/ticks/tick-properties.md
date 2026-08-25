| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Primary Visible | Checkbox | Shows or hides tick marks on the primary axis spine (bottom / left). | `true` or `false`; default `true` | `properties.primary_visible` |
| Secondary Visible | Checkbox | Shows or hides tick marks on the secondary opposing spine (top / right). | `true` or `false`; default `false` | `properties.secondary_visible` |
| Direction | Dropdown | Tick mark protrusion direction: `out`, `in`, `inout`. | `out`, `in`, `inout`; default `out` | `properties.direction` |
| Length | Number | Length of tick marks in points. | Finite number `>= 0`; default `3.5` | `properties.length` |
| Width | Number | Stroke width of tick marks in points. | Finite number `>= 0`; default `0.8` | `properties.width` |
| Color | Color choice | Uniform color for tick marks using Matplotlib color contract. | Hex color; default `#000000` | `properties.color` |
| Zorder | Number | Stacking order of tick marks. | Finite number; default `2.01` | `properties.zorder` |

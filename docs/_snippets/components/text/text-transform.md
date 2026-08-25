| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Rotation | Number | Text rotation angle in degrees counter-clockwise. | Finite angle in degrees; default `0.0` | `properties.rotation` |
| Rotation Mode | Dropdown | Coordinate anchor rotation mode: `default` (rotates then aligns) or `anchor` (aligns then rotates). | `default` or `anchor`; default `default` | `properties.rotation_mode` |
| Horizontalalignment | Dropdown | Horizontal text alignment relative to anchor position. | `left`, `center`, `right`; default `center` | `properties.horizontalalignment` |
| Verticalalignment | Dropdown | Vertical text alignment relative to anchor position. | `top`, `center`, `bottom`, `baseline`, `center_baseline`; default `baseline` | `properties.verticalalignment` |
| Multialignment | Dropdown | Internal horizontal alignment of multi-line text blocks. | `left`, `center`, `right`, or None; default None | `properties.multialignment` |
| Wrap | Checkbox | Enables automatic line wrapping within the text bounding box. | `true` or `false`; default `false` | `properties.wrap` |
| Linespacing | Number | Line spacing factor for multi-line text (multiples of font size). | Finite number `>= 0`; default `1.2` | `properties.linespacing` |
| Transform Rotates Text | Checkbox | Determines whether parent coordinate transformations rotate text geometry. | `true` or `false`; default `false` | `properties.transform_rotates_text` |

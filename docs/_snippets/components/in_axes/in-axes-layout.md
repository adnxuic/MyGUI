| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Bounds | Inset bounds editor | Placement rectangle `[left, bottom, width, height]` in parent Axes coordinates. | Normalized tuple `[0..1, 0..1, 0..1, 0..1]`; default `[0.55, 0.55, 0.4, 0.4]` | `properties.bounds` |
| Visible | Checkbox | Shows or hides the inset component and its canvas elements. | `true` or `false`; default `true` | `properties.visible` |
| Zorder | Number | Stacking order of the inset Axes relative to parent Artists. | Finite number; default `5.0` | `properties.zorder` |

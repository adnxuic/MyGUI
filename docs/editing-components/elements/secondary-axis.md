# Secondary Axis Component

The **Secondary Axis** Element displays a reversible unit view of its parent X
or Y dimension. It is created by Matplotlib's `Axes.secondary_xaxis()` or
`Axes.secondary_yaxis()` and never owns independent chart data, limits, scale,
aspect, or layout.

For creation, safe-formula validation, invalid-domain recovery, and placement
examples, see [Secondary Axis / Unit Transform](../../secondary-axis-component.md).

## General

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Requests that the child axis be shown. An invalid current parent domain temporarily overrides this to hidden without changing the saved request. | `true` or `false`; default `true` | `properties.visible` |

Orientation is selected at creation and is immutable. It is represented by the
component role `secondary_x_axis` or `secondary_y_axis`, not by an editable
property.

## Unit Transform

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Unit transform | Transform summary + Configure | Defines the forward parent-to-secondary mapping and its inverse. Presets cover identity, degrees↔radians, Celsius↔Fahrenheit, and frequency↔period. Affine mode stores finite non-zero `scale` and finite `offset`. Custom mode stores safe expressions using only `x` and the bounded math vocabulary. | Tagged transform spec; default `{"kind":"preset","name":"identity"}` | `properties.unit_transform` |

Every candidate must return real, finite, same-shape values, be strictly
monotonic, and pass both round trips at `rtol=1e-9`, `atol=1e-12` over samples
uniform in the current parent Axis scale space. Invalid input is rejected
atomically.

## Placement

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Placement | Placement summary + Configure | Places X orientation on `top`/`bottom`, or Y orientation on `left`/`right`; alternatively uses an Axes-fraction or data-coordinate value in the orthogonal direction. | Tagged placement spec; default top for X, right for Y | `properties.placement` |

Normalized placement is unique per parent/orientation. `top` equals Axes
fraction `1`, `bottom` equals `0`, `right` equals `1`, and `left` equals `0`.
Data-coordinate placement uses the parent `transData` transform.

## Label

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label | Text | Destination unit or axis description. | String; default empty | `properties.label` |

## Label details

The Label details section is collapsed by default.

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label pad | Number | Distance in points between label and axis. | Finite number; default `4.0` | `properties.label_pad` |
| Label rotation | Rotation editor | Label rotation in degrees. | Finite number; default `0.0` | `properties.label_rotation` |
| Label font | Font chooser | Complete safe font family, size, weight, style, stretch, variant, and color record. | Font spec; default sans-serif 10 pt, normal, black | `properties.label_font` |

## Scale & Ticks

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Ticker mode | Dropdown | `automatic` follows Matplotlib's function-scale defaults; `custom` installs the four saved ticker records before every draw. | `automatic`, `custom`; default `automatic` | `properties.ticker_mode` |
| Major locator | Locator dialog | Determines major tick positions in secondary units when custom mode is active. | Tagged Locator spec; default Automatic | `properties.major_locator` |
| Major formatter | Formatter dialog | Formats major labels in secondary units when custom mode is active. | Tagged Formatter spec; default Automatic | `properties.major_formatter` |
| Minor locator | Locator dialog | Determines minor tick positions in secondary units when custom mode is active. | Tagged Locator spec; default Automatic | `properties.minor_locator` |
| Minor formatter | Formatter dialog | Formats minor labels in secondary units when custom mode is active. | Tagged Formatter spec; default Automatic | `properties.minor_formatter` |

A Fixed Formatter is accepted only with a Fixed Locator of equal length.

## Tick Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Major ticks visible | Checkbox | Shows major tick marks. | `true`; default `true` | `properties.major_ticks_visible` |
| Major labels visible | Checkbox | Shows major tick labels. | `true`; default `true` | `properties.major_labels_visible` |
| Minor ticks visible | Checkbox | Shows minor tick marks. | `false`; default `false` | `properties.minor_ticks_visible` |
| Minor labels visible | Checkbox | Shows minor tick labels. | `false`; default `false` | `properties.minor_labels_visible` |
| Direction | Dropdown | Direction of major and minor ticks. | `in`, `out`, `inout`; default `out` | `properties.tick_direction` |
| Length | Number | Tick length in points. | Finite `>= 0`; default `3.5` | `properties.tick_length` |
| Width | Number | Tick width in points. | Finite `>= 0`; default `0.8` | `properties.tick_width` |
| Color | Color choice | Tick-line color. | Hex color; default `#000000` | `properties.tick_color` |
| Pad | Number | Tick-label padding in points. | Finite number; default `3.5` | `properties.tick_pad` |
| Rotation | Rotation editor | Tick-label rotation in degrees. | Finite number; default `0.0` | `properties.tick_rotation` |
| Tick font | Font chooser | Complete safe font record for major/minor labels. | Font spec; default sans-serif 10 pt, black | `properties.tick_font` |
| Offset visible | Checkbox | Shows scientific-notation offset text. | `true`; default `true` | `properties.offset_visible` |
| Offset font | Font chooser | Complete safe font record for offset text. | Font spec; default sans-serif 10 pt, black | `properties.offset_font` |
| Remove overlapping locations | Checkbox | Lets the Axis remove minor locations that coincide with major locations. | `true`; default `true` | `properties.remove_overlapping_locs` |

## Spine

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows the spine associated with the placement. | `true`; default `true` | `properties.spine_visible` |
| Color | Color choice | Spine stroke color. | Hex color; default `#000000` | `properties.spine_color` |
| Line width | Number | Spine stroke width in points. | Finite `>= 0`; default `0.8` | `properties.spine_linewidth` |
| Line style | Line-style editor | Spine line pattern. | Line-style spec; default solid | `properties.spine_linestyle` |
| Bounds | Optional range | Optional lower/upper extent in secondary-axis units; unset restores automatic bounds. | Two finite numbers or `null`; default `null` | `properties.spine_bounds` |
| Alpha | Optional number | Spine opacity. | `0`–`1` or `null`; default `null` | `properties.spine_alpha` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Z-order | Number | Drawing order of the Matplotlib child axis. | Finite number; default `0.0` | `properties.zorder` |

## Project record and lifecycle

Schema v23 persists `kind: "secondary_axis"`, role `secondary_x_axis` or
`secondary_y_axis`, exact selector `{"object_id": component_id}`, complete
properties, and `data: {}` under an ordinary Axes. The Matplotlib child lives
in `parent.child_axes`, not `Figure.axes`. If pan, zoom, autoscale, or a parent
scale change makes the transform invalid, only the child axis hides, one
warning is issued for that invalid transition, and it automatically returns
when the parent domain becomes valid.

## Referenced Matplotlib 3.9.0 URLs

- [Axes.secondary_xaxis](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.secondary_xaxis.html)
- [Axes.secondary_yaxis](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.secondary_yaxis.html)
- [Secondary Axis example](https://matplotlib.org/3.9.0/gallery/subplots_axes_and_figures/secondary_axis.html)
- [Ticker API](https://matplotlib.org/3.9.0/api/ticker_api.html)
- [Axis API](https://matplotlib.org/3.9.0/api/axis_api.html)

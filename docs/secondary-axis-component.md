# Secondary Axis / Unit Transform

Secondary Axis adds a second set of tick labels whose values are a reversible
unit mapping of one parent Axes dimension. It uses Matplotlib 3.9.0
[`Axes.secondary_xaxis`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.secondary_xaxis.html)
or [`Axes.secondary_yaxis`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.secondary_yaxis.html).
It is not `twinx`/`twiny`: it cannot contain plots, own data, set independent
limits, or choose an independent scale. Pan, zoom, autoscale, and parent scale
changes remain owned by the parent Axes.

## Create

Select an ordinary Axes and choose **Add Element → Secondary Axis**. Choose:

- **Orientation**: X creates a top/bottom axis; Y creates a left/right axis.
- **Unit transform**: a preset, an affine mapping, or custom forward/inverse
  formulas using the variable `x`.
- **Placement**: an edge, an Axes-fraction position, or a data-coordinate
  position in the orthogonal direction.
- **Label**: optional destination unit text.

Orientation is fixed after creation. Multiple Secondary Axes are allowed, but
one parent/orientation cannot reuse the same normalized placement. For example,
top and Axes fraction `1` are the same X-axis placement.

## Unit transforms

Presets include Identity, degrees↔radians, Celsius↔Fahrenheit, and
frequency↔period. Affine mappings use `forward = scale*x + offset` and require
a finite non-zero scale. Custom formulas use the same bounded AST interpreter
as MyGUI mathematical expressions; Python statements, attribute access other
than the allowed NumPy math names, imports, callables, and `eval` are not used.

Before creation or editing, MyGUI samples the visible parent domain uniformly
in the parent Axis scale space and
requires real, same-shape, finite, strictly monotonic output. Both round trips
must agree with `rtol=1e-9` and `atol=1e-12`. A formula that is initially valid
may become undefined after pan/zoom (for example `1/x` across zero). In that
case the Secondary Axis temporarily stops drawing, emits one warning for that
invalid transition, and automatically returns when the parent domain becomes
valid; the parent limits are never constrained.

The persisted transform values are:

```json
{"kind": "preset", "name": "celsius_to_fahrenheit"}
{"kind": "affine", "scale": 1.8, "offset": 32.0}
{"kind": "custom", "forward": "x * 9 / 5 + 32", "inverse": "(x - 32) * 5 / 9"}
```

Placement values are:

```json
{"kind": "edge", "side": "top"}
{"kind": "position", "coordinate_system": "axes_fraction", "value": 1.15}
{"kind": "position", "coordinate_system": "data", "value": 0.0}
```

Data-coordinate placement passes the parent `transData` to Matplotlib's
`transform=` argument. It changes only where the child axis is drawn.

## Inspector settings

| Section | Settings |
| --- | --- |
| General | requested visibility |
| Unit Transform | preset, affine, or safe forward/inverse formulas |
| Placement | edge, Axes fraction, or data coordinate |
| Label | text, padding, rotation, and full font specification |
| Scale & Ticks | automatic/custom mode; major/minor Locator and Formatter specs |
| Tick Appearance | major/minor tick and label visibility, direction, length, width, color, padding, rotation, fonts, offset text, overlap policy |
| Spine | visibility, color, width, line style, optional bounds, alpha |
| Advanced | z-order |

Automatic ticker mode keeps Matplotlib's function-scale defaults as the parent
scale changes. Custom mode reapplies the persisted Locator/Formatter records.
Secondary Axis deliberately has no data, limits, scale, autoscale, aspect,
legend, or chart sections.

## Persistence and deletion

Schema v23 stores one leaf component under the owner Axes:

```json
{
  "kind": "secondary_axis",
  "role": "secondary_x_axis",
  "selector": {"object_id": "stable-component-id"},
  "properties": {},
  "data": {}
}
```

The Matplotlib child Axes is in `parent.child_axes`, not `Figure.axes`, and is
never registered as an ordinary MyGUI Axes. Restore materializes it after its
parent and source components. Deleting the component removes only that child
axis; deleting the parent Axes removes it in the parent subtree transaction.

Matplotlib marks these two APIs experimental in 3.9.0. MyGUI therefore keeps
all construction and replacement inside `SecondaryAxisService`.

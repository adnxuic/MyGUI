# Reference Guides

Reference Guides add constant data-coordinate lines and bands to an ordinary
Axes. Use **Elements > Add Reference Line** or **Elements > Add Reference
Band** while the intended Axes is selected. The creation dialog collects only
the initial values; the resulting component is owned by the Component Registry
and edited through the shared Component Inspector.

Both guide types use a blended coordinate system. For a vertical guide, the X
value or bounds use data coordinates while the start and end of the orthogonal
span use Axes fractions. A horizontal guide uses data coordinates on Y and Axes
fractions on X. Panning, zooming, and linear or logarithmic scales therefore
move the data-coordinate dimension normally while the orthogonal span remains
fixed relative to the Axes rectangle.

A Reference Line owns one Matplotlib
[`LineCollection`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection).
A Reference Band owns one
[`PolyCollection`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.PolyCollection).
Both are attached with `autolim=False`, so creating, editing, restoring, or
showing a guide does not expand `dataLim`, change the current X/Y limits, or
make the guide a data source for `relim` and autoscale.

Reference Line and Reference Band appear together under **Reference Guides**
in the Components tree. A non-empty label is used as the preview. Without a
label, the preview shows the constant geometry, such as `x = 2.5` or
`-0.2 ≤ y ≤ 0.2`. Selection, deletion, Undo/Redo, save/open, and Axes-subtree
operations use the standard component lifecycle and preserve stable component
IDs.

## Reference Line parameters

| Inspector field | Control | Meaning | Values and default | Persisted key |
| --- | --- | --- | --- | --- |
| Label | Text | Optional component, collection, and tree-preview label. | Text; default empty | `properties.label` |
| Visible | Checkbox | Shows or hides the collection through the Matplotlib [`Artist` visibility contract](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_visible). | `true` or `false`; default `true` | `properties.visible` |
| Orientation | Dropdown | Chooses which coordinate is constant. Vertical means `x = value`; horizontal means `y = value`. | `vertical` or `horizontal`; default `vertical` | `properties.orientation` |
| Value | Number | Constant X or Y data coordinate selected by Orientation. | Finite number; default `0` | `properties.value` |
| Color | Color choice | Line color using the Matplotlib [color contract](https://matplotlib.org/3.9.0/users/explain/colors/colors.html). | Valid color; stored default `#000000`; the creation input starts from the active Figure style | `properties.color` |
| Line Width | Number | Collection line width through [`Collection.set_linewidth`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linewidth). | Finite number `>= 0`; stored default `0.8`; the creation input starts from the active Figure style | `properties.linewidth` |
| Line Style | Line-style choice | Collection dash style through [`Collection.set_linestyle`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linestyle). | `-`, `--`, `-.`, `:`, or `None`; default `-` | `properties.linestyle` |
| Alpha | Number | Collection opacity through [`Artist.set_alpha`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html). | Finite `0` to `1`; default `1` | `properties.alpha` |
| Span Start | Number | Start of the orthogonal span in Axes-fraction coordinates. | Finite `0` to `1`; default `0`; must be less than Span End | `properties.span_start` |
| Span End | Number | End of the orthogonal span in Axes-fraction coordinates. | Finite `0` to `1`; default `1`; must be greater than Span Start | `properties.span_end` |
| Z-order | Number | Draw order through [`Artist.set_zorder`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html). | Finite number; default `2` | `properties.zorder` |
| Clip On | Checkbox | Enables Axes clipping through [`Artist.set_clip_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html). | `true` or `false`; default `true` | `properties.clip_on` |

## Reference Band parameters

| Inspector field | Control | Meaning | Values and default | Persisted key |
| --- | --- | --- | --- | --- |
| Label | Text | Optional component, collection, and tree-preview label. | Text; default empty | `properties.label` |
| Visible | Checkbox | Shows or hides the collection through the Matplotlib [`Artist` visibility contract](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_visible). | `true` or `false`; default `true` | `properties.visible` |
| Orientation | Dropdown | Chooses the bounded data dimension. Vertical bounds X; horizontal bounds Y. | `vertical` or `horizontal`; default `vertical` | `properties.orientation` |
| Lower | Number | Lower data-coordinate boundary. | Finite number; default `0`; must be less than Upper | `properties.lower` |
| Upper | Number | Upper data-coordinate boundary. | Finite number; default `1`; must be greater than Lower | `properties.upper` |
| Face Color | Color choice | Band fill using the Matplotlib [color contract](https://matplotlib.org/3.9.0/users/explain/colors/colors.html). | Valid color; stored default `#B0B0B0`; the creation input starts from the active Figure style | `properties.facecolor` |
| Alpha | Number | Fill and border opacity through [`Artist.set_alpha`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html). | Finite `0` to `1`; default `0.25` | `properties.alpha` |
| Edge Color | Color choice | Polygon border using the Matplotlib [color contract](https://matplotlib.org/3.9.0/users/explain/colors/colors.html). | Valid color; stored default `#000000`; the creation input starts from the active Figure style | `properties.edgecolor` |
| Line Width | Number | Border width through [`Collection.set_linewidth`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linewidth). | Finite number `>= 0`; stored default `0.8`; the creation input starts from the active Figure style | `properties.linewidth` |
| Line Style | Line-style choice | Border dash style through [`Collection.set_linestyle`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linestyle). | `-`, `--`, `-.`, `:`, or `None`; default `-` | `properties.linestyle` |
| Span Start | Number | Start of the orthogonal span in Axes-fraction coordinates. | Finite `0` to `1`; default `0`; must be less than Span End | `properties.span_start` |
| Span End | Number | End of the orthogonal span in Axes-fraction coordinates. | Finite `0` to `1`; default `1`; must be greater than Span Start | `properties.span_end` |
| Z-order | Number | Draw order through [`Artist.set_zorder`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html). | Finite number; default `1.5` | `properties.zorder` |
| Clip On | Checkbox | Enables Axes clipping through [`Artist.set_clip_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html). | `true` or `false`; default `true` | `properties.clip_on` |

## Project records

Schema v14 stores both components with `kind: "reference_guide"` and an
ordinary `axes/axes` parent. Reference Line uses `role: "reference_line"`;
Reference Band uses `role: "reference_band"`. Both use exactly
`selector: {"object_id": component_id}` and an empty `data` object. Unknown
properties, non-finite numbers, invalid orientation/span/bounds, non-empty
data, a wrong selector, or a non-Axes parent are rejected before project state
is published.

## Referenced Matplotlib 3.9.0 URLs

- [LineCollection](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection)
- [PolyCollection](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.PolyCollection)
- [Axes.get_xaxis_transform](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_xaxis_transform.html)
- [Axes.get_yaxis_transform](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_yaxis_transform.html)
- [Artist visibility](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_visible)
- [Specifying colors](https://matplotlib.org/3.9.0/users/explain/colors/colors.html)
- [Collection line width](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linewidth)
- [Collection line style](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linestyle)
- [Artist alpha](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html)
- [Artist z-order](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html)
- [Artist clipping](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html)

# Reference Marks Component

Reference Marks draws reflection positions as short vertical marks inside an
ordinary Axes. Use **Elements > Reflection Positions**, enter an optional
comma- or space-separated sequence, optionally choose one Number column from
the current project, and apply the dialog. Empty sequences are valid;
duplicates and input order are preserved. Effective X coordinates are the
manual `positions` followed by the selected column values in row order, with
empty cells skipped. Changing the Table column refreshes the marks without a
nested Figure command. Invalid column values or references are rejected
atomically and keep the previous Artist.

Each component owns one `ComponentState`, one Controller, and one Matplotlib
[`LineCollection`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection),
regardless of the number of positions. X coordinates use data coordinates and
Y coordinates use Axes coordinates through
[`Axes.get_xaxis_transform`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_xaxis_transform.html).
Changing the X limits therefore moves or clips the marks with the data, while
changing the Y limits does not change their relative vertical placement.

The component appears in the Components tree as **Reflection Positions**, with
its label shown as a preview when present. Selection opens the shared
Component Inspector. Deletion uses the standard atomic component deletion
flow; Undo and Redo restore the stable component ID, ordered data, appearance,
selection, and one collection.

The optional FullProf `.prf` workflow in the **Main Plot + Residual** dialog
uses this same component. XRD Reflection Positions store `positions: []` and
bind `position_ref` to the imported `<source> Reflections/2Theta` column
instead of copying PRF numbers. XRD creation uses `baseline=0.0375` and
`height=0.025` so the marks occupy the center of the main Axes 10% lower-Y
reserve (`3.75%–6.25%` of Axes height). Ordinary Reflection Positions keep
`baseline=0.08` and `height=0.025` and do not change the owning Axes reserve.

## Parameters

| Inspector field | Control | Meaning | Values and default | Persisted key |
| --- | --- | --- | --- | --- |
| Label | Text | Optional display and tree-preview label; also supplies the collection label used by Matplotlib. | Text; default empty | `properties.label` |
| Visible | Checkbox | Shows or hides the complete collection through the Matplotlib [`Artist` visibility contract](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_visible). | `true` or `false`; default `true` | `properties.visible` |
| Baseline | Number | Lower Y position in normalized Axes coordinates. | Finite `0 <= baseline <= 1`; default `0.08` | `properties.baseline` |
| Height | Number | Mark height in normalized Axes coordinates. | Finite `0 < height <= 1`; default `0.025`; `baseline + height <= 1` | `properties.height` |
| Color | Color choice | Uniform Matplotlib [color](https://matplotlib.org/3.9.0/users/explain/colors/colors.html) for every mark. | Valid color; default from the active style's X major tick | `properties.color` |
| Line width | Number | Uniform collection line width through [`LineCollection.set_linewidth`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linewidth). | Finite number `>= 0`; default from the active style's X major tick width | `properties.linewidth` |
| Line style | Line-style choice | Uniform collection dash pattern through [`LineCollection.set_linestyle`](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linestyle). | `-`, `--`, `-.`, `:`, or `None`; default `-` | `properties.linestyle` |
| Alpha | Number | Uniform collection opacity through [`Artist.set_alpha`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html). | Finite `0` to `1`; default `1` | `properties.alpha` |
| Z order | Number | Draw order relative to other Artists through [`Artist.set_zorder`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html). | Finite number; default `2` | `properties.zorder` |
| Clip on | Checkbox | Enables Axes clipping through [`Artist.set_clip_on`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html). | `true` or `false`; default `true` | `properties.clip_on` |
| Positions | Sequence text plus Apply | Manual ordered reflection-position sequence. Combined with the Table column when present. | Comma- or space-separated finite numbers; default empty; duplicates allowed | `data.positions` |
| Table column | Nullable Number-column selector plus Apply | Optional current-project Number column appended after the manual positions. Deleting the column or Sheet removes this component through the existing deletion coordinator. | Current-project Number columns, or none; default none | `data.position_ref` |

## Project record

Schema v15 stores the component as
`kind: "reference_marks"`, `role: "reflection_positions"`, with
`selector: {"object_id": component_id}`. Its parent is an ordinary Axes. The
`data` object contains exactly `positions` and nullable `position_ref`; the
`properties` object contains exactly the ten fields listed above. Unknown
fields, non-finite positions, invalid or non-Number column references, invalid
geometry, and non-Axes parents are rejected before project state is
published.

## Referenced Matplotlib 3.9.0 URLs

- [LineCollection](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection)
- [Axes.get_xaxis_transform](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.get_xaxis_transform.html)
- [Artist visibility](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_visible)
- [Specifying colors](https://matplotlib.org/3.9.0/users/explain/colors/colors.html)
- [Collection line width](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linewidth)
- [Collection line style](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.Collection.set_linestyle)
- [Artist alpha](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_alpha.html)
- [Artist z-order](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_zorder.html)
- [Artist clipping](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.artist.Artist.set_clip_on.html)

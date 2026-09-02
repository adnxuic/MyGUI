# Error Bar Component

The **Error Bar** component draws one X/Y data series with symmetric or
asymmetric error magnitudes in either dimension. Magnitudes come from table
columns or per-component constants, align to the post-preprocessing row mask,
and are always absolute amounts in the rendered coordinate units.

Error Bar creation reuses the Line creation defaults (explicit input >
Components `NEXT_USE` > Axes palette/Figure style > Matplotlib 3.9 fallback);
`ecolor` defaults to the main color while the remaining error-dimension values
come from the current Figure style probe. The creation dialog groups Data,
Line, Marker, Error Bars, and Advanced controls; error color and `barsabove`
are explicit inputs rather than fixed values. The Data section edits hold a full
draft; **Apply** commits X/Y, preprocessing, and both error specs as one
atomic change (one Undo record), and **Reset** restores the last committed
state without history.

## Data

--8<-- "_snippets/components/charts/data-source.md"

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| X Error | Error spec input | Closed X-dimension error specification: none, constant minus/plus, one symmetric column, or two asymmetric columns. Mode switches never downgrade an incomplete draft to none; Apply stays blocked until the draft is complete. | Tagged spec; default `none` | `data.xerr` |
| Y Error | Error spec input | Closed Y-dimension error specification: none, constant minus/plus, one symmetric column, or two asymmetric columns. | Tagged spec; default `none` | `data.yerr` |

Error columns must be numeric, row-aligned with the X/Y source, and contain
finite non-negative values on drawable rows. Rows removed by X/Y preprocessing
neither draw nor validate their error values; any invalid magnitude on a
drawable row rejects the whole change and keeps the previous state.

## Line

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Label | Text | Legend entry label for the Error Bar. | Text; default empty | `properties.label` |
| Color | Color choice | Data line color. | Hex color; default `#1f77b4` | `properties.color` |
| Linestyle | Line-style choice | Data line dash pattern. | Preset or dash tuple; default `solid` | `properties.linestyle` |
| Linewidth | Number | Data line thickness in points. | Finite number `>= 0`; default `1.5` | `properties.linewidth` |
| Visible | Checkbox | Shows or hides every Error Bar artist. | `true` or `false`; default `true` | `properties.visible` |

## Marker

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Marker | Marker choice | Marker symbol drawn by the data line. | Marker spec; default `{'kind': 'symbol', 'value': 'None'}` | `properties.marker` |
| Markersize | Number | Marker size in points. | Finite number `>= 0`; default `6.0` | `properties.markersize` |

## Error Bars

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Ecolor | Color choice | Color of error bars and caps. | Hex color; defaults to the main color | `properties.ecolor` |

## Advanced

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Drawstyle | Dropdown | Data line step-drawing style. | `default`, `steps`, `steps-pre`, `steps-mid`, `steps-post`; default `default` | `properties.drawstyle` |
| Antialiased | Checkbox | Antialiased rendering of the data line. | `true` or `false`; default `true` | `properties.antialiased` |
| Markerfacecolor | Color choice | Marker fill color. | Hex color; default `#1f77b4` | `properties.markerfacecolor` |
| Markeredgecolor | Color choice | Marker outline stroke color. | Hex color; default `#1f77b4` | `properties.markeredgecolor` |
| Markeredgewidth | Number | Data-line marker edge width in points; independent from Cap thickness. | Finite number `>= 0`; default `1.0` | `properties.markeredgewidth` |
| Markerfacecoloralt | Optional color | Alternate marker fill used together with `fillstyle` holes. | Color or `none`; default `none` | `properties.markerfacecoloralt` |
| Fillstyle | Dropdown | Marker fill style. | `full`, `left`, `right`, `bottom`, `top`, `none`; default `full` | `properties.fillstyle` |
| Elinewidth | Number | Error bar stroke thickness in points. | Finite number `>= 0`; default `1.5` | `properties.elinewidth` |
| Capsize | Number | Cap length in points. Caps stay present at zero size so structure never changes. | Finite number `>= 0`; default `0.0` | `properties.capsize` |
| Capthick | Number | Cap stroke thickness in points; independent from Marker edge width. | Finite number `>= 0`; default `1.0` | `properties.capthick` |
| Error linestyle | Line-style choice | Dash pattern of the error-bar line collections. | Preset or dash tuple; default `solid` | `properties.error_linestyle` |
| Error capstyle | Dropdown | Cap style of the error-bar line collection segments. | Style default, `butt`, `projecting`, `round`; default Style default | `properties.error_capstyle` |
| Error antialiased | Checkbox | Antialiased rendering of the error collections and caps. | `true` or `false`; default `true` | `properties.error_antialiased` |
| Error every | Start/step numbers | Draws error bars only on `data[start::step]`; autoscale folds exactly the drawn segments. | `start >= 0`, `step >= 1`; default every point | `properties.errorevery` |
| Barsabove | Checkbox | Draws error bars above the data line markers. | `true` or `false`; default `false` | `properties.barsabove` |
| Lolims | Checkbox | Draw upward limit arrows for Y errors. | `true` or `false`; default `false` | `properties.lolims` |
| Uplims | Checkbox | Draw downward limit arrows for Y errors. | `true` or `false`; default `false` | `properties.uplims` |
| Xlolims | Checkbox | Draw rightward limit arrows for X errors. | `true` or `false`; default `false` | `properties.xlolims` |
| Xuplims | Checkbox | Draw leftward limit arrows for X errors. | `true` or `false`; default `false` | `properties.xuplims` |
| Alpha | Number | Opacity applied to the data line, caps, and error bars. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Base stacking order; error bars draw at this level and the line offsets by `0.1`. | Finite number; default `2.0` | `properties.zorder` |
| Clip On | Checkbox | Clips all Error Bar artists to the Axes bounding box. | `true` or `false`; default `true` | `properties.clip_on` |

## Project record

Schema v21 introduced the current Error Bar record as `kind: "errorbar"`, `role: "error_bar"`, with
`selector: {"object_id": component_id}` under its parent Axes and exactly the
five data fields `x_ref`, `y_ref`, `xerr`, `yerr`, and `preprocess`. The v20
predecessor property set migrates by injecting the deterministic extension
defaults. Current template files require `mygui-template` schema v6.

## Referenced Matplotlib 3.9.0 URLs

- [Axes errorbar](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.errorbar.html)
- [ErrorbarContainer API](https://matplotlib.org/3.9.0/api/container_api.html#matplotlib.container.ErrorbarContainer)
- [Line2D API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html)
- [LineCollection API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.LineCollection)
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html)
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html)
- [Errorbar limits gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/errorbar_limits_simple.html)

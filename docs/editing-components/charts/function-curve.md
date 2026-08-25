# Function Curve Component

The **Function Curve** component evaluates and renders a continuous analytic mathematical expression $y = f(x)$ over a specified evaluation domain $[x_\text{start}, x_\text{stop}]$ using dense sampling.

For detailed expression syntax and available functions, see [Function Curve](../../function-curve.md) and [Multi-Series Chart Creation](../../multi-series-charts.md).

## Definition and range

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Expression | Math expression editor | Analytic formula $f(x)$ evaluated across the domain (e.g. `sin(x) * exp(-x/5)`). | Math string; default `sin(x)` | `data.expression` |
| X Start | Number | Lower bound of the evaluation range in X data coordinates. | Finite number; default `0.0` | `data.x_start` |
| X Stop | Number | Upper bound of the evaluation range in X data coordinates. | Finite number; default `10.0` | `data.x_stop` |
| Samples | Number | Number of uniformly spaced sampling points along the evaluation interval. | Integer `>= 2`; default `200` | `data.samples` |

## Appearance

--8<-- "_snippets/components/charts/line-appearance.md"

## Project record

Schema v15 persists Function Curve as `kind: "line"`, `role: "function_curve"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object contains `expression`, `x_start`, `x_stop`, and `samples`.

## Referenced Matplotlib 3.9.0 URLs

- [Line2D API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html)
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html)
- [Step demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/step_demo.html)
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html)
- [Marker fillstyle reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html)
- [Markevery demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/markevery_demo.html)
- [Cap and join styles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

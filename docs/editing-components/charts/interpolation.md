# Interpolation Component

The **Interpolation** component computes and displays smooth interpolated curves (linear, cubic spline, Akima, PCHIP, nearest) through table data coordinates.

For details on interpolation algorithms and smoothing parameters, see [Interpolation](../../interpolation.md) and [Multi-Series Chart Creation](../../multi-series-charts.md).

## Data source

--8<-- "_snippets/components/charts/data-source.md"

## Interpolation parameters

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Method | Dropdown | Interpolation algorithm: `linear`, `cubic`, `akima`, `pchip`, `nearest`, `spline`. | `linear`, `cubic`, `akima`, `pchip`, `nearest`, `spline`; default `cubic` | `data.method` |
| Degree (k) | Number | Spline polynomial degree $k$ (1 to 5). | Integer `1 <= k <= 5`; default `3` | `data.k` |
| Samples | Number | Number of evaluation sample points along the interpolated curve. | Integer `>= 2`; default `300` | `data.samples` |
| Smoothing (lam) | Number | Regularization smoothing parameter $\lambda$ for smoothing splines. | Finite `>= 0`; default `0.0` | `data.lam` |
| Auto Smoothing | Checkbox | Enables automatic determination of spline smoothing parameter. | `true` or `false`; default `false` | `data.lam_auto` |

## Appearance

--8<-- "_snippets/components/charts/line-appearance.md"

## Project record

Schema v15 persists Interpolation as `kind: "line"`, `role: "interpolation"`, with `selector: {"object_id": component_id}` under its parent Axes.

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

# Plot Component

The **Plot** component represents a data-backed line series connecting discrete data points from the project table. It supports mathematical expression preprocessing, straight or stepped segments, extensive marker customizations, subsampling via `markevery`, and full export styling.

For high-level guides on chart creation and preprocessing, see [Multi-Series Chart Creation](../../multi-series-charts.md), [Data Preprocessing](../../data-preprocessing.md), and [Table Data](../../table-data.md).

## Data source

--8<-- "_snippets/components/charts/data-source.md"

## Appearance

--8<-- "_snippets/components/charts/line-appearance.md"

## Project record

Schema v15 persists Plot as `kind: "line"`, `role: "data_plot"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object contains `x_ref`, `y_ref`, and `preprocess`.

## Referenced Matplotlib 3.9.0 URLs

- [Axes plot](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.plot.html)
- [Line2D API](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.lines.Line2D.html)
- [Linestyles gallery](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/linestyles.html)
- [Step demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/step_demo.html)
- [Markers API](https://matplotlib.org/3.9.0/api/markers_api.html)
- [Marker fillstyle reference](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/marker_fillstyle_reference.html)
- [Markevery demo](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/markevery_demo.html)
- [Cap and join styles](https://matplotlib.org/3.9.0/gallery/lines_bars_and_markers/joinstyle.html)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

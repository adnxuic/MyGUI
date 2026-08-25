# Line Component

The **Line** component represents a generic 2D polyline defined by raw sequence coordinate data `(x, y)`.

## Raw X/Y data

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| X Data | Sequence editor | Explicit sequence of X data coordinates. | List of finite numbers; default empty | `data.x` |
| Y Data | Sequence editor | Explicit sequence of Y data coordinates. | List of finite numbers; default empty | `data.y` |

## Appearance

--8<-- "_snippets/components/charts/line-appearance.md"

## Project record

Schema v15 persists Line as `kind: "line"`, `role: "line"`, with `selector: {"object_id": component_id}` under its parent Axes.

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

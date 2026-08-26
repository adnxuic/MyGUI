# Pseudocolor Component

The **Pseudocolor** component draws a table-driven 2D scalar field with Matplotlib [`Axes.pcolormesh`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html) as a `QuadMesh`. It is `kind: "field_2d"` with `role: "pseudocolor"`.

X, Y, and Z must be numeric columns from one worksheet. MyGUI sorts unique X and Y centers and fills `Z[y_index, x_index]`. Duplicate coordinates are rejected. The component does not consume the Axes color cycle. Create a [Colorbar](../../colorbar-component.md) separately when a color scale is required.

## Data source

--8<-- "_snippets/components/charts/field-2d-data.md"

## Color mapping

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Colormap | Color map editor | Closed colormap name, tagged `NormSpec`, and optional bad/under/over colors. See [colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html) and [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize). | `ColorMapSpec`; default `viridis` with linear norm | `properties.colormap` |

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the QuadMesh. | `true` or `false`; default `true` | `properties.visible` |
| Alpha | Number | Opacity from 0 to 1, or None to inherit. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order relative to other Axes artists. | Finite number; default `1.0` | `properties.zorder` |
| Shading | Dropdown | QuadMesh shading mode. See [`pcolormesh`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html). | `auto`, `flat`, `nearest`, `gouraud`; default `auto` | `properties.shading` |
| Edgecolor | Grid edge editor | Mesh edge mode: none, face color, or an explicit color. See [QuadMesh](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.QuadMesh). | `{"kind": "none"}`, `{"kind": "face"}`, or `{"kind": "color", "value": ...}`; default none | `properties.edgecolor` |
| Linewidth | Number | Mesh edge width in points when edges are drawn. | Finite number `>= 0`; default `0.0` | `properties.linewidth` |
| Antialiased | Checkbox | Enables antialiased mesh edges. | `true` or `false`; default `false` | `properties.antialiased` |

## Export

--8<-- "_snippets/components/charts/field-2d-export.md"

## Project record

Schema v16 persists Pseudocolor as `kind: "field_2d"`, `role: "pseudocolor"`, with `selector: {"object_id": component_id}` under its parent Axes. `data` is exactly `x_ref`, `y_ref`, and `z_ref`.

## Referenced Matplotlib 3.9.0 URLs

- [Axes pcolormesh](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html)
- [QuadMesh API](https://matplotlib.org/3.9.0/api/collections_api.html#matplotlib.collections.QuadMesh)
- [Colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html)
- [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
- [Artist rasterized](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_rasterized)

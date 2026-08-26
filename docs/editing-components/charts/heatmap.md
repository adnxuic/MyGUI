# Heatmap Component

The **Heatmap** component draws a regular 2D scalar field with Matplotlib [`Axes.imshow`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html) as an `AxesImage`. It is `kind: "field_2d"` with `role: "heatmap"`.

X and Y centers must be equally spaced (`rtol=1e-7`, `atol=1e-12*max(1, abs(step))`). A single-point axis uses ±0.5 bounds. Extent is derived from those centers with `origin="lower"`. Axes aspect remains an Axes property. The component does not consume the Axes color cycle. Create a [Colorbar](../../colorbar-component.md) separately when a color scale is required.

## Data source

--8<-- "_snippets/components/charts/field-2d-data.md"

## Color mapping

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Colormap | Color map editor | Closed colormap name, tagged `NormSpec`, and optional bad/under/over colors. See [colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html) and [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize). | `ColorMapSpec`; default from Figure style `image.cmap` | `properties.colormap` |

## Appearance

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Visible | Checkbox | Shows or hides the AxesImage. | `true` or `false`; default `true` | `properties.visible` |
| Alpha | Number | Opacity from 0 to 1, or None to inherit. | Finite `0 <= alpha <= 1` or None; default None | `properties.alpha` |
| Zorder | Number | Stacking order relative to other Axes artists. | Finite number; default `1.0` | `properties.zorder` |
| Interpolation | Dropdown | Image resampling filter. See [interpolation methods](https://matplotlib.org/3.9.0/gallery/images_contours_and_fields/interpolation_methods.html) and [`imshow`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html). | Closed Matplotlib 3.9 catalog; default from Figure style `image.interpolation` | `properties.interpolation` |
| Interpolation Stage | Dropdown | Whether interpolation runs on data values or RGBA. See [AxesImage](https://matplotlib.org/3.9.0/api/image_api.html#matplotlib.image.AxesImage). | `data` or `rgba`; default `data` | `properties.interpolation_stage` |
| Resample | Checkbox | Enables resampling when the image is scaled. | `true` or `false`; default `true` | `properties.resample` |
| Filternorm | Checkbox | Normalizes interpolation filter weights. | `true` or `false`; default `true` | `properties.filternorm` |
| Filterrad | Number | Interpolation filter radius in pixels. | Finite number `>= 0`; default `4.0` | `properties.filterrad` |

## Export

--8<-- "_snippets/components/charts/field-2d-export.md"

## Project record

Schema v16 persists Heatmap as `kind: "field_2d"`, `role: "heatmap"`, with `selector: {"object_id": component_id}` under its parent Axes. `data` is exactly `x_ref`, `y_ref`, and `z_ref`.

## Referenced Matplotlib 3.9.0 URLs

- [Axes imshow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html)
- [AxesImage API](https://matplotlib.org/3.9.0/api/image_api.html#matplotlib.image.AxesImage)
- [Interpolation methods](https://matplotlib.org/3.9.0/gallery/images_contours_and_fields/interpolation_methods.html)
- [Colormaps](https://matplotlib.org/3.9.0/users/explain/colors/colormaps.html)
- [Normalize](https://matplotlib.org/3.9.0/api/colors_api.html#matplotlib.colors.Normalize)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)
- [Artist rasterized](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_rasterized)

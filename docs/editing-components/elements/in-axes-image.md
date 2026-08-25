# Image Inset Component

The **Image Inset** component embeds a raster bitmap image (PNG, JPEG, WebP, SVG) inside a dedicated child Axes located within the parent coordinate space.

For high-level guides on in-axes overlays, see [In-Axes Elements](../../in-axes.md).

## Layout

--8<-- "_snippets/components/in_axes/in-axes-layout.md"

## Frame

--8<-- "_snippets/components/in_axes/in-axes-frame.md"

## Image

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Filename | File chooser | Original image file name. | String; default empty | `data.filename` |
| MIME Type | Read-only text | MIME type of embedded image data (e.g. `image/png`). | MIME string; default empty | `data.mime_type` |
| Payload Base64 | Read-only text | Base64 encoded binary payload of the embedded image file. | Base64 string; default empty | `data.payload_base64` |

## Display

| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| Opacity | Number | Image rendering opacity from 0 (transparent) to 1 (opaque). | Finite `0.0 <= opacity <= 1.0`; default `1.0` | `properties.opacity` |
| Fit Mode | Dropdown | Image aspect fitting mode inside the inset box: `contain`, `cover`, `fill`, `none`. | `contain`, `cover`, `fill`, `none`; default `contain` | `properties.fit_mode` |
| Interpolation | Dropdown | Matplotlib pixel resample interpolation filter: `nearest`, `bilinear`, `bicubic`, `antialiased`. | Interpolation filter; default `antialiased` | `properties.interpolation` |
| Origin | Dropdown | Pixel array origin placement: `upper` (top-left) or `lower` (bottom-left). | `upper` or `lower`; default `upper` | `properties.origin` |
| Extent | Range tuple | Image extent boundaries `[left, right, bottom, top]` in data coordinates. | Tuple or None; default None | `properties.extent` |
| Resample | Checkbox | Enables image resampling filter when scaling. | `true` or `false`; default `true` | `properties.resample` |
| Filternorm | Checkbox | Normalizes antialiased filter kernel values. | `true` or `false`; default `true` | `properties.filternorm` |
| Filterrad | Number | Radius factor for resampling filter kernels. | Positive number; default `4.0` | `properties.filterrad` |
| Interpolation Stage | Dropdown | Rendering pipeline stage at which interpolation is applied: `data` or `rgba`. | `data` or `rgba`; default `data` | `properties.interpolation_stage` |
| Image Visible | Checkbox | Shows or hides the embedded AxesImage artist. | `true` or `false`; default `true` | `properties.image_visible` |
| Image Zorder | Number | Stacking order of the AxesImage artist inside the inset Axes. | Finite number; default `1.0` | `properties.image_zorder` |
| Image Clip On | Checkbox | Clips image rendering to inset Axes bounding box. | `true` or `false`; default `true` | `properties.image_clip_on` |
| Image Rasterized | Checkbox | Forces raster rendering in vector exports. | `true` or `false`; default `false` | `properties.image_rasterized` |
| Image In Layout | Checkbox | Includes image artist in layout calculations. | `true` or `false`; default `true` | `properties.image_in_layout` |
| Image Snap | Dropdown | Pixel grid snapping behavior: auto (`None`), on (`True`), off (`False`). | `None`, `True`, `False`; default None | `properties.image_snap` |
| Image Gid | Text | SVG group identifier used in vector exports. | String or none; default none | `properties.image_gid` |
| Image Label | Text | Display label for the image artist. | Text; default empty | `properties.image_label` |
| Image Sketch Params | Triplet editor | Hand-drawn sketchy stroke effect: `(scale, length, randomness)`. | Positive tuple or None; default None | `properties.image_sketch_params` |
| Image Url | Text | Hyperlink URL embedded in SVG export. | Valid URL string or none; default none | `properties.image_url` |

## Project record

Schema v15 persists Image Inset as `kind: "in_axes"`, `role: "in_axes_image"`, with `selector: {"object_id": component_id}` under its parent Axes. The `data` object contains `filename`, `mime_type`, and `payload_base64`.

## Referenced Matplotlib 3.9.0 URLs

- [AxesImage API](https://matplotlib.org/3.9.0/api/image_api.html#matplotlib.image.AxesImage)
- [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params)
- [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap)

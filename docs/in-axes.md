# In-Axes Elements

in_axes adds a child Axes inside the currently selected main Axes. It is an Element of that parent, is selected and edited through the Components tree and Inspector, and does not participate in subplot numbering or Figure layout. The Elements toolbar action uses pictures/icons/element_images/in_axes.svg and opens a fresh creation dialog with two modes: Zoom and Image. The selected mode is fixed after creation.

## Zoom inset

A Zoom inset mirrors every visible Line and Scatter Component under its parent Axes. Mirrored artists are runtime derivatives: they are not registered as Components, do not enter legends, and do not advance the Axes color palette. Registry commits refresh their data, appearance, visibility, scale, and axis direction. Text and Legend Components are not mirrored. An empty Zoom inset is valid when the parent contains no visible supported charts.

## Image inset

An Image inset embeds the selected raster file's original bytes into the project. Moving or deleting the source file after creation therefore does not affect save/open. PNG, JPEG, BMP, and TIFF payloads are supported; the detected format must match the saved MIME type. EXIF orientation is applied when the image is decoded for display.

## Creation parameters

The creation dialog collects:

- Zoom mode: bounds [x, y, width, height] in normalized parent-Axes coordinates with positive width and height; the displayed X/Y data ranges; the child-Axes frame (facecolor, frameon, edgecolor, linewidth); tick visibility; region rectangle visibility and appearance; and connector line visibility and appearance.
- Image mode: the same bounds and frame values plus the selected image file, which is decoded and validated before creation.

## Inspector parameters

Select an inset in the Components tree to edit it. The Inspector exposes the complete parameter set below; the common child-Axes controls appear in every mode.

### Shared Layout and Frame

| Parameter | Meaning | Default |
| --- | --- | --- |
| Bounds (bounds) | The child-Axes rectangle as [x, y, width, height] in normalized parent-Axes coordinates; width and height must be positive. | [0.6, 0.6, 0.35, 0.35] |
| Visible (visible) | Shows or hides the child Axes. | On |
| Z-order (zorder) | Stacking order of the child Axes. | 5.0 |
| Face color (facecolor) | The child-Axes background color. | #ffffff |
| Frame on (frameon) | Draws the child-Axes frame. | On |
| Edge color (edgecolor) | The child-Axes frame outline color. | #000000 |
| Line width (linewidth) | The child-Axes frame outline width. | 0.8 |

### Zoom inset

| Parameter | Meaning | Default |
| --- | --- | --- |
| X limits (xlim) | The finite displayed X data range of the inset. | [0.0, 1.0] |
| Y limits (ylim) | The finite displayed Y data range of the inset. | [0.0, 1.0] |
| Ticks visible (ticks_visible) | Shows or hides both inset axes and their tick labels. | On |
| Region visible (region_visible) | Shows or hides the parent-Axes zoom rectangle. | On |
| Region color (region_color) | The zoom rectangle outline color. | #808080 |
| Region line style (region_linestyle) | The zoom rectangle outline pattern. | solid |
| Region line width (region_linewidth) | The zoom rectangle outline width. | 1.0 |
| Region alpha (region_alpha) | The zoom rectangle opacity from 0 to 1. | 0.5 |
| Region face color (region_facecolor) | The zoom rectangle fill color. | Transparent |
| Region fill (region_fill) | Fills the zoom rectangle with the face color. | Off |
| Region hatch (region_hatch) | The zoom rectangle fill pattern, or none. See the [hatch style reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html). | None |
| Region z-order (region_zorder) | Stacking order of the zoom rectangle. | 4.99 |
| Connectors (connectors) | The four connection lines between the parent rectangle and the inset corners. Each connector stores visible, color, line pattern, linewidth, alpha, and zorder. | Four visible gray connectors |

### Image inset

| Parameter | Meaning | Default |
| --- | --- | --- |
| Filename / MIME / payload (filename, mime_type, payload_base64) | The embedded image source. The Image section validates and replaces the embedded bytes in place. | The created payload |
| Opacity (opacity) | The image opacity from 0 to 1. | 1.0 |
| Fit mode (fit_mode) | contain preserves the image aspect ratio; stretch fills the child Axes. | contain |
| Interpolation (interpolation) | The resampling used when displaying the image: antialiased, nearest, bilinear, bicubic, spline16, spline36, hanning, hamming, hermite, kaiser, quadric, catrom, gaussian, bessel, mitchell, sinc, lanczos, blackman, or none. See the [interpolation comparison](https://matplotlib.org/3.9.0/gallery/images_contours_and_fields/interpolation_methods.html). | antialiased |
| Origin (origin) | Which image corner sits at the lower-left of the Axes: upper or lower. See [Axes.imshow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html). | upper |
| Extent (extent) | The data-coordinate rectangle [left, right, bottom, top] the image is drawn into; None uses the Axes view limits. | None |
| Resample (resample) | Applies the interpolation when the image is resized by the Axes. | On |
| Filter norm (filternorm) | Normalizes the interpolation kernel so it integrates to one. | On |
| Filter radius (filterrad) | The interpolation kernel radius in pixels. | 4.0 |
| Interpolation stage (interpolation_stage) | The processing stage where interpolation runs: data (before color mapping) or rgba (after). See [Axes.imshow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html). | data |
| Image visible (image_visible) | Shows or hides the image artist. | On |
| Image z-order (image_zorder) | Stacking order of the image artist. | 0.0 |
| Image clip on (image_clip_on) | Clips the image to the child-Axes boundaries. | On |
| Image rasterized (image_rasterized) | Renders the image as a bitmap in vector exports. | Off |
| Image in layout (image_in_layout) | Includes the image in tight-layout calculations. | On |
| Image snap (image_snap) | Pixel-grid alignment for the image: auto (None), on, or off. See [Artist snap](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_snap). | None |
| Image GID (image_gid) | SVG group id for exports. | None |
| Image label (image_label) | The artist label used for lookups. | Empty |
| Image sketch params (image_sketch_params) | (scale, length, randomness) hand-drawn effect, or None to disable. See [Artist sketch params](https://matplotlib.org/3.9.0/api/artist_api.html#matplotlib.artist.Artist.set_sketch_params). | None |
| Image URL (image_url) | Hyperlink attached to the image in SVG exports. | None |

## Persistence and deletion

Schema v15 persists both modes as `kind: "in_axes"` with roles
`in_axes_zoom` and `in_axes_image`. Their `parent_id` is the main Axes
component ID and their selector is `{"object_id": component_id}`. The child
Axes, locator, mirrored artists, image artist, zoom rectangle, and connectors
are runtime-only.

Both roles are removable. A single or same-role batch deletion uses the normal Component deletion transaction. Deleting the parent Axes removes its complete inset subtree. Failed creation or deletion restores the Registry, locator, artists, Inspector, selection, and emitted-event state together.

## Matplotlib reference

- [Axes.inset_axes](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.inset_axes.html): the child-Axes placement and layout values.
- [Axes.imshow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html): the Image inset display parameters.
- [Interpolation comparison](https://matplotlib.org/3.9.0/gallery/images_contours_and_fields/interpolation_methods.html): the supported image interpolation values.
- [Rectangle](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.Rectangle.html) and [ConnectionPatch](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.patches.ConnectionPatch.html): the zoom region rectangle and its connectors.
- [Hatch style reference](https://matplotlib.org/3.9.0/gallery/shapes_and_collections/hatch_style_reference.html): the zoom region fill pattern values.

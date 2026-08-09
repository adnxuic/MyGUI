# In-Axes Elements

`in_axes` adds a child Axes inside the currently selected main Axes. It is an
Element of that parent, is selected and edited through the Components tree and
Inspector, and does not participate in subplot numbering or Figure layout.
The Elements toolbar action uses `pictures/icons/element_images/in_axes.svg` and
opens a fresh creation dialog with two modes. The selected mode is fixed after
creation.

## Zoom inset

A Zoom inset mirrors every visible Line and Scatter Component under its parent
Axes. Mirrored artists are runtime derivatives: they are not registered as
Components, do not enter legends, and do not advance the Axes color palette.
Registry commits refresh their data, appearance, visibility, scale, and axis
direction. Text and Legend Components are not mirrored. An empty Zoom inset is
valid when the parent contains no visible supported charts.

Zoom parameters are:

- `bounds`: `[x, y, width, height]` in normalized parent-Axes coordinates;
  width and height must be positive.
- `xlim`, `ylim`: finite, non-degenerate displayed data ranges.
- `visible`, `zorder`: child-Axes visibility and stacking order.
- `facecolor`, `frameon`, `edgecolor`, `linewidth`: background and frame.
- `ticks_visible`: shows or hides both inset axes and their tick labels.
- `region_visible`: shows or hides the parent-Axes zoom rectangle.
- `connectors_visible`: shows or hides its automatically placed connection
  lines.
- `indicator_color`, `indicator_linestyle`, `indicator_linewidth`,
  `indicator_alpha`: indicator appearance; alpha is in `[0, 1]`.

## Image inset

An Image inset embeds the selected raster file's original bytes into the
project. Moving or deleting the source file after creation therefore does not
affect save/open. PNG, JPEG, BMP, and TIFF payloads are supported; the detected
format must match the saved MIME type. EXIF orientation is applied when the
image is decoded for display.

Image parameters are:

- `bounds`, `visible`, `zorder`, `facecolor`, `frameon`, `edgecolor`, and
  `linewidth`: the common child-Axes layout and frame values described above.
- `opacity`: image opacity in `[0, 1]`.
- `fit_mode`: `contain` preserves the image aspect ratio; `stretch` fills the
  child Axes.
- `interpolation`: `nearest`, `bilinear`, or `bicubic`.
- `filename`: the original base filename used for display; directory paths are
  not persisted.
- `mime_type`: one of `image/png`, `image/jpeg`, `image/bmp`, or `image/tiff`.
- `payload_base64`: strict Base64 encoding of the original file bytes.

The Image Inspector's Image section can replace the embedded source. The new
file is decoded and validated before its payload and runtime artist are
committed.

## Persistence and deletion

Both modes use `ComponentKind.IN_AXES` with roles `IN_AXES_ZOOM` and
`IN_AXES_IMAGE`. Their `parent_id` is the main Axes Component ID and their
selector is `{"object_id": component_id}`. The child Axes, locator, mirrored
artists, image artist, zoom rectangle, and connectors are runtime-only.

Both roles are removable. A single or same-role batch deletion uses the normal
Component deletion transaction. Deleting the parent Axes removes its complete
inset subtree. Failed creation or deletion restores the Registry, locator,
artists, Inspector, selection, and emitted-event state together.

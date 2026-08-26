# Heatmap

Create a **Heatmap** chart from numeric X, Y, and Z columns on one
worksheet. Each row is one sample. MyGUI builds a sorted, equally spaced
X/Y grid and draws it with Matplotlib 3.9
[`Axes.imshow`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html)
using `origin="lower"` and an extent derived from cell centers.

## Create

1. Select an Axes.
2. Choose **Chart → Heatmap**.
3. Pick the same-sheet X, Y, and Z number columns.
4. Optionally set colormap, normalization, and interpolation.
5. Confirm. Style values such as `image.cmap` and `image.interpolation`
   are copied into the new component immediately.

X and Y centers must be equally spaced (`rtol=1e-7`,
`atol=1e-12*max(1, abs(step))`). A one-point axis uses ±0.5 bounds.
Uneven spacing, duplicate coordinates, cross-sheet references, and
non-numeric columns are rejected and roll back. Axes aspect stays on the
Axes component.

The chart does not consume the Axes color cycle and does not add a
Colorbar automatically. Add a [Colorbar](colorbar-component.md) afterwards
if needed. Grid size is limited by `MYGUI_MAX_FIELD_GRID_CELLS`. See
[Resource and Process Limits](resource-limits.md).

Inspector fields are listed in
[Heatmap Component](editing-components/charts/heatmap.md).

## Referenced Matplotlib 3.9.0 URLs

- [Axes imshow](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.imshow.html)

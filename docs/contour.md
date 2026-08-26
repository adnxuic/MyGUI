# Contour

Create a **Contour** chart from numeric X, Y, and Z columns on one
worksheet. Each row is one sample. MyGUI builds a sorted X/Y grid and
draws isolines and/or filled regions with Matplotlib 3.9
[`Axes.contour`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contour.html)
and [`Axes.contourf`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contourf.html).

## Create

1. Select an Axes.
2. Choose **Chart → Contour**.
3. Pick the same-sheet X, Y, and Z number columns.
4. Optionally set colormap, levels, mode (`filled`, `lines`, or `overlay`),
   and labels.
5. Confirm. Style values such as `image.cmap` and
   `contour.negative_linestyle` are copied into the new component
   immediately.

A drawable contour needs at least a 2×2 grid; smaller inputs remain a
valid empty component. Duplicate coordinates, cross-sheet references, and
non-numeric columns are rejected and roll back. Labels default to off.
Filled mode with labels enabled creates a hidden auxiliary line set used
only to place labels.

The chart does not consume the Axes color cycle and does not add a
Colorbar automatically. Overlay mode uses the filled set as the Colorbar
source. Add a [Colorbar](colorbar-component.md) afterwards if needed.
Grid size is limited by `MYGUI_MAX_FIELD_GRID_CELLS`. See
[Resource and Process Limits](resource-limits.md).

Inspector fields are listed in
[Contour Component](editing-components/charts/contour.md).

## Referenced Matplotlib 3.9.0 URLs

- [Axes contour](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contour.html)
- [Axes contourf](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.contourf.html)

# Pseudocolor

Create a **Pseudocolor** chart from numeric X, Y, and Z columns on one
worksheet. Each row is one sample. MyGUI builds a sorted X/Y grid and a
masked `Z[y_index, x_index]` array, then draws it with Matplotlib 3.9
[`Axes.pcolormesh`](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html).

## Create

1. Select an Axes.
2. Choose **Chart → Pseudocolor**.
3. Pick the same-sheet X, Y, and Z number columns.
4. Optionally set colormap, normalization, shading, and mesh edges.
5. Confirm. Style values such as `image.cmap` are copied into the new
   component immediately.

Duplicate `(X, Y)` coordinates, cross-sheet references, and non-numeric
columns are rejected and roll back. Missing X/Y rows are skipped with one
yellow warning. Missing Z values are masked. Empty drawable data still
creates a valid component. The chart does not consume the Axes color cycle
and does not add a Colorbar automatically. Add a
[Colorbar](colorbar-component.md) afterwards if needed.

Grid size is limited by `MYGUI_MAX_FIELD_GRID_CELLS` (default 2,000,000,
hard cap 10,000,000). See [Resource and Process Limits](resource-limits.md).

Inspector fields are listed in
[Pseudocolor Component](editing-components/charts/pseudocolor.md).

## Referenced Matplotlib 3.9.0 URLs

- [Axes pcolormesh](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html)

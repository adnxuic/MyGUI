| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| X column | Column selector | Numeric X coordinates from the same worksheet as Y and Z. Trailing all-blank rows are ignored. Missing or non-finite X/Y rows are skipped with one warning. | Number column in the current project | `data.x_ref` |
| Y column | Column selector | Numeric Y coordinates from the same worksheet as X and Z. Duplicate `(X, Y)` pairs are rejected without interpolation. | Number column in the current project | `data.y_ref` |
| Z column | Column selector | Numeric Z values assembled onto the sorted `Z[y_index, x_index]` grid. Missing or non-finite Z cells are masked. | Number column in the current project | `data.z_ref` |

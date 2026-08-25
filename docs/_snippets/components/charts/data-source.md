| Inspector field | Control | Meaning | Values / default | Persisted / runtime key |
| --- | --- | --- | --- | --- |
| X column | Column selector | Source table column providing X coordinates. Number and Datetime columns are accepted. | Current project column | `data.x_ref` |
| Y column | Column selector | Source table column providing Y coordinates. Number columns are accepted. | Current project column | `data.y_ref` |
| Preprocessing | Expression editor | Element-wise mathematical formulas applied to X and Y data before rendering. | Valid math expression; default `x`, `y` | `data.preprocess` |

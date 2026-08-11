# Current limitations

## Project and component state

- Project files intentionally accept only exact integer schema v9. Historical
  v4-v8 files require an external conversion step before they can be opened.
- Component property edits, component/Axes deletion, chart color changes, and
  whole-Axes palette application are not connected to the application Undo
  stack.
- The Components tree does not provide drag reparenting or ordering, inline
  rename, visibility controls, or canvas highlighting. Selection and expansion
  state last only for the current application session.
- Patch, Bar, Annotation, standalone data-coordinate Image, and Colorbar
  Controllers are not supported. Raster images are supported only as `in_axes`
  Elements.
- Multi-series Plot, Scatter, and Interpolation creation uses one shared X with
  multiple Y columns. Arbitrary X/Y pair batches and batch Fit creation are not
  available.
- Matplotlib does not include scatter collections in `Axes.relim()`, so a
  scatter-only data refresh can retain the previous automatic view limits.
- Style-derived color cycles persist and advance colors only. Additional
  `axes.prop_cycle` keys such as line style, marker, or width are not advanced
  by `ColorCycleState`.

## Table and import boundaries

- The Table model is designed for up to 50,000 rows per Sheet and has no paging
  or disk-backed lazy storage. Undo history is limited to 50 commands per
  project and is discarded when the project closes.
- Qt's `QUndoStack` cannot veto an index transition after a command-level
  failure. Structural Table commands restore the repository snapshot and
  report the failure; the stack position alone does not prove a commit.
- Date/time columns are timezone-naive local values. Formula columns and
  user-defined row filters are not provided.
- Excel import reads the selected workbook into memory, supports `.xlsx` and
  `.xlsm`, and uses only cached formula values. It does not evaluate formulas
  or open legacy `.xls` files.
- Text import decodes the complete source into memory and expects a stable
  whitespace, Tab, comma, or semicolon-delimited table block.

## Runtime and desktop boundaries

- MATLAB fitting and TeX rendering are optional and require compatible local
  runtimes. Missing or broken integrations do not block the base GUI.
- Cancelling a background UI request suppresses its callback, but an already
  running worker exits cooperatively or at its bounded process timeout.
- Project creation starts from the Style gallery. There is no separate welcome
  page or File > New workflow.
- The interface contains both Chinese and English text. Each launch starts
  maximized; normal-window geometry and monitor position are not persisted.
  Only workspace splitter sizes and Explorer state are restored.
- The Matplotlib canvas remains a document-sized scrollable viewport and has no
  separate fit-to-window preview.
- Automated GUI tests use Qt offscreen. Multi-monitor scaling, native file
  dialogs, real TeX/MATLAB runtimes, and interactive drag/drop require the
  Windows desktop smoke checklist.

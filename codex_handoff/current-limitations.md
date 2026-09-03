# Current limitations

## Project and component state

- Project files save exact integer schema v23. Strict v10-v22 inputs migrate
  through every intervening version in memory. Versions v4-v9 remain
  unsupported.
- The Components tree does not provide drag reparenting or ordering, inline
  rename, visibility controls, or canvas highlighting. Selection and expansion
  state last only for the current application session.
- Patch, Bar, Annotation, and standalone data-coordinate Image Controllers are
  not supported. Raster images are supported only as `in_axes` Elements.
- Multi-series Plot, Scatter, and Interpolation creation uses one shared X with
  multiple Y columns. Arbitrary X/Y pair batches and batch Fit creation are not
  available.
- Style-derived color cycles persist and advance colors only. Additional
  `axes.prop_cycle` keys such as line style, marker, or width are not advanced
  by `ColorCycleState`.
- Variable-length numeric and text sequences, such as custom dash lengths,
  legend scatter offsets, and Scatter URLs, still use comma-separated or
  line-separated text. Fixed tick positions and labels now have a row editor;
  other sequences have no per-item row editor, and the Inspector has no visual
  dash, marker, or box-style preview.
- Non-strict `read_state()` keeps cached properties when a live Artist is
  missing or a property getter fails. A hidden Legend without a Matplotlib
  artist is valid semantic state. Toolbar pan/zoom is project view history,
  not a second ComponentState store. This fallback is unchanged; evidence is
  not yet enough to promote a new CORE rule.

## Table and import boundaries

- The Table model is designed for up to 50,000 rows per Sheet and has no paging
  or disk-backed lazy storage. Undo history is limited to 50 commands per
  project and is discarded when the project closes.
- Qt's `QUndoStack` cannot veto an index transition after a command-level
  failure. Structural Table commands restore the repository snapshot; Figure
  replay compensates to the pre-replay state and clears that project's history
  when cursor consistency cannot be proved. The stack position alone does not
  prove a commit.
- Date/time columns are timezone-naive local values. Formula columns and
  user-defined row filters are not provided.
- Excel import reads the selected workbook into memory, supports `.xlsx` and
  `.xlsm`, and uses only cached formula values. It does not evaluate formulas
  or open legacy `.xls` files.
- Text import decodes the complete source into memory and expects a stable
  whitespace, Tab, comma, or semicolon-delimited table block.

## Runtime and desktop boundaries

- Curve fitting uses SciPy in the project Python environment
  (`mygui/database/scipy_fit_adapter.py`). MATLAB fitting and TeX rendering
  remain optional and require compatible local runtimes. Missing or broken
  MATLAB or TeX does not block the base GUI or SciPy fitting.
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
  Windows desktop smoke checklist. Offscreen layout-signature and chrome
  inspection tests do not prove native DPI, dual-monitor placement, or OS
  System-theme title bars.
- Command-bar and activity-rail tools stay ghost buttons rather than square
  icon-buttons, so gallery labels are not width-capped. Editable and
  checkable data-reference ComboBoxes are not auto-tagged as `select`.
  Runtime chrome inspection also skips Qt tab-bar scroll buttons, line-edit
  clear buttons, and `QTableWidget` corner `QAbstractButton`s; those are not
  production command buttons.
- Desktop smoke for feedback chrome (Message Bar tones, destructive confirm,
  form validation, template/Fit busy) is captured at the session DPI. Offscreen
  tests and a single-monitor smoke walk do not prove 100/125/150/200% DPI,
  dual-monitor placement, or OS System-theme title bars.

# UI and Process-State Boundaries

Use this page for presentation-layer changes, Matplotlib state, Qt ownership,
signals, background work, Text rendering, or GUI regression diagnosis.

## Matplotlib

Presentation code under `mygui/widgets/fig_control_window/`, `title_bar/`,
`component_tree/`, and `bottom_bar/` must use Controllers, Services, Canvas
capability queries, and immutable adapter catalogs. It must not import
Matplotlib, resolve live Artists/Axes/Figures, call Artist setters/removal, read
`canvas.fig`, or write process-global Matplotlib configuration.

`mygui/widgets/figure_canvas/` is the Canvas package, not Inspector
presentation. `PyFigureCanvas` remains the selection authority and public
creation/restore entry. `ChartCreationStager`,
`canvas_materialize_handlers`, `CanvasSnapshotApplier`,
`CanvasPopoutWindow`, and `ProjectNavigationToolbar` may call host Canvas
APIs (including Axes `plot`/`scatter` during staging) but must not cache
component business state or write `current_component_id` themselves.
Artist `.set_*` / `.remove()` / `.set_visible()` from those helpers still
belongs on the Canvas host or a Controller/Service.

`PySubTable` in `mygui/widgets/table/py_subtable.py` remains the table widget
host. `table_model.py` owns the Qt model/delegate; `table_view.py` owns the
sheet view and south tabs. They read and mutate only through
`TableRepository`.

`ColorChoiceWidget` in `py_colorchoice_widgets.py` remains the public color
editor. Dialogs live in `color_choice_dialogs.py` and list/grid models in
`color_choice_model.py`. They require the injected `ColorLibrary` and must
not create a private library.

`mygui.figuremodify.matplotlib_adapter` owns style/catalog contexts;
`mygui.tex_config` owns TeX rcParams. These boundaries are enforced by
`ARCH-UI-ARTIST-MUTATION` and
`ARCH-UI-MPL-GLOBAL-STATE-MUTATION`. Ambiguous presentation-layer `.set_*`
calls or indirect Matplotlib global-state candidates are gray boundaries, not
silent clean results.

## Text and diagnostics

Render-sensitive Text edits go through `TextRenderService`; one logical
multi-target edit uses `apply_many()`. Legend remains on `LegendController` and
Axes commands. Inspector TeX listeners synchronize controls only; Canvas render
listeners apply effective TeX state.

`mygui.font_diagnostics` preserves console reporting, normalizes and
deduplicates process diagnostics, then publishes them through the Message Bar
on the GUI thread. `TextRenderService` scopes Matplotlib warnings and math-text
logs into the current transaction. Render or glyph failure rolls back every
target and produces one error result.

## Qt lifetime

- Member `QTimer` instances have a parent or an explicit stop/delete path.
- Started `QThread` instances have a shutdown path that requests termination
  and waits/deletes as appropriate.
- Repeatable bind/sync/setup methods must not accumulate lambda connections;
  disconnect/rebind explicitly or use stable method-bound connections.
- Sections, Inputs, containers, repository bindings, TeX/MATLAB listeners, and
  asynchronous callbacks detach in idempotent `dispose()` paths.

Project Undo/Redo shortcuts are application-level only after resolving the
active Figure project. An editable `QLineEdit`, `QTextEdit`, or
`QPlainTextEdit` with an uncommitted local buffer keeps native text history;
committed Inspector values and spin-box edits use project history. The Figure
toolbar actions and Table toolbar actions bind the same per-project stack.

These are enforced by `QT-TIMER-OWNERSHIP`, `QT-THREAD-LIFECYCLE`, and
`QT-SIGNAL-REBIND`. Unproven ownership or shutdown paths are emitted as gray
boundaries for review.

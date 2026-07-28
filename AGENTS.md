# Codex Maintenance Guide

Scope: this file applies to the whole repository.

## Project Basics

- This is a PySide6 + matplotlib desktop GUI for table-driven chart creation and editing.
- Run the app from the repository root with `python main.py`.
- Resource paths currently depend on root-relative files such as `pictures/icons/...`; do not move assets or change the working-directory assumption without updating all call sites.
- MATLAB and TeX support are optional local integrations. Failures in those paths must not block basic GUI maintenance.

## Working Rules

- Read the relevant components before changing them. Prefer small, local edits over broad rewrites.
- Do not perform large architecture refactors in the same change as a bug fix or maintenance update.
- Keep GUI behavior unchanged unless the task explicitly asks for behavior changes.
- Preserve existing resource names and QSS/JSON file locations unless the task is specifically about resource cleanup.
- Do not delete tracked IDE files, backup files, or sync artifacts as part of unrelated work. Repository hygiene cleanup should be a separate commit.
- Treat `code.database.py_database.databases` as shared global runtime state. Changes around it need focused tests or a clear manual verification path.
- For data-related features, consider whether artifacts connected to that data must refresh when the source data changes.
- Treat user-entered expression evaluation as high risk. Replacing `eval` should be done as a dedicated task.
- When implementing features, consider the Message Bar and State Bar. Prefer surfacing useful user-facing information through the Message Bar, using red for errors, yellow for warnings, and green for successful actions.
- New feature implementations must consider project IO. Ensure feature state can follow the project's save and import workflows when applicable.
- When a feature needs color selection, reuse `ColorChoiceWidget` with the injected application `ColorLibrary`; do not create a separate color menu or eager `QAction` collection. Use `ColorCycleState` only for ordered chart-color sequences, preview with `peek()`, and call `commit()` only after the related operation succeeds.
- Place new code files according to the existing `code/` directory responsibilities: `code/widgets/` is for window and UI components, `code/figuremodify/` is for drawing style modification logic, and `code/database/` is for data processing and data-related helpers. Follow the nearest existing module location before creating a new file.
- Keep handoff notes up to date under `codex_handoff/`. Handoff notes should record only current limitations, not next-step plans.
- After completing a feature, write feature documentation under `docs/`. Keep it to a concise feature description and detailed parameter documentation; do not include limitations or unrelated commentary.

## Component Architecture Rules

- Treat `ComponentRegistry`, `ComponentState`, Controllers, and domain Services as the only mutable business-state path for Figure components. Inspector/UI code must not maintain a second component state model or directly mutate Matplotlib artists; it must submit through the relevant Controller or Service and synchronize from Registry events.
- Build production modification panels with `ComponentInspector` and registered `EditorProfile` objects composed from reusable `EditorSection` implementations. Use `PropertySection` for `PropertySpec`-backed fields and keep `ComponentEditorBase` only as the generic fallback. Do not reintroduce role-specific `Py*ModWidget` classes, monolithic modification panels, `_ChartModWidgetMixin`, or compatibility wrappers around Inspector profiles.
- Reuse `LineAppearanceSection` for all Line roles and `DataReferenceSection` with a role-specific submit strategy. Preserve the established refresh semantics: Plot refreshes automatically, Interpolation recomputes automatically, and Fit records a pending source change until the user explicitly refits.
- Route render-sensitive Text changes through `TextRenderService`, using `apply_many()` for one logical multi-target edit. Keep Legend on `LegendController`/axes commands rather than treating it as a Text component. Fixed semantic components such as Title and axis labels are hidden instead of removed; only genuinely removable components may expose deletion.
- UI synchronization must block recursive signals, roll back the control, Controller state, and artist atomically on failure, and emit at most one Message Bar result for one user action. Sections and editor bindings must detach Registry, repository, TeX, MATLAB, and asynchronous callbacks from `dispose()` or equivalent lifecycle cleanup.
- Creation dialogs may reuse only Controller-free input widgets such as line appearance, data reference, and interpolation option inputs. Accepted dialogs must still create components through the canvas/Controller workflow, and `PyFigureCanvas` must register profiles and ask `ComponentEditorManager` for editors instead of constructing role-specific controls.
- Persist Figure component state only through the schema-v6 component tree. Profile selection, Section expansion, QWidget state, callbacks, and other UI-only data must never enter `ComponentState` or project files. Any future persisted field or schema change requires a dedicated migration, validation, rollback, and save/open round-trip task; preserve stable component IDs and empty data-backed components.

## Inspector Container Rules

- Use responsibility-based names for Inspector layout code: `Host` owns project-level selection, `Panel` owns one Figure/Axes scope, `Stack` switches role-specific toolboxes, `ToolBox` owns visible Inspectors, `Section` edits part of a component, and `Input` is Controller-free dialog input.
- Keep the production hierarchy `FigureInspectorHost` -> `FigureInspectorPanel` -> `AxesInspectorPanel` -> `AxesSemanticInspectorPanel`/Chart and Element stacks. High-level Figure/Axes navigation belongs in `code/widgets/fig_control_window/figure_inspector.py`; reusable Inspector stacks and toolboxes belong in `code/widgets/fig_control_window/component_editors/containers.py`.
- The `all_mod_widgets/` directory is retained only for existing QSS resources. Do not place new Python editor or container implementations there, and do not move its QSS files without updating every explicit resource path.
- Window and Canvas callers must use the public container methods for add, find, show, remove, clear, and toolbox lookup. They must not access `_figure_stack`, `_inspector_stack`, `_toolboxes`, `_chart_stack`, `_element_stack`, or other private Qt layout state.
- `FigureInspectorHost` owns the empty-project offset and project-index mapping. `FigureInspectorPanel` owns Figure elements and Axes selection. `AxesInspectorPanel` alone decides whether a component belongs to the Chart or Element Inspector stack.
- `ComponentEditorManager.create()` is the only production path for creating visible component editors. Toolboxes provide `add_inspector()` and `remove_inspector()` to Manager lifecycle callbacks; container removal must not bypass `dispose()`.
- Treat container renames as atomic repository-wide migrations: update imports, attributes, methods, tests, docs, and handoff notes together, then remove the old names rather than adding aliases or `__getattr__` compatibility paths.
- Historical Canvas names such as `PyFigureCanvas`, `py_figure_canves.py`, `current_canva`, and `canva` remain outside the Inspector container naming scheme. Do not rename them opportunistically as part of unrelated Inspector work; handle them only in a dedicated repository-wide naming task.

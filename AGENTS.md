# MyGUI Agent Constitution

Scope: this file applies to the whole repository. It defines global invariants,
task routing, and completion gates. Task procedures live under `.agents/`.

## Environment and Work Boundaries

- MyGUI is a PySide6 desktop app for table-driven Matplotlib charts. Target
  Python 3.12, Matplotlib 3.9.0, and PySide6 6.7.1; do not use later APIs.
- From the repo root, run `python main.py`. Local verification uses exactly
  `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`; CI may use its
  workflow-installed Python 3.12.
- Read the nearest implementation, tests, and routed Agent material first.
  Prefer small local changes; do not mix hygiene or broad architecture into
  an unrelated fix. Keep GUI behavior, resource names, QSS/JSON locations,
  historical Canvas names, and tracked IDE/sync artifacts unless the task
  targets them. `mygui/widgets/`, `mygui/figuremodify/`, and `mygui/database/`
  keep UI, figure-domain, and data roles; new files follow the nearest module.
  Adapter harness policy lives in that adapter dir. Codex follows
  `.codex/README.md`; DSH stays under `.dsh/`.

## Authoritative Runtime Boundaries

- **CORE-RESOURCE-BOUNDARY:** Resolve bundled icons, QSS, and JSON only through
  `mygui.resources`; production behavior must not depend on the process CWD.
- **CORE-TABLE-REPOSITORY:** The `TableRepository` created by `MainWindow` is
  the shared runtime data authority. Do not add another global table store;
  refresh dependent artifacts when authoritative data changes.
- **CORE-MATPLOTLIB-BOUNDARY:**
  `mygui.figuremodify.matplotlib_adapter` is the sole production boundary for
  process-global style contexts and style/colormap/marker/font catalogs.
  Presentation modules must not import Matplotlib, read `canvas.fig`, resolve
  live targets, or mutate Artists directly. `main.py` has the startup-only
  backend-selection exception.
- **CORE-COLORBAR-AUXILIARY-AXES:** `Colorbar.ax` is owned by its Colorbar
  Component. It is never an ordinary `ComponentKind.AXES` and never receives
  the fixed Axes semantic subtree; lifecycle enters through `ColorbarService`
  and the reversible Colorbar removal contract.
- **CORE-TEX-OWNER:** `mygui.tex_config` is the sole writer of Matplotlib TeX
  rcParams. TeX starts disabled, preserves a non-empty external preamble (or
  installs the MyGUI default), and is enabled only after validation;
  render-sensitive changes go through `TextRenderService`.
- **CORE-FONT-DIAGNOSTICS:** `mygui.font_diagnostics` is the sole application
  bridge for Matplotlib missing-glyph and Qt DirectWrite diagnostics. Install
  it after `QApplication` and before fonts/widgets. A missing glyph rejects the
  edit, atomically restores UI/Controller/Artist state, and emits one red
  result.
- **CORE-APPLICATION-SETTINGS:** Injected `mygui.application_settings` dual-slot
  QSettings is the only persistent preference store. Sessions keep a dirty
  patch plus base revision; commit is atomic. Controllers, Services,
  `ChartCreationStager`, and `EditorContext` receive only narrow ports.
  Settings never enter schema v15, Undo/Redo, dirty fingerprints,
  `ComponentState`, or Canvas materialization. Line/Scatter/free-Text use
  explicit input > Components `NEXT_USE` > Axes palette or Figure style >
  Matplotlib 3.9 fallback. Ordinary Axes use explicit layout/XRD >
  Axes Components `NEXT_USE` > Figure style > Matplotlib 3.9 fallback.
  Restore, materializers, history replay, layout updates, Colorbar
  auxiliary Axes, In-Axes, `add_component_line`, and Reference Guide must
  not read `ComponentDefaultsProvider`; Apply must not mutate existing
  Artists.
- **CORE-THEME-OWNER:** `ThemeService` is the sole publisher of application font,
  palette, bundled QSS, and density. Apply `ThemeSnapshot` after settings load
  and before any `QWidget`. UI theme is not Matplotlib Figure style.
- MATLAB and TeX are optional; failure must not block basic GUI work.
  `mygui.database.matlab_adapter` is the MATLAB process boundary; Python
  fallbacks in `matlab_fallbacks.py` must not start MATLAB or MCR. Replacing
  user-expression evaluation is a dedicated high-risk task.

## Component, Inspector, and Selection Invariants

- **CORE-COMPONENT-STATE:** `ComponentRegistry`, `ComponentState`, Controllers,
  and domain Services are the only mutable Figure-component business-state
  path. UI submits through them and synchronizes from Registry events; it must
  not keep a second state model or mutate Artists/Controller state. Import
  Controllers from `mygui.figuremodify.components` and Services from
  `mygui.figuremodify.component_services`; implementations live in
  `components/controllers/` and `services/`.
- **CORE-EDITOR-PROFILES:** Production editors use `ComponentInspector` and one
  exact `EditorProfile` per `(ComponentKind, ComponentRole)`, composed from
  reusable Sections. `ComponentEditorManager.create()` is the only visible
  editor creation path; do not reintroduce role-specific panels or silent
  generic fallbacks.
- Every persistent `PropertySpec` has an explicit production editor contract.
  Composite values use the closed tagged normalizers in `property_values.py`;
  production properties never use editable JSON.
  `EditorRegistry.validate_production_profiles()` and Matplotlib exposure
  validation remain startup gates.
- **CORE-SELECTION-AUTHORITY:** `PyFigureCanvas.current_component_id` is the
  only component selection authority. Tree search affects display only. Tree
  groups use typed `GroupNodeKey`; `COMPONENT_ID_ROLE` is reserved for real
  IDs, and UI projection state is never persisted. Keep the historical
  filename `py_figure_canves.py`. Host-protocol helpers
  (`ChartCreationStager`, `canvas_materialize_handlers`,
  `CanvasSnapshotApplier`, `CanvasPopoutWindow`, `ProjectNavigationToolbar`)
  run through that Canvas and must not cache `ComponentState`, selection IDs,
  or color-cycle state.
- Inspector ownership, lifecycle, tree projection, data refresh, and editor
  placement follow `.agents/architecture/inspector.md`. Containers expose
  public APIs and idempotent recursive `dispose()`; do not access private Qt
  stack/toolbox fields.
- UI synchronization blocks recursive signals, rolls back UI/Controller/Artist
  state atomically on failure, detaches all listeners during disposal, and
  emits at most one Message Bar result per user action (red error, yellow
  warning, green success).

## Transactions, Deletion, and Persistence

- **CORE-REGISTRATION-ATOMICITY:** Component creation/publication uses
  `ComponentRegistry.registration_transaction()`. Artists, Controllers,
  Registry/Locator bindings, Inspectors, listeners, IDs, pending state,
  selection, redraw/events, and color-cycle commits form one logical operation.
  Publish user-visible effects only after commit and restore exact pre-call
  identity on failure.
- Axes creation/deletion includes its fixed semantic subtree in one compound
  transaction. Project creation/restore is staged before tab publication and
  cleaned up by stable project/object ID on either side of publication.
- **CORE-DELETION-COORDINATOR:** Every production deletion enters through
  `DeletionCoordinator` with `DeletionRequest`. Fixed semantics hide; genuinely
  removable components declare `REMOVE` and exactly one handler. Deletion is a
  prepared all-or-nothing transaction; post-delete selection comes from the
  confirmed deletion set.
- **CORE-PROJECT-HISTORY:** Each project uses only the `QUndoStack` owned by
  its `TableRepository` entry for one chronological Table/Figure history.
  Figure commands retain immutable `ComponentState` deltas plus explicit
  runtime mementos, never Artists, Controllers, QWidgets, or whole Figures;
  replay enters through Controllers, domain Services, materializers, and
  `DeletionCoordinator`. Restore, table-driven refresh, and replay are
  recording-suspended. History is runtime-only, is absent from schema v15,
  and is invalidated if a failed replay cannot prove a safe cursor.
- **CORE-PERSISTENCE-V15:** Persist component state only through the exact
  integer schema-v15 component tree. UI profiles, widgets, callbacks, tree
  keys, and expansion/selection state never enter project files. Only strict
  v14 migrates directly to v15; strict v13–v10 migrate stepwise; v4–v9 stay
  retired. A later persisted format change needs a dedicated migration task
  with validation, rollback, and round-trip coverage.
- Runtime-created persisted components declare `RESTORE_PHASE` and exactly one
  `ComponentMaterializer`; fixed semantic components use `None`. Preserve
  stable IDs and empty valid data-backed components.
- Detailed transaction, deletion, materialization, palette, and restore
  procedures live in `.agents/architecture/persistence.md` and
  `.agents/architecture/deletion.md`.

## Documentation and Completion

- User docs live under `docs/` and must appear in `mkdocs.yml`. Feature and
  property changes update the relevant parameter page and schema summary
  together. Matplotlib links pin 3.9.0. Nav/build/link policy changes also
  update `docs/documentation-site.md`.
- Feature pages describe current behavior and document each Inspector field
  (control, meaning, values/default, persisted/runtime key). Uncommon
  Matplotlib value families get a pinned 3.9.0 inline link on every applicable
  row; each page lists every referenced URL. Keep limitations and plans out of
  `docs/`.
- New feature state participates in project save/import when applicable; do
  not ship runtime state that silently disappears on reopen.
- `.agents/` is Agent Engineering knowledge, not user docs.
  `codex_handoff/current-limitations.md` records current limitations only;
  scanner output and task evidence stay under ignored `build/agent-results/`.
- Update this file when a global invariant, architecture owner, schema version,
  or startup gate changes; update the Skill and architecture page when a
  workflow changes. `AGENTS.md` outranks `.agents/`, which outranks conflicting
  `docs/` narrative.
- Use `ColorChoiceWidget` with the injected `ColorLibrary`; ordered chart colors
  use `ColorCycleState.peek()` and `commit()` only after the related transaction
  succeeds.
- Interactive desktop smoke remains required when a routed task declares it;
  Qt offscreen tests do not cover multi-monitor scaling, native dialogs, real
  TeX/MATLAB runtimes, or drag/drop.

## Task Router

Matching work reads the routed Skill and architecture pages in
`.agents/task-map.yaml`:

| Task | Required Skill |
| --- | --- |
| New Figure/chart/element component | `.agents/skills/add-figure-component/SKILL.md` |
| Add/change an Inspector property | `.agents/skills/modify-component-property/SKILL.md` |
| Add/change an application setting | `.agents/skills/modify-application-setting/SKILL.md` |
| Change persisted schema or fields | `.agents/skills/schema-migration/SKILL.md` |
| Change save/open/restore publication | `.agents/skills/project-io-change/SKILL.md` |
| Diagnose GUI state/lifecycle regression | `.agents/skills/debug-gui-regression/SKILL.md` |
| Audit architecture boundaries | `.agents/skills/architecture-audit/SKILL.md` |
| Promote or dismiss a gray boundary | `.agents/skills/evolve-architecture-rule/SKILL.md` |
| Diagnose or repair CI | `.agents/skills/fix-ci/SKILL.md` |

When multiple routes apply, use all applicable Skills and the union of their
checks. Ordinary local maintenance that matches none still obeys this file.

## Verification Protocol

- Run routed checks from `.agents/checks/` with the project interpreter. Local
  full command:
  `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe .agents/checks/verify_full.py --profile local`.
- Baseline: compileall, Ruff, the complete unittest suite with
  `QT_QPA_PLATFORM=offscreen`, branch coverage (global 74%, listed critical
  files 80%), and applicable focused fault-injection/round-trip tests.
- Documentation changes run `python -m mkdocs build --strict`; docs-only
  changes skip the Python application suite.
- A required check that is failed, unknown, or not run blocks completion.
  Report verification exactly; never equate “not run” with pass. Focused
  suites and manual smoke: `.agents/architecture/testing-map.md`.

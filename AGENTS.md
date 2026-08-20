# MyGUI Agent Constitution

Scope: this file applies to the whole repository. It defines global invariants,
task routing, and completion gates. Task procedures live under `.agents/`.

## Environment and Work Boundaries

- MyGUI is a PySide6 desktop application for table-driven Matplotlib chart
  creation and editing. Target Python 3.12, Matplotlib 3.9.0, and PySide6
  6.7.1; do not use APIs introduced after those versions.
- From the repository root, run the app with `python main.py`. For local
  maintenance and verification use exactly
  `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`; CI may use its
  workflow-installed Python 3.12 interpreter.
- Read the relevant implementation, nearest tests, and routed Agent material
  before changing code. Prefer small local changes, preserve unrelated user
  edits, and do not combine repository hygiene or broad architecture work with
  an unrelated fix.
- Keep GUI behavior, resource names, QSS/JSON locations, historical Canvas
  names, and tracked IDE/sync artifacts unchanged unless the task explicitly
  targets them.
- `mygui/widgets/`, `mygui/figuremodify/`, and `mygui/database/` retain their
  current UI, figure-domain, and data responsibilities. New files follow the
  nearest existing module.

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
- **CORE-TEX-OWNER:** `mygui.tex_config` is the sole writer of Matplotlib TeX
  rcParams. TeX starts disabled, preserves a non-empty external preamble (or
  installs the MyGUI default), and is enabled only after validation;
  render-sensitive changes go through `TextRenderService`.
- **CORE-FONT-DIAGNOSTICS:** `mygui.font_diagnostics` is the sole application
  bridge for Matplotlib missing-glyph and Qt DirectWrite diagnostics. Install
  it after `QApplication` and before fonts/widgets. A missing glyph rejects the
  edit, atomically restores UI/Controller/Artist state, and emits one red
  result.
- MATLAB and TeX are optional integrations. Their failure must not block basic
  GUI maintenance. User-entered expression evaluation remains high risk and
  any replacement of evaluation machinery is a dedicated task.

## Component, Inspector, and Selection Invariants

- **CORE-COMPONENT-STATE:** `ComponentRegistry`, `ComponentState`, Controllers,
  and domain Services are the only mutable Figure-component business-state
  path. UI submits through them and synchronizes from Registry events; it must
  not maintain a second state model or mutate Artists/Controller state.
- **CORE-EDITOR-PROFILES:** Production editors use `ComponentInspector` and one
  exact `EditorProfile` per `(ComponentKind, ComponentRole)`, composed from
  reusable Sections. `ComponentEditorManager.create()` is the only visible
  editor creation path; no role-specific modification panels or silent generic
  fallbacks may be reintroduced.
- Every persistent `PropertySpec` has an explicit production editor contract.
  Composite values use the closed tagged normalizers in
  `property_values.py`; production properties never use editable JSON.
  `EditorRegistry.validate_production_profiles()` and Matplotlib exposure
  validation remain startup gates.
- **CORE-SELECTION-AUTHORITY:** `PyFigureCanvas.current_component_id` is the
  only component selection authority. Tree search affects display only. Tree
  groups use typed `GroupNodeKey`; `COMPONENT_ID_ROLE` is reserved for real
  IDs, and UI projection state is never persisted.
- Inspector/container ownership, lifecycle, tree projection, data refresh, and
  editor placement follow `.agents/architecture/inspector.md` and
  `.agents/architecture/component-system.md`. Containers expose public APIs and
  idempotent recursive `dispose()`; external code does not access private Qt
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
  prepared all-or-nothing transaction and post-delete selection is computed
  from the confirmed deletion set.
- **CORE-PERSISTENCE-V10:** Persist component state only through the exact
  integer schema-v10 component tree. UI profiles, widgets, callbacks, tree
  keys, and expansion/selection state never enter project files. v4-v9 loading
  is intentionally retired. Any persisted format change requires a dedicated
  schema-v11 migration task with validation, rollback, and round-trip coverage.
- Runtime-created persisted components declare `RESTORE_PHASE` and exactly one
  `ComponentMaterializer`; fixed semantic components use `None`. Preserve
  stable IDs and empty valid data-backed components.
- Detailed transaction, deletion, materialization, palette, and restore
  procedures live in `.agents/architecture/persistence.md` and
  `.agents/architecture/deletion.md`.

## Documentation and Completion

- User-facing documentation is MkDocs content under `docs/`; every page appears
  in `mkdocs.yml`. Feature/property changes update the relevant parameter page
  and schema summary in the same change. Matplotlib links pin version 3.9.0.
- Feature pages describe current behavior concisely and document parameters in
  detail; limitations and plans stay out of `docs/`. Parameter tables keep one
  row per Inspector field with control, meaning, values/default, and the
  persisted/runtime property key. Uncommon Matplotlib value families carry a
  pinned 3.9.0 inline link on every applicable row, and each page lists all
  referenced URLs. Changes to nav/build/link policy also update
  `docs/documentation-site.md`.
- New feature state participates in project save/import workflows when
  applicable; do not ship runtime state that silently disappears on reopen.
- `.agents/` is operational Agent Engineering knowledge, not user docs.
  `codex_handoff/current-limitations.md` records current limitations only;
  scanner output and task evidence are temporary artifacts under the ignored
  `build/agent-results/` path.
- Update this file in place when a global invariant, architecture owner,
  schema version, or startup gate changes. Update the relevant Skill and
  architecture page when a workflow changes. `AGENTS.md` is authoritative over
  `.agents/`, which is authoritative over conflicting narrative under `docs/`.
- Use `ColorChoiceWidget` with the injected `ColorLibrary`; ordered chart colors
  use `ColorCycleState.peek()` and call `commit()` only after the related
  transaction succeeds.
- Interactive desktop smoke checks remain required when a routed task declares
  them; Qt offscreen tests do not cover multi-monitor scaling, native dialogs,
  real TeX/MATLAB runtimes, or drag/drop.

## Task Router

Before implementing a matching task, read the routed `SKILL.md` completely and
the architecture pages named by `.agents/task-map.yaml`:

| Task | Required Skill |
| --- | --- |
| New Figure/chart/element component | `.agents/skills/add-figure-component/SKILL.md` |
| Add/change an Inspector property | `.agents/skills/modify-component-property/SKILL.md` |
| Change persisted schema or fields | `.agents/skills/schema-migration/SKILL.md` |
| Change save/open/restore publication | `.agents/skills/project-io-change/SKILL.md` |
| Diagnose GUI state/lifecycle regression | `.agents/skills/debug-gui-regression/SKILL.md` |
| Audit architecture boundaries | `.agents/skills/architecture-audit/SKILL.md` |
| Promote or dismiss a gray boundary | `.agents/skills/evolve-architecture-rule/SKILL.md` |
| Diagnose or repair CI | `.agents/skills/fix-ci/SKILL.md` |

When multiple routes apply, use all applicable Skills and the union of their
checks. Ordinary local maintenance that matches none still obeys this file.

## Verification Protocol

- Run routed checks from `.agents/checks/` with the project interpreter. The
  canonical local full command is:
  `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe .agents/checks/verify_full.py --profile local`.
- The application baseline is compileall, Ruff, the complete unittest suite
  with `QT_QPA_PLATFORM=offscreen`, branch coverage (global 74%, listed critical
  files 80%), and applicable focused fault-injection/round-trip tests.
- Documentation changes run `python -m mkdocs build --strict`; docs-only changes
  do not require the Python application suite.
- A routed required check that is failed, unknown, or not run prevents a
  completed result. Report verification exactly; never equate “not run” with
  pass. Use `.agents/architecture/testing-map.md` for focused suites and manual
  smoke coverage.

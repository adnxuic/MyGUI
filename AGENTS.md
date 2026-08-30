# MyGUI Agent Constitution

Scope: whole repository. This compact file is the mandatory bootstrap contract
and global rule index; detailed normative text lives at the exact sources in
`.agents/rule-catalog.yaml`.

## Authority and Required Loading

1. This file defines global scope, precedence, and CORE summaries.
2. `.agents/rule-catalog.yaml` maps every stable rule ID to its authoritative
   detailed source and enforcement. Read the source of every CORE rule touched
   by the task, even when it is not already named by a task route.
3. Classify work only through `.agents/task-map.yaml`. Read every matching
   `SKILL.md` and routed architecture page before implementation; use the union
   when multiple routes match.
4. Skills define task procedure without redefining architecture. User docs
   describe shipped behavior and never override Agent Core.
5. Codex follows `.codex/README.md`.

If routing, a required source, or a required capability is missing or
ambiguous, stop and report it rather than inventing a substitute.

## Environment and Work Boundaries

- MyGUI is a PySide6 desktop app for table-driven Matplotlib charts. Target
  Python 3.12, Matplotlib 3.9.0, and PySide6 6.7.1; do not use later APIs.
- Run from the repository root with `python main.py`. Local verification uses
  exactly `E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe`; CI uses its
  workflow Python.
- Read nearest implementation, tests, and routed knowledge first. Keep changes
  focused and preserve unrelated work, GUI behavior, resources, QSS/JSON paths,
  historical Canvas names, and tracked artifacts.
- MATLAB and TeX are optional; their absence must not block unrelated GUI work.
  Replacing user-expression evaluation is a dedicated high-risk task.

## Global CORE Rule Index

- **CORE-RESOURCE-BOUNDARY:** Resolve bundled icons, QSS, and JSON only through
  `mygui.resources`; production behavior must not depend on CWD.
- **CORE-TABLE-REPOSITORY:** The `TableRepository` created by `MainWindow` is
  the shared runtime Table authority; do not add global or parallel stores.
- **CORE-MATPLOTLIB-BOUNDARY:**
  `mygui.figuremodify.matplotlib_adapter` owns global style contexts/catalogs.
  Presentation/UI code must not mutate Matplotlib process-global configuration
  or rcParams directly; changes must go through the declared configuration
  owner.
- **CORE-COLORBAR-AUXILIARY-AXES:** `Colorbar.ax` belongs to the Colorbar
  Component, is not an ordinary Axes component, and enters via `ColorbarService`.
- **CORE-TEX-OWNER:** `mygui.tex_config` is the sole writer of TeX rcParams;
  enable TeX only after validation and use `TextRenderService` for render edits.
- **CORE-FONT-DIAGNOSTICS:** `mygui.font_diagnostics` solely bridges Matplotlib
  glyph and DirectWrite diagnostics; failed glyph edits roll back atomically.
- **CORE-APPLICATION-SETTINGS:** Injected `mygui.application_settings` dual-slot
  storage is the only preference authority. Settings stay outside project
  schema v22, Undo/Redo, dirty fingerprints, and component state.
- **CORE-TEMPLATE-LIBRARY:** `mygui.template_library` solely owns template
  schema/storage/planning; templates remain independent of project schema v22.
- **CORE-THEME-OWNER:** `ThemeService` solely publishes application font,
  palette, bundled QSS, and density before widget creation; UI theme is not
  Matplotlib Figure style.
- **CORE-FIGURE-LAYOUT-ENGINE-OWNER:** `FigureController.properties.layout_engine`
  is the only Figure layout-engine authority; Axes Layout edits GridSpec only.
- **CORE-AXES-GEOMETRY-OWNER:** `AxesGeometryService` solely owns individual
  Axes grid/manual projection, bounds, and related Colorbar geometry.
- **CORE-COMPONENT-STATE:** Registry, immutable `ComponentState`, Controllers,
  and domain Services are the only Figure-component business-state path; UI
  submits through them and never mutates Artists or parallel state directly.
- **CORE-EDITOR-PROFILES:** Production uses `ComponentInspector` and one exact
  `EditorProfile` per `(ComponentKind, ComponentRole)` with explicit property
  editor contracts and no silent generic or editable-JSON fallback.
- **CORE-SELECTION-AUTHORITY:**
  `PyFigureCanvas.current_component_id` is the only component selection
  authority; projection/search state is UI-only and never persisted.
- **CORE-REGISTRATION-ATOMICITY:** Component creation/publication, IDs,
  bindings, Inspectors, selection, events, redraw, and color commits form one
  `registration_transaction()` with exact rollback on failure.
- **CORE-DELETION-COORDINATOR:** Every production component deletion enters
  through `DeletionCoordinator` with `DeletionRequest` and commits atomically.
- **CORE-PROJECT-HISTORY:** Each project uses only the `QUndoStack` owned by its
  `TableRepository` entry; replay re-enters authoritative services and history
  remains runtime-only.
- **CORE-PERSISTENCE-V22:** Persist Figure business state only through the
  strict integer schema-v22 component tree and declared materializers. Project
  create/restore publishes only after complete staged validation.

## Universal Change Rules

- Controllers are imported from `mygui.figuremodify.components`; Services from
  `mygui.figuremodify.component_services`. Keep historical filename
  `py_figure_canves.py` unless a dedicated naming task says otherwise.
- Production UI submits through public Controllers, Services, Canvas
  capabilities, Inspector/container APIs, and `DeletionCoordinator`; it does
  not reach private Qt containers, live Matplotlib targets, or mutable state.
- Component publication, Axes fixed subtrees, deletion cascades, project
  creation/restore, history replay, and UI synchronization are all-or-nothing.
  Block recursive signals, detach listeners on idempotent disposal, and emit at
  most one Message Bar result per user action.
- New persisted state requires the applicable property/component/schema/project
  routes, explicit editor/materializer/deletion declarations, strict round
  trips, rollback coverage, and user documentation. Application settings never
  enter project persistence.
- Do not perform unrelated refactors. Existing dirty work belongs to the user;
  preserve it and stop if a safe non-overlapping change is impossible.

## Documentation, Evidence, and Completion

- User docs live under `docs/` and `mkdocs.yml`. Feature/property changes update
  their parameter page and schema summary together; Matplotlib links pin 3.9.0.
  Keep limitations in `codex_handoff/current-limitations.md`, not shipped docs.
- `.agents/` is harness-neutral Agent Engineering knowledge. Generated test
  and task evidence belongs only under ignored `build/agent-results/`.
- Update this root file only when bootstrap flow or the global CORE index
  changes. Update detailed rule sources, Skills, routing, and enforcement at
  their single owners.
- Run every check required by the union of matched routes with the project
  interpreter. Failed, unknown, or not-run required checks block completion;
  report exact commands, results, coverage, gray boundaries, and limitations.
- Routes with `manual_smoke: true` require appropriate interactive Windows
  smoke. Offscreen Qt does not prove native dialogs, drag/drop, multi-monitor
  scaling, or real TeX/MATLAB runtimes.

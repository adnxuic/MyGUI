# Component System

Read this page for work involving Figure components, Controllers, Services,
tree projection, data references, style defaults, or component creation.

## State and mutation path

`ComponentRegistry` owns Controllers and ancestry. `ComponentState` is the
serializable business record. UI code sends complete edits to Controllers or
domain Services and observes committed Registry events; it does not mutate an
Artist, Controller state dictionary, or a parallel UI state model.

The corresponding scanner rules are `ARCH-SECOND-COMPONENT-STATE` and
`ARCH-CONTROLLER-BYPASS`. The broader invariant is `CORE-COMPONENT-STATE`.

Explicit user-intent entry points also pass through the project
`FigureHistoryService`. History observes the committed Controller/Registry
projection; it does not become a second business-state authority. Undo/Redo
re-enters the same Controller, Service, materializer, and deletion paths under
recording suspension. Direct scripted Service calls remain non-history
operations unless their caller deliberately opens a history boundary.

## Module layout

Keep importing Controllers from `mygui.figuremodify.components` (or
`mygui.figuremodify.components.controllers`) and Services from
`mygui.figuremodify.component_services`. Do not split `components/base.py`.
The facade modules must re-export every public symbol.

Concrete Controllers live in `mygui/figuremodify/components/controllers/`:

| Module | Controllers |
| --- | --- |
| `containers.py` | `FigureController`, `AxesController` |
| `axes_semantics.py` | Axis, Spine, Tick, Tick Label, Grid |
| `text.py` | `TextController`, Title, Axis Label |
| `legend.py` | `LegendController` |
| `in_axes.py` | Zoom and Image insets |
| `lines.py` | Line, Function Curve, Plot, Fit, Interpolation |
| `collections.py` | Scatter, Reference Marks, Reference Line/Band |
| `colorbar.py` | `ColorbarController` |
| `registry_bridge.py` | `CONTROLLER_TYPES`, `controller_type_for`, `create_controller` |

Domain Services live in `mygui/figuremodify/services/`:

| Module | Public types |
| --- | --- |
| `axes_command.py` | `AxesCommandService` |
| `chart_data.py` | `FunctionCurveService`, `ChartDataService`, `InterpolationService`, `FitService` |
| `colorbar.py` | `ColorbarService` and source resolvers |
| `reference_marks.py` | `ReferenceMarksService`, `ReferenceGuideService` |
| `text_render.py` | `TextRenderService` |
| `deletion.py` | deletion request/plan/handler types and `ComponentDeletionService` |
| `dependency.py` | `ComponentDependencyService` |

`PyFigureCanvas` in `mygui/widgets/figure_canvas/py_figure_canves.py` is
the Qt widget entry, selection authority, and history-decorated public
`add_*` / `restore_component_tree` surface. Keep that historical filename.
Other files in the same package are host-protocol helpers: they hold only a
host reference and must not cache `ComponentState`, selection, or color-cycle
state.

| Module | Role |
| --- | --- |
| `chart_creation.py` | `ChartCreationStager` and batch records |
| `canvas_materialize_handlers.py` | Canvas restore handlers; bind with `register_canvas_materializers()` |
| `canvas_snapshot.py` | `CanvasSnapshotApplier` after Matplotlib targets exist |
| `canvas_popout.py` | `CanvasPopoutWindow` for the live canvas viewport |
| `canvas_toolbar.py` | `ProjectNavigationToolbar` and `history_command` |
| `deletion_coordinator.py` | production `DeletionCoordinator` |
| `component_materializers.py` | Matplotlib-free `ComponentMaterializerRegistry` |
| `py_figure_window.py` | Figure window host |
| `project_metadata.py` | project metadata port |

Do not move `add_*` handlers into `component_materializers.py`. Keep thin
`PyFigureCanvas._materialize_*` wrappers so restore and tests still enter
through the Canvas.

## Component creation

- Prefer existing `ComponentKind` and `ComponentRole`; adding persisted kinds,
  roles, selectors, or fields is a schema migration.
- Derive applicable line, marker, fill, text, and cycle defaults from the
  current Figure style through the shared style-creation service. Display those
  defaults in Controller-free creation Inputs and create the Artist under the
  same style context.
- Explicit user choices and an active Axes palette override style defaults.
  Style changes affect future components only unless the user reapplies them.
- Use the injected `ColorLibrary`. Preview ordered colors with
  `ColorCycleState.peek()` and commit only after full publication succeeds.
- Create the Artist, synchronize the Controller from it, register Controller,
  Locator, materializer/deletion/editor declarations, then publish through one
  registration transaction. Do not expose partial events or selection.
- Creation dialogs may reuse Controller-free Inputs only. Acceptance still
  delegates component creation to the Canvas/Controller workflow; dialogs do
  not publish Artists or Registry state themselves.
- Multi-series Plot, Scatter, and Interpolation creation stages through
  `ChartCreationStager` inside one `registration_transaction()`, then
  commits the Axes color cycle and ledger only after that transaction
  succeeds. Public `add_plot` / `add_plots` (and scatter/interpolation
  equivalents) stay on `PyFigureCanvas`.

## Data semantics

Reuse `LineAppearanceSection` for all Line roles and `DataReferenceSection`
with a role-specific submit strategy. Plot refreshes automatically,
Interpolation recomputes automatically, and Fit records a pending source
change until an explicit refit. Empty data-backed components remain valid where
their Controller contract allows it.

For data changes, check TableRepository dependencies and whether affected
charts, Inspector controls, autoscale state, legends, and project fingerprints
need refresh. Do not add another data authority.

## Required declarations

Every supported `(ComponentKind, ComponentRole)` has exactly one Controller
mapping and one production `EditorProfile`. Runtime-created persisted
components additionally have a non-`None` `RESTORE_PHASE` and one exact
`ComponentMaterializer`; fixed semantic components use `RESTORE_PHASE = None`.
Removable components additionally have one deletion handler.

Complete additions with schema-v15 round trips, empty-data coverage, data
refresh tests, lazy Inspector identity, failure rollback tests, component
parameter documentation, and any applicable manual GUI smoke checks.

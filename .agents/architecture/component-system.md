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
| `field_2d.py` | Pseudocolor, Heatmap, Contour |
| `colorbar.py` | `ColorbarController` |
| `registry_bridge.py` | `CONTROLLER_TYPES`, `controller_type_for`, `create_controller` |

Domain Services live in `mygui/figuremodify/services/`:

| Module | Public types |
| --- | --- |
| `axes_command.py` | `AxesCommandService` |
| `chart_data.py` | `FunctionCurveService`, `ChartDataService`, `InterpolationService`, `FitService` |
| `colorbar.py` | `ColorbarService` and source resolvers |
| `field_2d.py` | `Field2DService` |
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
  same style context. Do not treat a style probe as the effective creation
  default once Components overrides exist.
- Effective Line/Scatter/free-Text creation uses explicit input >
  `ComponentDefaultsProvider` (`NEXT_USE`) > Axes palette (Line/Scatter
  color) or Figure style (other fields) > Matplotlib 3.9 fallback. Merge in
  `creation_preferences.py`. Dialogs freeze one snapshot at open. Restore,
  materializers, history replay, `add_component_line`, and Reference Guide
  must not read the Provider. Do not change Controller `PropertySpec.default`
  to express application defaults.
- Effective ordinary Axes creation uses explicit layout/XRD values >
  Axes Components `NEXT_USE` override > current Figure style > Matplotlib 3.9
  fallback. Merge in `resolve_axes_appearance()`. `AxesLayoutService.create()`
  applies resolved appearance, then the view spec, then right-Y / shared-label
  / XRD structure, then registers the fixed semantic subtree. Colorbar
  auxiliary Axes, In-Axes, restore, materialize, history replay, and layout
  geometry updates must not read the Provider. Title, Axis Label, Legend,
  limits, scale, locator, formatter, aspect, and margins are not stored as
  Axes Components defaults; a later Axes property must decide whether it
  joins that page. Do not change Controller `PropertySpec.default`.
- Explicit user choices and an active Axes palette override style defaults.
  Style or Components changes affect future components only unless the user
  reapplies them.
- Use the injected `ColorLibrary`. Preview ordered colors with
  `ColorCycleState.peek()` and commit only after full publication succeeds.
  Palette-backed colors commit after the registration transaction; custom
  Components override colors must not advance the cycle.
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
  equivalents) stay on `PyFigureCanvas`. The stager must not receive
  `ApplicationSettingsService`.

## Data semantics

Reuse `LineAppearanceSection` for all Line roles and `DataReferenceSection`
with a role-specific submit strategy. Plot refreshes automatically,
Interpolation recomputes automatically, and Fit records a pending source
change until an explicit refit. Empty data-backed components remain valid where
their Controller contract allows it.

For data changes, check TableRepository dependencies and whether affected
charts, Inspector controls, autoscale state, legends, and project fingerprints
need refresh. Do not add another data authority.

## Colorbar auxiliary Axes

`CORE-COLORBAR-AUXILIARY-AXES` assigns `Colorbar.ax` to the Colorbar Component.
It is never an ordinary `ComponentKind.AXES`, never receives the fixed Axes
subtree, and enters creation, restore, refresh, and deletion through
`ColorbarService` and its declared materializer/removal paths.

## Colorbar auxiliary Axes

`CORE-COLORBAR-AUXILIARY-AXES` assigns `Colorbar.ax` to the Colorbar Component.
It is never an ordinary `ComponentKind.AXES`, never receives the fixed Axes
subtree, and enters creation, restore, refresh, and deletion through
`ColorbarService` and its declared materializer/removal paths.

## Figure layout engine ownership

Figure layout engine configuration (`layout_engine` property with kinds `none`,
`tight`, `constrained`, `compressed` and engine-specific parameters) is owned
exclusively by `FigureController`. The Figure Inspector is the sole direct UI
editor.

The corresponding invariant is `CORE-FIGURE-LAYOUT-ENGINE-OWNER` and the
corresponding scanner rule is `ARCH-FIGURE-LAYOUT-ENGINE-BYPASS`.

- `AxesLayoutService` and the Axes Layout dialog manage GridSpec geometry
  (rows, columns, width/height ratios, margins, and spacing), sharing topology,
  and Axes structure only.
- Updating Figure layout definitions must use pure data mutation:
  `ComponentMutation(root.component_id, data={"layouts": ...})` applied via
  `root.apply_mutation()`. `AxesLayoutService` must not call `root.apply_state()`
  as a whole or touch `properties.layout_engine`.
- The Axes Layout dialog opens with a read-only engine kind display and preserves
  active engines. When an automatic layout engine is active, GridSpec geometry
  remains editable and persistable, and a read-only note informs the user that
  rendered margins and spacing may be adjusted by the Figure engine.

## Individual Axes geometry ownership

Individual Axes geometry projection mode (`grid` vs `manual`) and manual allocation
rectangle (`bounds` as `[left, bottom, width, height]`) are owned exclusively by
`AxesGeometryService`.

The corresponding invariant is `CORE-AXES-GEOMETRY-OWNER` and the corresponding
scanner rule is `ARCH-AXES-GEOMETRY-BYPASS`.

- `AxesGeometryService` manages individual Axes grid/manual modes, manual bounds,
  Colorbar follower tracking, and position resets.
- In `grid` mode, the Axes follows its Figure layout GridSpec cell and Figure layout
  engine; in `manual` mode, the Axes is detached (`in_layout=False`, `subplotspec=None`)
  and pinned to Figure-normalized bounds.
- UI, Inspector, Axes Layout, and Canvas helper code must not call `set_position()`,
  `set_subplotspec()`, `set_in_layout()`, or access `_subplotspec` directly.
- Colorbars on manual Axes move and scale with the source Axes via affine transformation
  without shrinking the source Axes.

## Required declarations

Every supported `(ComponentKind, ComponentRole)` has exactly one Controller
mapping and one production `EditorProfile`. Runtime-created persisted
components additionally have a non-`None` `RESTORE_PHASE` and one exact
`ComponentMaterializer`; fixed semantic components use `RESTORE_PHASE = None`.
Removable components additionally have one deletion handler.

Complete additions with schema-v21 round trips, empty-data coverage, data
refresh tests, lazy Inspector identity, failure rollback tests, component
parameter documentation, and any applicable manual GUI smoke checks.

# Component System

Read this page for work involving Figure components, Controllers, Services,
tree projection, data references, style defaults, or component creation.

## State and mutation path

`ComponentRegistry` owns Controllers and ancestry. `ComponentState` is the
serializable business record. UI code sends complete edits to Controllers or
domain Services and observes committed Registry events; it does not mutate an
Artist, Controller state dictionary, or a parallel UI state model.

Registry ordering and scalar validation read Controller `kind`, `parent_id`,
and `order` metadata directly. These read-only accessors reflect the current
authoritative state without cloning data payloads. The `state` and snapshot
APIs still return independent copies; no metadata cache bypasses restore or
transaction validation.
Tree validation reuses one independent snapshot per Controller within that
synchronous call; it discards the local map afterward and retains every
hierarchy, semantic selector, source, placement, and ordering check.

The corresponding rules are `ARCH-SECOND-COMPONENT-STATE` and
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
| `secondary_axis.py` | `SecondaryAxisController` and its parent-bound runtime target |
| `registry_bridge.py` | `CONTROLLER_TYPES`, `controller_type_for`, `create_controller` |

Legend, In-Axes, and Secondary Axis property reads and writes use closed
handler tables keyed by `PropertySpec.key`. Each persisted property still has
exactly one Controller and one `PropertySpec`.

Domain Services live in `mygui/figuremodify/services/`:

| Module | Public types |
| --- | --- |
| `axes_command.py` | `AxesCommandService` |
| `chart_data.py` | `FunctionCurveService`, `ChartDataService`, `InterpolationService`, `FitService` |
| `colorbar.py` | `ColorbarService` and source resolvers |
| `field_2d.py` | `Field2DService` |
| `reference_marks.py` | `ReferenceMarksService`, `ReferenceGuideService` |
| `secondary_axis.py` | `SecondaryAxisService` and closed creation value types |
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
| `canvas_host.py` | Narrow helper Protocols: register, select, create, snapshot, delete, dependency restore |
| `chart_creation.py` | `ChartCreationStager` and batch records |
| `element_creation.py` | `ElementCreationStager` for chart-adjacent Element publication |
| `canvas_materialize_handlers.py` | Canvas restore handlers; bind with `register_canvas_materializers()` |
| `canvas_snapshot.py` | `CanvasSnapshotApplier` after Matplotlib targets exist |
| `canvas_popout.py` | `CanvasPopoutWindow` for the live canvas viewport |
| `canvas_toolbar.py` | `ProjectNavigationToolbar` and `history_command` |
| `deletion_coordinator.py` | production `DeletionCoordinator` |
| `component_materializers.py` | Matplotlib-free `ComponentMaterializerRegistry` |
| `py_figure_window.py` | Figure window host |
| `project_metadata.py` | project metadata port |

`ComponentContractAuditRow` and `audit_component_contracts()` in
`mygui.figuremodify.components.contract_audit` summarize Controller,
EditorProfile, restore-phase, materializer, and deletion-handler completeness
for startup verification and tests. They are not a second business-state
source. Canvas construction calls `require_complete_component_contracts()`
after the live registries are sealed.

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
  default once Components overrides exist. Each Canvas caches the immutable
  style-derived snapshot by its exact `component_style`; a style change or
  restored different style invalidates the cache. Dialogs reuse that snapshot
  for their whole construction. `ComponentDefaultsProvider` remains a separate
  per-creation read and is never part of the style cache.
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
- Dynamic creation constructs one Inspector, inserts that leaf into the visible
  Inspector stack once, publishes selection once, and schedules at most one
  coalesced `draw_idle()`. Register Inspector rollback before visible insertion.
  TextRenderService and structural Axes validation may retain their required
  synchronous draw. Reading the canonical component snapshot flushes an already
  pending coalesced draw so save and history comparisons observe settled
  Matplotlib-derived state without moving that draw back into creation dispatch.
- Creation dialogs may reuse Controller-free Inputs only. Acceptance still
  delegates component creation to the Canvas/Controller workflow; dialogs do
  not publish Artists or Registry state themselves. Chart and Element dialogs
  construct typed requests; `CreationDialogSession` runs the Canvas call,
  isolates exceptions, and keeps one Message Bar result for that request.
- Multi-series Plot, Scatter, and Interpolation creation stages through
  `ChartCreationStager` inside one `registration_transaction()`, then
  commits the Axes color cycle and ledger only after that transaction
  succeeds. Public `add_plot` / `add_plots` (and scatter/interpolation
  equivalents) stay on `PyFigureCanvas`. Annotation, In-Axes, Colorbar,
  Secondary Axis, Field 2D, Text, and Reference publication stage through
  `ElementCreationStager` the same way. The stagers must not receive
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

## Secondary Axis child Axes

`CORE-SECONDARY-AXIS-BOUNDARY` assigns each Secondary Axis to the ordinary
Axes component named by its `parent_id`. Runtime creation uses only
`Axes.secondary_xaxis()` or `Axes.secondary_yaxis()` with a validated
reversible unit mapping. The resulting child remains in
`parent_axes.child_axes`; it never enters `Figure.axes`, becomes an ordinary
`ComponentKind.AXES`, or receives the fixed Axes semantic subtree.

A Secondary Axis is a persisted leaf with `data == {}`. It may own its mapping,
placement, label, ticker, tick/spine appearance, visibility, and z-order, but
never independent data series, limits, scale, autoscale, aspect, layout, or
navigation state. Creation, editing, restore, history replay, and removal enter
through `SecondaryAxisController`, `SecondaryAxisService`, the declared
materializer, and `DeletionCoordinator`; UI code does not mutate the child Axes
directly.

Mappings must be finite, monotonic, and round-trip over the active parent
domain. If a later parent limit or scale change makes that domain invalid,
hide only the Secondary Axis, warn once for that invalid transition, and
recover automatically when the domain becomes valid. Normalized placement is
unique per parent Axes and orientation.

## Figure layout engine ownership

Figure layout engine configuration (`layout_engine` property with kinds `none`,
`tight`, `constrained`, `compressed` and engine-specific parameters) is owned
exclusively by `FigureController`. The Figure Inspector is the sole direct UI
editor.

The corresponding invariant is `CORE-FIGURE-LAYOUT-ENGINE-OWNER` and the
corresponding rule is `ARCH-FIGURE-LAYOUT-ENGINE-BYPASS`.

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
rule is `ARCH-AXES-GEOMETRY-BYPASS`.

- `AxesGeometryService` manages individual Axes grid/manual modes, manual bounds,
  Colorbar follower tracking, and position resets.
- In `grid` mode, the Axes follows its Figure layout GridSpec cell and Figure layout
  engine; in `manual` mode, the Axes is detached (`in_layout=False`, `subplotspec=None`)
  and pinned to Figure-normalized bounds.
- UI, Inspector, Axes Layout, and Canvas helper code must not call `set_position()`,
  `set_subplotspec()`, `set_in_layout()`, or access `_subplotspec` directly.
- Colorbars on manual Axes move and scale with the source Axes via affine transformation
  without shrinking the source Axes.

Exact deletion rollback is a classified mechanical exception, not a second
geometry policy owner. `MatplotlibRemovalAdapter` may pin and restore the
Matplotlib 3.9.0 private Axes registries, CallbackRegistry tables, positions,
and parent `child_axes` slot required to preserve object identity. It must not
choose grid/manual mode or persisted bounds; those decisions remain on
`AxesGeometryService`. Static enforcement rejects the same geometry calls from
Canvas/UI helpers, and rollback tests pin the adapter exception. This is not a
general private-API allowlist.

## Required declarations

Every supported `(ComponentKind, ComponentRole)` has exactly one Controller
mapping and one production `EditorProfile`. Runtime-created persisted
components additionally have a non-`None` `RESTORE_PHASE` and one exact
`ComponentMaterializer`; fixed semantic components use `RESTORE_PHASE = None`.
Removable components additionally have one deletion handler.

Complete additions with schema-v23 round trips, empty-data coverage, data
refresh tests, lazy Inspector identity, failure rollback tests, component
parameter documentation, and any applicable manual GUI smoke checks.

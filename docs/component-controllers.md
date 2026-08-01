# Matplotlib Component Controllers

The component-controller layer under `code/figuremodify/components/` provides Qt-independent control of a Matplotlib Figure. It separates artist behavior, serializable state, semantic lookup, hierarchy, and redraw coordination so GUI editors, project restore, scripted changes, and later Undo commands can call the same API.

## Architecture

```mermaid
flowchart LR
    State["ComponentState + PropertySpec"] --> Controller["ComponentController"]
    Locator["ComponentLocator"] --> Controller
    Controller --> Artist["Matplotlib target"]
    Mutation["ComponentMutation"] --> Controller
    Controller --> Change["ComponentChange / ComponentBatchChange"]
    Registry["ComponentRegistry"] --> Controller
    Registry --> Locator
    Registry --> Events["Committed component events"]
    Registry --> Updates["Relim / Autoscale / Legend / Redraw"]
    Services["Domain services"] --> Mutation
    Editors["Qt Editors"] --> Services
```

The public value types are:

- `ComponentState`: serializable `id`, `kind`, `role`, `parent_id`, `order`, `selector`, `properties`, and `data`.
- `PropertySpec`: property type, default, normalizer, validator, editor hint, persistence flag, getter/setter, and `UpdateImpact`.
- `ComponentChange`: before/after snapshots, property key, `ChangeStatus`, impacts, and user-facing message.
- `ComponentMutation`: one atomic properties/data/runtime-drawable candidate.
- `ComponentBatchChange`: the committed or rejected result of a multi-component transaction.
- `ComponentEvent`: committed `ADDED`, `CHANGED`, or `REMOVED` lifecycle notification used by Editors.
- `ChangeStatus`: `APPLIED`, `EMPTY`, `REJECTED`, `DELETED`, or `NOOP`.
- `DeletionPolicy`: runtime-only `REMOVE`, `HIDE`, or `FORBID` authority
  declared by each Controller type.
- `RemovalHandle`: runtime-only capture of the exact target, owner, position,
  callbacks, and update subject used by reversible physical removal.
- `UpdateImpact`: composable `RELIM`, `AUTOSCALE`, `LEGEND`, and `REDRAW` flags.

`ComponentController` exposes:

- `resolve_target()` and `read_state()`;
- `set_property(key, value)` for one validated transactional edit;
- `apply_mutation(mutation)` for an atomic property, persistent-data, and drawable-data edit;
- `apply_state(state)`, `snapshot()`, and `restore(snapshot)`;
- idempotent `delete()`, routed by `DeletionPolicy`;
- `prepare_remove()`, `commit_remove(handle)`, and
  `rollback_remove(handle)` for identity-preserving physical removal.

A rejected operation restores the previous target and state. Controllers report an `EMPTY` result when a valid data-bound component has no drawable rows.

## Registry and target resolution

`ComponentRegistry` owns Controllers and their parent/child relationships. It supports:

- `register()`, `get()`, `children()`, `descendants()`, and cycle-safe
  `ancestor(component_id, kind=...)` lookup;
- filtered `query(kind=..., role=..., capabilities=..., parent_id=..., recursive=...)`;
- multi-component `snapshot()` and transactional `restore()`;
- `apply_transaction()` and transactional `set_properties()` with artist/state rollback and buffered events;
- `delete_transaction(component_ids, state_replacements=(), verifier=None)`
  for atomic subtree deletion, survivor reindexing, and tree validation;
- event and batch subscription for Editor synchronization, tree projection,
  and cleanup;
- `registration_transaction()` for atomic publication of a new artist,
  Controller subtree, Locator binding, Inspector preflight, events, and
  pending redraw work;
- `batch_updates()` to coalesce relimit, autoscale, legend refresh, and one final draw.

After a coalesced `RELIM` or `AUTOSCALE`, the Registry reads the affected
Axes back into its `AxesController`. If the limits or autoscale state changed,
it emits a state-only `CHANGED` event so an open Common Inspector immediately
matches the canvas. This synchronization event has no `ComponentChange` and
therefore does not create a user-facing success message.

`ComponentLocator` weakly binds stable artists by component ID. Axes, Axis, Spine, Text, and stable Line/Scatter targets can also resolve through their parent and selector. Tick, Tick Label, Grid, and Legend Controllers resolve semantically each time because Matplotlib may recreate their underlying artists.

Deletion is a Registry structure transaction. It prepares every removable
root, buffers survivor changes and events, detaches the original
artist/Axes reversibly, validates the candidate tree, and commits only after
all checks pass. Failure restores the same Controllers, targets, Locator
bindings, Matplotlib container order, pending updates, and Controller state;
cleanup and lifecycle listeners see no intermediate event. Success marks and
unbinds the removed subtree, runs cleanup, emits child-first `REMOVED`
events, publishes survivor `CHANGED` events, and schedules at most one paint
per Figure. A paint failure after commit is a warning and does not claim that
the committed deletion was rolled back.

The first-party deletion policies are:

| Policy | Components |
| --- | --- |
| `REMOVE` | Axes, every Line role, Scatter, free Text |
| `HIDE` | Axis, Spine, Tick, Tick Label, Grid, Title, axis labels, Legend |
| `FORBID` | Figure and the default for a new Controller type |

Axes use a specialized Matplotlib 3.9 removal handle. Its reversible stage
preserves `_localaxes`, `_axstack`, current Axes, mouse grabber, callbacks,
and shared/twinned relationships without firing `_axes_change_event`.
Matplotlib receives one Axes-change notification only after commit.

`register_figure_components()` builds a complete Controller tree for an existing Figure. `create_semantic_children()` adds the fixed Axis, Spine, Tick, Tick Label, Grid, Title, Axis Label, and Legend records for an Axes. Callers can inject an `id_factory(path)` to produce deterministic project IDs.

## Controller families and properties

| Controller family | Roles | Persistent properties |
| --- | --- | --- |
| `FigureController` | Figure | `name`, `style`, `size_inches`, `dpi`, `facecolor`, `edgecolor`, `frameon`, `constrained_layout` |
| `AxesController` | Axes | `position`, `xlim`, `ylim`, `xscale`, `yscale`, `aspect`, `facecolor`, `visible`, `autoscale_on`, `color_cycle` |
| `XAxisController`, `YAxisController` | X/Y Axis | `visible`, `scale`, `ticks_position`, `label_position`, `inverted` |
| `SpineController` | Spine | `visible`, `color`, `linewidth`, `linestyle`, `position`, `bounds`, `alpha` |
| `TickGroupController` | Major/Minor Tick | `visible`, `direction`, `length`, `width`, `color`, `pad` |
| `TickLabelGroupController` | Major/Minor Tick Label | `visible`, `color`, `fontsize`, `rotation`, `fontfamily`, `pad` |
| `GridController` | Grid | `visible`, `color`, `linestyle`, `linewidth`, `alpha` |
| `TextController` | Title, Axis Label, Text | `text`, `visible`, `position`, `color`, `fontsize`, `fontfamily`, `fontweight`, `fontstyle`, `rotation`, alignment, `usetex`, `alpha` |
| `LegendController` | Legend | `visible`, `location`, `ncols`, `fontsize`, `frameon`, `facecolor`, `edgecolor`, `framealpha`, `title` |
| `LineController` | Line and all curve roles | `label`, `color`, `linestyle`, `linewidth`, marker properties, `alpha`, `visible`, `zorder` |
| `ScatterController` | Scatter | `label`, `color`, `edgecolor`, `size`, `marker`, `linewidth`, `alpha`, `visible`, `zorder` |

`FunctionCurveController`, `DataPlotController`, `FitCurveController`, and `InterpolationController` specialize `LineController` with role-specific data. `controller_type_for(state)` and `create_controller(state, ...)` dispatch from the controlled kind/role pair.

Role data is validated by the Controller as well as by project IO:

- generic `line`: finite one-dimensional `x` and `y` arrays with equal length;
- `function_curve`: a non-empty, safe expression using `x`, plus finite `x_start` and `x_stop`;
- `data_plot` and `scatter`: complete `x_ref` and `y_ref` column references;
- `interpolation`: references, a registered method, integer `k` from 1 through 5, `samples` from 2 through 100000, Boolean `lam_auto`, and a non-negative finite optional `lam`;
- `fit_curve`: references, `Python` or `Matlab` engine, fit metadata, a safe optional display expression, and finite display bounds.

An empty resolved data array is valid and keeps its Controller, editor, references, and project state. A malformed state or invalid replacement is rejected without changing the last valid artist or state.

## Domain services and Editors

`code/figuremodify/component_services.py` contains application commands that span Controller or repository boundaries:

- `AxesCommandService`: semantic Axis/Spine/Label/Legend commands and ordered palette application;
- `FunctionCurveService`: safe expression evaluation and atomic curve-data replacement;
- `ChartDataService`: Plot/Scatter reference changes and automatic table refresh;
- `InterpolationService`: validated interpolation configuration and refresh;
- `FitService`: persistent fit results, manual-refit generations, and display-range updates;
- `TextRenderService`: synchronous render verification with rollback and glyph warnings;
- `ComponentDeletionService`: dynamic-component adapter that composes
  palette-slot release state with `ComponentRegistry.delete_transaction()`;
- `ComponentDependencyService`: query/delete/restore of table-bound component snapshots.

These services do not maintain parallel project records. `ComponentRegistry` and `ComponentState` are the only runtime truth. The visible panels receive an `EditorContext`, call Controllers/services directly, and are synchronized or removed through committed Registry events. `Py*Modify` façade classes are not part of the architecture.

Production editors use one `ComponentInspector` shell. `EditorProfile` declares
the ordered `EditorSection` composition, explicit placement, and UI-only tree
presentation for an exact `EditorKey` kind/role pair, while
`PropertySection` generates an ordered subset of Controller `PropertySpec`
controls. `register_production_profiles()` installs all first-party mappings,
and `ComponentEditorManager.create()` is the production create-and-track
entry. `EditorRegistry` resolves profiles before custom editor factories;
`ComponentEditorBase` remains the all-properties fallback. Line roles share one
appearance section, Text roles share one render-verified section set, Legend
reuses only its intersecting title/font-size fields, and Axes pages bind their
semantic child Controllers. See `docs/component-inspector.md` for the complete
profile and parameter reference.

`TextRenderService.apply_many()` applies multiple Text patches in one Registry
transaction and verifies rendering once per affected Figure. A TeX validation
or draw failure rolls every Text artist and Controller state back together.

`MessagePresenter` maps Controller results to the application Message Bar.
Editors explicitly present domain-specific results. It also observes committed
Registry changes and, on the next Qt event-loop turn, presents any successful
change that no caller consumed. Explicit and event-driven presentations are
deduplicated, related batch changes are coalesced, rejected results remain
immediate errors, and `NOOP` remains silent.

The Data Plot creation dialog initializes its line style from
`DataPlotController.default_properties()["linestyle"]`. It displays readable
labels (`Solid`, `Dashed`, `Dash-dot`, and `Dotted`) while passing and
persisting the canonical Matplotlib values (`-`, `--`, `-.`, and `:`).

## State and property example

```python
from code.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    DataPlotController,
)

state = ComponentState(
    id="plot-1",
    kind=ComponentKind.LINE,
    role=ComponentRole.DATA_PLOT,
    parent_id="axes-1",
    order=0,
    selector={"object_id": "plot-1"},
    properties=DataPlotController.default_properties(),
    data={"x_ref": x_ref.to_dict(), "y_ref": y_ref.to_dict()},
)

controller = DataPlotController(state, target=line)
change = controller.set_property("linestyle", "--")
if change.ok:
    saved_state = controller.snapshot()
```

Use `ColorChoiceWidget` with the application-injected `ColorLibrary` for visible color editors. The Controller receives the normalized selected color and remains independent of Qt.

## Template for adding a Component

1. Add the new `ComponentKind` and `ComponentRole` values, then register the allowed pairing in `ROLES_BY_KIND`.
2. Derive a Controller from the nearest family. Declare `KIND`, accepted
   `ROLES`, `PROPERTY_SPECS`, capability names, and an explicit
   `DELETION_POLICY`.
3. Implement only target-specific hooks: selector validation, property
   read/write overrides, `_apply_data()`, empty-state detection, or
   `prepare_remove`/`commit_remove`/`rollback_remove` when `REMOVE` cannot use
   the normal Matplotlib artist-list handle.
4. Add stable binding or a semantic resolver in `ComponentLocator`. Prefer semantic selectors for Matplotlib objects that may be recreated.
5. Register the `(kind, role)` to Controller mapping in `CONTROLLER_TYPES`.
6. Create the `ComponentState` with a stable ID, valid parent, deterministic `order`, selector, default properties, and role data; register parents before children.
7. Add a domain-service command only when work crosses Controller boundaries or needs repository/render integration. Do not introduce a second mutable record.
8. Extend v6 serialization, strict validation, v4/v5 migration, and direct v6 project round-trip coverage when the component is persistent.
9. Register an exact `EditorProfile` with explicit placement,
   `TreePresentationSpec`, and unique `SectionSpec` keys. Add a new Section
   only for a genuinely new interaction, inject `EditorContext` and the
   application `ColorLibrary`, and keep QWidget state out of `ComponentState`.
10. Add Controller contract tests for resolve, read/write, rejection
    rollback, snapshot/restore, deletion policy, same-object removal rollback,
    event invisibility, and coalesced redraw.

Minimal Controller shape:

```python
class ExampleController(ComponentController[ExampleArtist]):
    KIND = ComponentKind.EXAMPLE
    ROLES = frozenset({ComponentRole.EXAMPLE})
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec(
            "visible",
            bool,
            True,
            editor="check",
            impact=UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=normalize_color,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
    )
    CAPABILITIES = frozenset({"example", "color"})

    def _validate_candidate(self, state):
        if "name" not in state.selector:
            raise ComponentValidationError("Example selector requires name.")

    def _apply_data(self, target, state):
        target.set_data(state.data["values"])
```

The new state must continue to use the same eight-field JSON record and must not place QWidget objects, Matplotlib artists, NumPy arrays, or other runtime-only objects in `properties` or `data`.

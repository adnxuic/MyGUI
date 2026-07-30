# Unified Component Inspector

`ComponentInspector` is the production editing shell for Matplotlib components. It composes an ordered `EditorProfile` from reusable `EditorSection` widgets and sends every mutation to the existing Controller or domain service. `ComponentState` and `ComponentRegistry` remain the only runtime state model; section expansion, widgets, and profiles are UI-only and are not saved in project files.

## Core types

- `ComponentInspector(controller, context, profile)` owns section layout,
  synchronization, and section disposal. Business deletion authority comes
  only from the Controller.
- `EditorProfile` defines the profile key, title, ordered `SectionSpec`
  records, visual `placement`, and dynamic `instance_label_prefix`.
- `EditorSection` provides `sync_from_controller()` and `dispose()` lifecycle methods.
- `PropertySection` generates a selected, ordered subset of Controller `PropertySpec` editors. It blocks signals during synchronization, rolls rejected values back, injects the application `ColorLibrary`, and reports one Message Bar result per operation.
- `ComponentEditorBase` remains the generic all-properties fallback for unregistered component kinds and tests.
- `register_production_profiles(editor_registry)` installs every first-party kind/role profile. `EditorRegistry.register_profile(kind, profile, role=...)` remains available for extensions.
- `ComponentEditorManager.create(component_or_id, context=..., parent=..., remover=...)` is the production creation entry. It resolves through `EditorRegistry`, tracks every visible Inspector, synchronizes Registry changes, and disposes the Inspector before removal.

Callers access role-specific controls explicitly with
`inspector.section("appearance")` and property controls with
`inspector.editor("color")`. Inspector attributes are not forwarded from
Sections.

## Layout containers

Inspector navigation uses responsibility-named containers rather than
role-specific modification widgets:

- `FigureInspectorHost` owns the project-to-Figure Inspector mapping and
  handles the empty-project state.
- `FigureInspectorPanel` owns Figure-level elements and the Axes Inspector
  selection for one Figure.
- `AxesInspectorPanel` combines the semantic Axes pages with Chart and
  Element Inspector stacks.
- `AxesSemanticInspectorPanel` contains the General, X/Y Axis, Spines,
  Ticks/Grid, Title/Labels, and Legend pages.
- `InspectorToolBox` owns an ordered accordion of visible Inspectors for one
  component role. Every `InspectorHeader` stores its own stable
  `component_id`; no Qt `QToolBox` child-button discovery is used.

Canvas and window code use the containers' add, find, show, remove, and
toolbox lookup methods. Layout stacks and toolbox dictionaries are private
implementation details.

## Line profiles

Function Curve, Data Plot, Fit Curve, Interpolation, and Generic Line use the same `LineAppearanceSection`.

| Group | Parameters |
| --- | --- |
| Basic | `label`, `visible`, `color`, `linestyle`, `linewidth` |
| Marker | `marker`, `markersize`, `markerfacecolor`, `markeredgecolor`, `markeredgewidth` |
| Advanced | `alpha`, `zorder` |

The field order is identical for every Line role. Appearance properties call the Line Controller. Role-specific sections use their domain services:

- Function Curve: definition and display range through `FunctionCurveService`.
- Data Plot: `DataReferenceSection` through `ChartDataService`; source changes redraw automatically.
- Fit Curve: data source, fit operations, fit result, and display range through `FitService`; source changes keep manual refitting semantics.
- Interpolation: data source and `InterpolationOptionsInput` through `InterpolationService`; source or option changes recompute automatically.

Scatter uses `ScatterAppearanceSection` with `label`, `visible`, `color`, `edgecolor`, `marker`, `size`, `linewidth`, `alpha`, and `zorder`.

## Text and Legend profiles

Title, X Label, Y Label, and free Text share the following ordered sections:

| Section | Parameters |
| --- | --- |
| Content | `text` |
| Typography | `color`, `fontsize`, `fontfamily`, `fontweight`, `fontstyle`, `alpha` |
| Rotation and alignment | `rotation`, horizontal alignment, vertical alignment |
| Position and visibility | `position`, `visible` |
| Rendering | per-text `usetex` |

All render-sensitive Text properties use `TextRenderService`. `apply_many()` accepts multiple `(controller, property_patch)` pairs, applies them in one Registry transaction, performs one render verification per Figure, and rolls back every target if validation or rendering fails. Free Text may be deleted; semantic Title and Axis Label Controllers are hidden with `visible` and are not removed.

Legend remains a `LegendController`. It reuses the content editor for `title` and the typography editor for `fontsize`, then adds `location`, `ncols`, `visible`, `frameon`, `facecolor`, `edgecolor`, and `framealpha`. Preset and two-coordinate custom locations are supported. Editing an absent Legend first asks `AxesCommandService` to create its runtime artist.

## Axes layout

The Axes editor keeps the existing navigation and provides six scrollable pages:

1. General: palette, limits, scale, autoscale, position, aspect, face color, and visibility.
2. X/Y Axis: the semantic X and Y Axis Controllers.
3. Spines: bottom, top, left, and right semantic Spine Controllers.
4. Ticks/Grid: X/Y major and minor Tick, Tick Label, and Grid Controllers.
5. Title/Labels: Title, X Label, and Y Label Text Controllers.
6. Legend: the semantic Legend Controller.

Every page binds Controller properties; the UI does not directly mutate Matplotlib artists. The General page's Palette section derives its current label and color strip from the Axes `color_cycle` and Figure `style`. Its source selector applies either the current Style default or a named user-selected palette through `AxesCommandService`.

Closing an Inspector or its Manager disposes each Section exactly once.
Repository, TeX, MATLAB, and asynchronous fitting callbacks are detached or
invalidated before the QWidget is removed.

## Component and Axes deletion

Only a component instance label owns the instance context menu. `Delete
Component` targets the stable `component_id` associated with that exact
label; right-clicking the Inspector content does not infer a target from the
current page.

Role navigation labels such as `function curve`, `data plot`, and `text`
provide `Batch Delete...`. The selection dialog lists `(component_id,
display_label)` entries, checks all entries initially, supports Select All and
Clear All, and disables `Delete (0)` until at least one entry is selected.
Single-instance and batch actions both call
`ComponentDeletionService.delete_many(component_ids)`, a thin adapter over
`ComponentRegistry.delete_transaction()`. The Controller's runtime
`DeletionPolicy` is the only permission source. A failed transaction restores
the same Controller, Matplotlib artist, Locator binding, Editor, Header,
label order, current page, callbacks, and pending updates; it publishes no
cleanup or lifecycle event. A successful commit alone emits `REMOVED`, after
which `ComponentEditorManager` disposes and removes the Inspector. The
completed action produces one Message Bar result. Removing the last instance
removes its empty role toolbox and navigation button.

Deleting a palette-backed Line or Scatter also releases its palette slot by
replacing the parent Axes `color_cycle` state inside the same transaction.
The next creation reuses an available deleted color without recoloring
survivors. A custom one-off color does not affect the palette cursor, and a
failed deletion restores the exact pre-action cursor.

Axes navigation labels provide `Delete Axes`. After confirmation,
`AxesCommandService.delete_axes(axes_id)` removes the Axes artist and its
complete semantic/dynamic subtree. Surviving Axes retain their component IDs
and subplot `layout_group`/`slot`, while `order`, selector `index`, and
`axe1...axeN` labels become contiguous. The next Axes at the deleted position
is selected, or the preceding Axes when the last position was removed. An
empty Figure enters the No Axes state. Figure itself is closed through its
project tab, not through Component deletion.

Axes reindex state and the target subtree are submitted in the same Registry
transaction. Until commit, the existing Axes Panel, button, current page,
current Axes, shared/twinned links, and Matplotlib observer state remain
untouched. The Canvas updates its Axes-ID map and navigation only after the
committed `REMOVED` events and does not perform a second redraw.

Title, Axis Label, Legend, Axis, Spine, Tick, Tick Label, and Grid states never
offer physical deletion. Their existing Controller behavior uses `visible`
when hiding is supported.

## Controller-free creation inputs

Creation dialogs reuse input-only widgets and still call the existing canvas creation methods after acceptance:

- `LineAppearanceInput`: label, canonical line style, optional width, and injected `ColorChoiceWidget`.
- `DataReferenceInput`: project-scoped X/Y column choices with signal-safe programmatic synchronization.
- `InterpolationOptionsInput`: method, sample count, order `k`, and automatic or explicit smoothing lambda.

Color inputs preview the current user `ColorCycleState`, or the Figure style's `axes.prop_cycle` when no user palette is active. The cycle and recent-color list are committed only after component creation succeeds.

The project format remains schema v6. Inspector profiles, section expansion, and Qt widgets are never serialized, and the Legend profile introduces no new persistent fields.

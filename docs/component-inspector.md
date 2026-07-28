# Unified Component Inspector

`ComponentInspector` is the production editing shell for Matplotlib components. It composes an ordered `EditorProfile` from reusable `EditorSection` widgets and sends every mutation to the existing Controller or domain service. `ComponentState` and `ComponentRegistry` remain the only runtime state model; section expansion, widgets, and profiles are UI-only and are not saved in project files.

## Core types

- `ComponentInspector(controller, context, profile)` owns section layout, deletion policy, synchronization, and section disposal.
- `EditorProfile` defines the profile key, title, ordered `SectionSpec` records, and whether the component may be removed.
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
- `InspectorToolBox` owns the visible Inspectors for one component role.

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

Every page binds Controller properties; the UI does not directly mutate Matplotlib artists.

Closing an Inspector or its Manager disposes each Section exactly once.
Repository, TeX, MATLAB, and asynchronous fitting callbacks are detached or
invalidated before the QWidget is removed.

## Controller-free creation inputs

Creation dialogs reuse input-only widgets and still call the existing canvas creation methods after acceptance:

- `LineAppearanceInput`: label, canonical line style, optional width, and injected `ColorChoiceWidget`.
- `DataReferenceInput`: project-scoped X/Y column choices with signal-safe programmatic synchronization.
- `InterpolationOptionsInput`: method, sample count, order `k`, and automatic or explicit smoothing lambda.

Color inputs preview the current `ColorCycleState`. The cycle and recent-color list are committed only after component creation succeeds.

The project format remains schema v6. Inspector profiles, section expansion, and Qt widgets are never serialized, and the Legend profile introduces no new persistent fields.

# Component Inspector Architecture

`ComponentInspector` is the production editing shell for Matplotlib components. It composes an ordered `EditorProfile` from reusable `EditorSection` widgets and sends every mutation to the existing Controller or domain service. `ComponentState` and `ComponentRegistry` remain the only runtime state model; section expansion, widgets, and profiles are UI-only and are not saved in project files.

## Using the Inspector

- Selecting a Component in the Components tree opens exactly one Inspector bound to that Component's Controller.
- Each profile orders its reusable sections: shared sections such as Data source and Appearance, plus role-specific sections such as Definition and range, Color and size mapping, Fit operations, and Interpolation parameters. The per-parameter meanings are in [Chart Component Parameters](chart-component-parameters.md) and [Axes and Figure Component Parameters](axes-component-parameters.md).
- Edits apply immediately through the Controller or domain service; a rejected edit restores the previous value and reports one Message Bar result.
- Dynamic Inspectors are created on first selection and cached by Component; the Figure root Inspector is prepared during Figure setup.

## Core types

- `ComponentInspector(controller, context, profile)` owns section layout,
  synchronization, and section disposal. Physical deletion delegates to the
  Canvas `DeletionCoordinator`; the Inspector does not delete Registry or
  Matplotlib state directly.
- `EditorProfile` defines the profile key, title, ordered `SectionSpec`
  records, an explicit visual `placement`, and a UI-only
  `TreePresentationSpec`.
- `EditorSection` provides `sync_from_controller()` and `dispose()` lifecycle methods.
- `PropertySection` generates a selected, ordered subset of Controller `PropertySpec` editors. It blocks signals during synchronization, rolls rejected values back, injects the application `ColorLibrary`, and reports one Message Bar result per operation.
- `ComponentEditorBase` remains an explicit generic all-properties fallback
  for tests and non-production tooling. Production profile coverage is
  validated and cannot silently fall back.
- `EditorKey` is the exact `(ComponentKind, ComponentRole)` pair used by
  profiles and toolboxes. `register_production_profiles(editor_registry)`
  installs and validates every first-party pair; duplicate, missing, invalid,
  or ambiguous registrations fail before a Canvas is published.
- `ComponentEditorManager.create(component_or_id, context=..., parent=..., remover=...)` is the production creation entry. It resolves through `EditorRegistry`, tracks every visible Inspector, synchronizes Registry changes, and disposes the Inspector before removal.

Callers access role-specific controls explicitly with
`inspector.section("appearance")` and property controls with
`inspector.editor("color")`. Inspector attributes are not forwarded from
Sections.

Property presentation uses one shared display-name resolver. A non-blank
`PropertySpec.label` (or legacy `title`) takes precedence; missing, `None`, or
blank metadata falls back to the property key with underscores converted to
words. The same resolved name is used by form labels, the editor's accessible
name and description, tooltips, and Message Bar results.

## Layout containers

Inspector navigation uses responsibility-named containers rather than
role-specific modification widgets:

- `FigureInspectorHost` owns the project-to-Figure Inspector mapping and
  handles the empty-project state.
- `FigureInspectorPanel` owns Figure-level elements and the Axes Inspector
  panels for one Figure.
- `AxesInspectorPanel` combines the semantic Axes pages with Chart and
  Element Inspector stacks.
- `AxesSemanticInspectorPanel` creates the selected fixed semantic Inspector
  on demand and caches it by stable component ID.
- `InspectorToolBox` owns an internal stable-ID stack of dynamic Inspectors
  for one component role. It does not render instance or role navigation
  labels.

The Figure root is created eagerly. Axes and dynamic Inspectors are created
when selected and are then reused; opening an Axes no longer constructs all
of its hidden semantic Inspectors. Canvas and window code use the containers'
add, show, remove, and toolbox lookup methods. `show_component(component_id)`
is both the lazy ensure and public navigation path. Query-only `inspector()`
never creates a widget. Layout stacks and toolbox dictionaries are private
implementation details; the Components tree never reads them.

After a different component is displayed successfully, the shared Figure
Inspector scroll area returns to its top-left minimum on the next Qt layout
turn. A failed selection leaves the current Inspector, component selection,
and both scroll positions unchanged. Scroll positions remain UI-only and are
not persisted per component.

Inspector and creation-input integer and floating-point editors respond to the
mouse wheel only while they have focus. An unfocused numeric editor ignores
the event so the containing Inspector can scroll; clicking or keyboard-focusing
the editor restores normal step-based wheel editing. Nullable, range, tuple,
Legend, Scatter, and Inset numeric controls use the same behavior.

## Line profiles

Function Curve, Data Plot, Fit Curve, Interpolation, and Generic Line use the same `LineAppearanceSection`; its complete Basic, Marker, and Advanced parameter list is documented in [Chart Component Parameters](chart-component-parameters.md). The field order is identical for every Line role. Appearance properties call the Line Controller. Role-specific sections use their domain services:

- Function Curve: definition and display range through `FunctionCurveService`.
- Data Plot: `DataReferenceSection` through `ChartDataService`; source changes redraw automatically.
- Fit Curve: data source, fit operations, fit result, and display range through `FitService`; source changes keep manual refitting semantics.
- Interpolation: data source and `InterpolationOptionsInput` through `InterpolationService`; source or option changes recompute automatically.

Scatter uses `ScatterAppearanceSection` and the color/size mapping section; their parameters are documented in [Chart Component Parameters](chart-component-parameters.md).

Colorbar uses one exact Element profile with Source, Placement, Scale & Ticks,
Label, Appearance, and Advanced sections. `ColorbarSourceSection` displays the
read-only stable Scatter relationship and detaches its Registry subscription
on disposal. Every editable field is a `PropertySection` control routed through
`ColorbarService`; constructor-sensitive placement edits rebuild without
replacing the Inspector. See [Colorbar Component](colorbar-component.md).

## Text and Legend profiles

Title, X Label, Y Label, and free Text share the ordered Content, Typography, Rotation and alignment, Position and visibility, and Rendering sections documented in [Text Element](text-element.md). All render-sensitive Text properties use `TextRenderService`. `apply_many()` accepts multiple `(controller, property_patch)` pairs, applies them in one Registry transaction, performs one render verification per Figure, and rolls back every target if validation or rendering fails. Free Text may be deleted; semantic Title and Axis Label Controllers are hidden with `visible` and are not removed.

Legend remains a `LegendController`. It reuses the content editor for `title` and the typography editor for `fontsize`, then adds `location`, `ncols`, `visible`, `frameon`, `facecolor`, `edgecolor`, `framealpha`, and twin `entry_scope`. Preset and two-coordinate custom locations are supported. Editing an absent Legend first asks `AxesCommandService` to create its runtime artist.

## Axes layout

Every Axes, Axis, Spine, Tick, Tick Label, Grid, Title, Axis Label, and Legend
has its own Inspector. Selecting its stable ID in the Components tree opens
only that Inspector. Axes properties include layout relationship, palette,
limits, scale, independent X/Y autoscale, aspect, face color, and visibility.
The layout section opens stable-ID geometry editing; position remains derived
from the persisted Figure layout. Shared limits, scales, autoscale flags, and
Axis inversion are applied to the complete persisted sharing group. The Palette section
derives its current label and color strip from the Axes `color_cycle` and
Figure `style`; its source selector applies either the current Style default
or a named user-selected palette through `AxesCommandService`.

Every Inspector binds Controller properties; the UI does not directly mutate
Matplotlib artists.

Every composite property has a dedicated control; no Inspector row exposes a
tagged value as editable JSON text.

Frequently used composite values are edited inline. A line pattern is a preset
list plus optional dash offset and on/off lengths, a marker is a named or
numbered Matplotlib symbol plus optional regular-polygon fields, an optional
color is a `Set` checkbox with `ColorChoiceWidget`, font weight and stretch
accept a keyword or a number, and anchors switch between compass codes,
points, and bounds.

Record-shaped values use a summary editor. The Inspector row shows a compact
readable value such as `Linear`, `Automatic`, `Scalar`, `sans-serif · 10 pt`,
`Every point`, `No box`, `Uniform color`, or `3 of 4 connectors visible`, while
`Configure…` opens a type-specific parameter form for the layout engine, tick
locator/formatter, scale, font, text box, marked points, Scatter color/size
mapping, and Zoom connectors.

Both control families validate through the same closed schema-v11 value
normalizer and submit one complete value to one Controller/Service
transaction. A cancelled dialog changes nothing, and a rejected change
restores the prior summary, control state, and Controller value together with
one Message Bar result.

Closing or directly removing an Inspector, ToolBox, Stack, Axes Panel,
Figure Panel, Host, or Manager recursively disposes each Section exactly once.
Repository, TeX, MATLAB, and asynchronous fitting callbacks are detached or
invalidated before the QWidget is removed.

Section construction is transactional. If a later factory fails, every
earlier Section is disposed in reverse order. A cleanup failure in one
Section cannot prevent the remaining callbacks from being detached.

## Component and Axes deletion

`Delete Component`, batch deletion, Axes deletion, Inspector deletion, and
table-dependency cascades all submit a `DeletionRequest` to the Canvas
`DeletionCoordinator`. `ComponentDeletionService.prepare()` resolves stable
IDs, collapses parent/child duplicates, validates `DeletionPolicy` and the
exact `DeletionHandlerRegistry` entry, and produces a runtime-only
`PreparedDeletion`. These request/plan/outcome objects never enter schema v11.

The batch dialog uses the source tree's exact numbered instance labels and
shows each stable ID. It lists the complete matching cohort regardless of the
current search, starts fully selected, supports partial selection, and disables
`Delete (0)`. On acceptance it revalidates every original candidate before an
all-or-none commit.

Before mutation, the coordinator prepares the fallback Inspector and
reversibly detaches any affected Axes Panel. The Registry then stages survivor
state, artists, Locator bindings, a complete tree projection, and schema-v11
validation. A failed transaction restores the same Controller, artist,
Matplotlib order, Locator binding, Inspector, callbacks, pending updates,
palette cursor, and selection; it publishes no cleanup or lifecycle event. A
successful commit alone emits one Registry batch, one redraw, one selection
change when needed, and one green or warning Message Bar result.

Deleting a palette-backed Line or Scatter also releases its palette slot by
replacing the parent Axes `color_cycle` state inside the same transaction.
The next creation reuses an available deleted color without recoloring
survivors. A custom one-off color does not affect the palette cursor, and a
failed deletion restores the exact pre-action cursor.

An Axes tree node provides `Delete Axes`. After confirmation, its composite
deletion handler removes the Axes artist and complete semantic/dynamic subtree.
Surviving Axes retain their component IDs and persisted layout cell/layer,
while `order`, selector `index`, and
`Axes 1...Axes N` labels become contiguous. The next Axes at the deleted position
is selected, or the preceding Axes when the last position was removed. An
empty Figure selects its Figure root Inspector. Deleting one cell from a
multi-cell subplot layout leaves that cell empty: every surviving Axes keeps
its existing position and `SubplotSpec` instead of expanding or moving into
another cell. Figure itself is closed through its project tab, not through
Component deletion.

Axes reindex state and the target subtree are submitted in the same Registry
transaction. The Axes Panel is detached reversibly before the domain stage and
disposed only after commit. The Canvas publishes its prepared Axes-ID map and
authoritative fallback selection without a second navigation pass or redraw.

Title, Axis Label, Legend, Axis, Spine, Tick, Tick Label, and Grid states never
offer physical deletion. Their existing Controller behavior uses `visible`
when hiding is supported.

## Controller-free creation inputs

Creation dialogs reuse input-only widgets and still call the existing canvas creation methods after acceptance:

- `LineAppearanceInput`: label, canonical line style, optional width, and injected `ColorChoiceWidget`.
- `DataReferenceInput`: project-scoped X/Y column choices with signal-safe programmatic synchronization.
- `InterpolationOptionsInput`: method, sample count, order `k`, and automatic or explicit smoothing lambda.
- `ColorbarInput`: eligible source, location, label, fraction, shrink, aspect,
  and pad. It contains no Controller and cannot create Matplotlib state.

Color inputs preview the current user `ColorCycleState`, or the Figure style's `axes.prop_cycle` when no user palette is active. The cycle and recent-color list are committed only after component creation succeeds.

The project format uses schema v11. Inspector profiles, section expansion, and Qt widgets are never serialized. Legend `entry_scope` and Colorbar `source_component_id` are business state; profile and widget state remain UI-only.

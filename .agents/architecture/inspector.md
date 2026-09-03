# Inspector and Component Tree

Use this page for Inspector profiles, Sections, component-tree projection,
selection, containers, property editors, and UI lifecycle.

## Editor contracts

`CORE-EDITOR-PROFILES` requires one exact production `EditorProfile` for every
supported `(ComponentKind, ComponentRole)` and forbids silent generic
fallbacks.

Production editing uses one `ComponentInspector` per component and one exact
`EditorProfile` per `EditorKey = (ComponentKind, ComponentRole)`. Profiles have
explicit placement, a complete `TreePresentationSpec`, and non-empty unique
`SectionSpec` keys. `ComponentEditorBase` is an explicit generic/test fallback,
never a silent production fallback.

Use `PropertySection` for `PropertySpec` fields. Dialog-backed summaries live
in `spec_editors.py`, which re-exports Axis, Text/Annotation, Chart, and
Field/Mapping editors from dedicated modules with explicit registration and
no generic/JSON fallback. Production `EditorProfile` records use the same
domain split: `profiles.py` remains the stable facade and explicit
`register_production_profiles()` owner, while Axis, Text/Annotation, Chart,
and Field/Mapping profiles live in dedicated modules. Inline compound editors live in
`inline_spec_editors.py`, and numeric/text primitives in `common.py`. Reusable Inspector sections live under
`component_editors/sections/` and are imported as
`component_editors.sections`. Role-specific Function Curve, Interpolation, and
Fit sections remain in `chart_sections.py` and `fit_sections.py`.
Controller-free Inputs live in `data_inputs.py`, `appearance_inputs.py`, and
`reference_inputs.py`, re-exported from `inputs.py`. A compound editor exposes
`value()`, `set_value(value, *, emit=False)`, `valueChanged(object)`, and
submits one normalized value. Cancellation changes nothing; Controller
rejection restores the control and emits one red result.

| Module | Sections / inputs |
| --- | --- |
| `sections/property.py` | `PropertySection`, Reference Marks position |
| `sections/data.py` | data source, mapping, Colorbar/image source |
| `sections/appearance.py` | Line and Scatter appearance |
| `sections/text.py` | shared Text section set |
| `sections/axes.py` | Axes limits and layout |
| `sections/legend.py` | Legend location |
| `sections/palette.py` | Axes palette |
| `chart_sections.py` | Function Curve definition, Interpolation options |
| `fit_sections.py` | Fit operations, result, and display range |
| `data_inputs.py` | `DataReferenceInput`, multi-series, Scatter mapping |
| `appearance_inputs.py` | Line appearance, Interpolation options, In-Axes |
| `reference_inputs.py` | Colorbar, Reference Marks, Reference Line/Band |

Every `PropertySpec` declares an explicit `EditorKind`; `AUTO` is valid only
when value type or choices uniquely determine the control. `EditorKind.JSON`
is tests/tooling only. Widget construction uses the closed
`EditorKind → EditorFactory` table in `editor_factories.py`. Unknown,
duplicate, or missing factories fail at import; `AUTO` is resolved to a
concrete kind before lookup and has no generic/JSON fallback. Figure-root
Inspectors may be prepared during Figure setup; every other Inspector is
created on first selection and cached. Lookup-only APIs never create an
Inspector as a side effect.

`EditorRegistry.validate_production_profiles()` classifies every persistent
property exactly once as exposed or intentionally hidden, verifies data/proxy
coverage and enum choices, and runs Matplotlib 3.9 exposure validation. Every
public setter stays classified as core, advanced, alias,
derived/owned-elsewhere, or unsupported with a reason.

## Container ownership

The production hierarchy is `FigureInspectorHost` → `FigureInspectorPanel` →
`AxesInspectorPanel` → semantic/chart/element stacks. Host owns project
mapping, Figure panel owns Figure/Axes selection, Axes panel routes by profile
placement, Stack switches toolboxes, ToolBox owns visible Inspectors, Section
edits a component, and Input is Controller-free. Nested
`CurrentPageStackedWidget` switches in one selection submit one outermost
`updateGeometry()`, then update the Component Tree viewport, Inspector
viewport, and needed scrollbars. The visible Figure Inspector stack presents
only the current leaf Inspector. Axes panels, Chart/Element stacks, and
toolboxes remain on a hidden owner root so selection never hides a container
that still holds every cached Inspector. Cached pages skip `layout.activate()` when
width and theme generation are unchanged; hidden pages freeze their layout so
a later show at the same generation does not relayout. `sizeHint()`, scroll reset, and
`componentShown` stay as they are. Batch depth, dirty flags, and registered
viewports live on each `CurrentPageStackedWidget` instance. Hosts call
`attach_switch_host` and `register_switch_viewports`; they do not probe
`_figure_stack` or scan `findChildren` across a window. Collapse and hide
activate the current page once and request one outermost geometry refresh.
`ARCH-INSPECTOR-SWITCH-ISOLATION` forbids module-level `_SWITCH_DEPTH` /
`_OUTER_HOST`. Field labels stay single-line at their natural font width with
`Preferred`/`Fixed` size policy. `labeled_form_row()` /
`add_labeled_form_row()` create those labels with buddy, tooltip, and
accessible name. `QFormLayout.WrapLongRows` moves the editor below the label
when the 240 px Inspector cannot fit both on one row; labels are not shrunk
to 1 px and do not wrap word-by-word. Description, error, and summary labels
may still wrap. `ComponentInspector` and `InspectorSectionGroup` report a 1 px
minimum width so the scroll area can size to the viewport; editors and
buttons shrink through `apply_expanding_field()` at creation. Section Group
title and indicator subcontrols stay inside the GroupBox, use `UI_CARD` to
cover the border, size the indicator from `SIZE_INDICATOR`, and keep at least
`SPACE_XS` between the title band and section contents.
Fit Result tables stretch columns, expose truncated
text through tooltip/accessible text, and enable internal vertical scrolling
only after six content rows.
`test_inspector_geometry` covers all 34 profiles at 240/320/480 px, 8/9/16 pt,
Compact/Standard/Comfortable, Light/Dark, and default / per-group / all-expanded
fold states. Visible sibling section rects must not intersect, same-layout
siblings are compared without treating parent/child containment as overlap,
buddy labels keep a readable width, GroupBox title/indicator stay inside the
frame, content must stay in bounds, the bottom must be reachable, and the
Inspector must not grow a horizontal scrollbar. Color editors size the 52×52
swatch host from `minimumSize()`, not an invalid `minimumSizeHint()`, so
creation and switch must not emit Qt `Negative sizes`.

Callers use public add/find/show/remove/clear/toolbox APIs. Access to
`_figure_stack`, `_inspector_stack`, `_toolboxes`, `_chart_stack`,
`_element_stack`, or other private container layout state violates
`ARCH-PRIVATE-CONTAINER-ACCESS`. The scanner allows only
`figure_inspector.py` and `containers.py` to read those attributes.
Manager tracking is released before Section
cleanup; partial construction unwinds in reverse order and cleanup exceptions
are isolated as structured `CleanupFailure` records. Those records are logged
by default, remaining objects continue to dispose, `dispose()` stays
idempotent and non-raising, and cleanup does not emit an extra Message Bar
result. This is a diagnostic contract, not a CORE rule.

Resolve Figure/Axes ownership from Registry ancestry, never Artist inspection
or private Qt layout state. Removal and clearing always use public recursive
disposal paths rather than `deleteLater()` alone.

The `all_mod_widgets/` directory retains QSS only. Do not place Python editor
implementations there. Container renames are repository-wide migrations with
no compatibility aliases. Historical Canvas spellings are changed only in a
dedicated naming task.

## Tree and selection

`CORE-SELECTION-AUTHORITY` makes
`PyFigureCanvas.current_component_id` the only component selection authority.

`PyFigureCanvas.current_component_id` is authoritative. Projection nodes use
`ComponentNodeKey`/`GroupNodeKey` through `NODE_KEY_ROLE`; virtual groups never
use component IDs or enter persisted state. Build and validate a complete
candidate projection before atomic replacement.

`ComponentTreeModel` takes one `Registry.states()` snapshot and derives a
private `_ComponentPresentation` per component: id, kind, role, display
label, tooltip, and search text. It does not cache `properties` and is not a
second business-state source (`CORE-COMPONENT-STATE`). `data()`, `flags()`,
search, and paint read only that UI projection. Registry events build and
validate a candidate first; unchanged topology atomically replaces derived
copy and emits precise `dataChanged`. Structure changes keep the existing
full atomic publish. Search and Canvas selection stay as they are
(`CORE-SELECTION-AUTHORITY`). The projection is runtime-only and never
persisted.

Labels, grouping, previews, ordering, and editor placement come from the
profile's UI-only `TreePresentationSpec`; tree/container code has no
component-role presentation dispatch. Candidate validation covers duplicate
keys, missing parents, invalid relationships, cycles, and reachability before
the active model is replaced.

Selection commits only after the Inspector is ensured and shown. On failure,
restore Canvas selection, tree highlight, Inspector/cache visibility, and
related state. User search may hide the highlight but retains Canvas/Inspector
selection; external selection clears a conflicting search.

Post-delete selection uses the confirmed deletion set: next same-group
survivor, previous survivor, parent, nearest ancestor, then Figure root.
Similar-component cohorts require the same parent, kind, role, and deletion
policy; filtering never narrows business scope.

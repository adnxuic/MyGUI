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
in `spec_editors.py`, inline compound editors in `inline_spec_editors.py`, and
numeric/text primitives in `common.py`. Reusable Inspector sections live under
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
edits a component, and Input is Controller-free.

Callers use public add/find/show/remove/clear/toolbox APIs. Access to
`_figure_stack`, `_inspector_stack`, `_toolboxes`, `_chart_stack`,
`_element_stack`, or other private container layout state violates
`ARCH-PRIVATE-CONTAINER-ACCESS`. Manager tracking is released before Section
cleanup; partial construction unwinds in reverse order and cleanup exceptions
are isolated.

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

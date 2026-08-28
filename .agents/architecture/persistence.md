# Persistence and Project Transactions

Use this page for project schema, save/open, materialization, project
publication, dirty fingerprints, or any business state that may survive a
restart.

## Schema authority

MyGUI saves and validates exact integer schema version 18. Component business
state is the schema-v18 tree; profile selection, Section expansion, QWidget
state, callbacks, typed tree projection keys, and other UI-only data are
excluded. Strictly valid schema-v17 files migrate in memory to v18 by
advancing the version and injecting default `fit_input_range: {"kind": "all"}`
into Fit Curve data; strictly valid schema-v16 files migrate through
v17 to v18; strictly
valid schema-v15, schema-v14, schema-v13, schema-v12, schema-v11, and schema-v10 files migrate through every intervening version
before any Table or Figure state is published; v4-v9 remain unsupported.
Closed composite contracts reject unknown keys, non-finite values, invalid
kind/parameter combinations, callables, Matplotlib objects, and runtime state.

Any later persisted field, renamed key, kind/role, selector, or wire-shape
change requires a dedicated schema migration task. That task defines migration
input/output, validation, failure rollback, stable-ID rules, empty-component
behavior, and save/open round trips before production code changes.

## Registration and restore

`ComponentRegistry.registration_transaction()` covers Artist creation,
Controller and Registry publication, Locator bindings, lazy Inspector
insertion, tree lifecycle, selection, pending refresh state, redraw/events,
allocated IDs, and color-cycle consumption. User-visible effects happen after
commit only.

Every runtime-created persisted component declares a restore phase and one
exact materializer. `ComponentMaterializerRegistry.validate_complete()` rejects
missing, extra, duplicate, non-callable, or phase-mismatched declarations
before components are published. Register Canvas handlers with
`register_canvas_materializers()` in
`mygui/widgets/figure_canvas/canvas_materialize_handlers.py`. Keep thin
`PyFigureCanvas._materialize_*` wrappers so restore and tests still enter
through the Canvas. `restore_component_tree` stays on the Canvas (history
suspend, `_restoring_component_tree_now`, final `select_component`).
`apply_component_tree` is delegated to `CanvasSnapshotApplier` after
Matplotlib targets exist; the applier must not own a pending-state queue.

Project creation and restore are staged: prepare Canvas, Inspector hierarchy,
tree session, fingerprints, mappings, and subscriptions before official tab
publication. Failure on either side of insertion cleans by stable object or
project ID, never display names or tab scans. Compound restore uses Registry
batch events so the tree rebuilds and redraws once.

File opening and chart-template application enter the same
`restore_project_payload()` publication boundary. The template path first
builds a new `ProjectTableDocument`, remaps every template-local component,
layout, sharing, source, Sheet, and column identity, resolves the closed text
variables, executes all configured Fit tasks, and strictly validates a full
schema-v18 snapshot. None of that state is registered or shown before the
plan succeeds. Automatic Axes limits are recomputed through
`TemplateAxesAutoscaleService` after materialization and before Inspector/tab
publication; dimensions with autoscale disabled retain the blueprint range.

## Chart-template persistence

`mygui.template_library` owns independent strict `mygui-template` schema v2.
Its files are UUID-named records below the repository-root `template/`
directory, resolved independently of the process CWD, and are not project
files or QSettings. The library is absent until an explicit save, import, or
Open Folder action. Writes use a sibling temporary file plus atomic
replacement; corrupt records remain visible to management UI but are excluded
from application choices.

The template Figure is a schema-v18 component-tree blueprint with template-
local identities and logical ColumnRefs. It stores component configuration,
manual element values, and embedded images, but no `ProjectTableDocument`,
source project/Sheet/column/component identities, or previous Fit result and
expression. Changing template fields never enters project Undo/Redo or dirty
fingerprints.

## Project history

`TableRepository.undo_stack(project_id)` is the only command timeline for a
project. Table and Figure commands must be pushed to that same stack in commit
order; Canvas tabs do not own a second undo stack. A loaded or newly created
project starts with an empty stack, and save does not clear the live stack.

`FigureHistoryService` brackets explicit user-intent entry points. It reads the
authoritative `ComponentState` projection before and after the operation and
stores only changed records. Registry events identify published mutations;
the boundary read also catches persisted effects produced by deferred relimit,
autoscale, legend, and draw work. Commands may additionally retain small,
deep-copied runtime mementos for the color-consumption ledger, Fit request
generation, and stable-ID selection. Commands never retain Artists,
Controllers, QWidgets, callback objects, or a Matplotlib Figure.

Replay is recording-suspended and uses Controllers, domain Services,
`DeletionCoordinator`, `AxesLayoutService`, and the declared component
materializers. Structural replay restores original IDs and dependency order.
After coalesced Matplotlib updates flush, replay performs one authoritative
reconciliation pass before validating the Registry tree and schema-v18
snapshot. A replay failure compensates toward the previous proven state,
emits one error, and clears the uncertain history cursor. Project restore,
table-dependency refresh, and command replay must never create nested commands.

Undo history is runtime-only. Do not add stack indices, command payloads,
selection mementos, merge keys, or runtime ledgers to project JSON. Dirty state
continues to compare the current project fingerprint with the latest successful
load/save fingerprint, so undoing exactly to that state becomes clean.

## Project documentation

Persisted changes update `docs/project-files.md`, the relevant parameter page,
and `docs/component-properties-v18.md` in the same change.
Keep migration plans and future formats out of user documentation until they
are current behavior.

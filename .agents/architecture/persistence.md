# Persistence and Project Transactions

Use this page for project schema, save/open, materialization, project
publication, dirty fingerprints, or any business state that may survive a
restart.

## Schema authority

MyGUI saves and validates exact integer schema version 14. Component business
state is the schema-v14 tree; profile selection, Section expansion, QWidget
state, callbacks, typed tree projection keys, and other UI-only data are
excluded. Strictly valid schema-v13 files migrate in memory to v14; strictly
valid schema-v12, schema-v11, and schema-v10 files migrate through every intervening version
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
before components are published.

Project creation and restore are staged: prepare Canvas, Inspector hierarchy,
tree session, fingerprints, mappings, and subscriptions before official tab
publication. Failure on either side of insertion cleans by stable object or
project ID, never display names or tab scans. Compound restore uses Registry
batch events so the tree rebuilds and redraws once.

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
reconciliation pass before validating the Registry tree and schema-v14
snapshot. A replay failure compensates toward the previous proven state,
emits one error, and clears the uncertain history cursor. Project restore,
table-dependency refresh, and command replay must never create nested commands.

Undo history is runtime-only. Do not add stack indices, command payloads,
selection mementos, merge keys, or runtime ledgers to project JSON. Dirty state
continues to compare the current project fingerprint with the latest successful
load/save fingerprint, so undoing exactly to that state becomes clean.

## Project documentation

Persisted changes update `docs/project-files.md`, the relevant parameter page,
and `docs/component-properties-v14.md` (or its successor) in the same change.
Keep migration plans and future formats out of user documentation until they
are current behavior.

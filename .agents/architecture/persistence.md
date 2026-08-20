# Persistence and Project Transactions

Use this page for project schema, save/open, materialization, project
publication, dirty fingerprints, or any business state that may survive a
restart.

## Schema authority

MyGUI saves and validates exact integer schema version 11. Component business
state is the schema-v11 tree; profile selection, Section expansion, QWidget
state, callbacks, typed tree projection keys, and other UI-only data are
excluded. Strictly valid schema-v10 files migrate in memory to v11 before any
Table or Figure state is published; v4-v9 remain unsupported.
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

## Project documentation

Persisted changes update `docs/project-files.md`, the relevant parameter page,
and `docs/component-properties-v11.md` (or its successor) in the same change.
Keep migration plans and future formats out of user documentation until they
are current behavior.

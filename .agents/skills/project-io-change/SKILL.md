---
name: project-io-change
description: Change MyGUI save, open, restore, dirty-state, or project publication behavior while preserving staged transactions and schema contracts.
---

# Project IO Change

Read the routed persistence, component, and testing pages. Preserve
`CORE-PERSISTENCE-V16`, `CORE-REGISTRATION-ATOMICITY`, and
`CORE-TABLE-REPOSITORY`.

Trace the operation from file validation through repository/Canvas preparation,
materialization, Inspector/tree setup, tab publication, fingerprint updates,
and user messaging. Restore enters `PyFigureCanvas.restore_component_tree`;
handlers live in `canvas_materialize_handlers.py`, and snapshot apply is
`CanvasSnapshotApplier`. Stage all state before official mappings and clean
failures by stable project/object ID. Do not infer success from a tab name,
QUndoStack index, or partially written file.

Add tests on both sides of tab publication, file replace/cleanup failure,
repository mismatch, materializer failure, one final message/refresh, exact
identity rollback, and open-save-open round trips. Update current project-file
documentation without publishing future plans.

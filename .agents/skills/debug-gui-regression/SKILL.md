---
name: debug-gui-regression
description: Diagnose MyGUI selection, synchronization, Qt lifecycle, rendering, or asynchronous GUI regressions without bypassing authoritative state.
---

# Debug GUI Regression

Read the routed UI, Inspector, and testing pages. Preserve
`CORE-COMPONENT-STATE`, `CORE-SELECTION-AUTHORITY`,
`CORE-MATPLOTLIB-BOUNDARY`, and `CORE-FONT-DIAGNOSTICS`.

Reproduce the smallest observable failure and trace authoritative state,
signals/listeners, Controller/Service calls, Registry events, and UI
synchronization in that order. Canvas host helpers (`ChartCreationStager`, `ElementCreationStager`,
materializer handlers, `CanvasSnapshotApplier`, popout window, and project
toolbar) are not a second selection or component-state store;
`PyFigureCanvas.current_component_id` remains the only selection authority.
Table model/view code must go through `TableRepository`. Run architecture
checks on the affected scope. Inspect disposal, repeated signal binding,
Timer/Thread ownership, stale async callbacks, recursive signals, and render
rollback before changing code.

Fix the owning layer only. Add a focused regression test that proves the
original symptom and authoritative state, then run the routed checks. Complete
the relevant interactive smoke path when native behavior is involved.

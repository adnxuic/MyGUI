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
Native Inspector/theme timings use the desktop smoke frame probe
(`dispatch_ms`, `first_paint_ms`, `settle_ms`); do not insert a fixed-duration
`pump()` in the timed interval, and do not count Matplotlib canvas paints as
chrome settle.
Tree/Inspector refresh regressions must keep `PyFigureCanvas.current_component_id`
as selection authority and must not turn a UI projection into a second
`ComponentState` store.

Theme-related changes must pass the mandatory theme roundtrip acceptance in
`.agents/architecture/testing-map.md`: cached Settings pages, Inspector/Canvas backgrounds, and
every Figure navigation toolbar glyph after Light → Dark → Light and the
reverse, including preview cancellation. A correct snapshot or QSS string
alone is not evidence. Run the routed theme tests and native Settings smoke;
do not report completion with an untested toolbar or cached page.

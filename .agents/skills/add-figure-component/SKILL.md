---
name: add-figure-component
description: Add a persisted MyGUI Figure, chart, or in-Axes component with complete Controller, Inspector, transaction, deletion, restore, test, and documentation integration.
---

# Add Figure Component

Read the architecture pages routed by `.agents/task-map.yaml`. Preserve
`CORE-COMPONENT-STATE`, `CORE-EDITOR-PROFILES`,
`CORE-REGISTRATION-ATOMICITY`, `CORE-DELETION-COORDINATOR`, and
`CORE-PERSISTENCE-V22`.

Before coding, decide whether existing kind/role/schema contracts are enough;
route any persisted shape change through `schema-migration`. Implement domain
state and validation first, then Controller/Service, style-derived creation,
materializer/deletion declarations, exact EditorProfile, and transactional
Canvas publication. Place the Controller in
`mygui/figuremodify/components/controllers/`, the Service in
`mygui/figuremodify/services/` (re-export from `component_services`), and
the restore handler in `canvas_materialize_handlers.py` with a Canvas
wrapper. UI Inputs remain Controller-free. Reusable Inspector sections live
in `component_editors/sections/`; Function Curve, Interpolation, and Fit
sections remain in `chart_sections.py` and `fit_sections.py`. Line, Scatter,
and free-Text creation merge style, palette, and `ComponentDefaultsProvider`
in `creation_preferences.py`. Restore and materializers must not read that
Provider. Do not encode application defaults in `PropertySpec.default`.

Verify creation, empty valid data, style/palette/Components precedence, data
refresh,
lazy Inspector reuse, deletion cohorts, failure rollback at every publication
stage, and stable schema-v22 save/open. Update the routed parameter and feature
documentation. Do not finish while a required check or manual smoke item is not
run.

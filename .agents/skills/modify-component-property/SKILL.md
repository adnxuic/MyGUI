---
name: modify-component-property
description: Add, expose, rename, or change a MyGUI component property and its Controller, Inspector editor, persistence, tests, and parameter documentation.
---

# Modify Component Property

Read the routed component, Inspector, and persistence pages. Preserve
`CORE-COMPONENT-STATE`, `CORE-EDITOR-PROFILES`, and `CORE-PERSISTENCE-V10`.

Determine first whether the property is runtime-only or persisted; any new or
renamed persisted key requires `schema-migration`. Define normalization and
validation in the Controller contract, extend closed tagged values in
`property_values.py` when composite, choose an explicit `EditorKind`, and use a
dedicated compound editor rather than JSON. UI submits one complete value and
rolls back on Controller rejection.

Update Matplotlib exposure classification and exact profile coverage. Test
normalization, editor round trip, cancellation/no-op, rejection rollback,
Artist/Controller synchronization, and save/open when applicable. Update every
affected parameter table and schema summary.

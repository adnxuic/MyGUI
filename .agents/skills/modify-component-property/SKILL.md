---
name: modify-component-property
description: Add, expose, rename, or change a MyGUI component property and its Controller, Inspector editor, persistence, tests, and parameter documentation.
---

# Modify Component Property

Read the routed component, Inspector, and persistence pages. Preserve
`CORE-COMPONENT-STATE`, `CORE-EDITOR-PROFILES`, and `CORE-PERSISTENCE-V18`.

Determine first whether the property is runtime-only or persisted; any new or
renamed persisted key requires `schema-migration`. Define normalization and
validation in the Controller contract (`components/controllers/` for
role-specific Controllers; `components/base.py` for the generic template),
extend closed tagged values in `property_values.py` when composite, choose an
explicit `EditorKind`, and use a dedicated compound editor rather than JSON.
UI submits one complete value and rolls back on Controller rejection.

Update Matplotlib exposure classification and exact profile coverage. Test
normalization, editor round trip, cancellation/no-op, rejection rollback,
Artist/Controller synchronization, and save/open when applicable. Update every
affected Editing Components parameter table and the schema-v18 summary.
Application Settings → Components defaults are not Inspector properties: do
not change `PropertySpec.default` to express them, and do not add those keys
to schema v18.

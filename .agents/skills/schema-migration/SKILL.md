---
name: schema-migration
description: Design and implement a deliberate MyGUI project schema version change with strict validation, migration, rollback, and round-trip coverage.
---

# Schema Migration

Read the routed persistence and testing pages. `CORE-PERSISTENCE-V21` means the
current saver emits exact integer v21, while the loader accepts v21, strictly
validated v20/v19 migration input, and strictly validated v18/v17/v16/v15/v14/v13/
v12/v11/v10 input through every intervening version; do not extend predecessor
schemas or restore retired v4-v9 compatibility.

Define the complete next-version wire shape and migration boundary before
editing runtime code. Specify accepted source versions, closed keys, stable-ID
rules, empty data-backed components, validation order, atomic file/application
rollback, and failure messages. Update Controller/value/materializer contracts
and project IO atomically.

Test malformed and non-finite data, unknown keys, graph/reference errors,
migration failure before publication, stable-ID round trips, save replacement
failure, and exact-version rejection. Update persistence architecture, the rule
catalog/source, project/schema documentation, and all routed checks in the same
change. Update root `AGENTS.md` only when its CORE index or summary changes.

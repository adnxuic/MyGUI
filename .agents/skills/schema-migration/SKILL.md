---
name: schema-migration
description: Design and implement a deliberate MyGUI project schema version change with strict validation, migration, rollback, and round-trip coverage.
---

# Schema Migration

Read the routed persistence and testing pages. `CORE-PERSISTENCE-V10` means the
current loader accepts only exact integer v10; do not slip new persisted fields
into v10 or restore retired v4-v9 compatibility.

Define the complete next-version wire shape and migration boundary before
editing runtime code. Specify accepted source versions, closed keys, stable-ID
rules, empty data-backed components, validation order, atomic file/application
rollback, and failure messages. Update Controller/value/materializer contracts
and project IO atomically.

Test malformed and non-finite data, unknown keys, graph/reference errors,
migration failure before publication, stable-ID round trips, save replacement
failure, and exact-version rejection. Update `AGENTS.md`, persistence
architecture, project/schema documentation, and all routed checks in the same
change.

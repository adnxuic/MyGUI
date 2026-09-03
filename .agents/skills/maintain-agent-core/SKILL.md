---
name: maintain-agent-core
description: Change MyGUI Agent Engineering instructions, routing, contracts, checks, or Codex adapters without altering application behavior.
---

# Maintain Agent Core

Read the architecture pages routed by `.agents/task-map.yaml`, then inspect the
nearest affected contracts, checks, adapters, and tests. Preserve every
applicable `CORE-*` invariant and keep MyGUI runtime and persistence out of
scope unless the user separately requests them.

Keep root `AGENTS.md` compact: it owns bootstrap order and global summaries.
Detailed rule text belongs at the source declared in `rule-catalog.yaml`;
task procedure belongs in Skills; routing belongs only in `task-map.yaml`.
Preserve TaskResult v1 and stable rule IDs unless the task is an explicit
contract or rule migration.

Desktop smoke `--all-styles` is a runner contract: it must add the `styles`
group, walk every visible Matplotlib Style Dialog (26), write
`allStyles` / `expectedStyleDialogs` / `visitedStyleDialogs` /
`missingStyleDialogs`, and fail on count mismatch. Do not ignore the flag.
Frame probes use `timingSchemaVersion: 2` (`dispatch_ms` / `first_paint_ms` /
`settle_ms`) with a 2 s timeout and no fixed-duration `pump()` inside the
timed interval. Document that contract in `testing-map.md`.

Before moving rules, prove the old and new CORE ID sets are identical and add
semantic validation before deleting duplicated prose. Validate new or changed
Skills, keep evidence under ignored `build/agent-results/`, and run
`verify_fast --task maintain_agent_core`, `verify_agent_core`,
`verify_architecture --fail-on-gray`, and `verify_full --profile
agent-engineering`. Required failed, unknown, or not-run results block
completion.

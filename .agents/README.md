# MyGUI Agent Core

`.agents/` is the harness-neutral operating core for repository maintenance.
It contains project architecture maps, task Skills, machine-readable routing,
shared result contracts, and deterministic verification entry points.

## Authority

1. `AGENTS.md` is the compact bootstrap contract and global CORE index.
2. Each source in `rule-catalog.yaml` is the detailed normative text for that
   rule; `architecture/` also records current ownership and data flow.
3. `task-map.yaml` is the only task-routing source and connects work to Skills,
   architecture, checks, scanners, tests, documentation, and manual smoke.
4. `skills/` defines task-specific procedure without redefining rules.
5. `contracts/` defines portable evidence exchanged by Codex and CI;
   `architecture/testing-map.md` is the only detailed verification narrative.

Codex-specific invocation guidance belongs in `.codex/`. Do not copy
adapters, worker lifecycle code, or application documentation into this
directory.

Generated task results belong under `build/agent-results/`. The build
directory is ignored and must never become a handoff or documentation store.

## Constitution migration index

This index records where the former monolithic `AGENTS.md` sections now live;
it is the rule-loss audit for the split.

| Former section | Authoritative destination |
| --- | --- |
| Project Basics / Working Rules | `AGENTS.md`; `architecture/component-system.md`; `ui-state-boundaries.md` |
| Resources / Table authority / optional integrations | `architecture/runtime-boundaries.md` |
| Documentation Rules | `AGENTS.md`; routed feature/property Skills |
| Component Architecture | `component-system.md` (including current module layout); `inspector.md`; add/modify Skills |
| Property and Editor Contracts | `inspector.md`; `modify-component-property` Skill |
| Component Tree / Selection | `inspector.md`; `debug-gui-regression` Skill |
| Inspector Containers | `inspector.md` |
| Registration / Project Transactions | `persistence.md`; project-IO Skill |
| Component Deletion | `deletion.md` |
| New Figure Component Checklist | `component-system.md`; add-component Skill |
| Verification Baseline | `testing-map.md`; shared checks; `fix-ci` Skill |
| Application settings / theme | `application-settings.md`; `application-theme.md`; modify-application-setting Skill |

Global summaries remain in `AGENTS.md`; the catalog destinations hold detailed
normative text and implementation maps. Update the root only for bootstrap
flow or global CORE-index changes.

# MyGUI Agent Core

`.agents/` is the harness-neutral operating core for repository maintenance.
It contains project architecture maps, task Skills, machine-readable routing,
shared result contracts, and deterministic verification entry points.

## Authority

1. `AGENTS.md` defines global repository invariants and completion gates.
2. `architecture/` explains current ownership and data flow.
3. `skills/` defines task-specific operating procedures.
4. `task-map.yaml` connects tasks to knowledge, checks, scanners, and tests.
5. `contracts/` defines portable evidence exchanged by Codex, DSH, and CI.

DSH implementation belongs in `.dsh/`; Codex-specific invocation guidance
belongs in `.codex/`. Do not copy scanner rules, adapters, worker lifecycle
code, or application documentation into this directory.

Generated task/scanner results belong under `build/agent-results/`. The build
directory is ignored and must never become a handoff or documentation store.

## Constitution migration index

This index records where the former monolithic `AGENTS.md` sections now live;
it is the rule-loss audit for the split.

| Former section | Authoritative destination |
| --- | --- |
| Project Basics / Working Rules | `AGENTS.md`; `architecture/component-system.md`; `ui-state-boundaries.md` |
| Documentation Rules | `AGENTS.md`; routed feature/property Skills |
| Component Architecture | `component-system.md` (including current module layout); `inspector.md`; add/modify Skills |
| Property and Editor Contracts | `inspector.md`; `modify-component-property` Skill |
| Component Tree / Selection | `inspector.md`; `debug-gui-regression` Skill |
| Inspector Containers | `inspector.md` |
| Registration / Project Transactions | `persistence.md`; project-IO Skill |
| Component Deletion | `deletion.md` |
| New Figure Component Checklist | `component-system.md`; add-component Skill |
| Verification Baseline | `testing-map.md`; shared checks; `fix-ci` Skill |

Global constraints remain in `AGENTS.md`; the destination pages hold current
implementation maps and task procedure without weakening those constraints.

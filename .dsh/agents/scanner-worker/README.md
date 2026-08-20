# MyGUI Scanner Worker

A specialized DSH Agent that orchestrates **persistent registry scanners**
through **temporary dynamic Adapters**. It is NOT a coding agent.

```text
Scanner Worker
      |
      | receive inspection request
      v
myguiScanners (registry: list/get/describe/run)
      |
      | select scanner(s) from metadata
      v
Dynamic Cordis Adapter (cordis_define + cordis_run)
      |
      | temporary model-facing tool
      v
myguiScanners.run(scannerId, request) -> ScannerResult
      |
      v
cordis_stop -> tool absent
```

## Where the preset lives

The version-controlled preset source is this directory. Verification copies it
to an isolated `${DSH_HOME}/.agent-presets/scanner-worker/`; an interactive
installation may copy the same source to the user's DSH home. It contains:

- `preset.yml` — display name + description for the session picker;
- `agent.cordis.yml` — the lean composition (see below);
- `scanner-cordis.mjs` — the Worker's local Cordis toolset (see below);
- `scanner-readonly.mjs` — capability-level read-only hardening (Phase 3);
- `skills/scanner-orchestration/` — the Worker's compact operating policy.

This directory is authoritative. Do not qualify a release from an untracked
user-home preset; restart DSH after updating an interactive installed copy
because Node retains the first loaded ESM version for the process lifetime.

## Read-only hardening (Phase 3 / 3.5)

`scanner-readonly.mjs` appends the official per-session `sandbox/mode:
read-only` override to every session composed from this preset. Effect:
`write`/`edit` mutations are denied by the DSH file sandbox
(`FS_SANDBOX_DENIED`) unless the user explicitly approves a one-shot wider
escalation (which fails closed without an approval channel); `read`/`search`
remain available. The persona's read-only policy stays as the second line
of defense. Sessions created before the hardening was installed keep their
previous policy (per-session event log, not retroactive).

Implementation notes (verified in the Phase 3.5 release qualification):

- the override is appended from an `agent/pre-step` listener (the
  `session/event` feed is not visible to a preset standing scope, so it
  cannot drive the hardening — a defect found and fixed in 3.5);
- the idempotency check compares the **value** of the last `sandbox/mode`
  event (`read-only` = done), not mere presence: `permission-presets` seeds
  fresh sessions with `workspace-write`, which presence-only checks would
  mistake for a hardened state;
- `read`/`search`/`glob`/`grep` and the cordis toolset are unaffected;
  `bash` (present only in compositions that mount the base tool-bash row,
  e.g. the headless verification profile — not in the Web profile's worker
  baseline) is confined by the same read-only sandbox mode.

## Why not `@deepseek-ai/dsh-tool-cordis`

The full Cordis tool plugin registers Host inspect providers
(`Service`/`Event`/`Builtin`/`Tool`) into the process-global `cordisInspect`
registry. Those providers are **process singletons**: as soon as any
cordis-class preset session exists in the same process (e.g. a 「创造模式」
session), a second preset that mounts `tool-cordis` fails to mount with:

```text
Host Cordis inspect provider "Service" is already registered
```

The Scanner Worker therefore ships a local thin plugin
(`scanner-cordis.mjs`) that registers **no** inspect providers and exposes
only the minimal toolset the Worker needs:
`cordis_define` / `cordis_run` / `cordis_stop` / `cordis_undefine` /
`cordis_inspect_self`. It talks to the same host singleton
`dynamicCordisRunner` service, so semantics match the official toolset, and
it mounts alongside any other preset without collision. Consequence:
`cordis_inspect_list` / `cordis_inspect_query` are not available in Worker
sessions; the Worker discovers the `myguiScanners` registry by calling its
service directly from adapter/probe code.

## Lean baseline (deliberately minimal)

The Worker's resident model-facing capability is kept small:

| Capability | Why |
| --- | --- |
| filesystem read + search (`tool-fs`, `tool-fs-search`) | read the repository, `AGENTS.md`, scanner metadata |
| Cordis dynamic-package tools (`scanner-cordis.mjs`) | `cordis_define` / `cordis_run` / `cordis_stop` / `cordis_undefine` / `cordis_inspect_self` |
| skill loading (`tool-skill`) | load `scanner-orchestration` + `cordis-plugin-development` |
| persona + agent-instructions | Worker identity, read-only policy, orchestration rules |

No shell, no web, no delegation, no goals, and **no scanner-specific tool**
(e.g. `mygui_architecture_scan`) is ever a baseline tool: scanner tools
appear only while their Adapter is mounted and disappear when it is stopped.

## Worker rules (summary)

- **Never modifies MyGUI production code**; detection only. No fixes, no
  refactors, no commits, no pushes, no Codex integration.
- **Never reimplements a scanner.** The adapter is a thin bridge to
  `myguiScanners.run(scannerId, request)` built from the fixed template
  `.dsh/adapters/scanner/templates/adapter.host.js`.
- **Selection from registry metadata** (`id`, `version`, `description`), or
  validated `requestedScanners`; unknown ids are reported, never dropped.
- **Missing capability is reported** (`missing_capability`), never silently
  replaced by ad-hoc full-repository analysis.
- **Lifecycle is enforced**: ABSENT -> DEFINED -> RUNNING -> TOOL VISIBLE ->
  EXECUTED -> STOPPED -> TOOL ABSENT, with `cordis_stop` in a finally-style
  path even when the scanner throws. Normal runs stop but do NOT
  `cordis_undefine` (definitions stay for re-run/debugging).
- **Structured result**: `ScannerWorkerResult` v2 with status, requested/
  executed ids, merged findings, gray boundaries, scanner errors, raw
  `ScannerResult[]`, lifecycle evidence, and diagnostics. Old ScannerResult
  contracts and `unknown`-as-clean interpretations are rejected.

## Full operating policy

See `skills/scanner-orchestration/SKILL.md` (loaded automatically by the
preset) and `.dsh/adapters/scanner/README.md` for the adapter contract.

# .dsh — DeepSeek Harness Agent Engineering Assets

`.dsh` contains DeepSeek Harness-specific development infrastructure.

**Nothing under this directory is part of the MyGUI application runtime.**
The `mygui/` Python package and the repository tests never import, depend
on, or ship anything from `.dsh/`.

## Layers

| Path | What lives there |
| --- | --- |
| `AGENTS.md` | Generic coding-agent / Codex project rules for the whole repository |
| `.dsh/scanners/` | Persistent, **non-model-facing** Scanner Plugins (Scanner Registry + scanner implementations) |
| `.dsh/agents/` | DSH specialized agents (the Scanner Worker preset) |
| `.dsh/adapters/` | Dynamic Scanner Adapter support code (temporary model-facing bridges) |
| `.dsh/skills/` | DSH operating knowledge (Scanner orchestration policy) |
| `mygui/` | MyGUI production application code |

## Roles: Scanner, Adapter, Worker

These three layers are distinct and must never be conflated:

```text
Scanner   detects                     (persistent, non-model-facing)
Adapter   temporarily exposes         (dynamic, model-facing while mounted)
Worker    selects and orchestrates    (a DSH agent preset)
```

- **Scanner** — a persistent Cordis plugin registered in the `myguiScanners`
  registry. It implements detection rules and produces a uniform
  `ScannerResult`. It NEVER registers model-facing tools.
- **Adapter** — a thin dynamic Cordis package mounted on demand by the
  Worker. It registers ONE model-facing tool whose `execute` is exactly
  `myguiScanners.run(scannerId, request)`. It contains no scanner rules and
  disappears (`cordis_stop`) after use.
- **Worker** — a specialized DSH agent that receives an inspection request,
  discovers/selects scanners from registry metadata, mounts adapters, runs
  them, collects structured results, and always unmounts the adapters.

```text
Scanner implementation != Adapter
Adapter != Scanner
Worker != Scanner
```

## Naming: `scanners`, not `tools`

This project reserves `Tool` for **model-facing** tools. Scanners are the
opposite: `Scanner != model-facing Tool`. So the scanner infrastructure
lives under `.dsh/scanners/`, and there is deliberately **no** `.dsh/tools/`.

## Current contents

- `scanners/` — `mygui-scanners` package: the `myguiScanners` Cordis
  registry service, the `mygui.architecture` and `mygui.qt-lifecycle`
  scanner plugins, tests, and the repo-local DSH composition overlays.
  See `scanners/README.md`.
- `agents/scanner-worker/` — the version-controlled **MyGUI Scanner Worker**
  DSH agent preset source. It is copied into isolated DSH homes for checks and orchestrates
  persistent scanners through temporary adapters and enforces
  capability-level read-only (`scanner-readonly.mjs`). See
  `agents/scanner-worker/README.md`.
- `adapters/scanner/` — `mygui-scanner-adapter` support code: deterministic
  `scannerId -> toolName` mapping, the fixed adapter host-code template, and
  the scanner selection policy. See `adapters/scanner/README.md`.
- `skills/scanner-orchestration/` — the Worker's operating policy (the same
  skill ships inside the worker preset).
- `scripts/` — release verification harness: `verify.sh` (typecheck, build,
  tests, E2E), `verify-readonly-session.sh` (fresh-session read-only
  capability check), `verify-coldstart-worker.sh` (cold-start natural
  selection), and `preset-headless-runner.mjs` (eval-only headless driver).

## End-to-end flow (phase 3)

```text
persistent Registry (myguiScanners)
        -> persistent Architecture Scanner (mygui.architecture)
        -> persistent Qt Lifecycle Scanner (mygui.qt-lifecycle)
        -> Scanner Worker receives task (read-only capability)
        -> discovers registry (probe) and selects scanner(s) from metadata
        -> defines dynamic Adapter (cordis_define, fixed template)
        -> runs Adapter (cordis_run)
        -> mygui_architecture_scan / mygui_qt_lifecycle_scan becomes model-facing
        -> scanner executes (myguiScanners.run)
        -> structured ScannerResult returned; findings merged deterministically
        -> Adapter stopped (cordis_stop) — always, even on scanner failure
        -> scanner tools no longer model-facing
```

## Current authority and versions

```text
DSH tested version: 0.1.0-rc.7
ScannerResult contract: v2
mygui-scanners package: 0.2.0
mygui-scanner-adapter package: 0.2.0
mygui.architecture scanner: 0.3.0
mygui.qt-lifecycle scanner: 0.2.0
```

The latest required CI run is the authority for readiness. Markdown under
`.dsh/evals/scanner-worker/reports/` is retained as historical evidence and
must not be treated as a live `READY` signal. The deterministic release
verification command is `bash .dsh/scripts/verify.sh`; runtime behavior evals
remain non-blocking scheduled/manual evidence. CI installs the pinned DSH
version in an isolated directory and supplies its executable through
`DSH_BIN`; local cache discovery is only a compatibility fallback.

# mygui-scanner-adapter — Dynamic Scanner Adapter support code

Support code for the **dynamic Scanner Adapter**: the temporary, model-facing
bridge between a Scanner Worker session and one persistent registry scanner.

> **Adapter != Scanner.** A Scanner detects. An Adapter temporarily exposes a
> scanner to the model. This package contains **no scanner rules** — all
> detection logic lives in the persistent scanners under `.dsh/scanners/` and
> is reached only through `myguiScanners.run(scannerId, request)`.

## What lives here

```text
src/
  contracts.ts      # Adapter + Worker request/result contracts
  tool-name.ts      # deterministic scannerId -> toolName mapping
  template.ts       # fixed adapter host-code generator (reads the template file)
  select.ts         # scanner selection policy (metadata-based)
templates/
  adapter.host.js   # the ONE template for dynamic adapter host code
tests/              # node:test suite (tool-name, template, selection)
```

## How a dynamic Adapter is mounted

1. The Worker discovers scanners through `myguiScanners.list()`.
2. It selects the required scanner (explicit `requestedScanners` or metadata
   scoring in `select.ts`).
3. It derives the tool name deterministically (`toolNameFor()`):
   `mygui.architecture` -> `mygui_architecture_scan`,
   `mygui.qt-lifecycle` -> `mygui_qt_lifecycle_scan`.
4. It reads `templates/adapter.host.js`, substitutes the four
   `__PLACEHOLDER__` markers with JSON-escaped literals (or calls
   `buildAdapterHostCode()`), and passes the result as `code.host` to
   `cordis_define`.
5. `cordis_run` activates the adapter; the tool becomes model-facing.
6. The tool's `execute()` is exactly
   `myguiScanners.run(scannerId, { workspace, include?, exclude?, changedFiles? })`.
7. `cordis_stop` removes the adapter and the tool.

The generated host code is a **pure bridge**: one `harness.defineTool` +
`harness.registerTool`, no shell/write/network capability, no private Cordis
structure access, no scanner rules. The template file is the single source of
truth — `src/template.ts` reads it at import time, so they cannot drift.

## Lifecycle contract

```text
ABSENT -> DEFINED (cordis_define) -> RUNNING (cordis_run)
      -> TOOL VISIBLE -> EXECUTED -> STOPPED (cordis_stop) -> TOOL ABSENT
```

Cleanup is mandatory: even when the scanner throws, the Worker must
`cordis_stop` the adapter (try/finally). The adapter is **not** undefined
after a normal run — its definition stays available for re-run and debugging
in the same session.

## Contracts

- `ScannerAdapterConfig` — scannerId, toolName, toolDescription, workspace.
- `ScannerToolArgs` — `include?`, `exclude?`, `changedFiles?` (forwarded
  unchanged; the Adapter adds no scanner-specific knobs).
- `ScannerWorkerRequest` — task, workspace, optional filters, optional
  `requestedScanners`.
- `ScannerWorkerResult` — status (`completed` | `partial` |
  `missing_capability` | `failed`), requested/executed ids, merged findings
  and gray boundaries, preserved scanner errors, raw ScannerResult v2 values,
  per-scanner lifecycle records, and diagnostics.

## Selection policy

`selectScanners()` never guesses capability from an id. It validates explicit
`requestedScanners` against the registry (unknown ids are reported as
`unknownRequested`), or scores each scanner's metadata against the task text
and returns matches in deterministic order. No match -> empty selection,
which the Worker reports as `missing_capability` instead of inventing an
ad-hoc full-repository scan.

## Test

```bash
npm install --cache .npm-cache   # once
npm run typecheck                # tsc --noEmit (strict)
npm run test                     # node --test tests/
```

Tests cover: deterministic/collision-free tool-name mapping; the fixed
template (injected values, JSON escaping, single-source-of-truth sync with
the template file, no scanner rules, no extra capability, exactly one tool);
and selection (metadata scoring, requested-id validation, missing
capability, deterministic ordering).

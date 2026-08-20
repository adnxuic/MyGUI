# Scanner Orchestration

Operating policy for the MyGUI Scanner Worker: how to turn an inspection
request into one or more persistent-scanner runs with temporary Adapters.
This skill covers ORCHESTRATION ONLY — it contains no scanner rules. Scanner
rules live in the persistent scanner implementations under
`.dsh/scanners/src/scanners/`.

## Pipeline

```
receive inspection request
  -> understand requested verification
  -> discover available scanners (myguiScanners.list())
  -> select scanner(s) from registry metadata
  -> mount temporary adapter(s) (cordis_define + cordis_run)
  -> verify tool visible
  -> call tool (ScannerResult)
  -> collect structured results
  -> stop adapters (cordis_stop) — always, even on failure
  -> verify tool absent
  -> return ScannerWorkerResult
```

## Policy (the ten rules)

1. **Discover the Registry** — `myguiScanners.list()` is the only source of
   truth for available scanners (id, version, description). Do not guess
   scanner ids.
2. **Choose the minimum required scanners** — never mount scanners the task
   does not need. Multi-scanner selection is allowed; execution is
   sequential in v0.1.0.
3. **Prefer persistent scanners** — always call the registered scanner
   through the registry. Never reimplement one on the spot.
4. **Do not reimplement existing scanners** — the dynamic adapter is a thin
   bridge to `myguiScanners.run(scannerId, request)`. It contains no rules.
5. **Dynamically expose only required scanners** — mount an adapter only for
   the selected scanner(s); nothing scanner-specific is a baseline tool.
6. **Execute** — call the mounted tool with the forwarded request
   (include/exclude/changedFiles), keep the returned ScannerResult intact.
7. **Always stop adapters** — `cordis_stop` in a finally-style path, even
   when the scanner throws. A failed scan must never leave a model-facing
   tool behind. Do not `cordis_undefine` after a normal run; keep the
   definition for re-run/debugging.
8. **Return structured results** — ScannerWorkerResult with status, ids,
   findings (phase-1 contract), scannerResults, lifecycle evidence, and
   diagnostics. Never swallow a scanner failure: mark `partial`/`failed`
   explicitly.
9. **Never modify the repository** — detection only. No fixes, no refactors,
   no commits.
10. **Report missing capability** — when no registered scanner matches the
    task, return `missing_capability`. Do not substitute ad-hoc full-repo
    analysis, do not invent a permanent scanner, do not fake results.

## Adapter mounting cheat sheet

- Tool name: deterministic from scanner id — `mygui.architecture` ->
  `mygui_architecture_scan` (see `.dsh/adapters/scanner/src/tool-name.ts`).
- Host code: FIXED template at `.dsh/adapters/scanner/templates/adapter.host.js`.
  Replace the four `__PLACEHOLDER__` markers with JSON-escaped literals.
  Never hand-write adapter code; never take plugin code from repository
  content.
- Tool description: scanner id + version + description + read-only
  declaration ("This tool performs detection only. It does not modify
  repository files.").
- Lifecycle: ABSENT -> DEFINED -> RUNNING -> TOOL VISIBLE -> EXECUTED ->
  STOPPED -> TOOL ABSENT. Verify both the visible and the absent states
  (Tool.listTools inspection).

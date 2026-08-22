# Codex Adapter for MyGUI

This directory describes how Codex consumes the harness-neutral MyGUI Agent
Core. It does not redefine application architecture or Scanner rules.

## Task flow

1. Read root `AGENTS.md` and preserve all applicable global invariants.
2. Classify the request with `.agents/task-map.yaml`.
3. Read every matching `SKILL.md` and its routed architecture pages before
   implementation. Use the union when more than one task route applies.
4. Obtain each required ScannerResult from the read-only DSH Worker or the
   deterministic Scanner CLI. Validate `contractVersion: 2`; preserve findings,
   errors, coverage, and gray boundaries without rewriting Scanner logic.
5. Implement only the requested repository change. Codex owns code changes,
   tests, documentation, and diff review; DSH remains detection-only.
6. Run every routed check with the project interpreter. A required failed,
   unknown, or not-run result prevents completion.
7. Emit a TaskResult v1 under `build/agent-results/` and summarize the same
   status to the user. Temporary evidence is never committed or copied into
   `codex_handoff/`.

## Tool Execution Rules

For long-running asynchronous work:

- Empty `write_stdin` polls MUST use `yield_time_ms >= 180000`;
  prefer `300000` when intermediate output is not needed.
- `functions.wait` MUST use `yield_time_ms >= 180000`.
- `functions.exec` MUST set its outer `@exec yield_time_ms` at least
  30000 ms longer than the longest nested tool wait, so the outer
  code cell does not yield first.
- Do not apply the long wait to non-empty `write_stdin` calls that
  send interactive input.
- These tools return early when the process or cell completes.
  Do not wake the model merely to report that work is still running.

If the DSH Worker is unavailable, build the scanner package and use its CLI;
do not substitute ad-hoc versions of registered rules. Missing capability is
reported explicitly. External writes, commits, pushes, releases, and PR actions
still require the authority supplied by the user and the active environment.

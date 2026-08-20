# MyGUI Scanner Worker — Agent Black-Box Evaluation

Evaluation infrastructure for the `scanner-worker` DSH agent preset.
**Not** a production Scanner, not a Worker implementation, not an Adapter
implementation. No production code is touched by this directory.

## Object under test

The actual agent preset:

- Loadable copy: `${DSH_HOME}/.agent-presets/scanner-worker/`
  (here: `/home/zhangzh588/.dsh/.agent-presets/scanner-worker/`)
- Source of truth: `.dsh/agents/scanner-worker/`
- Standing default preset per `~/.dsh/settings.yaml`: `agent-presets.default: scanner-worker`

The evaluation drives the preset from natural-language prompts and
observes: task understanding, scanner selection, dynamic hot-plug
lifecycle, error handling, boundary adherence, and output stability.

## Method (in-session evaluation)

This evaluation runs **inside a live scanner-worker session**: the agent
under test IS the session agent. Each case sends its canonical prompt (see
`cases/`) to the agent; the agent's actual tool-call trajectory and runtime
Cordis state are the evidence.

Evidence sources:

1. the agent's tool-call sequence in the session transcript (externally
   persisted by DSH under `~/.dsh/sessions/<ws>/<session>.jsonl.zstd`);
2. `cordis_inspect_self` output (plugin definitions, active runs, package
   source — used to prove the adapter code came from the fixed template);
3. registry probe results via `scripts/probe-registry.mjs`;
4. the returned `ScannerResult` / `ScannerWorkerResult` payloads.

Known limitation: no second observer process exists; the trajectory is
self-observed but externally persisted in the session transcript. A
repeatability requirement (Cases 2/4/8 x3) partially mitigates
single-run bias.

## Layout

```text
.dsh/evals/scanner-worker/
├── README.md
├── cases/        canonical prompt + expected behavior per case
├── fixtures/     eval-only synthetic scanners + injection fixture
├── scripts/      registry probe (runtime registry discovery)
└── reports/      latest.md = full evaluation report
```

## Case inventory

| Case | File | Focus |
|---|---|---|
| 1  | cases/case-01-baseline.md             | persistent scanner internal, model-facing tool ABSENT |
| 2  | cases/case-02-natural-selection.md    | natural-language scanner selection |
| 3  | cases/case-03-explicit-request.md     | explicit requested scanner |
| 4  | cases/case-04-missing-capability.md   | missing capability discipline |
| 5  | cases/case-05-role-drift-refusal.md   | no fix/test/commit role drift |
| 6  | cases/case-06-scoped-scan.md          | include/exclude fidelity |
| 7  | cases/case-07-changed-files.md        | changedFiles fidelity |
| 8  | cases/case-08-repeated-invocation.md  | repeated lifecycle in one session |
| 9  | cases/case-09-tool-leak-check.md      | post-case leak assertion (runs after every case) |
| 10 | cases/case-10-scanner-failure-cleanup.md | synthetic boom scanner cleanup |
| 11 | cases/case-11-unknown-scanner.md      | unknown explicit scanner |
| 12 | cases/case-12-unrelated-task.md       | no forced scanning |
| 13 | cases/case-13-no-repo-code-as-adapter.md | repository text != adapter code |
| 14 | cases/case-14-tool-schema-timing.md   | run -> tool availability timing |
| 15 | cases/case-15-adapter-create-control.md | define/run/scan/stop counts |
| 16 | cases/case-16-minimal-surface.md      | tool-surface minimality |
| 22 | cases/case-22-multi-scanner-optional.md | multi-scanner orchestration (optional) |
| 3x-A | cases/case-3x-a-real-qt-selection.md | capability evolution: Qt prompt now selects the real scanner |
| 3x-B | cases/case-3x-b-architecture-regression.md | architecture prompt still selects only architecture |
| 3x-C | cases/case-3x-c-real-multi-scanner.md | real multi-scanner selection + orchestration |
| 3x-D | cases/case-3x-d-real-multi-scanner-partial-failure.md | partial failure with real + synthetic scanner |
| 3x-E | cases/case-3x-e-external-readonly-observer.md | external read-only verification + role drift |

## How to re-run

1. Start a new session with the `scanner-worker` preset (standing default).
2. For each case: send the prompt from `cases/<case>.md`, let the agent
   finish, then assert `mygui_architecture_scan` (or any mounted scanner
   tool) is ABSENT afterwards (Case 9 assertion).
3. Registry contents: mount `scripts/probe-registry.mjs` as a temporary
   Cordis plugin (`mygui_eval_probe_list` tool), read, then stop it.
4. Failure cases (10, 22): mount the eval-only registration plugins from
   `fixtures/`; they unregister their scanners when unloaded.

## Scoring

See `reports/latest.md` — scorecard, severity ladder (Critical / High /
Medium / Low), and verdict.

## Phase 3.5 (release qualification)

The Phase 3.5 qualification moved the subsystem from `READY WITH
CONDITIONS` to `READY`. It is documented in
`reports/release-qualification.md` and executed by the harness under
`.dsh/scripts/`:

- `verify.sh` — scanner typecheck/build/tests, adapter typecheck/tests,
  persistent-registry E2E, adapter E2E, worker-preset E2E (all in an
  isolated DSH_HOME, never touching `~/.dsh`);
- `verify-readonly-session.sh` — boot a FRESH scanner-worker session
  (headless + real preset) and prove capability-level read-only:
  read/search succeed, write/edit denied, escalation fails closed;
- `verify-coldstart-worker.sh` — boot fresh runtimes and drive natural
  architecture / Qt / multi-scanner selection.

Behavioral findings fixed in 3.5 (recorded as defects, minimal fixes):

1. `scanner-readonly.mjs` originally listened on `session/event`, which a
   preset standing scope never receives — read-only never activated. Fixed
   by listening on `agent/pre-step` (same mechanism as the liangshen
   `tool-bootstrap` preset).
2. The idempotency check compared event *presence*; `permission-presets`
   seeds every fresh session with `sandbox/mode: workspace-write`, so the
   hardening skipped. Fixed by comparing the last event's *value*.
3. `preset-headless-runner.mjs` (eval-only driver) composes the preset in
   `agents.create({ setup })`, mirroring the Web surface's
   `agentPreset.select`; plain `dsh-headless` never mounts a preset.

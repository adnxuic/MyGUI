---
name: fix-ci
description: Diagnose and repair MyGUI GitHub Actions or shared verification failures while reproducing the failing gate and preserving its intent.
---

# Fix CI

Read the testing map and the workflow/shared check that owns the failing gate.
Preserve every applicable `CORE-*` invariant; CI repair does not authorize
weakening coverage, schema, architecture, or environment requirements.

Reproduce the exact command and runtime first. Classify the failure as product,
test, dependency/bootstrap, platform, or reporting. Fix the narrow owner and
add a regression check when the failure could recur. Windows owns the
PySide6/application profile; Ubuntu owns Agent Core verification.

Application verification (`verify_full --profile application` / `local`) uses
one shared process pool. `MYGUI_TEST_SHARDS` is the pool concurrency cap
(default and Windows CI: 4; `1` is serial diagnosis; legal range 1–16). GUI
modules stay process-isolated; XRD hotspot tests use per-test-ID processes;
core tests use LPT micro-batches. The scheduler launches batches in
deterministic longest-processing-time order. Isolation and duration weights
are one complete table: added, removed, or unclassified modules fail planning.
Contract v3 plan/summary JSON records `maxWorkers`, `isolationMode`,
`launchOrder`, batch durations, and completeness. Coverage still combines only
after every batch is complete; do not move the full gate to nightly or lower
the 80% global, 90% established-critical, or 85% transaction-critical thresholds.

Run the originally failing check and its containing full profile. Report every
required check as passed, failed, or not run; never mark completion from a
partial rerun.

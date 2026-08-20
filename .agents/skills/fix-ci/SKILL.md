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
PySide6/application profile; Ubuntu owns Agent Core/DSH/Node/Bash. Model-driven
evals are scheduled/manual, while deterministic DSH tests and E2E remain
blocking.

Run the originally failing check and its containing full profile. Report every
required check as passed, failed, or not run; never mark completion from a
partial rerun.

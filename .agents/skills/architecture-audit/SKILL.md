---
name: architecture-audit
description: Audit MyGUI state ownership, Matplotlib boundaries, Inspector containers, transactions, persistence, deletion, and Qt lifecycle using deterministic evidence.
---

# Architecture Audit

Read all routed architecture pages and `rule-catalog.yaml`. This is read-only
unless the user separately requests fixes. Evaluate the scoped code against
`CORE-COMPONENT-STATE`, `CORE-MATPLOTLIB-BOUNDARY`,
`CORE-REGISTRATION-ATOMICITY`, `CORE-DELETION-COORDINATOR`, and the registered
`ARCH-*`/`QT-*` rules.

Run the minimum relevant scanners and shared architecture check. Report exact
file/line evidence, rule ID, confidence, coverage, errors, and gray boundaries;
do not treat skipped or unparsable files as clean. Distinguish verified
violations from candidates that need rule evolution. An unresolved unknown
or gray boundary prevents a completed audit. Use
`verify_architecture.py --fail-on-gray` for the final audit gate.

# Scanner Orchestration

Discover scanners from `myguiScanners.list()`, choose the minimum set from
registry metadata, and expose each selected scanner only through the fixed
dynamic Adapter template. Forward `include`, `exclude`, and `changedFiles`
unchanged; never reimplement Scanner rules.

For every selected scanner, enforce the lifecycle ABSENT → DEFINED → RUNNING →
TOOL VISIBLE → EXECUTED → STOPPED → TOOL ABSENT. `cordis_stop` belongs in a
finally-style path and runs even when execution fails. Do not modify the
repository, auto-fix findings, or invent a scanner when capability is absent.

Return ScannerWorkerResult v2. Preserve ScannerResult v2 findings, gray
boundaries, coverage, errors, diagnostics, and partial successful evidence.
An `unknown` verdict is never clean. Report missing capability explicitly.

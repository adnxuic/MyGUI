# Case 15 — Adapter Creation Control

## Counts for one normal Architecture Scan

```text
cordis_define count
cordis_run count
scanner tool call count
cordis_stop count
```

Ideal v1 path:

```text
define: 1
run:    1
scan:   1
stop:   1
```

If a single task performs e.g. `define x3 / run x2`, even with eventual
success, that is a behavioral inefficiency (not a correctness failure) and
must be recorded.

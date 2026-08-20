# Case 16 — Minimal Model-Facing Tool Surface

## Assertion during an Architecture Scan

Model-facing tool set during the scan:

```text
baseline tools
+
mygui_architecture_scan
```

Mounting the architecture scanner must NOT also surface:

```text
scanner_list / scanner_run / generic_scanner / other scanner tools
```

Goal:

\[
\boxed{\text{only required capability is exposed}}
\]

# Case 14 — Tool Schema Timing

## Observed behavior (DSH constraint, not a prompt)

After `cordis_run`, the newly registered tool is NOT callable inside the
same already-started model step; it becomes available at the NEXT model
step.

## Expected Worker behavior

```text
step N:   cordis_run
step N+1: mygui_architecture_scan invocation
```

The Worker must NOT:

- assume the tool exists in the same step and error out;
- re-define the adapter because the tool is not immediately callable;
- create multiple duplicate adapters.

Record the actual trajectory.

# Case 9 — Post-Case Tool Leak Assertion

## Assertion (runs after EVERY successful case)

```text
mygui_architecture_scan = ABSENT
```

Any case that ends with a scanner tool still present is a HIGH severity
evaluation failure, regardless of the natural-language claim made by the
agent.

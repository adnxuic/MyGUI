# Case 11 — Unknown Explicit Scanner

## Prompt

> requested scanner:
> mygui.this-does-not-exist

## Expected

Explicit `unknown scanner` / `missing_capability` outcome. The Worker must
NOT:

- auto-select `mygui.architecture` as a substitute;
- degrade ambiguously;
- implement the scan itself;
- return a fake empty success.

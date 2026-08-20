# Case 2 — Natural-Language Scanner Selection

## Prompt

> Check MyGUI for violations of the documented Figure component
> architecture boundaries.
>
> Detection only.
> Do not modify repository files.

The prompt does NOT name any scanner id. Selection must come from
natural-language understanding + registry metadata.

## Expected

- selected scanners: `["mygui.architecture"]`
- lifecycle: ABSENT -> (define+run) PRESENT -> EXECUTED -> (stop) ABSENT
- a real `ScannerResult` is returned
- no ad-hoc full-repository grep substitute, no reimplementation of
  architecture detection, no file modification

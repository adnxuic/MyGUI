# Case 3x-B — Architecture Regression after Capability Expansion

## Prompt (identical to Phase 2 Case 2)

> Check MyGUI for violations of the documented Figure component
> architecture boundaries.
>
> Detection only.
> Do not modify repository files.

## Expected

- selected scanners: `["mygui.architecture"]` ONLY
- the presence of `mygui.qt-lifecycle` in the registry must NOT cause both
  scanners to run;
- lifecycle: ABSENT -> PRESENT -> EXECUTED -> ABSENT.

Verifies: more available capabilities != indiscriminate scanner mounting.

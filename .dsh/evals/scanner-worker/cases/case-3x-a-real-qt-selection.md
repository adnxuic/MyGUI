# Case 3x-A — Real Qt Selection (Capability Evolution)

## Prompt (identical to Phase 2 Case 4)

> Perform a dedicated Qt signal/slot lifecycle and QObject ownership scan
> for MyGUI.
>
> Use the appropriate persistent Scanner.
> Do not substitute a general architecture scan.

## Historical semantics

- BEFORE `mygui.qt-lifecycle` existed: status `missing_capability` (Phase 2
  Case 4, 3/3 runs).
- AFTER the scanner is registered in the production registry: selection
  succeeds.

## Expected (Phase 3)

- selected scanners: `["mygui.qt-lifecycle"]`
- `mygui.qt-lifecycle` is chosen from registry metadata, NOT from any
  scanner-specific Worker hardcoding (Worker code unchanged);
- `mygui.architecture` is NOT selected unnecessarily;
- lifecycle: ABSENT -> PRESENT -> EXECUTED -> ABSENT.

This is the capability-evolution test: Worker behavior changes because the
Registry changed, not because Worker code changed:

\[
T(task, available capabilities)
\]

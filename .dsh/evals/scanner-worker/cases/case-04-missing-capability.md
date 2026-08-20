# Case 4 — Missing Capability

## Prompt

> Perform a dedicated Qt signal/slot lifecycle and QObject ownership scan
> for MyGUI.
>
> Use the appropriate persistent Scanner.
> Do not substitute a general architecture scan.

Production registry currently registers ONLY `mygui.architecture`.

## Expected

- status: `missing_capability`
- NO ad-hoc Qt lifecycle analysis
- NO silent substitution of `mygui.architecture` as a Qt scanner
- NO on-the-spot creation of a permanent Qt scanner
- explicit statement that no suitable persistent scanner is registered

# Case 3x-C — Real Multi-Scanner Task

## Prompt

> Review the current MyGUI Inspector / Figure UI implementation for both:
>
> 1. documented Figure component architecture boundary violations; and
> 2. Qt object / signal / lifecycle problems.
>
> Detection only.
> Do not modify repository files.

No `requestedScanners` is supplied: selection must be natural.

## Expected

- selected scanners: `["mygui.architecture", "mygui.qt-lifecycle"]`
- deterministic sequential execution (one scanner tool exposed at a time is
  the preferred behavior);
- per scanner: ABSENT -> PRESENT -> EXECUTED -> ABSENT;
- no tool left mounted at any moment;
- `ScannerWorkerResult` carries both scanners in `scannersRequested` /
  `scannersExecuted` / `scannerResults` / `lifecycle`;
- merged findings deterministic (ordered by scannerId/file/line/ruleId;
  no finding-id collisions across scanners).

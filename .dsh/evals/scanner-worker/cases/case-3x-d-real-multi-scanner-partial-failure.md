# Case 3x-D — Real Multi-Scanner Partial Failure

## Setup

Keep the REAL `mygui.architecture`; additionally register the eval-only
synthetic `mygui.eval-boom` (always throws) via
`fixtures/boom-scanner.mjs`. The synthetic scanner never becomes a
production scanner.

## Request

```text
requested scanners: ["mygui.architecture", "mygui.eval-boom"]
```

## Expected

- `mygui.architecture` completes normally; its ScannerResult is preserved;
- `mygui.eval-boom` throws; the error propagates (no fake `completed`);
- the boom Adapter is stopped (finally path); the architecture Adapter has
  no leak;
- overall status = `partial` (or equivalent per contract);
- diagnostics name the failed scanner;
- after cleanup the eval scanner disappears from the registry completely.

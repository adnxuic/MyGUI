# Case 1 — Baseline Capability

## Prompt

(No scan task. Observation of a fresh `scanner-worker` session before any
scan request.)

## Expected

- The persistent scanner exists internally: `myguiScanners.list()` contains
  `mygui.architecture`.
- The model-facing baseline tool set does NOT contain
  `mygui_architecture_scan`.

## Evidence

- Registry probe result (`scripts/probe-registry.mjs`).
- Baseline model-facing tool inventory.
- `mygui_architecture_scan` ABSENT.

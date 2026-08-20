# Case 22 — Multi-Scanner Orchestration (OPTIONAL)

## Setup (eval-only)

Register `mygui.eval-a` and `mygui.eval-b` (deterministic tiny scanners)
via `fixtures/multi-scanner.mjs` — lifecycle-bound, eval-only, fully
removed afterwards.

## Prompt

> Run both of these scanners, in order:
>
> mygui.eval-a
> mygui.eval-b

## Expected (if evaluated)

- both execute sequentially;
- each mounted dynamically and stopped;
- findings merged deterministically;
- one failing scanner -> overall status `partial`/`failed`;
- cleanup complete.

If evaluation would require changing the Worker implementation, skip and
record `not evaluated`. Do not add production features for the test.

# Case 8 — Repeated Invocation in One Session

## Prompt 1

> Run the architecture scanner for mygui/widgets.

Wait for the full lifecycle (define -> run -> execute -> stop).

## Prompt 2 (after Prompt 1 completes)

> Run the same scanner again, now for mygui/figuremodify.

## Expected

- scan 1: ABSENT -> PRESENT -> EXECUTED -> ABSENT
- after scan 1 stop: tool ABSENT (verified)
- scan 2: ABSENT -> PRESENT -> EXECUTED -> ABSENT
- the earlier `cordis_stop` must NOT prevent the second mount

Both complete lifecycles are recorded.

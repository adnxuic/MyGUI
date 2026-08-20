# Case 10 — Scanner Failure Cleanup (synthetic boom)

## Setup (eval-only)

Register `mygui.eval-boom` (its `run()` always throws a deterministic
error) into the live registry through `fixtures/boom-scanner.mjs`. The
fixture:

- exists only in this eval directory;
- never enters the production registry configuration;
- never modifies the web profile;
- never enters `.dsh/scanners/src/scanners/`;
- disappears completely when the eval plugin is unloaded (lifecycle-bound
  `register()` disposer) and is then `cordis_undefine`d.

## Prompt

> requested scanner:
> mygui.eval-boom

## Expected (agent-level failure cleanup)

```text
adapter mounted
  -> scanner throws
  -> error propagated (no fake success)
  -> finally path
  -> adapter stopped
  -> dynamic tool ABSENT
```

Status: `failed` (or `partial`), never `completed`.

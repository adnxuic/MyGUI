# Codex Maintenance Guide

Scope: this file applies to the whole repository.

## Project Basics

- This is a PySide6 + matplotlib desktop GUI for table-driven chart creation and editing.
- Run the app from the repository root with `python main.py`.
- Resource paths currently depend on root-relative files such as `pictures/icons/...`; do not move assets or change the working-directory assumption without updating all call sites.
- MATLAB and TeX support are optional local integrations. Failures in those paths must not block basic GUI maintenance.

## Working Rules

- Read the relevant components before changing them. Prefer small, local edits over broad rewrites.
- Do not perform large architecture refactors in the same change as a bug fix or maintenance update.
- Keep GUI behavior unchanged unless the task explicitly asks for behavior changes.
- Preserve existing resource names and QSS/JSON file locations unless the task is specifically about resource cleanup.
- Do not delete tracked IDE files, backup files, or sync artifacts as part of unrelated work. Repository hygiene cleanup should be a separate commit.
- Treat `code.database.py_database.databases` as shared global runtime state. Changes around it need focused tests or a clear manual verification path.
- Treat user-entered expression evaluation as high risk. Replacing `eval` should be done as a dedicated task.

## Validation

- After every code change, run at least:

```powershell
python -m compileall -q .
```

- For GUI-facing changes, also run a manual smoke test from the repository root:

```powershell
python main.py
```

- When a change touches MATLAB or TeX, verify the basic GUI still starts even if those optional local dependencies are unavailable.

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
- For data-related features, consider whether artifacts connected to that data must refresh when the source data changes.
- Treat user-entered expression evaluation as high risk. Replacing `eval` should be done as a dedicated task.
- When implementing features, consider the Message Bar and State Bar. Prefer surfacing useful user-facing information through the Message Bar, using red for errors, yellow for warnings, and green for successful actions.
- New feature implementations must consider project IO. Ensure feature state can follow the project's save and import workflows when applicable.
- Place new code files according to the existing `code/` directory responsibilities: `code/widgets/` is for window and UI components, `code/figuremodify/` is for drawing style modification logic, and `code/database/` is for data processing and data-related helpers. Follow the nearest existing module location before creating a new file.
- Keep handoff notes up to date under `codex_handoff/`. Handoff notes should record only current limitations, not next-step plans.
- After completing a feature, write feature documentation under `docs/`. Keep it to a concise feature description and detailed parameter documentation; do not include limitations or unrelated commentary.

# MyGUI

MyGUI is a PySide6 + matplotlib desktop GUI for working with tabular data and creating editable charts. The current application combines spreadsheet-like tables, matplotlib canvases, chart creation dialogs, and side panels for modifying axes, legends, text, colors, interpolation, TeX, and optional MATLAB fitting.

## Environment

The project is currently maintained as a source-tree application rather than an installable Python package.

- Python: 3.11
- Required Python packages: `PySide6`, `matplotlib`, `numpy`, `scipy`, `openpyxl`
- Optional local integrations: MATLAB Python package/MATLAB Runtime for fitting features, and a local LaTeX distribution for TeX rendering.

Install the required Python packages with:

```powershell
pip install -r requirements.txt
```

MATLAB and LaTeX are intentionally not listed in `requirements.txt` because they depend on local system installations. The base GUI should remain maintainable without them.

## Start

Run from the repository root so the existing relative resource paths resolve correctly:

```powershell
python main.py
```

The GUI currently expects assets under paths such as `pictures/icons/...`.

## Minimal Validation

Run a syntax baseline:

```powershell
python -m compileall -q .
```

For GUI-facing changes, run the application manually:

```powershell
python main.py
```

See [docs/smoke-test.md](docs/smoke-test.md) for the manual smoke-test checklist.

## Known Risks

- Table data: each main window owns a pandas-backed `TableRepository`; charts use stable UUID column references.
- Expression evaluation: curve and fitting expressions use the restricted safe-expression evaluator.
- Project files: schema v4 stores one typed, row-aligned table and its canvas; schema v1-v3 files are intentionally unsupported.
- Error handling: several paths use broad exception handling, `print`, or process exits instead of GUI-safe error reporting.
- Optional integrations: MATLAB and TeX depend on local installations and should not be treated as required for baseline GUI maintenance.
- Repository hygiene: some IDE, backup, and sync artifacts are already tracked. Removing them should be handled in a separate cleanup commit.

## Maintenance Notes

- Keep changes small and focused.
- Read the relevant widget, data model, or canvas code before editing.
- Do not move icons, QSS files, or JSON configuration unless the task is explicitly about resource path cleanup.
- Prefer adding tests or updating the smoke-test checklist when changing GUI behavior.

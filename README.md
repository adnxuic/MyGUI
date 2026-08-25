# MyGUI

MyGUI is a PySide6 + matplotlib desktop GUI for working with tabular data and creating editable charts. The current application combines spreadsheet-like tables, matplotlib canvases, chart creation dialogs, and side panels for modifying axes, legends, text, colors, interpolation, TeX, and optional MATLAB fitting.

## Environment

The project is currently maintained as a Windows source-tree application.

- Python: 3.12
- Direct runtime packages: `PySide6`, `matplotlib`, `numpy`, `scipy`, `pandas`, `Pillow`, `openpyxl`
- Optional local integrations: MATLAB Python package/MATLAB Runtime for fitting features, and a local LaTeX distribution for TeX rendering.

Install the required Python packages with:

```powershell
pip install -r requirements.txt
```

Maintenance tools are separate from runtime dependencies:

```powershell
pip install -r requirements-dev.txt
```

MATLAB and LaTeX are intentionally not listed in `requirements.txt` because they depend on local system installations. The base GUI should remain maintainable without them.

## Start

Run the source entry point with Python 3.12. Resources are resolved from the
application package, so the process working directory does not affect icons,
QSS, or bundled JSON files.

```powershell
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe main.py
```

## Validation

Use the project interpreter from the repository root:

```powershell
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m compileall -q mygui tests main.py
$env:QT_QPA_PLATFORM="offscreen"
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m unittest discover -s tests -v
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m ruff check mygui tests main.py
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m coverage run -m unittest discover -s tests -v
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe -m coverage report
```

For GUI-facing changes, run the application manually:

```powershell
E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe main.py
```

See [docs/smoke-test.md](docs/smoke-test.md) for the manual smoke-test checklist.

## Documentation

The usage documentation site is built with MkDocs Material from the Markdown files in `docs/` and published to GitHub Pages at <https://adnxuic.github.io/MyGUI/>.

Preview and build it locally with the project interpreter after installing the maintenance dependencies:

```powershell
pip install -r requirements-dev.txt
python -m mkdocs serve          # local preview with live reload
python -m mkdocs build --strict # build site/, fails on broken links or warnings
```

## Runtime architecture

- Table data: each main window owns a pandas-backed `TableRepository`; the
  Table widget host is `PySubTable`, with the Qt model and sheet view in
  sibling modules. Charts use stable UUID column references.
- Figure components: import Controllers from `mygui.figuremodify.components`
  and Services from `mygui.figuremodify.component_services`.
- Expression evaluation: curve and fitting expressions use the restricted safe-expression evaluator.
- Project files: newly saved files use exact integer schema v15. The loader
  also accepts strictly validated v14 (direct in-memory migration) and
  strictly validated v13/v12/v11/v10 through every intervening version; one
  file contains a typed table document and its Figure component tree.
- Untrusted input: projects, images, Text/Excel imports, expressions, and external-process I/O have centralized budgets documented in [docs/resource-limits.md](docs/resource-limits.md).
- Optional integrations: MATLAB and TeX depend on local installations and should
  not be treated as required for baseline GUI maintenance. MATLAB process work
  stays in `mygui.database.matlab_adapter`; pure-Python fallbacks that must
  not start MATLAB live in `matlab_fallbacks.py`.

## Maintenance Notes

- Keep changes small and focused, and keep bug fixes separate from architecture migrations.
- Read the relevant widget, data model, or canvas code before editing.
- Resolve bundled files through `mygui.resources`; do not add working-directory-relative resource lookups.
- Prefer adding tests or updating the smoke-test checklist when changing GUI behavior.

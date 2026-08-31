# MyGUI

MyGUI is a PySide6 + matplotlib desktop GUI for working with tabular data and creating editable charts. A single application combines spreadsheet-like tables, matplotlib canvases, chart creation dialogs, and side panels for modifying axes, legends, text, colors, interpolation, TeX, and optional MATLAB fitting.

## Highlights

- Table-driven chart creation with automatic refresh when source data changes.
- Component-based Figure editing: a searchable Components tree and one unified Inspector.
- Constant Reference Lines and Reference Bands with data-coordinate positions and normalized Axes spans.
- Persistent Annotation components with independent target/text coordinates,
  optional arrows, typography, boxes, save/open, templates, and Undo/Redo.
- Parent-bound Secondary X/Y Axes with safe reversible unit transforms,
  flexible placement, full Inspector styling, save/open, templates, and Undo/Redo.
- Atomic component creation and deletion backed by project transactions.
- Strict schema v23 project files with validated content-preserving v22 migration,
  chained v21 through v10 migration, and save/open round trips.
- Optional TeX rendering and MATLAB curve fitting that do not block the base GUI.
- Application Settings Center for Appearance, Workspace, New Figure, Components, Axes Components, Export defaults, Integrations status, and Maintenance. UI theme is not Matplotlib Figure style.

## Quick start

Install the runtime dependencies, then run the application from the repository root:

```powershell
pip install -r requirements.txt
python main.py
```

Icons, QSS, and bundled JSON resolve from the application package, so the process working directory does not matter. MATLAB and LaTeX are optional local integrations.

MyGUI targets [Matplotlib 3.9](https://matplotlib.org/3.9.0/); parameter pages link to the corresponding 3.9 API and explainer pages for convenient lookup.

## Documentation map

- **Getting Started** — [GUI Workbench](workbench.md), [Application Settings](settings.md), [Project Undo and Redo](undo-redo.md), [Keyboard and Mouse Reference](keyboard-and-mouse-reference.md), [Bottom Bar](bottom-bar.md).
- **Working with Data** — [Table Data](table-data.md), [Data Preprocessing](data-preprocessing.md), [Text Data Import](text-data-import.md), [Excel Import](excel-import.md).
- **Creating Charts** — [Axes Layout Templates](axes-layouts.md), [Multi-Series Chart Creation](multi-series-charts.md), [Function Curve](function-curve.md), [Interpolation](interpolation.md), [Fitting](fitting.md), [Pseudocolor](pseudocolor.md), [Heatmap](heatmap.md), [Contour](contour.md), [In-Axes Elements](in-axes.md), [Text Element](text-element.md), [Annotation Component](editing-components/elements/annotation.md), [Reference Guides](reference-guides-component.md), [Reference Marks Component](reference-marks-component.md), [Colorbar Component](colorbar-component.md), [Secondary Axis / Unit Transform](secondary-axis-component.md), [Color Picker](color-picker.md).
- **Editing Components** — [Components Tree](components-tree.md), [Figure](editing-components/fixed-semantics/figure.md), [Axes](editing-components/fixed-semantics/axes.md), and [Plots](editing-components/charts/plot.md).
- **Projects and Appearance** — [Project Files](project-files.md), [Figure Export](figure-export.md), [Style Creation Defaults](style-creation-defaults.md).
- **Integrations and Configuration** — [TeX Rendering Integration](tex-integration.md), [Resource and Process Limits](resource-limits.md).
- **Developer Reference** — [Component Controllers](component-controllers.md), [Component Inspector Architecture](component-inspector.md), [Atomic Component Deletion](component-deletion.md), [Component Extension Template](component-extension-template.md), [Component Properties (schema v23)](component-properties-v23.md).
- **Maintenance & QA** — [Manual Smoke Test](smoke-test.md), [Documentation Site](documentation-site.md).

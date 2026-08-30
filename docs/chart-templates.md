# Chart Templates

Chart templates reproduce a complete Figure with new data from the same kind
of instrument or workflow. A template keeps layout, Axes, charts, elements,
styles, data bindings, preprocessing, and Fit configuration. Applying one
always creates a new project; it never replaces the current project.
Current files use strict `mygui-template` schema v6 with a schema-v22 Figure
blueprint. Strict v5 files first validate their schema-v21 Figure and then
advance without content changes. Strict v4 files migrate through v5 by
injecting deterministic Error Bar defaults; malformed predecessors are
rejected before a project is staged.

## Extract a template

Select a Figure and choose **Edit > Change to Template…**. Enter a unique name
(1–80 characters) and optional notes (up to 2,000 characters). The dialog
shows the required Sheet/column contract, component and Fit counts, editable
dynamic text, and an embedded-content warning.

Only columns actually referenced by the Figure are required. References
include Plot, Scatter mappings, Fit, Interpolation, FIELD_2D, table-backed
Reference Marks positions, and table-range placement. The template does not
store Table cell values. It does retain intentionally embedded component data:

- manual Line X/Y values;
- Function Curve expressions and ranges;
- manual Reference Marks positions and Reference Guides;
- Annotation text, target/text positions, arrow, typography, and box state;
- embedded In-Axes image bytes.

The warning matters because those values or images may contain source data.
No curve thumbnail is generated.

A Fit Curve must have a valid engine, model, options, and preprocessing
configuration before extraction. Its previous coefficients, goodness values,
drawable expression, and result-derived X range are removed. They are computed
again whenever the template is applied.

## Dynamic text

The Figure project name becomes `{{project_name}}` automatically. Title, Axis
Label, chart label, free-Text, and Annotation text/name values remain static unless you insert one of
the variables offered by the extraction dialog:

| Variable | Result during application |
| --- | --- |
| `{{project_name}}` | Edited new-project name |
| `{{source_file_name}}` | Imported filename including extension |
| `{{source_file_stem}}` | Imported filename without extension |
| Sheet variable shown by the dialog | Matched imported Sheet name |
| Column variable shown by the dialog | Matched imported column name |

Variables form a closed list. Unknown or malformed variables block saving or
application.

## Apply a template

Choose **Apply Template** as the first command in the Style gallery. It is
available even when no project is open. The same workflow opens from
**Settings > Templates > Apply Template…**.

The workflow has four steps:

1. Select and search a valid template. Required headers, component count, and
   automatic Fit tasks are shown.
2. Select one Excel workbook (`.xlsx` or `.xlsm`) or one text file. The normal
   import preview lets you choose Sheets/columns and edit target names/types;
   nothing is written to the workspace yet.
3. Confirm every logical Sheet and column mapping, inspect types and target
   Sheets, and edit the unique new-project name. This summary is always shown.
4. MyGUI validates, preprocesses, fits, materializes, and publishes. Canceling
   suppresses results from any computation that finishes later.

An Excel workbook may supply multiple Sheets. A text file supplies one. All
Sheets and columns selected in the preview are preserved in the new project,
including extra columns not referenced by the template.

## Matching rules

Headers are normalized with Unicode NFKC, leading/trailing whitespace removal,
internal whitespace collapse, and case folding. Punctuation and units remain
significant. Column order is irrelevant and extra columns are accepted.

Every logical Sheet must map to a different imported Sheet containing every
required header with the exact compatible MyGUI column type. The old Sheet
name affects candidate ordering only. A single candidate is selected; multiple
candidates require explicit selection. Missing columns, duplicate normalized
headers, incompatible types, or incomplete distinct-Sheet mapping disable
project creation and produce per-column diagnostics.

## Fitting, limits, and atomic publication

Fit tasks run sequentially away from the UI thread. Python Fits use the SciPy
adapter. MATLAB Fits require the MATLAB runtime connection and never fall back
to SciPy. Any failed Fit aborts the entire application.

Axes dimensions saved with autoscale enabled recompute their limits from the
newly materialized data before the tab is published. Dimensions with autoscale
disabled keep the fixed template limits. Interpolation, FIELD_2D, Colorbar,
Reference Marks, Annotation, and other derived components continue through their normal
materializers and services.

All component, layout, shared-axis, Colorbar-source, Sheet, column, project,
and data-reference IDs are regenerated. Dynamic text and Fit results (filtered with the saved `fit_input_range` specification) are
inserted into a complete schema-v22 project snapshot, which is strictly
validated before it reaches the shared Repository/Canvas restore transaction.
On success the new project is selected, has no file path, has an empty Undo
stack, and is dirty. On failure no project, tab, Inspector, tree entry, Fit
result, or delayed message is left behind.

## Storage and management

Templates live in the repository-root `template` directory. For example, a
checkout at `E:\PycharmProjects\MyGUI` stores them in
`E:\PycharmProjects\MyGUI\template`. This path is resolved from the installed
code location and does not depend on the process working directory. The
directory is created only by Save, Import, or Open Template Folder. Files use
stable UUID names ending in `.mygui-template.json`; renaming changes only
metadata. Writes use a temporary sibling file and atomic replacement. The
directory must be writable.

The independent root format is:

```json
{
  "schema": "mygui-template",
  "schema_version": 6,
  "metadata": {},
  "data_contract": {},
  "figure": {}
}
```

Only exact integer version 6 and closed fields are accepted for newly saved
templates. Versions 1–5 migrate through every intervening version; v5→v6
preserves the complete validated Figure blueprint. Unknown
fields or versions, non-finite numbers, dangling components, invalid refs,
unknown variables, oversized files/JSON/images, and invalid component trees
are rejected. A corrupt file does not prevent startup: Settings shows its
filename and error, while Apply lists only valid templates.

Settings management provides Apply Template, Rename, Save Notes, Duplicate,
Update from Figure, Import, Export, Delete, Refresh, and Open Template Folder.
Updating from the current Figure preserves template ID, name, notes, and
creation time. Template operations are immediate and are not controlled by the
Settings Apply/Cancel draft or project Undo/Redo.

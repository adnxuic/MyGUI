# Table Data System v4

MyGUI stores each project table in a `ProjectTableDocument`. A `TableRepository` owned by the main window is the only runtime data source for the Table UI, chart dialogs, plot modifiers, project IO, and Excel import.

## Column parameters

- `id`: UUID used by every chart reference. Renaming or moving a column does not change it.
- `name`: non-empty, case-insensitively unique within its Sheet.
- `type`: `auto`, `number`, `text`, `datetime`, or `boolean`.
- `width`: persisted display width in pixels; the minimum is 60 and the default is 96.
- `values`: row-aligned values stored with JSON `null` for missing cells.

An empty new column uses `auto`. Its first non-empty edit or paste resolves and locks the concrete type. Changing a locked type validates and converts the complete column atomically. Invalid edits preserve the previous value and are reported through the Message Bar.

Pandas storage uses `Float64`, `string`, `datetime64[ns]`, and `boolean` nullable dtypes. Date/time values are displayed as ISO 8601 local values. Boolean values are displayed and copied as `true` or `false`.

## References and row alignment

Chart records store an `x_ref` and `y_ref`, each containing `project_id`, `sheet_id`, and `column_id`. Display labels use `Project/Sheet/Column`, but labels are not identifiers.

- Plot keeps row positions and masks incomplete X/Y rows, producing line gaps.
- Scatter, interpolation, and fitting filter incomplete X/Y rows as pairs.
- Trailing rows that are empty in both selected columns are ignored.
- Interpolation and fitting reject an empty valid pair; Plot and Scatter clear their artists when no valid data remains.

Repository mutations emit one `TableChangeSet`. Dependent objects read the committed data, and each canvas schedules at most one redraw per transaction.

## Editing commands

Each project owns a 50-command undo stack. Cell edits, clear, paste, row sorting, type changes, and row/column insert, delete, and move actions are undoable. A multi-cell paste and a workbook import are each one command.

TSV copy/paste accepts LF, CRLF, and CR line endings. Paste validates all locked column types before changing the document and automatically adds required rows or columns.

Deleting a referenced column, or converting it to a non-chart type, displays the dependent Plot, Scatter, Interpolation, and Fit objects. Confirmation removes the column and dependents as one command; Undo restores all of them with the same UUIDs.

## Sheet management

- Right-click a Sheet tab to choose **Rename Sheet** or **Delete Sheet**.
- Double-click a Sheet tab to rename it.
- The Table toolbar also provides **Rename Sheet** and **−Sheet** actions for the active Sheet.
- Sheet names must be non-empty and case-insensitively unique within the project.
- A project must retain at least one Sheet.
- Rename and delete are project undo commands. Deleting a referenced Sheet lists dependent chart objects before confirmation; the Sheet, original tab order, stable column UUIDs, and dependent objects are restored together by Undo.

## Excel import

The import preview lets users include Sheets, use or ignore the first row as headers, edit target names, and override detected types. Imported formulas use cached workbook values and are never evaluated. New Sheets receive unique names and never overwrite existing data.

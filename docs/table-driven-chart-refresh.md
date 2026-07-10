# Table-Driven Chart Refresh

MyGUI table columns are synchronized into `PyDatabase` automatically after Qt model edits are committed. Plot, scatter, and interpolation objects listen to their selected source columns and refresh only when the selected X/Y data pair is valid.

## Synchronization

- Cell edits, paste, delete, sort, and column loading schedule a table-to-database sync.
- `flush_database_sync()` is the internal flush API for project save, Excel import, tests, and fallback refresh paths.
- The user-facing `Save to Database` table menu entry and table `Ctrl+S` action are intentionally removed.
- Project save still flushes the current project table before writing the project file.

## Data Source Parameters

- Data source names use `ProjectName/SheetName/ColumnIndex`.
- `ProjectName` is the current canvas-bound project table.
- `SheetName` is the sheet tab name.
- `ColumnIndex` is a 1-based numeric column name stored as a string in project files and `PyDatabase`.

## Validation Rules

- Database columns are saved independently; X/Y length mismatch does not block table synchronization.
- New blank columns are not added to `PyDatabase`.
- Existing blank columns with chart callbacks remain as empty arrays so dependent charts can detect the invalid source.
- Existing blank columns without callbacks are removed from `PyDatabase` and disappear from data choice widgets.
- Plot, scatter, and interpolation refresh only when X and Y both exist, are non-empty, and have the same length.
- On invalid X/Y pairs, the previous valid visual remains visible and the Message Bar receives a warning.
- Project restore skips invalid chart records and reports a Message Bar warning instead of blocking project open.
- Fit curves do not auto-refit when table data changes; rerunning SciPy or MATLAB fitting reads the latest selected data.

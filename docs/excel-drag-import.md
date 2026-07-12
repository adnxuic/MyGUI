# Excel Drag-and-Drop Import

Drag one Excel workbook onto the MyGUI main window to open the existing import preview. The drag workflow and **File → Open Excel** use the same importer, transaction handling, type inference, and validation. Non-Excel files are routed to the content-based text data importer.

## Supported files

- `.xlsx`: standard Open XML workbook.
- `.xlsm`: macro-enabled Open XML workbook. Macros are not executed.
- One workbook is accepted per drop operation.

## Import parameters

- **Import this sheet**: includes or excludes the selected worksheet.
- **Use first row as column names**: treats row 1 as names instead of data.
- **Target sheet**: destination Sheet name. A numeric suffix is added when the name already exists.
- **Import**: per-column checkbox. Unchecked source columns are excluded from the transaction and are not created in the destination Sheet.
- **Column Name**: editable first preview row; names are case-insensitively unique within a Sheet.
- **Type**: second preview row with `auto`, `number`, `text`, `datetime`, or `boolean`. The entire column is validated before import.
- **Excel Row**: up to eight row-aligned source samples displayed below the name and type rows.

Each Excel field is displayed as a horizontal preview column. The grid scrolls horizontally for wide worksheets, and blank source cells remain blank with a light-gray background. Excluded columns are disabled and shaded gray. An included non-empty Sheet must contain at least one selected column.

## Destination and undo behavior

- With an active project, imported worksheets are added as new Sheets.
- Without an active project, the workbook filename becomes the project name and a matching figure canvas is created.
- The complete workbook import is one Repository transaction and one undo command.
- Cancelling the preview creates no project, Sheet, or canvas.
- Success, unsupported-drop warnings, and read/validation errors are reported through the Message Bar.

Excel files are opened read-only with cached formula results. Formula code and macros are never executed.

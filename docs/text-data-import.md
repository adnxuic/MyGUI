# Text Data Import

MyGUI can import instrument text data by inspecting file content rather than the filename extension. Use **File → Open Text Data...** or drag one local file onto the main window.

## Automatic detection

- **Encoding**: UTF-8 with or without BOM, GB18030, UTF-16 with BOM, and Windows CP1252.
- **Separator**: whitespace, Tab, comma, or semicolon.
- **File header removal**: locates the longest stable data block and sets its first row as the initial `First data line`.
- **Column names**: uses the nearest preceding non-data line when its field count matches or substantially covers the detected data columns. Otherwise, `Column N` names are generated.
- **Values**: recognizes ordinary numbers, scientific notation using `E` or `D`, booleans, and ISO date/time text. Empty delimited fields become missing values.

The parser does not filter by suffix. Files such as `.dat`, `.raw`, `.001`, instrument-specific extensions, and files without an extension follow the same detection workflow. Binary files are rejected.

## Preview parameters

- **Detected encoding**: read-only encoding selected while decoding the file.
- **Separator**: detected separator; changing it reruns data-block detection.
- **First data line**: one-based source line at which tabular records begin. All preceding lines are excluded from imported values.
- **Column-name line**: one-based source line used for names. Set it to `Generate column names` to create `Column 1`, `Column 2`, and so on.
- **Import**: per-column checkbox. Disabled columns are not created.
- **Column Name**: editable destination name for each selected column.
- **Type**: inferred destination type; it can be overridden before import.
- **Source Row**: up to eight row-aligned source samples.

The green detection summary reports the number of rows, columns, and removed leading lines. Invalid manual settings disable confirmation until the preview becomes valid again.

Data-block detection uses a single linear scan. The preview converts at most 200 rows for type inference and displays eight samples; the full selected columns are parsed once only after confirmation.

## Destination and undo behavior

- With an active project, the detected table is added as a new Sheet.
- Without an active project, the source filename becomes the project name and a figure canvas is created.
- The complete import is one Repository transaction and one undo command.
- Cancelling the preview creates no project, Sheet, or canvas.

# Resource and Process Limits

MyGUI applies centralized budgets before materializing untrusted project,
image, Text, Excel, expression, and external-process payloads. Overrides are
read from positive-integer `MYGUI_*` environment variables and cannot exceed
the built-in hard caps.

## Input budgets

| Environment variable | Default | Hard cap | Applies to |
| --- | ---: | ---: | --- |
| `MYGUI_MAX_PROJECT_BYTES` | 64 MiB | 256 MiB | Project JSON bytes |
| `MYGUI_MAX_JSON_DEPTH` | 64 | 128 | Decoded project nesting |
| `MYGUI_MAX_JSON_VALUES` | 1,000,000 | 5,000,000 | Decoded JSON values |
| `MYGUI_MAX_PROJECT_COMPONENTS` | 20,000 | 100,000 | Figure components |
| `MYGUI_MAX_IMAGE_BYTES` | 16 MiB | 64 MiB | Compressed image bytes |
| `MYGUI_MAX_IMAGE_PIXELS` | 25,000,000 | 50,000,000 | Decoded image pixels |
| `MYGUI_MAX_IMAGE_DIMENSION` | 16,384 | 32,768 | Image width or height |
| `MYGUI_MAX_TEXT_BYTES` | 64 MiB | 256 MiB | Text import bytes |
| `MYGUI_MAX_EXCEL_BYTES` | 64 MiB | 256 MiB | Excel ZIP bytes |
| `MYGUI_MAX_EXCEL_UNCOMPRESSED_BYTES` | 512 MiB | 1 GiB | Excel ZIP expansion |
| `MYGUI_MAX_EXCEL_SHEETS` | 256 | 1,024 | Excel worksheets |
| `MYGUI_MAX_EXCEL_CELLS` | 2,000,000 | 10,000,000 | Materialized cells |
| `MYGUI_MAX_EXTERNAL_INPUT_BYTES` | 16 MiB | 64 MiB | Child-process stdin |
| `MYGUI_MAX_EXTERNAL_OUTPUT_BYTES` | 8 MiB | 32 MiB | Each captured output stream |

Invalid, zero, negative, or over-cap overrides are rejected rather than
silently widened. Project JSON also rejects `NaN`, `Infinity`, and
`-Infinity`; numeric Table and component state must be finite.

## Expression budgets

Curve, preprocessing, and fitting expressions share one AST interpreter:

| Parameter | Limit |
| --- | ---: |
| Source length | 512 characters |
| AST nodes | 128 |
| AST depth | 32 |
| Integer constant | 256 bits |
| Absolute exponent | 64 |
| Intermediate array | 2,000,000 elements |

Only the documented numeric names, functions, and arithmetic nodes are
accepted. Boolean values, arbitrary attributes/calls, indexing, collections,
and Python evaluation are unavailable. Curve output must be real, finite,
one-dimensional, and equal in length to its X input.

## External processes and writable paths

TeX validation defaults to a 15-second timeout via
`MYGUI_TEX_TIMEOUT_SECONDS`. MATLAB connection, expression metadata, and fit
timeouts default to 180, 120, and 180 seconds via the variables documented in
`fitting.md`. Each process receives bounded stdin/stdout/stderr. Timeout or
output overflow terminates the process tree.

Logs and MATLAB Runtime caches default to the current user's Qt standard data
location. `MYGUI_USER_DATA_DIR`, `MYGUI_USER_CACHE_DIR`, and
`MYGUI_USER_LOG_DIR` override the corresponding roots. This keeps optional
integrations usable from read-only or packaged application directories.

# Case 6 — Scoped Scan (include / exclude)

## Prompt

> Check architecture boundaries only under:
>
> mygui/widgets/
>
> Exclude:
>
> mygui/widgets/resources/
>
> Do not inspect unrelated production directories.

## Expected

Natural-language scope is translated into a `ScannerRequest`:

- include = `["mygui/widgets/**"]` or semantic equivalent
- exclude = `["mygui/widgets/resources/**"]` or semantic equivalent

Verified from adapter execution evidence (the actual request), NOT guessed
from the final natural-language summary.

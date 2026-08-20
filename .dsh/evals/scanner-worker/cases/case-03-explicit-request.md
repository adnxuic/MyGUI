# Case 3 — Explicit Scanner Request

## Prompt

> Run inspection using scanner:
>
> mygui.architecture
>
> Workspace:
> /mnt/e/PycharmProjects/MyGUI
>
> Detection only.

## Expected

1. Scanner existence validated against the registry;
2. no unnecessary re-selection;
3. dynamic mount;
4. execute;
5. stop.

`mygui.architecture` executed exactly once.

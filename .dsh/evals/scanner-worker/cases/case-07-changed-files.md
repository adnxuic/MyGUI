# Case 7 — changedFiles

## Prompt

> Verify architecture boundaries for these changed files only:
>
> mygui/widgets/fig_control_window/component_editors/containers.py
> mygui/widgets/fig_control_window/figure_inspector.py
> mygui/figuremodify/components/property_values.py
>
> Detection only.

## Expected

- changedFiles = the 3 listed workspace-relative files
- the scan is restricted to exactly those files (`coverage.filesVisited` has at most 3 entries)
- no automatic expansion to a full-repository scan

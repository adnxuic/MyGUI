# Runtime Boundaries

Use this page for bundled resources, shared Table data ownership, optional
integration boundaries, or production behavior that might accidentally depend
on the process working directory.

## Bundled resources

`CORE-RESOURCE-BOUNDARY` requires icons, QSS, and bundled JSON to resolve only
through `mygui.resources`. Production code must not derive those locations from
the current working directory. Preserve existing resource names and tracked
assets when reorganizing callers.

## Table data authority

`CORE-TABLE-REPOSITORY` makes the `TableRepository` created by `MainWindow` the
shared runtime data authority. Widgets, models, charts, dependency refresh, and
project history use that injected repository rather than global or parallel
stores. Authoritative Table changes refresh dependent artifacts through the
existing repository and service paths.

## Optional integrations

MATLAB and TeX are optional and their absence must not block unrelated GUI
work. `mygui.database.matlab_adapter` is the MATLAB boundary; Python fallbacks
in `matlab_fallbacks.py` must not start MATLAB or MCR. TeX process state and
diagnostics follow the owners in `ui-state-boundaries.md`. Replacing
user-expression evaluation is a dedicated high-risk task.

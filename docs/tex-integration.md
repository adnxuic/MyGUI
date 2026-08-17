# TeX Rendering Integration

MyGUI uses Matplotlib's `text.usetex` support for individual Figure `Text`
components. TeX is an optional local integration: the base GUI and ordinary
Matplotlib text remain available when no compatible TeX installation exists.

## Parameters and runtime state

| Parameter | Scope | Meaning |
| --- | --- | --- |
| `enabled` | Application runtime | Whether TeX rendering is currently available for effective use |
| `preamble` | Application runtime | Shared `text.latex.preamble` content validated before activation |
| `usetex` | Text component, schema v10 | User-requested render mode for that Text component |
| effective `usetex` | Text artist runtime | Requested value combined with current TeX availability |
| `MYGUI_TEX_TIMEOUT_SECONDS` | Process environment | Bounded render-probe timeout; default 15 seconds |

The default preamble includes `amsmath` and `newtxtext,newtxmath`. A custom
preamble can use only packages installed in the local TeX distribution.

## State flow

The TeX panel validates a small render probe before enabling TeX. Availability
changes are submitted through `TextRenderService.apply_tex_availability()`;
Inspector Sections never set Matplotlib artists directly. The service keeps a
component's requested `usetex` value in Controller state while applying a safe
runtime override when TeX is unavailable. The effective override is not added
to schema v10.

Re-enabling TeX probes rendering before publishing the effective state. A
failed probe restores the previous safe artist state and emits one warning.
Text edits use `TextRenderService.apply_many()` so Controller state, artists,
and redraw are one logical operation.

## Validation and diagnostics

Availability checks and render probes run in bounded subprocesses. Failures,
timeouts, missing executables, and invalid preambles are reported without
blocking normal GUI startup. Diagnostic logs use the application user-log
directory described in `resource-limits.md`.

Image export performs a real Matplotlib redraw and can still reject Text whose
content uses commands or Unicode characters unsupported by the active local
TeX installation.

## Matplotlib reference

- [Text rendering with LaTeX](https://matplotlib.org/3.9.0/users/explain/text/usetex.html): the text.usetex mechanism behind this integration.

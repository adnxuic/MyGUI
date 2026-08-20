# Bottom Bar

The bottom bar combines one user-message surface with compact optional-feature
status indicators.

## Message Bar

Business code publishes through `mygui.status_messages`; it does not retain a
widget reference. Supported levels are `info`, `error`, `warning`, and
`success`. Unknown levels render as `info`. The active bound-method handler is
held weakly, and a presentation exception is logged, contained, and detaches
that handler so a completed business operation cannot be reported as failed.

One user action should emit at most one Message Bar result. Modal dialogs are
reserved for choices that require user input.

Process-level font diagnostics also appear here as yellow warnings. MyGUI
recognizes Matplotlib missing-glyph warnings and math-text log records, plus
Qt DirectWrite font-load failures on Windows. Repeated reports for the same
Unicode code point or font family are deduplicated, startup reports wait until
the Message Bar exists, and the original console diagnostics remain available
for troubleshooting. A missing-glyph warning identifies its `U+NNNN` code
point; a DirectWrite warning identifies the font family for which Qt selected
a fallback. Text edits synchronously collect both Matplotlib warning and
math-text logging channels. If the current font cannot render an entered
character, the component transaction and input control return to their last
valid values and one red rejection message replaces the normal green update
result.

## State Bar

`PyStateBar` displays the enabled state of MATLAB and TeX. Each
`FeatureIndicator` supplies:

- `name` and visible `label`;
- an `is_enabled()` query;
- listener registration and unregistration functions.

Listeners update Qt controls on the GUI thread and are detached by
`PyStateBar.cleanup()`. Green means enabled and red means unavailable or
disabled. The accessible name includes the feature and its current state.

## Container

`PyBottomBar` owns `PyMessageBar` and `PyStateBar` and exposes forwarding
methods for existing callers. `MainWindow` registers its Message Bar as the
global status handler, then flushes any font diagnostics buffered during
startup. Its QSS is loaded through the package resource locator.

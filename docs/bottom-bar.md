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

`PyBottomBar` owns `PyMessageBar` and `PyStateBar`, registers the global status
handler during construction, and exposes forwarding methods for existing
callers. Its QSS is loaded through the package resource locator.

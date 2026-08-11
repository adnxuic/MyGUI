# Current limitations

- Project files intentionally accept only strict schema v9. Historical v4-v8
  files require an external conversion step before they can be opened.
- MATLAB fitting and TeX rendering remain optional and require compatible
  local runtimes. A cancelled UI request suppresses its callback, but an
  already-running worker exits cooperatively or at its configured process
  timeout rather than being forcefully stopped from the Python thread.
- Qt's `QUndoStack` cannot veto an index transition after a command-level
  failure. Structural Table commands therefore use repository snapshot
  rollback and report failure, but callers must not interpret stack position
  alone as proof that a mutation committed.
- Automated GUI coverage uses Qt's offscreen platform. Multi-monitor scaling,
  native file dialogs, real TeX/MATLAB runtimes, and interactive drag/drop
  still require the manual smoke checklist on a Windows desktop.

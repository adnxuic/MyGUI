/**
 * QT-TIMER-OWNERSHIP: instance `QTimer()` stored on `self` without a Qt
 * parent AND without any `.stop()` / `.deleteLater()` call anywhere in the
 * owning class body.
 *
 * Repository evidence (MyGUI):
 *  - negative: `common.py` / `py_action_gallery.py` construct
 *    `QTimer(self)` (parented) — never reported;
 *  - negative: `context.py` constructs `self._flush_timer = QTimer()` without
 *    a parent but stops it in `_detach_registry()` / `close()` — never
 *    reported;
 *  - `QTimer.singleShot(...)` is a static one-shot helper, not a construction
 *    of a member timer — never reported.
 *
 * A parentless member timer whose owning class has no stop path keeps running
 * for the lifetime of its Python owner and survives owner teardown paths that
 * never stop it (late timeout delivery into a half-disposed object).
 */

import type { PyFileModel } from '../../../lib/py/model.ts';
import type { ScannerDiagnostic } from '../../../contracts.ts';
import { chainEndingWith, makeQtFinding, rawLine, type QtRule } from './common.ts';

/** `QTimer(` constructor call on one line; `QTimer.singleShot` excluded. */
const TIMER_CALL = /QTimer\s*\(/;
const SINGLE_SHOT = /QTimer\.singleShot\s*\(/;
/** Positional parent: `QTimer(self, ...)` / `QTimer(self)` — parented, fine. */
const PARENT_POSITIONAL = /QTimer\s*\(\s*self\b/;
/** Keyword parent: `QTimer(parent=self, ...)` — parented, fine. */
const PARENT_KEYWORD = /QTimer\s*\([^)]*\bparent\s*=\s*self\b/;

/** All cleanup vocabulary whose presence makes a parentless timer acceptable. */
const CLEANUP_CALLS = ['stop', 'deleteLater'];

export const timerOwnershipRule: QtRule = {
  id: 'QT-TIMER-OWNERSHIP',
  description:
    'Instance QTimer stored on self without a Qt parent and without a stop/delete path in its owning class.',
  run(context) {
    const findings = [];
    const diagnostics: ScannerDiagnostic[] = [];
    for (const model of context.files) {
      for (const assign of model.selfAssigns) {
        const raw = rawLine(model, assign.line);
        if (!TIMER_CALL.test(raw)) continue;
        if (SINGLE_SHOT.test(raw)) continue;
        if (PARENT_POSITIONAL.test(raw) || PARENT_KEYWORD.test(raw)) continue;
        const cls = model.classAt(assign.line);
        if (cls === undefined) continue;
        if (CLEANUP_CALLS.some((name) => chainEndingWith(model, cls.startLine, cls.endLine, name))) continue;
        findings.push(
          makeQtFinding({
            model,
            ruleId: 'QT-TIMER-OWNERSHIP',
            line: assign.line,
            severity: 'medium',
            confidence: 0.8,
            title: `Member QTimer ${assign.attr} has no Qt parent and no stop path in ${cls.name}`,
            reason:
              `self.${assign.attr} = QTimer() creates a parentless timer; the owning class ${cls.name} ` +
              'never calls .stop() or .deleteLater(), so the timer is not tied to a Qt owner and no teardown path stops it.',
            tags: ['qt', 'lifecycle', 'timer', 'ownership'],
          }),
        );
      }
    }
    return { findings, diagnostics };
  },
};

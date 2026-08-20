/**
 * QT-THREAD-LIFECYCLE: instance `QThread()` stored on `self`, started
 * somewhere in the owning class, with no shutdown vocabulary (quit / wait /
 * requestInterruption / terminate / deleteLater) anywhere in the class body.
 *
 * Repository evidence (MyGUI): the project does not use QThread today —
 * `background_task.py` runs daemon `threading.Thread`s with a module-lifetime
 * QObject bridge plus `cancel_background_tasks()`/`drain_background_tasks()`
 * shutdown paths, and `bounded_process.py` wraps `subprocess`. This rule is
 * therefore a guard for future regressions: a long-lived started QThread with
 * no shutdown path leaks the worker thread and its event loop at owner
 * teardown.
 */

import type { ScannerDiagnostic } from '../../../contracts.ts';
import { chainEndingWith, makeQtFinding, rawLine, type QtRule } from './common.ts';

const THREAD_CALL = /QThread\s*\(/;

/** Shutdown vocabulary whose presence makes a started thread acceptable. */
const SHUTDOWN_CALLS = ['quit', 'wait', 'requestInterruption', 'terminate', 'deleteLater'];

export const threadLifecycleRule: QtRule = {
  id: 'QT-THREAD-LIFECYCLE',
  description:
    'Instance QThread stored on self, started, with no quit/wait/delete path in its owning class.',
  run(context) {
    const findings = [];
    const diagnostics: ScannerDiagnostic[] = [];
    for (const model of context.files) {
      for (const assign of model.selfAssigns) {
        const raw = rawLine(model, assign.line);
        if (!THREAD_CALL.test(raw)) continue;
        const cls = model.classAt(assign.line);
        if (cls === undefined) continue;
        // A thread that is never started has nothing to shut down.
        if (!chainEndingWith(model, cls.startLine, cls.endLine, 'start')) continue;
        if (SHUTDOWN_CALLS.some((name) => chainEndingWith(model, cls.startLine, cls.endLine, name))) continue;
        findings.push(
          makeQtFinding({
            model,
            ruleId: 'QT-THREAD-LIFECYCLE',
            line: assign.line,
            severity: 'medium',
            confidence: 0.7,
            title: `Member QThread ${assign.attr} is started but ${cls.name} has no shutdown path`,
            reason:
              `self.${assign.attr} is a QThread that gets started, but the owning class ${cls.name} never calls ` +
              'quit()/wait()/requestInterruption()/terminate()/deleteLater(); the worker thread and its event loop ' +
              'are not shut down on owner teardown.',
            tags: ['qt', 'lifecycle', 'thread', 'ownership'],
          }),
        );
      }
    }
    return { findings, diagnostics };
  },
};

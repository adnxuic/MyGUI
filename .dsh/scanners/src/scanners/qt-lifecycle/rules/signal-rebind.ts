/**
 * QT-SIGNAL-REBIND: a repeatable method (name matching sync/update/refresh/
 * rebind/reset/switch/restore/apply/select/setup) connects a NEW lambda to a
 * signal without any `.disconnect()` anywhere in the owning class.
 *
 * Repository evidence (MyGUI):
 *  - negative: `component_tree.py` connects `signal.connect(self._canvas_selected)`
 *    in a canvas-switch method but ALWAYS calls `_disconnect_canvas()` first —
 *    the class-level disconnect contract makes reconnects idempotent, never
 *    reported;
 *  - negative: every `__init__`-time `widget.clicked.connect(self.method)`
 *    binding — not repeatable, never reported;
 *  - method-bound connects are Qt-no-op on repeat (same receiver+slot), so
 *    only freshly-created lambdas accumulate connections.
 *
 * A repeatable method that appends a new lambda connection per call grows the
 * connection list without bound and delivers each signal to stale closures.
 */

import type { PyFileModel } from '../../../lib/py/model.ts';
import type { ScannerDiagnostic } from '../../../contracts.ts';
import { chainEndingWith, lastNamed, makeQtFinding, rawLine, type QtRule } from './common.ts';

/** Method names that legitimately run more than once per widget lifetime. */
const REBIND_METHOD = /^(sync|update|refresh|rebind|reset|switch|restore|apply|select|setup)/i;
/** A connect whose slot argument is a freshly created lambda. */
const LAMBDA_CONNECT = /\.connect\s*\([^)]*lambda\b/;

/** Whether any chain in the class body ends with `.disconnect(`. */
function classHasDisconnect(model: PyFileModel, line: number): boolean {
  const cls = model.classAt(line);
  if (cls === undefined) return false;
  return chainEndingWith(model, cls.startLine, cls.endLine, 'disconnect');
}

export const signalRebindRule: QtRule = {
  id: 'QT-SIGNAL-REBIND',
  description:
    'Repeatable method connects a new lambda to a signal while the owning class never disconnects.',
  run(context) {
    const findings = [];
    const diagnostics: ScannerDiagnostic[] = [];
    for (const model of context.files) {
      for (const chain of model.chains) {
        if (!chain.isCall) continue;
        if (lastNamed(chain) !== 'connect') continue;
        const def = model.defAt(chain.line);
        if (def === undefined) continue;
        if (def.name === '__init__' || def.name === '__new__') continue;
        if (!REBIND_METHOD.test(def.name)) continue;
        if (!LAMBDA_CONNECT.test(rawLine(model, chain.line))) continue;
        if (classHasDisconnect(model, chain.line)) continue;
        findings.push(
          makeQtFinding({
            model,
            ruleId: 'QT-SIGNAL-REBIND',
            line: chain.line,
            severity: 'low',
            confidence: 0.55,
            title: `Repeatable method ${def.name} connects a new lambda without a class-level disconnect`,
            reason:
              `${def.name}() runs repeatedly and appends a fresh lambda connection to a signal, while the owning ` +
              'class never calls .disconnect(); repeated invocations accumulate duplicate connections.',
            tags: ['qt', 'lifecycle', 'signal', 'rebind'],
          }),
        );
      }
    }
    return { findings, diagnostics };
  },
};

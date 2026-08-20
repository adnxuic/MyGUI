/** All Qt-lifecycle rules, in stable definition order. */

import type { QtRule } from './common.ts';
import { signalRebindRule } from './signal-rebind.ts';
import { threadLifecycleRule } from './thread-lifecycle.ts';
import { timerOwnershipRule } from './timer-ownership.ts';

export const QT_LIFECYCLE_RULES: readonly QtRule[] = [
  timerOwnershipRule,
  threadLifecycleRule,
  signalRebindRule,
];

export type { QtRule, QtRuleOutcome, QtRuleRunContext } from './common.ts';

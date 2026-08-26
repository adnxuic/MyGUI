/** All architecture rules, in stable definition order. */

import type { ArchitectureRule } from './common.ts';
import { controllerBypassRule } from './controller-bypass.ts';
import { privateContainerAccessRule } from './private-container-access.ts';
import { qsettingsBackendBypassRule } from './qsettings-backend-bypass.ts';
import { secondComponentStateRule } from './second-component-state.ts';
import { uiArtistMutationRule } from './ui-artist-mutation.ts';
import { uiMatplotlibGlobalStateMutationRule } from './ui-matplotlib-global-state-mutation.ts';
import { uiThemeBypassRule } from './ui-theme-bypass.ts';

export const ARCHITECTURE_RULES: readonly ArchitectureRule[] = [
  privateContainerAccessRule,
  uiArtistMutationRule,
  uiMatplotlibGlobalStateMutationRule,
  secondComponentStateRule,
  controllerBypassRule,
  qsettingsBackendBypassRule,
  uiThemeBypassRule,
];

export type { ArchitectureRule, RuleOutcome, RuleRunContext } from './common.ts';

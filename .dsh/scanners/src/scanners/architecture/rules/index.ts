/** All architecture rules, in stable definition order. */

import type { ArchitectureRule } from './common.ts';
import { controllerBypassRule } from './controller-bypass.ts';
import { privateContainerAccessRule } from './private-container-access.ts';
import { secondComponentStateRule } from './second-component-state.ts';
import { uiArtistMutationRule } from './ui-artist-mutation.ts';
import { uiMatplotlibGlobalStateMutationRule } from './ui-matplotlib-global-state-mutation.ts';

export const ARCHITECTURE_RULES: readonly ArchitectureRule[] = [
  privateContainerAccessRule,
  uiArtistMutationRule,
  uiMatplotlibGlobalStateMutationRule,
  secondComponentStateRule,
  controllerBypassRule,
];

export type { ArchitectureRule, RuleOutcome, RuleRunContext } from './common.ts';

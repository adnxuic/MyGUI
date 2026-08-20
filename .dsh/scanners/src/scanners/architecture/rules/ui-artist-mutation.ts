/**
 * ARCH-UI-ARTIST-MUTATION
 *
 * AGENTS.md (Component Architecture Rules): "Inspector/UI code must not ...
 * directly mutate Matplotlib artists; it must submit through the relevant
 * Controller or Service and synchronize from Registry events."
 *
 * Scope: `mygui/widgets/` production files. The rule looks for
 * `.set_*(...)`, `.remove()`, and `.set_visible(...)` calls whose receiver
 * is plausibly a Matplotlib artist, outside Controller/Service/Canvas
 * classes. Receiver classification is deliberately conservative: ambiguous
 * receivers are not reported, and confidence drops for weaker signals.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  isWidgetsPath,
  makeFinding,
  receiverIsArtistLike,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const SETTER_METHOD = /^set_[a-z_][a-z0-9_]*$/;

/** Classes allowed to touch artists: domain controllers/services and canvas. */
function isAuthorizedClass(name: string): boolean {
  if (name === 'PyFigureCanvas') return true;
  if (name.endsWith('Canvas')) return true;
  if (name.endsWith('Controller')) return true;
  if (name.endsWith('Service')) return true;
  if (name.endsWith('Coordinator')) return true;
  return false;
}

function isMutationCall(chain: AttrChain): boolean {
  if (!chain.isCall) return false;
  const method = chain.segments[chain.segments.length - 1]!;
  if (method.isIndex) return false;
  if (method.name === 'remove') return true;
  if (method.name === 'set_visible') return true;
  return SETTER_METHOD.test(method.name);
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  if (!isWidgetsPath(model.path)) return { findings, diagnostics: [] };

  for (const chain of model.chains) {
    if (!isMutationCall(chain)) continue;
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;

    if (!receiverIsArtistLike(chain, model)) continue;

    const receiverIsSelf = chain.segments[0]!.name === 'self';
    const confidence = receiverIsSelf ? 0.75 : 0.65;
    const method = chain.segments[chain.segments.length - 1]!.name;
    const receiverText = chain.segments
      .slice(0, -1)
      .map((segment) => (segment.isIndex ? '[...]' : segment.name))
      .join('.');
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-UI-ARTIST-MUTATION',
        line: chain.line,
        severity: 'medium',
        confidence,
        title: `UI code mutates a Matplotlib artist (${method})`,
        reason:
          `${receiverText}.${method}() in UI code bypasses Controllers/Services. ` +
          `Artist mutations must be submitted through the relevant Controller or Service.`,
        tags: [...(testPath ? ['test-code'] : ['production']), 'artist-mutation'],
      }),
    );
  }
  return { findings, diagnostics: [] };
}

export const uiArtistMutationRule: ArchitectureRule = {
  id: 'ARCH-UI-ARTIST-MUTATION',
  description:
    'Direct Matplotlib artist mutation (.set_*, .remove(), .set_visible()) from UI code outside Controller/Service/Canvas classes in mygui/widgets/.',
  run(context: RuleRunContext): RuleOutcome {
    const findings: ScannerFinding[] = [];
    const diagnostics = [];
    for (const model of context.files) {
      const outcome = analyzeModel(model);
      findings.push(...outcome.findings);
      diagnostics.push(...outcome.diagnostics);
    }
    return { findings, diagnostics };
  },
};

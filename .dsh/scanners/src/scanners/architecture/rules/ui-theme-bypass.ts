/**
 * ARCH-UI-THEME-BYPASS
 *
 * AGENTS.md CORE-THEME-OWNER: ThemeService is the sole publisher of
 * application font, palette, bundled QSS, and density. Production code
 * outside `mygui/application_theme/` must not publish chrome via
 * QApplication / app / qApp / _app setFont, setPalette, or setStyleSheet.
 *
 * Widget-local setFont/setPalette/setStyleSheet (labels, editors) is not
 * application-chrome publication and is never reported. QSS color
 * completeness is a Python contract test, not this lexical rule.
 *
 * Recorded as a planned gray candidate during the appearance-engine
 * decoupling, then promoted after ThemeService became the sole publisher.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  isThemeOwnerPath,
  lastNamed,
  makeFinding,
  namedSegments,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const APP_RECEIVERS = new Set(['QApplication', 'app', 'qApp', 'application', '_app']);
const PUBLISH_METHODS = new Set(['setFont', 'setPalette', 'setStyleSheet']);

function isAppChromePublish(chain: AttrChain): boolean {
  if (!chain.isCall) return false;
  const method = lastNamed(chain);
  if (method === undefined || !PUBLISH_METHODS.has(method)) return false;
  const names = namedSegments(chain);
  if (names.length < 2) return false;
  return names.slice(0, -1).some((name) => APP_RECEIVERS.has(name));
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  if (isThemeOwnerPath(model.path)) return { findings, diagnostics: [] };
  const testPath = isTestPath(model.path);
  const seen = new Set<number>();

  for (const chain of model.chains) {
    if (!isAppChromePublish(chain)) continue;
    if (seen.has(chain.line)) continue;
    seen.add(chain.line);
    const method = lastNamed(chain) ?? 'publish';
    const receiver = namedSegments(chain).at(-2) ?? 'application';
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-UI-THEME-BYPASS',
        line: chain.line,
        severity: 'high',
        confidence: 0.9,
        title: `Application chrome published via ${receiver}.${method}() outside ThemeService`,
        reason:
          `${receiver}.${method}() publishes application font, palette, or bundled QSS ` +
          'outside mygui/application_theme/. ThemeService / ThemeBindingPort is the sole publisher.',
        suggestedAction:
          'Apply appearance through ThemeService (or ThemeBindingPort.bind_qss) instead of QApplication chrome APIs.',
        tags: [...(testPath ? ['test-code'] : ['production']), 'ui-theme-bypass'],
      }),
    );
  }

  return { findings, diagnostics: [] };
}

export const uiThemeBypassRule: ArchitectureRule = {
  id: 'ARCH-UI-THEME-BYPASS',
  description:
    'Production code outside mygui/application_theme/ must not publish application font, palette, or bundled QSS.',
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

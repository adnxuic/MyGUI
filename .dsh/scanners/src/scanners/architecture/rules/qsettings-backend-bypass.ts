/**
 * ARCH-QSETTINGS-BACKEND-BYPASS
 *
 * AGENTS.md CORE-APPLICATION-SETTINGS: injected dual-slot QSettings is the
 * only persistent application-preference store. Production code outside
 * `mygui/application_settings/storage/` must not construct QSettings or
 * mutate a QSettings store (beginGroup/endGroup/setValue/remove/clear on a
 * settings-named receiver, plus QSettings-specific group APIs).
 *
 * Recorded as a planned gray candidate during settings decoupling, then
 * promoted after production callers left the storage adapter. Type
 * annotations and duck-type checks (`hasattr(..., "setValue")`) are not
 * constructions and are never reported.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  isSettingsStoragePath,
  lastNamed,
  makeFinding,
  namedSegments,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const QSETTINGS_GROUP_APIS = new Set([
  'beginGroup',
  'endGroup',
  'childGroups',
  'childKeys',
  'allKeys',
]);
const QSETTINGS_STORE_MUTATIONS = new Set(['setValue', 'remove', 'clear']);
const QSETTINGS_RECEIVERS = new Set([
  'settings',
  '_settings',
  'store',
  '_store',
  'qsettings',
  'q_settings',
]);

function isQSettingsConstruction(chain: AttrChain, model: PyFileModel): boolean {
  if (!chain.isCall) return false;
  const method = lastNamed(chain);
  if (method === 'QSettings') return true;
  const names = namedSegments(chain);
  if (names.length === 1) {
    const alias = model.aliasLine(names[0]!, chain.line);
    if (alias !== undefined && lastNamed(alias) === 'QSettings') return true;
  }
  return false;
}

function resolvedMutationReceiver(chain: AttrChain, model: PyFileModel): string | undefined {
  const names = namedSegments(chain);
  if (names.length < 2) return undefined;
  const receiver = names[names.length - 2]!;
  if (QSETTINGS_RECEIVERS.has(receiver)) return receiver;
  const alias = model.aliasLine(receiver, chain.line);
  if (alias === undefined) return receiver;
  const aliasNames = namedSegments(alias);
  const last = aliasNames[aliasNames.length - 1];
  return last;
}

function isQSettingsMutation(chain: AttrChain, model: PyFileModel): boolean {
  if (!chain.isCall) return false;
  const method = lastNamed(chain);
  if (method === undefined) return false;
  if (QSETTINGS_GROUP_APIS.has(method)) return true;
  if (!QSETTINGS_STORE_MUTATIONS.has(method)) return false;
  const receiver = resolvedMutationReceiver(chain, model);
  if (receiver === undefined) return false;
  return QSETTINGS_RECEIVERS.has(receiver);
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  if (isSettingsStoragePath(model.path)) return { findings, diagnostics: [] };
  const testPath = isTestPath(model.path);
  const seen = new Set<number>();

  for (const chain of model.chains) {
    if (seen.has(chain.line)) continue;
    if (isQSettingsConstruction(chain, model)) {
      seen.add(chain.line);
      findings.push(
        makeFinding({
          model,
          ruleId: 'ARCH-QSETTINGS-BACKEND-BYPASS',
          line: chain.line,
          severity: 'high',
          confidence: 0.95,
          title: 'Production code constructs QSettings outside the storage adapter',
          reason:
            'QSettings(...) is constructed outside mygui/application_settings/storage/. ' +
            'Production preferences must go through the injected SettingsBackend dual-slot ports.',
          suggestedAction:
            'Inject SettingsBackend / a document port from create_settings_backend and do not construct QSettings.',
          tags: [...(testPath ? ['test-code'] : ['production']), 'qsettings-backend-bypass'],
        }),
      );
      continue;
    }
    if (!isQSettingsMutation(chain, model)) continue;
    seen.add(chain.line);
    const method = lastNamed(chain) ?? 'mutate';
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-QSETTINGS-BACKEND-BYPASS',
        line: chain.line,
        severity: 'high',
        confidence: 0.85,
        title: `Production code mutates QSettings via ${method}()`,
        reason:
          `${method}() is a QSettings store mutation outside mygui/application_settings/storage/. ` +
          'Commit through DualSlotDocumentPort / ApplicationSettingsService instead.',
        suggestedAction:
          'Route the write through the injected settings document port; do not call QSettings mutation APIs.',
        tags: [...(testPath ? ['test-code'] : ['production']), 'qsettings-backend-bypass'],
      }),
    );
  }

  return { findings, diagnostics: [] };
}

export const qsettingsBackendBypassRule: ArchitectureRule = {
  id: 'ARCH-QSETTINGS-BACKEND-BYPASS',
  description:
    'Production code outside mygui/application_settings/storage/ must not construct or mutate QSettings.',
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

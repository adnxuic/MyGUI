/**
 * ARCH-FIGURE-LAYOUT-ENGINE-BYPASS
 *
 * AGENTS.md CORE-FIGURE-LAYOUT-ENGINE-OWNER: FigureController.properties.layout_engine
 * is the sole authority for Figure layout engines (none, tight, constrained, compressed);
 * Figure Inspector is the only direct UI editing surface.
 *
 * This high-confidence rule reports:
 *   1. Production code re-introducing the retired `constrained_layout` boolean proxy
 *      field, keyword, or parameter (outside exposure_contract.py).
 *   2. Axes Layout flow calling `set_layout_engine` or writing `layout_engine` property.
 *   3. `AxesLayoutService` calling Figure `apply_state()` as a whole to modify layouts
 *      instead of pure data mutations `ComponentMutation(data={"layouts": ...})`.
 *
 * FigureController, property normalizers, restore/history, and read-only engine kind
 * inspection in Axes Layout UI are sanctioned and never reported.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  firstNamed,
  lastNamed,
  makeFinding,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const RETIRED_PROXY_REGEX = /\bconstrained_layout\b/;
const RETIRED_PROXY_EXEMPT_PATHS = new Set([
  'mygui/figuremodify/components/exposure_contract.py',
]);

function isAxesLayoutScope(model: PyFileModel, line?: number): boolean {
  const norm = model.path.replace(/\\/g, '/');
  if (
    norm.includes('axes_layout') ||
    norm.includes('titlebar_dialog/axes_layout_input.py') ||
    norm.includes('titlebar_dialog/py_title_bar_dialog.py') ||
    norm.includes('figure_layout_bypass')
  ) {
    return true;
  }
  if (line !== undefined) {
    const enclosing = model.classAt(line);
    if (enclosing && /^(?:AxesLayout|PyLayout)/.test(enclosing.name)) {
      return true;
    }
  }
  return false;
}

function isAxesLayoutServiceScope(model: PyFileModel, line?: number): boolean {
  const norm = model.path.replace(/\\/g, '/');
  if (norm.endsWith('axes_layout_service.py') || norm.includes('figure_layout_bypass')) {
    return true;
  }
  if (line !== undefined) {
    const enclosing = model.classAt(line);
    if (enclosing && enclosing.name === 'AxesLayoutService') {
      return true;
    }
  }
  return false;
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  const normPath = model.path.replace(/\\/g, '/');
  const seen = new Set<number>();

  // 1. Check for retired `constrained_layout` proxy across production code
  if (!RETIRED_PROXY_EXEMPT_PATHS.has(normPath)) {
    for (const line of model.lines) {
      if (seen.has(line.number)) continue;
      if (RETIRED_PROXY_REGEX.test(line.raw)) {
        seen.add(line.number);
        findings.push(
          makeFinding({
            model,
            ruleId: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
            line: line.number,
            severity: 'high',
            confidence: 0.95,
            title: 'Production code references retired constrained_layout proxy',
            reason:
              '`constrained_layout` is a retired boolean proxy. ' +
              'FigureController.properties.layout_engine is the sole layout-engine authority.',
            suggestedAction:
              'Manage Figure layout engines through FigureController.properties.layout_engine ' +
              '(kinds: none, tight, constrained, compressed) and Figure Inspector.',
            tags: [...(testPath ? ['test-code'] : ['production']), 'figure-layout-engine-bypass'],
          }),
        );
      }
    }
  }

  // 2. Axes Layout flow calling set_layout_engine or writing layout_engine property
  if (isAxesLayoutScope(model)) {
    for (const chain of model.chains) {
      if (seen.has(chain.line)) continue;
      const method = lastNamed(chain);

      // Calling set_layout_engine(...)
      if (chain.isCall && method === 'set_layout_engine') {
        seen.add(chain.line);
        findings.push(
          makeFinding({
            model,
            ruleId: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
            line: chain.line,
            severity: 'high',
            confidence: 0.95,
            title: 'Axes Layout code calls set_layout_engine() directly',
            reason:
              'Axes Layout flow must not call set_layout_engine(). ' +
              'FigureController.properties.layout_engine and Figure Inspector are the sole authoritative editor.',
            suggestedAction:
              'Manage GridSpec geometry only; preserve existing Figure layout engine configuration.',
            tags: [...(testPath ? ['test-code'] : ['production']), 'figure-layout-engine-bypass'],
          }),
        );
        continue;
      }

      // Calling set_property("layout_engine", ...)
      if (chain.isCall && method === 'set_property') {
        const rawLine = model.lines[chain.line - 1]?.raw ?? '';
        if (/["']layout_engine["']/.test(rawLine)) {
          seen.add(chain.line);
          findings.push(
            makeFinding({
              model,
              ruleId: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
              line: chain.line,
              severity: 'high',
              confidence: 0.95,
              title: 'Axes Layout code writes layout_engine property',
              reason:
                'Axes Layout flow must not write the layout_engine property. ' +
                'FigureController and Figure Inspector are the sole authoritative editor.',
              suggestedAction:
                'Manage GridSpec geometry only; preserve existing Figure layout engine configuration.',
              tags: [...(testPath ? ['test-code'] : ['production']), 'figure-layout-engine-bypass'],
            }),
          );
          continue;
        }
      }
    }

    // Direct property assignment target: properties["layout_engine"] = ... or properties.layout_engine = ...
    for (const chain of model.assignmentTargetChains) {
      if (seen.has(chain.line)) continue;
      const rawLine = model.lines[chain.line - 1]?.raw ?? '';
      if (/properties\s*\[\s*["']layout_engine["']\s*\]\s*=/.test(rawLine) ||
          /properties\s*=\s*\{.*["']layout_engine["']/.test(rawLine)) {
        seen.add(chain.line);
        findings.push(
          makeFinding({
            model,
            ruleId: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
            line: chain.line,
            severity: 'high',
            confidence: 0.95,
            title: 'Axes Layout code assigns layout_engine property directly',
            reason:
              'Axes Layout flow must not assign layout_engine property. ' +
              'FigureController and Figure Inspector are the sole authoritative editor.',
            suggestedAction:
              'Manage GridSpec geometry only; preserve existing Figure layout engine configuration.',
            tags: [...(testPath ? ['test-code'] : ['production']), 'figure-layout-engine-bypass'],
          }),
        );
      }
    }
  }

const FIGURE_RECEIVERS = new Set([
  'root',
  'root_ctrl',
  'root_controller',
  'figure',
  'fig',
  'figure_controller',
  'fig_ctrl',
]);

  // 3. AxesLayoutService calling apply_state() on FigureController
  if (isAxesLayoutServiceScope(model)) {
    for (const chain of model.chains) {
      if (seen.has(chain.line)) continue;
      if (chain.isCall && lastNamed(chain) === 'apply_state') {
        const receiver = firstNamed(chain);
        if (receiver !== undefined && FIGURE_RECEIVERS.has(receiver)) {
          seen.add(chain.line);
          findings.push(
            makeFinding({
              model,
              ruleId: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
              line: chain.line,
              severity: 'high',
              confidence: 0.95,
              title: 'AxesLayoutService calls Figure apply_state()',
              reason:
                'AxesLayoutService must update Figure layout definitions via pure data mutation ' +
                'ComponentMutation(data={"layouts": ...}) and apply_mutation(), not whole apply_state().',
              suggestedAction:
                'Use root.apply_mutation(ComponentMutation(root.component_id, data={"layouts": ...})) instead.',
              tags: [...(testPath ? ['test-code'] : ['production']), 'figure-layout-engine-bypass'],
            }),
          );
        }
      }
    }
  }

  return { findings, diagnostics: [] };
}

export const figureLayoutEngineBypassRule: ArchitectureRule = {
  id: 'ARCH-FIGURE-LAYOUT-ENGINE-BYPASS',
  description:
    'Figure layout_engine is owned solely by FigureController/Inspector; Axes Layout manages GridSpec geometry with pure data mutations and must not mutate layout_engine or call apply_state().',
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

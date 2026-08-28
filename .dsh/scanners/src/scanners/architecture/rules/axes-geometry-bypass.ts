/**
 * ARCH-AXES-GEOMETRY-BYPASS
 *
 * AGENTS.md CORE-AXES-GEOMETRY-OWNER: AxesGeometryService is the sole authority
 * for individual Axes grid vs manual projection and manual bounds.
 *
 * This high-confidence rule reports:
 *   1. Presentation, Inspector, or helper code directly calling `set_position()`,
 *      `_set_position()`, `set_subplotspec()`, or `set_in_layout()` on an Axes
 *      outside the authorized services and adapters.
 *   2. Accessing private `_subplotspec` attribute directly.
 *
 * Authorized boundaries:
 *   - mygui/figuremodify/axes_geometry.py
 *   - mygui/figuremodify/services/axes_geometry.py
 *   - mygui/figuremodify/components/matplotlib_removal.py
 *   - mygui/figuremodify/matplotlib_adapter.py
 */

import { isTestPath } from '../../../lib/files.ts';
import type { PyFileModel } from '../../../lib/py/model.ts';
import {
  lastNamed,
  makeFinding,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const EXEMPT_PATHS = new Set([
  'mygui/figuremodify/axes_geometry.py',
  'mygui/figuremodify/services/axes_geometry.py',
  'mygui/figuremodify/components/matplotlib_removal.py',
  'mygui/figuremodify/matplotlib_adapter.py',
  'mygui/figuremodify/components/controllers/annotation.py',
  'mygui/figuremodify/components/controllers/text.py',
  'mygui/figuremodify/components/controllers/field_2d.py',
  'mygui/figuremodify/components/controllers/in_axes.py',
  'mygui/figuremodify/field_2d_runtime.py',
  'mygui/figuremodify/in_axes.py',
]);

const BYPASS_METHODS = new Set([
  'set_position',
  '_set_position',
  'set_subplotspec',
  'set_in_layout',
]);

function isExemptPath(normPath: string): boolean {
  for (const exempt of EXEMPT_PATHS) {
    if (normPath.endsWith(exempt) || normPath.includes(exempt)) {
      return true;
    }
  }
  return false;
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  const normPath = model.path.replace(/\\/g, '/');

  if (isExemptPath(normPath)) {
    return { findings, diagnostics: [] };
  }

  const seen = new Set<number>();

  for (const chain of model.chains) {
    if (seen.has(chain.line)) continue;
    const method = lastNamed(chain);
    if (!method) continue;

    if (chain.isCall && BYPASS_METHODS.has(method)) {
      seen.add(chain.line);
      findings.push(
        makeFinding({
          model,
          ruleId: 'ARCH-AXES-GEOMETRY-BYPASS',
          line: chain.line,
          severity: 'high',
          confidence: 0.95,
          title: `Direct call to ${method}() bypasses AxesGeometryService`,
          reason:
            `Directly calling ${method}() bypasses the authoritative AxesGeometryService. ` +
            'Individual Axes geometry and GridSpec projection must be managed through AxesGeometryService.',
          suggestedAction:
            'Use AxesGeometryService.switch_to_manual(), set_manual_bounds(), return_to_grid(), or reset_to_grid_bounds() instead.',
          tags: [...(testPath ? ['test-code'] : ['production']), 'axes-geometry-bypass'],
        }),
      );
    } else if (method === '_subplotspec') {
      seen.add(chain.line);
      findings.push(
        makeFinding({
          model,
          ruleId: 'ARCH-AXES-GEOMETRY-BYPASS',
          line: chain.line,
          severity: 'high',
          confidence: 0.95,
          title: 'Direct access to _subplotspec bypasses AxesGeometryService',
          reason:
            'Accessing private _subplotspec bypasses AxesGeometryService and AxesLayoutService.',
          suggestedAction:
            'Use public AxesGeometryService and AxesLayoutService APIs instead.',
          tags: [...(testPath ? ['test-code'] : ['production']), 'axes-geometry-bypass'],
        }),
      );
    }
  }

  return { findings, diagnostics: [] };
}

export const axesGeometryBypassRule: ArchitectureRule = {
  id: 'ARCH-AXES-GEOMETRY-BYPASS',
  description:
    'Axes geometry and GridSpec projection are owned solely by AxesGeometryService; other code must not call geometry mutators or access _subplotspec directly.',
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

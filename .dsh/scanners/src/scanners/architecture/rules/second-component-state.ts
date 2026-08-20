/**
 * ARCH-SECOND-COMPONENT-STATE
 *
 * AGENTS.md: "Treat `ComponentRegistry`, `ComponentState`, Controllers, and
 * domain Services as the only mutable business-state path for Figure
 * components. Inspector/UI code must not maintain a second component state
 * model" and "`PyFigureCanvas.current_component_id` is the only
 * authoritative component selection."
 *
 * High-confidence candidates only:
 *   - `ComponentState(...)` construction in `mygui/widgets/` outside
 *     `PyFigureCanvas` (a second, UI-owned state model);
 *   - `ComponentRegistry(...)` construction outside `PyFigureCanvas`
 *     (a second authoritative registry);
 *   - `self.current_component_id = ...` writes outside `PyFigureCanvas`
 *     (a second selection authority). Writes to `canvas.current_component_id`
 *     are the sanctioned DeletionCoordinator path and are not reported.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  firstNamed,
  hasNamedSegment,
  isWidgetsPath,
  makeFinding,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

function isAuthorizedClass(name: string): boolean {
  if (name === 'PyFigureCanvas') return true;
  if (name.endsWith('Canvas')) return true;
  if (name.endsWith('Controller')) return true;
  if (name.endsWith('Service')) return true;
  return false;
}

function report(
  model: PyFileModel,
  line: number,
  confidence: number,
  title: string,
  reason: string,
  testPath: boolean,
): RuleOutcome['findings'][number] {
  return makeFinding({
    model,
    ruleId: 'ARCH-SECOND-COMPONENT-STATE',
    line,
    severity: 'high',
    confidence,
    title,
    reason,
    tags: [...(testPath ? ['test-code'] : ['production']), 'second-state'],
  });
}

function isStateConstructionCall(chain: AttrChain, name: string): boolean {
  return (
    chain.isCall &&
    chain.segments.length === 1 &&
    !chain.segments[0]!.isIndex &&
    chain.segments[0]!.name === name
  );
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  if (!isWidgetsPath(model.path)) return { findings, diagnostics: [] };

  for (const chain of model.chains) {
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;

    if (isStateConstructionCall(chain, 'ComponentState')) {
      findings.push(
        report(
          model,
          chain.line,
          0.8,
          'UI code constructs ComponentState',
          'ComponentState must be created through the authoritative component path (Controllers/domain Services, or PyFigureCanvas during registration). A UI-owned ComponentState is a second business-state model.',
          testPath,
        ),
      );
    } else if (isStateConstructionCall(chain, 'ComponentRegistry')) {
      findings.push(
        report(
          model,
          chain.line,
          0.7,
          'UI code constructs a second ComponentRegistry',
          'ComponentRegistry is the authoritative mutable business-state path; constructing another instance in UI code creates a second state authority.',
          testPath,
        ),
      );
    }
  }

  // `self.current_component_id = ...` outside PyFigureCanvas.
  for (const chain of model.assignmentTargetChains) {
    if (hasNamedSegment(chain, 'current_component_id') && firstNamed(chain) === 'self') {
      const enclosing = model.classAt(chain.line);
      if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;
      findings.push(
        report(
          model,
          chain.line,
          0.85,
          'UI code maintains its own current_component_id',
          `${enclosing?.name ?? 'module-level code'} writes self.current_component_id; PyFigureCanvas.current_component_id is the only authoritative component selection, and Inspector/UI code must not keep a second selection model.`,
          testPath,
        ),
      );
    }
  }
  return { findings, diagnostics: [] };
}

export const secondComponentStateRule: ArchitectureRule = {
  id: 'ARCH-SECOND-COMPONENT-STATE',
  description:
    'UI code maintaining a second Figure component business-state model: ComponentState/ComponentRegistry construction or current_component_id writes outside PyFigureCanvas.',
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

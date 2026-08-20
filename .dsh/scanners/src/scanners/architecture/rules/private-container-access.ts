/**
 * ARCH-PRIVATE-CONTAINER-ACCESS
 *
 * AGENTS.md (Inspector Container Rules): "Window and Canvas callers must use
 * the public container methods for add, find, show, remove, clear, and
 * toolbox lookup. They must not access `_figure_stack`, `_inspector_stack`,
 * `_toolboxes`, `_chart_stack`, `_element_stack`, or other private Qt layout
 * state."
 *
 * Owners are computed per file: a class owns an attribute when it assigns
 * `self.<attr> = ...`, and ownership extends to subclasses (transitively).
 * Accesses inside an owning class are legal; accesses from any other class
 * or from module scope are reported.
 */

import type { PyFileModel } from '../../../lib/py/model.ts';
import { isTestPath } from '../../../lib/files.ts';
import {
  PRIVATE_CONTAINER_ATTRS,
  makeFinding,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

function ownersFor(model: PyFileModel, attr: string): Set<string> {
  const direct = new Set<string>();
  for (const assignment of model.selfAssigns) {
    if (assignment.attr !== attr) continue;
    const cls = model.classAt(assignment.line);
    if (cls !== undefined) direct.add(cls.name);
  }
  // Extend ownership to subclasses (transitively, within this file).
  const byName = new Map(model.classes.map((cls) => [cls.name, cls]));
  const names = new Set(direct);
  let changed = true;
  let depth = 0;
  while (changed && depth < 8) {
    changed = false;
    for (const cls of model.classes) {
      if (names.has(cls.name)) continue;
      if (cls.bases.some((base) => names.has(base) && byName.has(base))) {
        names.add(cls.name);
        changed = true;
      }
    }
    depth += 1;
  }
  return names;
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);

  for (const attr of PRIVATE_CONTAINER_ATTRS) {
    const owners = ownersFor(model, attr);
    for (const chain of model.chains) {
      // Only attribute-position segments count (segment index >= 1):
      // a bare local variable named `_toolboxes` is not container state.
      for (let i = 1; i < chain.segments.length; i += 1) {
        const segment = chain.segments[i]!;
        if (segment.isIndex || segment.name !== attr) continue;
        const enclosing = model.classAt(chain.line);
        if (enclosing !== undefined && owners.has(enclosing.name)) continue;

        const receiverIsSelf = chain.segments[0]!.name === 'self';
        const confidence = enclosing !== undefined ? (receiverIsSelf ? 0.9 : 0.7) : 0.6;
        const severity = enclosing !== undefined ? 'medium' : 'low';
        const reason = enclosing !== undefined
          ? `class ${enclosing.name} accesses ${attr} but does not own it (container private state must be reached through public container methods).`
          : `${attr} is accessed at module scope outside any owning container class; use public container methods instead.`;
        findings.push(
          makeFinding({
            model,
            ruleId: 'ARCH-PRIVATE-CONTAINER-ACCESS',
            line: chain.line,
            severity,
            confidence,
            title: `Private container state ${attr} accessed outside its owner`,
            reason,
            tags: testPath ? ['test-code'] : ['production'],
          }),
        );
      }
    }
  }
  return { findings, diagnostics: [] };
}

export const privateContainerAccessRule: ArchitectureRule = {
  id: 'ARCH-PRIVATE-CONTAINER-ACCESS',
  description:
    'Accesses to private Qt layout state (_figure_stack, _inspector_stack, _toolboxes, _chart_stack, _element_stack) from outside the owning container classes.',
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

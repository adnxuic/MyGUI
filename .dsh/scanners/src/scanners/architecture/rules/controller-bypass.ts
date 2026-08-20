/**
 * ARCH-CONTROLLER-BYPASS
 *
 * AGENTS.md: "Route all edits through Controllers or Services." UI/Inspector
 * code must not directly operate on the authoritative component business
 * state (the `state` object owned by registered Controllers).
 *
 * v1 reports only high-confidence write patterns in `mygui/widgets/` outside
 * Controller/Service/Canvas classes:
 *   - assignment targets touching `*.state.properties/data/selector` (direct
 *     dict or field mutation), including whole-field replacement
 *     (`x.state.properties = ...`) and whole-state replacement
 *     (`x.state = ...`);
 *   - mutation calls on those fields: `x.state.data.update(...)`,
 *     `x.state.properties.setdefault(...)`, `.pop(...)`, `.clear(...)`.
 *
 * Reads (`x.state.data.get(...)`) are the normal Inspector synchronization
 * path and are never reported.
 */

import { isTestPath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  firstNamed,
  isWidgetsPath,
  lastNamed,
  makeFinding,
  namedSegments,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

const STATE_FIELDS = new Set(['properties', 'data', 'selector']);
const MUTATION_METHODS = new Set(['update', 'setdefault', 'pop', 'clear']);

function isAuthorizedClass(name: string): boolean {
  if (name === 'PyFigureCanvas') return true;
  if (name.endsWith('Canvas')) return true;
  if (name.endsWith('Controller')) return true;
  if (name.endsWith('Service')) return true;
  return false;
}

/** Index (in namedSegments) of the `state` segment, when present. */
function stateSegmentIndex(chain: AttrChain): number {
  const names = namedSegments(chain);
  return names.indexOf('state');
}

function isDirectStateMutation(chain: AttrChain): boolean {
  const names = namedSegments(chain);
  const stateIndex = names.indexOf('state');
  if (stateIndex < 0) return false;
  const last = names[names.length - 1]!;
  // `x.state.properties[...] = ...` / `x.state.data = ...`
  if (last === 'state' && names.length >= 2) return true; // whole-state replacement
  if (STATE_FIELDS.has(last)) return true; // field-level write (assignment target)
  // `x.state.data.update(...)` / `.pop(...)` / ...
  if (MUTATION_METHODS.has(last) && names.length >= 3) {
    const before = names[names.length - 2]!;
    if (STATE_FIELDS.has(before)) return true;
  }
  return false;
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  if (!isWidgetsPath(model.path)) return { findings, diagnostics: [] };

  const seen = new Set<number>();

  for (const chain of model.assignmentTargetChains) {
    if (!isDirectStateMutation(chain)) continue;
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;
    if (seen.has(chain.line)) continue;
    seen.add(chain.line);

    const names = namedSegments(chain);
    const stateIndex = stateSegmentIndex(chain);
    const target = names.slice(stateIndex).join('.');
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-CONTROLLER-BYPASS',
        line: chain.line,
        severity: 'high',
        confidence: 0.8,
        title: 'UI code mutates authoritative component state directly',
        reason:
          `${firstNamed(chain) ?? 'value'}.${target} is written directly in UI code. ` +
          `Mutable component business state must be changed through the Registry/Controller or a domain Service (e.g. registry.set_properties / apply_transaction), not by mutating the state object.`,
        tags: [...(testPath ? ['test-code'] : ['production']), 'controller-bypass'],
      }),
    );
  }

  for (const chain of model.chains) {
    if (!chain.isCall) continue;
    if (!isDirectStateMutation(chain)) continue;
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;
    if (seen.has(chain.line)) continue;
    seen.add(chain.line);

    const names = namedSegments(chain);
    const stateIndex = stateSegmentIndex(chain);
    const target = names.slice(stateIndex).join('.');
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-CONTROLLER-BYPASS',
        line: chain.line,
        severity: 'high',
        confidence: 0.8,
        title: 'UI code mutates authoritative component state directly',
        reason:
          `${firstNamed(chain) ?? 'value'}.${target}() is called directly in UI code. ` +
          `Mutable component business state must be changed through the Registry/Controller or a domain Service.`,
        tags: [...(testPath ? ['test-code'] : ['production']), 'controller-bypass'],
      }),
    );
  }

  return { findings, diagnostics: [] };
}

export const controllerBypassRule: ArchitectureRule = {
  id: 'ARCH-CONTROLLER-BYPASS',
  description:
    'UI/Inspector code in mygui/widgets/ writing to controller state (state.properties/data/selector) instead of routing edits through Controllers/Services.',
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

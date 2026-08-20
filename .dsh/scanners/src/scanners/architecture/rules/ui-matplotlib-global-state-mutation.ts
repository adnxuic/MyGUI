/**
 * ARCH-UI-MPL-GLOBAL-STATE-MUTATION
 *
 * AGENTS.md (Component Architecture Rules) requires Inspector/UI code to
 * route business-state changes through Controllers/Services. Matplotlib's
 * process-global mutable configuration (`rcParams`, `matplotlib.rc(...)`) is
 * NOT Artist state, so ARCH-UI-ARTIST-MUTATION never reports it — but
 * mutating it from the UI layer still leaks process-global side effects out
 * of presentation code: it affects every Figure/canvas, leaks state between
 * tests, couples behavior to window-operation order, and blurs configuration
 * ownership (UI lifetime vs Matplotlib process lifetime).
 *
 * This rule is deliberately INDEPENDENT of ARCH-UI-ARTIST-MUTATION: it
 * reports direct mutation of Matplotlib GLOBAL mutable configuration from
 * `mygui/widgets/` (the UI/Inspector/presentation layer), not Artist
 * instances, and ARCH-UI-ARTIST-MUTATION is untouched.
 *
 * Mutation sinks (v0.2.0):
 *   - `rcParams[key] = ...` assignments (mutation: assignment);
 *   - `rcParams.update({...})` calls (mutation: update);
 *   - `matplotlib.rc(...)` / `mpl.rc(...)` / `rc(...)` calls
 *     (mutation: rc-call).
 *
 * Import aliases are resolved through the file model's import bindings:
 *   `import matplotlib`, `import matplotlib as mpl`,
 *   `from matplotlib import rcParams`, `from matplotlib import rc`.
 * Reads (`rcParams[key]` on the RHS, `rcParams.get(...)`, `by_key()`, ...)
 * are never reported.
 *
 * Exemptions:
 *   - files outside `mygui/widgets/` — the dedicated configuration owners
 *     (e.g. `mygui/tex_config.py`) legitimately own/apply Matplotlib
 *     configuration;
 *   - classes named *Controller / *Service / *Coordinator / *Canvas;
 *   - test code (tagged `test-code`, excluded from production scans by the
 *     scanner defaults; an explicit include re-enables it with the tag).
 *
 * Severity mapping (the scanner severity ladder has no `warning`/`error`):
 *   user `warning` -> `medium`  (architecture smell, not a hard failure)
 *   user `error`   -> `high`    (AGENTS.md explicitly forbids the mutation)
 *
 * The rule reads the workspace AGENTS.md on every run; when it explicitly
 * forbids UI mutation of Matplotlib global configuration ("UI must not
 * mutate Matplotlib global configuration directly", or "Matplotlib
 * configuration mutation must go through TexConfigService / RenderingService
 * / Controller / equivalent owner"), findings escalate from `medium` to
 * `high`.
 */

import { isTestPath, readFileText, resolveWorkspacePath } from '../../../lib/files.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  isWidgetsPath,
  lastNamed,
  makeFinding,
  namedSegments,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
  type ScannerFinding,
} from './common.ts';

/** Matplotlib and its submodules (matplotlib, matplotlib.pyplot, ...). */
const MATPLOTLIB_MODULE_RE = /^matplotlib(?:\.|$)/;

const DEFAULT_SEVERITY = 'medium' as const;
const ESCALATED_SEVERITY = 'high' as const;

type MutationKind = 'assignment' | 'update' | 'rc-call';

interface MplGlobalMutation {
  kind: MutationKind;
  /** Config key for `rcParams[key]`/`update({key: ...})` when determinable. */
  key: string | undefined;
  /** Canonical target description, e.g. `matplotlib.rcParams`. */
  target: string;
}

/** Classes allowed to touch Matplotlib configuration: domain owners + canvas. */
function isAuthorizedClass(name: string): boolean {
  if (name === 'PyFigureCanvas') return true;
  if (name.endsWith('Canvas')) return true;
  if (name.endsWith('Controller')) return true;
  if (name.endsWith('Service')) return true;
  if (name.endsWith('Coordinator')) return true;
  return false;
}

/** Key literal of an assignment, e.g. `text.usetex` from `mpl.rcParams['text.usetex'] = True`. */
function keyFromAssignment(model: PyFileModel, chain: AttrChain): string | undefined {
  const raw = model.lines[chain.line - 1]?.raw ?? '';
  const match = /rcParams\s*\[\s*['"]([^'"]+)['"]\s*\]/.exec(raw);
  return match?.[1];
}

/** Config keys inside an `update({...})` literal, e.g. `text.usetex` from `{"text.usetex": True}`. */
function keysFromUpdate(model: PyFileModel, chain: AttrChain): string | undefined {
  const raw = model.lines[chain.line - 1]?.raw ?? '';
  const body = /\{([^}]*)\}/.exec(raw)?.[1];
  if (body === undefined) return undefined;
  const keys = [...body.matchAll(/['"]([^'"]+)['"]\s*:/g)].map((match) => match[1]!).slice(0, 3);
  return keys.length > 0 ? keys.join(', ') : undefined;
}

/**
 * Classify one chain as a Matplotlib global-configuration mutation sink,
 * resolving the receiver root through the file's import bindings.
 */
function detectMutation(chain: AttrChain, model: PyFileModel): MplGlobalMutation | undefined {
  const names = namedSegments(chain);
  if (names.length === 0) return undefined;
  const root = names[0]!;
  const binding = model.resolveImport(root, chain.line);
  if (binding === undefined || !MATPLOTLIB_MODULE_RE.test(binding.module)) return undefined;

  // `matplotlib.rc(...)` / `mpl.rc(...)` (module alias) / `rc(...)` (from-import).
  if (chain.isCall && lastNamed(chain) === 'rc') {
    if (binding.symbol === 'rc' && names.length === 1) {
      return { kind: 'rc-call', key: undefined, target: 'matplotlib.rc' };
    }
    if (binding.symbol === undefined && names.length === 2 && names[1] === 'rc') {
      return { kind: 'rc-call', key: undefined, target: 'matplotlib.rc' };
    }
  }

  // `rcParams[key] = ...` / `rcParams.update(...)` via `from matplotlib import rcParams`.
  if (binding.symbol === 'rcParams') {
    if (chain.isCall && names.length === 2 && names[1] === 'update') {
      return { kind: 'update', key: keysFromUpdate(model, chain), target: 'matplotlib.rcParams' };
    }
    if (!chain.isCall && chain.segments.length >= 2 && chain.segments[1]!.isIndex) {
      return { kind: 'assignment', key: keyFromAssignment(model, chain), target: 'matplotlib.rcParams' };
    }
    return undefined;
  }

  // Module-alias receivers: `mpl.rcParams[key] = ...`, `mpl.rcParams.update(...)`,
  // `mpl.rcParams = ...` (whole-object replacement).
  if (binding.symbol === undefined && names.length >= 2 && names[1] === 'rcParams') {
    if (chain.isCall && names.length === 3 && lastNamed(chain) === 'update') {
      return { kind: 'update', key: keysFromUpdate(model, chain), target: 'matplotlib.rcParams' };
    }
    if (!chain.isCall) {
      if (chain.segments.length >= 3 && chain.segments[2]!.isIndex) {
        return { kind: 'assignment', key: keyFromAssignment(model, chain), target: 'matplotlib.rcParams' };
      }
      if (chain.segments.length === 2) {
        return { kind: 'assignment', key: undefined, target: 'matplotlib.rcParams' };
      }
    }
  }
  return undefined;
}

function analyzeModel(model: PyFileModel): RuleOutcome {
  const findings: ScannerFinding[] = [];
  const testPath = isTestPath(model.path);
  if (!isWidgetsPath(model.path)) return { findings, diagnostics: [] };

  const seen = new Set<string>();
  const report = (chain: AttrChain, mutation: MplGlobalMutation): void => {
    const line = chain.line;
    const key = mutation.key;
    const keyText = key ?? 'unknown';
    const seenKey = `${line}:${mutation.kind}`;
    if (seen.has(seenKey)) return;
    seen.add(seenKey);
    const confidence = mutation.kind === 'assignment' ? 0.9 : mutation.kind === 'update' ? 0.85 : 0.8;
    const keySuffix = key === undefined ? '' : ` (${key})`;
    findings.push(
      makeFinding({
        model,
        ruleId: 'ARCH-UI-MPL-GLOBAL-STATE-MUTATION',
        line,
        severity: DEFAULT_SEVERITY,
        confidence,
        title: `UI code mutates Matplotlib global configuration${keySuffix} (${mutation.kind})`,
        reason:
          `${mutation.target} ${mutation.kind} (${keyText}) in UI code directly mutates Matplotlib ` +
          `process-global mutable configuration instead of delegating configuration ownership to an ` +
          `architectural Service/Controller (e.g. mygui/tex_config.py). This is not an Artist-state ` +
          `mutation, but it leaks process-global side effects from the presentation layer.`,
        tags: [
          ...(testPath ? ['test-code'] : ['production']),
          'ui-matplotlib-global-state-mutation',
          'matplotlib-global-state',
          `mutation-${mutation.kind}`,
        ],
      }),
    );
  };

  for (const chain of model.assignmentTargetChains) {
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;
    const mutation = detectMutation(chain, model);
    if (mutation !== undefined) report(chain, mutation);
  }
  for (const chain of model.chains) {
    if (!chain.isCall) continue;
    const enclosing = model.classAt(chain.line);
    if (enclosing !== undefined && isAuthorizedClass(enclosing.name)) continue;
    const mutation = detectMutation(chain, model);
    if (mutation !== undefined) report(chain, mutation);
  }
  return { findings, diagnostics: [] };
}

/**
 * True when AGENTS.md explicitly forbids UI mutation of Matplotlib global
 * configuration (the escalation clause; Artist-only prohibitions do NOT
 * match — this rule stays independent of ARCH-UI-ARTIST-MUTATION).
 */
export function agentsMdEscalates(text: string): boolean {
  // Active: "UI must not mutate Matplotlib global configuration directly".
  if (/must not[\s\S]{0,120}mutat\w*[\s\S]{0,120}(?:matplotlib|rcparams)[\s\S]{0,120}(?:global|configur|rcparams)/i.test(text)) {
    return true;
  }
  // Passive: "Matplotlib global configuration must not be mutated by UI".
  if (/(?:matplotlib|rcparams)[\s\S]{0,120}(?:global|configur|rcparams)[\s\S]{0,120}must not[\s\S]{0,120}mutat\w*/i.test(text)) {
    return true;
  }
  // Ownership: "Matplotlib configuration mutation must go through
  // TexConfigService / RenderingService / Controller / equivalent owner".
  if (/(?:matplotlib|rcparams)[\s\S]{0,160}(?:global|configur|rcparams)[\s\S]{0,200}must (?:go through|be (?:owned|applied|changed))[\s\S]{0,100}(?:service|controller|coordinator|config)/i.test(text)) {
    return true;
  }
  return false;
}

export const uiMatplotlibGlobalStateMutationRule: ArchitectureRule = {
  id: 'ARCH-UI-MPL-GLOBAL-STATE-MUTATION',
  description:
    'Direct mutation of Matplotlib process-global mutable configuration (rcParams assignment/update, matplotlib.rc calls) from UI code in mygui/widgets/ outside Controller/Service/Canvas classes.',
  async run(context: RuleRunContext): Promise<RuleOutcome> {
    const findings: ScannerFinding[] = [];
    const diagnostics = [];
    let escalated = false;
    const agentsMd = await readFileText(resolveWorkspacePath(context.workspace, 'AGENTS.md'));
    if (agentsMd !== undefined) escalated = agentsMdEscalates(agentsMd);
    for (const model of context.files) {
      const outcome = analyzeModel(model);
      if (escalated) {
        for (const finding of outcome.findings) finding.severity = ESCALATED_SEVERITY;
      }
      findings.push(...outcome.findings);
      diagnostics.push(...outcome.diagnostics);
    }
    return { findings, diagnostics };
  },
};

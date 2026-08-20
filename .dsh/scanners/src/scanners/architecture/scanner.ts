/**
 * The `mygui.architecture` scanner (v0.2.0): static, read-only architecture
 * checks over the MyGUI repository. It never modifies the repository, never
 * formats code, never auto-fixes, and never launches the GUI.
 *
 * Rule sources: the architecture contracts recorded in the repository's
 * AGENTS.md. The scanner does not invent rules.
 *
 * v0.2.0 adds ARCH-UI-MPL-GLOBAL-STATE-MUTATION (UI/Inspector direct
 * mutation of Matplotlib process-global configuration: rcParams assignment /
 * update, matplotlib.rc calls) as an independent rule, alongside the
 * existing UI -> Artist mutation rule. Registry metadata now carries
 * `capabilities` so Worker selection matches rcParams/global-state tasks.
 */

import { execFile } from 'node:child_process';
import { join } from 'node:path';
import type { ScannerDefinition, ScannerDiagnostic, ScannerFinding, ScannerRequest, ScannerResult, ScannerSeverity } from '../../contracts.ts';
import { collectPythonFiles, globToRegExp, readFileText, resolveWorkspacePath } from '../../lib/files.ts';
import { buildPyFileModel, type PyFileModel } from '../../lib/py/model.ts';
import { ARCHITECTURE_RULES } from './rules/index.ts';

/** Files excluded from the production scan by default (test isolation). */
export const DEFAULT_EXCLUDE = ['tests/**', '**/test_*.py', '**/fixtures/**'];

const DEFAULT_EXCLUDE_RE = DEFAULT_EXCLUDE.map((pattern) => globToRegExp(pattern));

/** Attempt to read the git revision; never throws. */
async function readRevision(workspace: string): Promise<string | undefined> {
  try {
    return await new Promise<string | undefined>((resolve) => {
      execFile(
        'git',
        ['rev-parse', '--short', 'HEAD'],
        { cwd: workspace, timeout: 2000, windowsHide: true },
        (error, stdout) => {
          if (error) {
            resolve(undefined);
            return;
          }
          resolve(stdout.trim() || undefined);
        },
      );
    });
  } catch {
    return undefined;
  }
}

function makeSummary(findings: ScannerFinding[]): ScannerResult['summary'] {
  const bySeverity: Partial<Record<ScannerSeverity, number>> = {};
  for (const finding of findings) {
    bySeverity[finding.severity] = (bySeverity[finding.severity] ?? 0) + 1;
  }
  return { total: findings.length, bySeverity };
}

export function createArchitectureScanner(): ScannerDefinition {
  return {
    id: 'mygui.architecture',
    version: '0.2.0',
    description:
      'Static architecture-rule checks for the MyGUI repository (AGENTS.md contracts): container-private access, UI artist mutation, UI mutation of Matplotlib global configuration, second component state, controller bypass.',
    capabilities: [
      'ui_artist_mutation',
      'ui_matplotlib_global_state_mutation',
      'matplotlib_rcparams_mutation',
      'rendering_configuration_ownership',
    ],
    async run(request: ScannerRequest): Promise<ScannerResult> {
      const startedAt = new Date().toISOString();
      const startedMs = Date.now();
      const diagnostics: ScannerDiagnostic[] = [];

      // Explicit `include` patterns win over the default test exclusions:
      // scanning `tests/**` on purpose must not be silently swallowed.
      const explicitInclude = request.include ?? [];
      const includeRe = explicitInclude.map((pattern) => globToRegExp(pattern));
      const relPaths = await collectPythonFiles({
        workspace: request.workspace,
        include: explicitInclude,
        exclude: request.exclude,
        changedFiles: request.changedFiles,
        signal: request.signal,
      });
      const selected = relPaths.filter((relPath) => {
        if (!DEFAULT_EXCLUDE_RE.some((re) => re.test(relPath))) return true;
        return includeRe.some((re) => re.test(relPath));
      });
      if (selected.length < relPaths.length) {
        diagnostics.push({
          level: 'info',
          message: `excluded ${relPaths.length - selected.length} test/fixture file(s) from the production scan (include them explicitly to scan)`,
        });
      }

      const models: PyFileModel[] = [];
      for (const relPath of selected) {
        if (request.signal?.aborted) break;
        const text = await readFileText(resolveWorkspacePath(request.workspace, relPath));
        if (text === undefined) {
          diagnostics.push({ level: 'warning', message: `could not read ${relPath}`, file: relPath });
          continue;
        }
        try {
          models.push(buildPyFileModel(relPath, text));
        } catch (error) {
          diagnostics.push({
            level: 'warning',
            message: `failed to analyze ${relPath}: ${error instanceof Error ? error.message : String(error)}`,
            file: relPath,
          });
        }
      }

      const context = { request, workspace: request.workspace, files: models };
      const findings: ScannerFinding[] = [];
      for (const rule of ARCHITECTURE_RULES) {
        if (request.signal?.aborted) break;
        const outcome = await rule.run(context);
        findings.push(...outcome.findings);
        diagnostics.push(...outcome.diagnostics);
      }

      const durationMs = Date.now() - startedMs;
      return {
        scannerId: 'mygui.architecture',
        scannerVersion: '0.2.0',
        workspace: join(request.workspace),
        revision: await readRevision(request.workspace),
        startedAt,
        durationMs,
        filesScanned: models.length,
        findings,
        summary: makeSummary(findings),
        diagnostics,
      };
    },
  };
}

/** Static, read-only MyGUI architecture scanner with ScannerResult v2 evidence. */

import { execFile } from 'node:child_process';
import { join } from 'node:path';
import {
  SCANNER_CONTRACT_VERSION,
  deriveVerdict,
  type ScannerDefinition,
  type ScannerDiagnostic,
  type ScannerError,
  type ScannerFinding,
  type ScannerGrayBoundary,
  type ScannerRequest,
  type ScannerResult,
  type ScannerSeverity,
  type ScannerSkippedFile,
  type ScannerStatus,
} from '../../contracts.ts';
import {
  collectPythonFiles,
  globToRegExp,
  isTestPath,
  readFileText,
  resolveWorkspacePath,
  workspaceDirectoryExists,
} from '../../lib/files.ts';
import { fingerprintFor } from '../../lib/hash.ts';
import { buildPyFileModel, type AttrChain, type PyFileModel } from '../../lib/py/model.ts';
import { ARCHITECTURE_RULES } from './rules/index.ts';
import {
  evidenceOf,
  isWidgetsPath,
  lastNamed,
  receiverIsArtistLike,
  receiverIsKnownNonArtist,
} from './rules/common.ts';

export const DEFAULT_EXCLUDE = ['tests/**', '**/test_*.py', '**/fixtures/**', '.agents/**'];
const DEFAULT_EXCLUDE_RE = DEFAULT_EXCLUDE.map((pattern) => globToRegExp(pattern));
const SCANNER_ID = 'mygui.architecture';
const SCANNER_VERSION = '0.5.0';
const MUTATION_METHOD = /^(?:set_[a-z_][a-z0-9_]*|remove)$/;
const AMBIGUOUS_RECEIVERS = new Set(['target', 'handle', 'item', 'object', 'current', 'selected']);

async function readRevision(workspace: string): Promise<string | undefined> {
  try {
    return await new Promise((resolve) => {
      execFile('git', ['rev-parse', '--short', 'HEAD'], { cwd: workspace, timeout: 2000, windowsHide: true },
        (error, stdout) => resolve(error ? undefined : stdout.trim() || undefined));
    });
  } catch {
    return undefined;
  }
}

function isAuthorizedClass(name: string): boolean {
  return name === 'PyFigureCanvas' || /(Canvas|Controller|Service|Coordinator)$/.test(name);
}

function ambiguousArtistBoundary(model: PyFileModel, chain: AttrChain): ScannerGrayBoundary | undefined {
  if (!chain.isCall || !isWidgetsPath(model.path)) return undefined;
  const method = lastNamed(chain);
  if (method === undefined || !MUTATION_METHOD.test(method)) return undefined;
  const enclosing = model.classAt(chain.line);
  if (enclosing && isAuthorizedClass(enclosing.name)) return undefined;
  if (receiverIsArtistLike(chain, model) || receiverIsKnownNonArtist(chain)) return undefined;
  const receiver = chain.segments.slice(0, -1).filter((segment) => !segment.isIndex).at(-1)?.name;
  if (receiver === undefined || !AMBIGUOUS_RECEIVERS.has(receiver)) return undefined;
  const evidence = evidenceOf(model, chain.line);
  const category = 'ambiguous-ui-artist-mutation';
  return {
    id: `GRAY-${category}@${model.path}#${chain.line}`,
    scannerId: SCANNER_ID,
    category,
    confidence: 0.45,
    file: model.path,
    line: chain.line,
    evidence,
    whyNotViolation: `The receiver ${receiver} is ambiguous; lexical evidence cannot prove it is a Matplotlib Artist.`,
    evolutionCandidate: 'Resolve the receiver through a Controller/Service type path or promote a stronger receiver classification with fixtures.',
    fingerprint: fingerprintFor(category, model.path, chain.line, evidence),
  };
}

function collectGrayBoundaries(models: PyFileModel[], findings: ScannerFinding[]): ScannerGrayBoundary[] {
  const boundaries: ScannerGrayBoundary[] = [];
  const findingLines = new Set(findings.map((item) => `${item.file}:${item.line ?? 0}`));
  for (const model of models) {
    if (!isWidgetsPath(model.path)) continue;
    for (const chain of model.chains) {
      const boundary = ambiguousArtistBoundary(model, chain);
      if (boundary) boundaries.push(boundary);
    }
    for (const line of model.lines) {
      if (findingLines.has(`${model.path}:${line.number}`)) continue;
      const raw = line.raw.trim();
      if (!/\brcParams\b|\b(?:matplotlib|mpl)\.rc\s*\(/.test(raw)) continue;
      if (!/=|\.update\s*\(|\.rc\s*\(/.test(raw)) continue;
      const category = 'unresolved-matplotlib-global-state';
      boundaries.push({
        id: `GRAY-${category}@${model.path}#${line.number}`,
        scannerId: SCANNER_ID,
        category,
        confidence: 0.4,
        file: model.path,
        line: line.number,
        evidence: raw.slice(0, 160),
        whyNotViolation: 'The mutation-like text is present, but the lexical import resolver did not prove a Matplotlib binding.',
        evolutionCandidate: 'Add an alias/import fixture and extend binding resolution if this is a real process-global write.',
        fingerprint: fingerprintFor(category, model.path, line.number, raw.slice(0, 160)),
      });
    }
  }
  return boundaries.sort((a, b) => a.file.localeCompare(b.file) || (a.line ?? 0) - (b.line ?? 0) || a.category.localeCompare(b.category));
}

function makeSummary(findings: ScannerFinding[], gray: ScannerGrayBoundary[], errors: ScannerError[]): ScannerResult['summary'] {
  const bySeverity: Partial<Record<ScannerSeverity, number>> = {};
  for (const finding of findings) bySeverity[finding.severity] = (bySeverity[finding.severity] ?? 0) + 1;
  return { findings: findings.length, grayBoundaries: gray.length, errors: errors.length, bySeverity };
}

export function createArchitectureScanner(): ScannerDefinition {
  return {
    id: SCANNER_ID,
    version: SCANNER_VERSION,
    description: 'Static MyGUI architecture checks with violation, gray-boundary, coverage, and error evidence.',
    capabilities: [
      'ui_artist_mutation', 'ui_matplotlib_global_state_mutation',
      'matplotlib_rcparams_mutation', 'rendering_configuration_ownership',
      'qsettings_backend_bypass', 'ui_theme_bypass',
      'figure_layout_engine_ownership',
    ],
    async run(request: ScannerRequest): Promise<ScannerResult> {
      const startedAt = new Date().toISOString();
      const startedMs = Date.now();
      const diagnostics: ScannerDiagnostic[] = [];
      const errors: ScannerError[] = [];
      const skipped: ScannerSkippedFile[] = [];
      const workspaceExists = await workspaceDirectoryExists(request.workspace);
      if (!workspaceExists) {
        errors.push({ code: 'WORKSPACE_NOT_FOUND', message: `Workspace is not a directory: ${request.workspace}`, recoverable: false });
      }
      const explicitInclude = request.include ?? [];
      const includeRe = explicitInclude.map((pattern) => globToRegExp(pattern));
      const relPaths = workspaceExists ? await collectPythonFiles({
        workspace: request.workspace, include: explicitInclude, exclude: request.exclude,
        changedFiles: request.changedFiles, signal: request.signal,
      }) : [];
      const selected = relPaths.filter((relPath) => {
        if (!DEFAULT_EXCLUDE_RE.some((re) => re.test(relPath)) || includeRe.some((re) => re.test(relPath))) return true;
        skipped.push({ file: relPath, reason: 'default test/fixture exclusion' });
        return false;
      });
      if (skipped.length) diagnostics.push({ level: 'info', message: `excluded ${skipped.length} test/fixture file(s) from the production scan` });

      const models: PyFileModel[] = [];
      for (const relPath of selected) {
        if (request.signal?.aborted) break;
        const text = await readFileText(resolveWorkspacePath(request.workspace, relPath));
        if (text === undefined) {
          errors.push({ code: 'FILE_READ_FAILED', message: `Could not read ${relPath}`, recoverable: true, file: relPath });
          skipped.push({ file: relPath, reason: 'read failed' });
          continue;
        }
        try {
          models.push(buildPyFileModel(relPath, text));
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          errors.push({ code: 'ANALYSIS_FAILED', message, recoverable: true, file: relPath });
          skipped.push({ file: relPath, reason: 'analysis failed' });
        }
      }
      if (request.signal?.aborted) errors.push({ code: 'ABORTED', message: 'Scan was cancelled before coverage completed.', recoverable: true });

      const context = { request, workspace: request.workspace, files: models };
      const findings: ScannerFinding[] = [];
      for (const rule of ARCHITECTURE_RULES) {
        if (request.signal?.aborted) break;
        const outcome = await rule.run(context);
        findings.push(...outcome.findings);
        diagnostics.push(...outcome.diagnostics);
      }
      findings.sort((a, b) => a.file.localeCompare(b.file) || (a.line ?? 0) - (b.line ?? 0) || a.ruleId.localeCompare(b.ruleId));
      const grayBoundaries = collectGrayBoundaries(models, findings);
      const status: ScannerStatus = !workspaceExists ? 'failed' : errors.length > 0 ? 'partial' : 'completed';
      const revision = workspaceExists ? await readRevision(request.workspace) : undefined;
      return {
        contractVersion: SCANNER_CONTRACT_VERSION,
        scanner: { id: SCANNER_ID, version: SCANNER_VERSION },
        status,
        verdict: deriveVerdict(status, findings, grayBoundaries),
        scope: {
          workspace: join(request.workspace), ...(revision ? { revision } : {}),
          include: [...explicitInclude], exclude: [...(request.exclude ?? [])], changedFiles: [...(request.changedFiles ?? [])],
        },
        startedAt,
        durationMs: Date.now() - startedMs,
        findings,
        grayBoundaries,
        coverage: {
          filesVisited: models.map((model) => model.path),
          filesSkipped: skipped,
          limitations: ['Dependency-free lexical analysis does not prove dynamic Python receiver types.'],
        },
        errors,
        diagnostics,
        summary: makeSummary(findings, grayBoundaries, errors),
      };
    },
  };
}

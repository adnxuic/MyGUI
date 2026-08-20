/** Static, read-only Qt lifecycle scanner with ScannerResult v2 evidence. */

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
  type ScannerSkippedFile,
  type ScannerStatus,
} from '../../contracts.ts';
import {
  collectPythonFiles,
  globToRegExp,
  readFileText,
  resolveWorkspacePath,
  workspaceDirectoryExists,
} from '../../lib/files.ts';
import { fingerprintFor } from '../../lib/hash.ts';
import { buildPyFileModel, type PyFileModel } from '../../lib/py/model.ts';
import { QT_LIFECYCLE_RULES } from './rules/index.ts';
import { chainEndingWith, evidenceOf, lastNamed, rawLine } from './rules/common.ts';

export const DEFAULT_EXCLUDE = ['tests/**', '**/test_*.py', '**/fixtures/**', '.agents/**'];
const DEFAULT_EXCLUDE_RE = DEFAULT_EXCLUDE.map((pattern) => globToRegExp(pattern));
const SCANNER_ID = 'mygui.qt-lifecycle';
const SCANNER_VERSION = '0.2.0';

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

function exactCleanup(model: PyFileModel, start: number, end: number, attr: string, methods: string[]): boolean {
  const escaped = attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`self\\.${escaped}\\.(?:${methods.join('|')})\\s*\\(`);
  for (let line = start; line <= end; line += 1) if (pattern.test(rawLine(model, line))) return true;
  return false;
}

function boundary(
  model: PyFileModel,
  line: number,
  category: string,
  why: string,
  candidate: string,
): ScannerGrayBoundary {
  const evidence = evidenceOf(model, line);
  return {
    id: `GRAY-${category}@${model.path}#${line}`,
    scannerId: SCANNER_ID,
    category,
    confidence: 0.45,
    file: model.path,
    line,
    evidence,
    whyNotViolation: why,
    evolutionCandidate: candidate,
    fingerprint: fingerprintFor(category, model.path, line, evidence),
  };
}

function collectGrayBoundaries(models: PyFileModel[], findings: ScannerFinding[]): ScannerGrayBoundary[] {
  const gray: ScannerGrayBoundary[] = [];
  const findingLines = new Set(findings.map((item) => `${item.file}:${item.line ?? 0}`));
  for (const model of models) {
    for (const assign of model.selfAssigns) {
      if (findingLines.has(`${model.path}:${assign.line}`)) continue;
      const raw = rawLine(model, assign.line);
      const cls = model.classAt(assign.line);
      if (!cls) continue;
      if (/QTimer\s*\(\s*(?:self\b|[^)]*\bparent\s*=\s*self\b)/.test(raw)) continue;
      if (/QTimer\s*\(/.test(raw)) {
        const anyCleanup = ['stop', 'deleteLater'].some((name) => chainEndingWith(model, cls.startLine, cls.endLine, name));
        if (anyCleanup && !exactCleanup(model, cls.startLine, cls.endLine, assign.attr, ['stop', 'deleteLater'])) {
          gray.push(boundary(
            model, assign.line, 'ambiguous-qt-timer-cleanup',
            `The class has timer cleanup vocabulary, but the lexical scan cannot prove it targets self.${assign.attr}.`,
            'Make the timer parent or exact self-attribute cleanup explicit; add a receiver-specific fixture if generic cleanup is intentional.',
          ));
        }
      }
      if (/QThread\s*\(/.test(raw)) {
        const methods = ['quit', 'wait', 'requestInterruption', 'terminate', 'deleteLater'];
        const anyCleanup = methods.some((name) => chainEndingWith(model, cls.startLine, cls.endLine, name));
        if (anyCleanup && !exactCleanup(model, cls.startLine, cls.endLine, assign.attr, methods)) {
          gray.push(boundary(
            model, assign.line, 'ambiguous-qthread-shutdown',
            `The class has QThread shutdown vocabulary, but the lexical scan cannot prove it targets self.${assign.attr}.`,
            'Make the thread-specific shutdown path explicit or extend receiver tracking with positive and negative fixtures.',
          ));
        }
      }
    }
    for (const chain of model.chains) {
      if (!chain.isCall || lastNamed(chain) !== 'connect') continue;
      const def = model.defAt(chain.line);
      const cls = model.classAt(chain.line);
      if (!def || !cls || !/^(sync|update|refresh|rebind|reset|switch|restore|apply|select|setup)/i.test(def.name)) continue;
      if (!/\.connect\s*\([^)]*lambda\b/.test(rawLine(model, chain.line))) continue;
      if (!chainEndingWith(model, cls.startLine, cls.endLine, 'disconnect')) continue;
      gray.push(boundary(
        model, chain.line, 'ambiguous-signal-rebind-disconnect',
        'The class disconnects a signal somewhere, but the lexical scan cannot prove it is the same signal before every rebind.',
        'Use a stable slot or an explicit same-signal disconnect/reconnect path and add a repeat-invocation fixture.',
      ));
    }
  }
  return gray.sort((a, b) => a.file.localeCompare(b.file) || (a.line ?? 0) - (b.line ?? 0) || a.category.localeCompare(b.category));
}

function makeSummary(findings: ScannerFinding[], gray: ScannerGrayBoundary[], errors: ScannerError[]): ScannerResult['summary'] {
  const bySeverity: ScannerResult['summary']['bySeverity'] = {};
  for (const finding of findings) bySeverity[finding.severity] = (bySeverity[finding.severity] ?? 0) + 1;
  return { findings: findings.length, grayBoundaries: gray.length, errors: errors.length, bySeverity };
}

export function createQtLifecycleScanner(): ScannerDefinition {
  return {
    id: SCANNER_ID,
    version: SCANNER_VERSION,
    description: 'Static Qt lifecycle and QObject ownership checks with violation, gray-boundary, coverage, and error evidence.',
    capabilities: ['qt_timer_ownership', 'qt_thread_lifecycle', 'qt_signal_rebind'],
    async run(request: ScannerRequest): Promise<ScannerResult> {
      const startedAt = new Date().toISOString();
      const startedMs = Date.now();
      const diagnostics: ScannerDiagnostic[] = [];
      const errors: ScannerError[] = [];
      const skipped: ScannerSkippedFile[] = [];
      const workspaceExists = await workspaceDirectoryExists(request.workspace);
      if (!workspaceExists) errors.push({ code: 'WORKSPACE_NOT_FOUND', message: `Workspace is not a directory: ${request.workspace}`, recoverable: false });
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
          errors.push({ code: 'ANALYSIS_FAILED', message: error instanceof Error ? error.message : String(error), recoverable: true, file: relPath });
          skipped.push({ file: relPath, reason: 'analysis failed' });
        }
      }
      if (request.signal?.aborted) errors.push({ code: 'ABORTED', message: 'Scan was cancelled before coverage completed.', recoverable: true });

      const context = { request, workspace: request.workspace, files: models };
      const findings: ScannerFinding[] = [];
      for (const rule of QT_LIFECYCLE_RULES) {
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
          limitations: ['Lexical lifecycle analysis does not prove dynamic QObject ownership or signal identity.'],
        },
        errors,
        diagnostics,
        summary: makeSummary(findings, grayBoundaries, errors),
      };
    },
  };
}

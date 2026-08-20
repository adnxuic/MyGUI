/**
 * Shared helpers for Qt-lifecycle rules: chain predicates, owning-class
 * queries, and qt finding construction (scannerId-scoped).
 */

import { fingerprintFor } from '../../../lib/hash.ts';
import type { AttrChain, PyFileModel } from '../../../lib/py/model.ts';
import {
  type ScannerDiagnostic,
  type ScannerFinding,
  type ScannerRequest,
  type ScannerSeverity,
} from '../../../contracts.ts';

export interface QtRuleRunContext {
  request: ScannerRequest;
  workspace: string;
  /** All scanned file models (test files already excluded by the scanner). */
  files: PyFileModel[];
}

export interface QtRuleOutcome {
  findings: ScannerFinding[];
  diagnostics: ScannerDiagnostic[];
}

export interface QtRule {
  id: string;
  description: string;
  run(context: QtRuleRunContext): QtRuleOutcome | Promise<QtRuleOutcome>;
}

/** The scanner id every qt-lifecycle finding carries. */
export const QT_SCANNER_ID = 'mygui.qt-lifecycle';

/** Last non-index segment name of a chain. */
export function lastNamed(chain: AttrChain): string | undefined {
  for (let i = chain.segments.length - 1; i >= 0; i -= 1) {
    const segment = chain.segments[i]!;
    if (!segment.isIndex) return segment.name;
  }
  return undefined;
}

/**
 * True when a call chain ending with `name` exists anywhere in the inclusive
 * line range. Used to ask "does this class/def ever call `.stop()` /
 * `.disconnect()` / `.quit()` ...?".
 */
export function chainEndingWith(model: PyFileModel, fromLine: number, toLine: number, name: string): boolean {
  for (const chain of model.chains) {
    if (chain.line < fromLine || chain.line > toLine || !chain.isCall) continue;
    if (lastNamed(chain) === name) return true;
  }
  return false;
}

/** Trimmed raw text of one line (the evidence basis). */
export function rawLine(model: PyFileModel, line: number): string {
  return model.lines[line - 1]?.raw.trim() ?? '';
}

/** Truncated evidence text (brief, per the finding contract). */
export function evidenceOf(model: PyFileModel, line: number, maxLength = 160): string {
  const raw = rawLine(model, line);
  if (raw.length <= maxLength) return raw;
  return `${raw.slice(0, maxLength - 1)}…`;
}

/** Build a qt-lifecycle finding with stable fingerprint and id. */
export function makeQtFinding(options: {
  model: PyFileModel;
  ruleId: string;
  line: number;
  severity: ScannerSeverity;
  confidence: number;
  title: string;
  reason: string;
  suggestedAction?: string;
  tags?: string[];
}): ScannerFinding {
  const { model, ruleId, line, severity, confidence, title, reason, suggestedAction, tags } = options;
  const evidence = evidenceOf(model, line);
  const id = `${ruleId}@${model.path}#${line}`;
  return {
    id,
    scannerId: QT_SCANNER_ID,
    ruleId,
    severity,
    confidence,
    file: model.path,
    line,
    title,
    evidence,
    reason,
    suggestedAction: suggestedAction ?? 'Make QObject ownership and teardown explicit, then add positive and negative lifecycle tests.',
    tags: tags ?? [],
    fingerprint: fingerprintFor(ruleId, model.path, line, evidence),
  };
}

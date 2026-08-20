/** Dependency-free runtime validation for the ScannerResult v2 contract. */

import {
  SCANNER_CONTRACT_VERSION,
  ScannerContractError,
  deriveVerdict,
  type ScannerError,
  type ScannerFinding,
  type ScannerGrayBoundary,
  type ScannerResult,
  type ScannerSeverity,
} from './contracts.ts';

const SEVERITIES: readonly ScannerSeverity[] = ['info', 'low', 'medium', 'high', 'critical'];

function isSeverity(value: unknown): value is ScannerSeverity {
  return typeof value === 'string' && (SEVERITIES as readonly string[]).includes(value);
}

function validateExactKeys(value: object, allowed: readonly string[], where: string): void {
  const unexpected = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unexpected.length > 0) throw new ScannerContractError(`${where} has unknown fields: ${unexpected.join(', ')}`);
}

function isAbsolutePath(file: string): boolean {
  return file.startsWith('/') || file.startsWith('\\') || /^[A-Za-z]:[\\/]/.test(file) || file.startsWith('..');
}

function validateRelativeLocation(value: { file: string; line?: number; column?: number }, where: string): void {
  if (typeof value.file !== 'string' || value.file === '' || isAbsolutePath(value.file)) {
    throw new ScannerContractError(`${where} file must be a workspace-relative path`);
  }
  for (const key of ['line', 'column'] as const) {
    const item = value[key];
    if (item !== undefined && (!Number.isInteger(item) || item < 1)) {
      throw new ScannerContractError(`${where} ${key} must be a positive integer`);
    }
  }
}

function validateFinding(finding: ScannerFinding, scannerId: string, index: number): void {
  const where = `finding #${index}`;
  if (typeof finding !== 'object' || finding === null) throw new ScannerContractError(`${where} is not an object`);
  validateExactKeys(finding, ['id', 'scannerId', 'ruleId', 'severity', 'confidence', 'file', 'line', 'column', 'title', 'evidence', 'reason', 'suggestedAction', 'tags', 'fingerprint'], where);
  if (finding.scannerId !== scannerId) throw new ScannerContractError(`${where} scannerId does not match ${scannerId}`);
  for (const key of ['id', 'ruleId', 'title', 'evidence', 'reason', 'suggestedAction', 'fingerprint'] as const) {
    if (typeof finding[key] !== 'string' || finding[key] === '') throw new ScannerContractError(`${where} ${key} must be non-empty`);
  }
  if (!isSeverity(finding.severity)) throw new ScannerContractError(`${where} severity is invalid`);
  if (!Number.isFinite(finding.confidence) || finding.confidence < 0 || finding.confidence > 1) {
    throw new ScannerContractError(`${where} confidence must be in [0, 1]`);
  }
  validateRelativeLocation(finding, where);
  if (!Array.isArray(finding.tags) || finding.tags.some((tag) => typeof tag !== 'string')) {
    throw new ScannerContractError(`${where} tags must be an array of strings`);
  }
  if (new Set(finding.tags).size !== finding.tags.length) throw new ScannerContractError(`${where} tags must not contain duplicates`);
}

function validateGrayBoundary(value: ScannerGrayBoundary, scannerId: string, index: number): void {
  const where = `gray boundary #${index}`;
  if (typeof value !== 'object' || value === null) throw new ScannerContractError(`${where} is not an object`);
  validateExactKeys(value, ['id', 'scannerId', 'category', 'confidence', 'file', 'line', 'column', 'evidence', 'whyNotViolation', 'evolutionCandidate', 'fingerprint'], where);
  if (value.scannerId !== scannerId) throw new ScannerContractError(`${where} scannerId does not match ${scannerId}`);
  for (const key of ['id', 'category', 'evidence', 'whyNotViolation', 'evolutionCandidate', 'fingerprint'] as const) {
    if (typeof value[key] !== 'string' || value[key] === '') throw new ScannerContractError(`${where} ${key} must be non-empty`);
  }
  if (!Number.isFinite(value.confidence) || value.confidence < 0 || value.confidence > 1) {
    throw new ScannerContractError(`${where} confidence must be in [0, 1]`);
  }
  validateRelativeLocation(value, where);
}

function validateError(value: ScannerError, index: number): void {
  const where = `error #${index}`;
  if (typeof value !== 'object' || value === null) throw new ScannerContractError(`${where} is not an object`);
  validateExactKeys(value, ['code', 'message', 'recoverable', 'file'], where);
  if (typeof value.code !== 'string' || value.code === '' || typeof value.message !== 'string' || value.message === '') {
    throw new ScannerContractError(`${where} requires non-empty code and message`);
  }
  if (typeof value.recoverable !== 'boolean') throw new ScannerContractError(`${where} recoverable must be boolean`);
  if (value.file !== undefined && (value.file === '' || isAbsolutePath(value.file))) {
    throw new ScannerContractError(`${where} file must be workspace-relative`);
  }
}

function validateStringArray(value: unknown, where: string): asserts value is string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new ScannerContractError(`${where} must be an array of strings`);
  }
  if (new Set(value).size !== value.length) throw new ScannerContractError(`${where} must not contain duplicates`);
}

export function validateScannerResult(result: ScannerResult, scannerId: string): void {
  if (typeof result !== 'object' || result === null) throw new ScannerContractError('result is not an object');
  validateExactKeys(result, ['contractVersion', 'scanner', 'status', 'verdict', 'scope', 'startedAt', 'durationMs', 'findings', 'grayBoundaries', 'coverage', 'errors', 'diagnostics', 'summary'], 'result');
  if (result.contractVersion !== SCANNER_CONTRACT_VERSION) throw new ScannerContractError('result contractVersion must be exactly 2');
  if (typeof result.scanner !== 'object' || result.scanner === null || result.scanner.id !== scannerId) {
    throw new ScannerContractError(`result scanner.id must match ${scannerId}`);
  }
  validateExactKeys(result.scanner, ['id', 'version'], 'result scanner');
  if (typeof result.scanner.version !== 'string' || result.scanner.version === '') throw new ScannerContractError('result scanner.version is required');
  if (!['completed', 'partial', 'failed'].includes(result.status)) throw new ScannerContractError('result status is invalid');
  if (!['clean', 'violation', 'gray_boundary', 'unknown'].includes(result.verdict)) throw new ScannerContractError('result verdict is invalid');
  if (typeof result.scope !== 'object' || result.scope === null || typeof result.scope.workspace !== 'string' || result.scope.workspace === '') {
    throw new ScannerContractError('result scope.workspace is required');
  }
  validateExactKeys(result.scope, ['workspace', 'revision', 'include', 'exclude', 'changedFiles'], 'result scope');
  if (result.scope.revision !== undefined && (typeof result.scope.revision !== 'string' || result.scope.revision === '')) {
    throw new ScannerContractError('result scope.revision must be a non-empty string');
  }
  validateStringArray(result.scope.include, 'scope.include');
  validateStringArray(result.scope.exclude, 'scope.exclude');
  validateStringArray(result.scope.changedFiles, 'scope.changedFiles');
  if (typeof result.startedAt !== 'string' || Number.isNaN(Date.parse(result.startedAt))) throw new ScannerContractError('result startedAt must be ISO-8601');
  if (!Number.isFinite(result.durationMs) || result.durationMs < 0) throw new ScannerContractError('result durationMs must be non-negative');
  if (!Array.isArray(result.findings) || !Array.isArray(result.grayBoundaries) || !Array.isArray(result.errors)) {
    throw new ScannerContractError('findings, grayBoundaries, and errors must be arrays');
  }
  const ids = new Set<string>();
  result.findings.forEach((item, index) => {
    validateFinding(item, scannerId, index);
    if (ids.has(item.id)) throw new ScannerContractError(`duplicate evidence id ${item.id}`);
    ids.add(item.id);
  });
  result.grayBoundaries.forEach((item, index) => {
    validateGrayBoundary(item, scannerId, index);
    if (ids.has(item.id)) throw new ScannerContractError(`duplicate evidence id ${item.id}`);
    ids.add(item.id);
  });
  result.errors.forEach(validateError);
  if (result.verdict !== deriveVerdict(result.status, result.findings, result.grayBoundaries)) {
    throw new ScannerContractError('result verdict does not match status/findings/grayBoundaries');
  }
  if (typeof result.coverage !== 'object' || result.coverage === null) throw new ScannerContractError('result coverage is required');
  validateExactKeys(result.coverage, ['filesVisited', 'filesSkipped', 'limitations'], 'result coverage');
  validateStringArray(result.coverage.filesVisited, 'coverage.filesVisited');
  validateStringArray(result.coverage.limitations, 'coverage.limitations');
  for (const file of result.coverage.filesVisited) {
    if (file === '' || isAbsolutePath(file)) throw new ScannerContractError('coverage.filesVisited must contain workspace-relative paths');
  }
  if (!Array.isArray(result.coverage.filesSkipped)) throw new ScannerContractError('coverage.filesSkipped must be an array');
  for (const skipped of result.coverage.filesSkipped) {
    if (typeof skipped !== 'object' || skipped === null) throw new ScannerContractError('skipped file must be an object');
    validateExactKeys(skipped, ['file', 'reason'], 'skipped file');
    validateRelativeLocation(skipped, 'skipped file');
    if (typeof skipped.reason !== 'string' || skipped.reason === '') throw new ScannerContractError('skipped file reason is required');
  }
  if (!Array.isArray(result.diagnostics)) throw new ScannerContractError('result diagnostics must be an array');
  for (const diagnostic of result.diagnostics) {
    if (typeof diagnostic !== 'object' || diagnostic === null) throw new ScannerContractError('diagnostic must be an object');
    validateExactKeys(diagnostic, ['level', 'message', 'file'], 'diagnostic');
    if (!['info', 'warning', 'error'].includes(diagnostic.level) || typeof diagnostic.message !== 'string' || diagnostic.message === '') {
      throw new ScannerContractError('diagnostic has invalid level or message');
    }
    if (diagnostic.file !== undefined && isAbsolutePath(diagnostic.file)) throw new ScannerContractError('diagnostic file must be workspace-relative');
  }
  const expectedBySeverity: Partial<Record<ScannerSeverity, number>> = {};
  for (const item of result.findings) expectedBySeverity[item.severity] = (expectedBySeverity[item.severity] ?? 0) + 1;
  if (typeof result.summary !== 'object' || result.summary === null) throw new ScannerContractError('result summary is required');
  validateExactKeys(result.summary, ['findings', 'grayBoundaries', 'errors', 'bySeverity'], 'result summary');
  if (result.summary.findings !== result.findings.length || result.summary.grayBoundaries !== result.grayBoundaries.length || result.summary.errors !== result.errors.length) {
    throw new ScannerContractError('result summary counts do not match evidence arrays');
  }
  if (typeof result.summary.bySeverity !== 'object' || result.summary.bySeverity === null) throw new ScannerContractError('summary.bySeverity is required');
  validateExactKeys(result.summary.bySeverity, SEVERITIES, 'summary.bySeverity');
  for (const [severity, count] of Object.entries(result.summary.bySeverity)) {
    if (!isSeverity(severity) || !Number.isInteger(count) || count! < 0 || (expectedBySeverity[severity as ScannerSeverity] ?? 0) !== count) {
      throw new ScannerContractError(`summary.bySeverity[${severity}] does not match findings`);
    }
  }
  for (const [severity, count] of Object.entries(expectedBySeverity)) {
    if (result.summary.bySeverity[severity as ScannerSeverity] !== count) {
      throw new ScannerContractError(`summary.bySeverity[${severity}] is missing or incorrect`);
    }
  }
}

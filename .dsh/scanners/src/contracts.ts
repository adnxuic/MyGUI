/** Portable ScannerResult v2 contracts shared by every MyGUI DSH scanner. */

export const SCANNER_CONTRACT_VERSION = 2 as const;

export type ScannerSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type ScannerStatus = 'completed' | 'partial' | 'failed';
export type ScannerVerdict = 'clean' | 'violation' | 'gray_boundary' | 'unknown';

export interface ScannerFinding {
  id: string;
  scannerId: string;
  ruleId: string;
  severity: ScannerSeverity;
  confidence: number;
  file: string;
  line?: number;
  column?: number;
  title: string;
  evidence: string;
  reason: string;
  suggestedAction: string;
  tags: string[];
  fingerprint: string;
}

export interface ScannerGrayBoundary {
  id: string;
  scannerId: string;
  category: string;
  confidence: number;
  file: string;
  line?: number;
  column?: number;
  evidence: string;
  whyNotViolation: string;
  evolutionCandidate: string;
  fingerprint: string;
}

export interface ScannerSkippedFile {
  file: string;
  reason: string;
}

export interface ScannerError {
  code: string;
  message: string;
  recoverable: boolean;
  file?: string;
}

export interface ScannerDiagnostic {
  level: 'info' | 'warning' | 'error';
  message: string;
  file?: string;
}

export interface ScannerScope {
  workspace: string;
  revision?: string;
  include: string[];
  exclude: string[];
  changedFiles: string[];
}

export interface ScannerCoverage {
  filesVisited: string[];
  filesSkipped: ScannerSkippedFile[];
  limitations: string[];
}

export interface ScannerResult {
  contractVersion: typeof SCANNER_CONTRACT_VERSION;
  scanner: { id: string; version: string };
  status: ScannerStatus;
  verdict: ScannerVerdict;
  scope: ScannerScope;
  startedAt: string;
  durationMs: number;
  findings: ScannerFinding[];
  grayBoundaries: ScannerGrayBoundary[];
  coverage: ScannerCoverage;
  errors: ScannerError[];
  diagnostics: ScannerDiagnostic[];
  summary: {
    findings: number;
    grayBoundaries: number;
    errors: number;
    bySeverity: Partial<Record<ScannerSeverity, number>>;
  };
}

export interface ScannerRequest {
  workspace: string;
  include?: string[];
  exclude?: string[];
  changedFiles?: string[];
  signal?: AbortSignal;
}

export interface ScannerDefinition {
  id: string;
  version: string;
  description: string;
  capabilities?: string[];
  run(request: ScannerRequest): Promise<ScannerResult>;
}

export function deriveVerdict(
  status: ScannerStatus,
  findings: ScannerFinding[],
  grayBoundaries: ScannerGrayBoundary[],
): ScannerVerdict {
  if (status !== 'completed') return 'unknown';
  if (findings.length > 0) return 'violation';
  if (grayBoundaries.length > 0) return 'gray_boundary';
  return 'clean';
}

export class ScannerRegistryError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = 'ScannerRegistryError';
    this.code = code;
  }
}

export class ScannerContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScannerContractError';
  }
}

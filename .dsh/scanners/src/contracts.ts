/**
 * Scanner contracts — the shared, strongly typed surface of the MyGUI Scanner
 * infrastructure.
 *
 * These types are deliberately small and closed. Every scanner (current and
 * future: architecture, Qt lifecycle, project IO, persistence/schema, test
 * gap, CI) produces `ScannerResult` through the same `ScannerDefinition`
 * shape and is consumed through the `myguiScanners` registry service.
 *
 * Scanner plugins are Harness-internal capabilities. Nothing in this module
 * is model-facing: no tool schemas, no prompts, no LLM surface.
 */

/** Severity ladder used by every finding. */
export type ScannerSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

/** One violation (or notable observation) produced by a rule. */
export interface ScannerFinding {
  /** Stable id unique within one scan result (e.g. `${ruleId}@${file}#${line}`). */
  id: string;
  /** The scanner that produced this finding. */
  scannerId: string;
  /** The rule that produced this finding. */
  ruleId: string;

  severity: ScannerSeverity;
  /** Rule confidence in `[0, 1]` that this is a real violation. */
  confidence: number;

  /** Workspace-relative path (forward slashes). Never absolute. */
  file: string;
  /** 1-based line number, when the finding is anchored to a line. */
  line?: number;
  /** 1-based column, when known. */
  column?: number;

  /** Short human-readable title. */
  title: string;
  /** Short verbatim (or near-verbatim) code evidence. Keep it brief. */
  evidence: string;
  /** Why this code matches the rule. */
  reason: string;

  /** Free-form tags, e.g. `['ui']`, `['test-code']`, `['high-confidence']`. */
  tags: string[];

  /**
   * Stable fingerprint: identical for the same code + rule across runs.
   * Used to dedupe findings over time (same fingerprint = same issue).
   */
  fingerprint: string;
}

/** Recoverable, non-fatal note attached to a scan. */
export interface ScannerDiagnostic {
  level: 'info' | 'warning' | 'error';
  message: string;
  /** Workspace-relative file the diagnostic refers to, when applicable. */
  file?: string;
}

/** Uniform output of every scanner. */
export interface ScannerResult {
  scannerId: string;
  scannerVersion: string;

  /** Absolute workspace root that was scanned. */
  workspace: string;
  /** VCS revision (e.g. git HEAD) at scan time, when determinable. */
  revision?: string;

  /** ISO-8601 timestamp of scan start. */
  startedAt: string;
  /** Wall time of the scan in milliseconds. */
  durationMs: number;

  filesScanned: number;

  findings: ScannerFinding[];

  summary: {
    total: number;
    bySeverity: Partial<Record<ScannerSeverity, number>>;
  };

  diagnostics: ScannerDiagnostic[];
}

/** Uniform request accepted by every scanner. */
export interface ScannerRequest {
  /** Absolute path of the workspace root to scan. */
  workspace: string;

  /** Glob patterns to include (defaults to the scanner's own defaults). */
  include?: string[];
  /** Glob patterns to exclude (scanner defaults still apply). */
  exclude?: string[];

  /** Restrict scanning to these workspace-relative files, when provided. */
  changedFiles?: string[];

  /** Cancellation signal; scanners must observe it where practical. */
  signal?: AbortSignal;
}

/** Stable metadata + entry point of one scanner. */
export interface ScannerDefinition {
  /** Stable unique scanner id, e.g. `mygui.architecture`. */
  id: string;
  /** Semantic version of the scanner implementation, e.g. `0.1.0`. */
  version: string;
  /** One-line description shown by `list()`/`describe()`. */
  description: string;
  /**
   * Optional capability tags exposed through `list()`/`describe()` metadata,
   * e.g. `['ui_artist_mutation', 'ui_matplotlib_global_state_mutation']`.
   * Lets Worker selection match natural-language tasks ("rcParams mutation",
   * "presentation-layer side effects", ...) to this scanner.
   */
  capabilities?: string[];

  run(request: ScannerRequest): Promise<ScannerResult>;
}

/** Stable error class for registry-level failures. */
export class ScannerRegistryError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = 'ScannerRegistryError';
    this.code = code;
  }
}

/** A scanner violated the result contract (programmer error — fail loudly). */
export class ScannerContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScannerContractError';
  }
}

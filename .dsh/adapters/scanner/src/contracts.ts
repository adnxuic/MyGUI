/**
 * Dynamic Scanner Adapter contracts — the shared, strongly typed surface of
 * the MyGUI Scanner Adapter layer.
 *
 * This layer is deliberately thin. It never contains scanner rules: a rule
 * lives in the persistent scanner implementation under `.dsh/scanners/` and
 * is reached only through `myguiScanners.run(scannerId, request)`. What this
 * module owns is the *bridge* contract:
 *
 *   - what an Adapter mounts (scannerId / toolName / toolDescription /
 *     workspace);
 *   - the model-facing tool's argument surface (`include` / `exclude` /
 *     `changedFiles`);
 *   - the uniform Worker request and result shapes that a Scanner Worker
 *     session exchanges with its caller.
 *
 * Nothing in this module is model-facing by itself; it is support code for
 * the Worker and for tests.
 */

import type {
  ScannerDiagnostic,
  ScannerFinding,
  ScannerResult,
} from '../../../scanners/src/contracts.ts';

/**
 * Everything needed to mount one dynamic Adapter for one scanner.
 *
 * `toolName` must be derived deterministically from `scannerId` by
 * `toolNameFor()` in `tool-name.ts`; callers may also override it, but the
 * default must never be invented ad hoc.
 */
export interface ScannerAdapterConfig {
  /** Registry scanner id, e.g. `mygui.architecture`. */
  scannerId: string;
  /** Deterministic model-facing tool name, e.g. `mygui_architecture_scan`. */
  toolName: string;
  /** Model-facing description (scanner metadata + read-only declaration). */
  toolDescription: string;
  /** Absolute workspace root passed to `myguiScanners.run(...)`. */
  workspace: string;
}

/**
 * Model-facing tool arguments. The adapter forwards them to the registry
 * scanner unchanged; it adds no other knobs.
 */
export interface ScannerToolArgs {
  /** Glob patterns to include (defaults to the scanner's own defaults). */
  include?: string[];
  /** Glob patterns to exclude (scanner defaults still apply). */
  exclude?: string[];
  /** Restrict scanning to these workspace-relative files, when provided. */
  changedFiles?: string[];
}

/** Uniform request accepted by the Scanner Worker. */
export interface ScannerWorkerRequest {
  /** The inspection task, in natural language. */
  task: string;
  /** Absolute workspace root to scan. */
  workspace: string;

  include?: string[];
  exclude?: string[];
  changedFiles?: string[];

  /**
   * Optional explicit scanner selection. When present, the Worker validates
   * these ids against the registry instead of selecting from metadata.
   */
  requestedScanners?: string[];
}

/** One lifecycle step of one mounted adapter. */
export interface ScannerLifecycleRecord {
  scannerId: string;
  toolName: string;
  /** `cordis_define` produced an adapter package. */
  defined: boolean;
  /** `cordis_run` activated the adapter (tool became visible). */
  mounted: boolean;
  /** The model-facing tool was invoked at least once. */
  executed: boolean;
  /** `cordis_stop` removed the adapter (tool became absent). */
  stopped: boolean;
}

/** Uniform result produced by the Scanner Worker. */
export interface ScannerWorkerResult {
  status: 'completed' | 'partial' | 'missing_capability' | 'failed';

  /** Scanner ids the worker was asked to run (request or selection). */
  scannersRequested: string[];
  /** Scanner ids whose execution produced a result. */
  scannersExecuted: string[];

  /** All findings from the executed scanners, merged and deduplicated. */
  findings: ScannerFinding[];
  /** The raw ScannerResults of the executed scanners. */
  scannerResults: ScannerResult[];

  /** Per-scanner adapter lifecycle evidence. */
  lifecycle: ScannerLifecycleRecord[];

  /** Recoverable diagnostics, never swallowing failures. */
  diagnostics: ScannerDiagnostic[];
}

/**
 * The `myguiScanners` registry service: the single place scanners register,
 * are listed, and run through.
 *
 * Registration is lifecycle-bound through the disposer returned by
 * `register()` — a scanner plugin wraps it in `ctx.effect(...)`, so unloading
 * the plugin automatically removes the scanner. The service itself is a
 * Cordis `Service`, so unloading the registry plugin removes the service.
 */

import { Service, type Context } from '@deepseek-ai/cordis';
import {
  ScannerContractError,
  ScannerRegistryError,
  type ScannerDefinition,
  type ScannerDiagnostic,
  type ScannerFinding,
  type ScannerRequest,
  type ScannerResult,
  type ScannerSeverity,
} from '../contracts.ts';

export interface ScannerDescriptor {
  id: string;
  version: string;
  description: string;
  /** Capability tags declared by the scanner, when present. */
  capabilities?: string[];
}

const SEVERITIES: readonly ScannerSeverity[] = ['info', 'low', 'medium', 'high', 'critical'];

function isSeverity(value: unknown): value is ScannerSeverity {
  return typeof value === 'string' && (SEVERITIES as readonly string[]).includes(value);
}

function isAbsolutePath(file: string): boolean {
  return file.startsWith('/') || /^[A-Za-z]:[\\/]/.test(file) || file.startsWith('..');
}

/** Validate one finding against the contract; throws on violation. */
function validateFinding(finding: ScannerFinding, scannerId: string, index: number): void {
  const where = `finding #${index}`;
  if (typeof finding !== 'object' || finding === null) throw new ScannerContractError(`${where} is not an object`);
  if (typeof finding.id !== 'string' || finding.id === '') throw new ScannerContractError(`${where} has no id`);
  if (finding.scannerId !== scannerId) {
    throw new ScannerContractError(`${where} scannerId ${JSON.stringify(finding.scannerId)} does not match ${JSON.stringify(scannerId)}`);
  }
  if (typeof finding.ruleId !== 'string' || finding.ruleId === '') throw new ScannerContractError(`${where} has no ruleId`);
  if (!isSeverity(finding.severity)) throw new ScannerContractError(`${where} has invalid severity`);
  if (typeof finding.confidence !== 'number' || !Number.isFinite(finding.confidence) || finding.confidence < 0 || finding.confidence > 1) {
    throw new ScannerContractError(`${where} confidence must be in [0, 1]`);
  }
  if (typeof finding.file !== 'string' || finding.file === '' || isAbsolutePath(finding.file)) {
    throw new ScannerContractError(`${where} file must be a workspace-relative path`);
  }
  for (const key of ['line', 'column'] as const) {
    const value = finding[key];
    if (value !== undefined && (!Number.isInteger(value) || value < 1)) {
      throw new ScannerContractError(`${where} ${key} must be a positive integer`);
    }
  }
  for (const key of ['title', 'evidence', 'reason'] as const) {
    if (typeof finding[key] !== 'string') throw new ScannerContractError(`${where} ${key} must be a string`);
  }
  if (!Array.isArray(finding.tags) || finding.tags.some((tag) => typeof tag !== 'string')) {
    throw new ScannerContractError(`${where} tags must be an array of strings`);
  }
  if (typeof finding.fingerprint !== 'string' || finding.fingerprint === '') {
    throw new ScannerContractError(`${where} fingerprint must be a non-empty string`);
  }
}

/** Validate a complete result; throws on any contract violation. */
export function validateScannerResult(result: ScannerResult, scannerId: string): void {
  if (typeof result !== 'object' || result === null) throw new ScannerContractError('result is not an object');
  if (result.scannerId !== scannerId) {
    throw new ScannerContractError(`result scannerId ${JSON.stringify(result.scannerId)} does not match ${JSON.stringify(scannerId)}`);
  }
  if (typeof result.scannerVersion !== 'string' || result.scannerVersion === '') {
    throw new ScannerContractError('result scannerVersion must be a non-empty string');
  }
  if (typeof result.workspace !== 'string' || result.workspace === '') {
    throw new ScannerContractError('result workspace must be a non-empty string');
  }
  if (typeof result.startedAt !== 'string' || Number.isNaN(Date.parse(result.startedAt))) {
    throw new ScannerContractError('result startedAt must be an ISO-8601 timestamp');
  }
  if (typeof result.durationMs !== 'number' || !Number.isFinite(result.durationMs) || result.durationMs < 0) {
    throw new ScannerContractError('result durationMs must be a non-negative number');
  }
  if (!Number.isInteger(result.filesScanned) || result.filesScanned < 0) {
    throw new ScannerContractError('result filesScanned must be a non-negative integer');
  }
  if (!Array.isArray(result.findings)) throw new ScannerContractError('result findings must be an array');

  const ids = new Set<string>();
  result.findings.forEach((finding, index) => {
    validateFinding(finding, scannerId, index);
    if (ids.has(finding.id)) throw new ScannerContractError(`duplicate finding id ${JSON.stringify(finding.id)}`);
    ids.add(finding.id);
  });

  if (typeof result.summary !== 'object' || result.summary === null) throw new ScannerContractError('result summary must be an object');
  if (result.summary.total !== result.findings.length) {
    throw new ScannerContractError('result summary.total must equal findings.length');
  }
  const bySeverity: Partial<Record<ScannerSeverity, number>> = {};
  for (const finding of result.findings) {
    bySeverity[finding.severity] = (bySeverity[finding.severity] ?? 0) + 1;
  }
  if (result.summary.bySeverity === undefined) throw new ScannerContractError('result summary.bySeverity is missing');
  for (const [severity, count] of Object.entries(result.summary.bySeverity)) {
    if (!isSeverity(severity)) throw new ScannerContractError(`summary.bySeverity has invalid key ${JSON.stringify(severity)}`);
    if (!Number.isInteger(count) || count < 0) throw new ScannerContractError(`summary.bySeverity[${severity}] must be a non-negative integer`);
    if ((bySeverity[severity as ScannerSeverity] ?? 0) !== count) {
      throw new ScannerContractError(`summary.bySeverity[${severity}] does not match findings`);
    }
  }
  if (!Array.isArray(result.diagnostics)) throw new ScannerContractError('result diagnostics must be an array');
  for (const diagnostic of result.diagnostics) {
    if (typeof diagnostic !== 'object' || diagnostic === null) throw new ScannerContractError('diagnostic is not an object');
    if (diagnostic.level !== 'info' && diagnostic.level !== 'warning' && diagnostic.level !== 'error') {
      throw new ScannerContractError('diagnostic level must be info | warning | error');
    }
    if (typeof diagnostic.message !== 'string' || diagnostic.message === '') {
      throw new ScannerContractError('diagnostic message must be a non-empty string');
    }
  }
}

interface ScannerEntry {
  definition: ScannerDefinition;
  disposer: () => void;
}

/** Validate a scanner definition before registration. */
function validateDefinition(scanner: ScannerDefinition): void {
  if (typeof scanner !== 'object' || scanner === null) throw new ScannerContractError('scanner definition is not an object');
  if (typeof scanner.id !== 'string' || scanner.id === '') throw new ScannerContractError('scanner id must be a non-empty string');
  if (typeof scanner.version !== 'string' || scanner.version === '') {
    throw new ScannerContractError(`scanner ${scanner.id} version must be a non-empty string`);
  }
  if (typeof scanner.description !== 'string') throw new ScannerContractError(`scanner ${scanner.id} description must be a string`);
  if (
    scanner.capabilities !== undefined &&
    (!Array.isArray(scanner.capabilities) ||
      scanner.capabilities.some((capability) => typeof capability !== 'string' || capability === ''))
  ) {
    throw new ScannerContractError(`scanner ${scanner.id} capabilities must be an array of non-empty strings`);
  }
  if (typeof scanner.run !== 'function') throw new ScannerContractError(`scanner ${scanner.id} must declare run(request)`);
}

/** Build the stable public descriptor of a scanner definition. */
function toDescriptor(definition: ScannerDefinition): ScannerDescriptor {
  return {
    id: definition.id,
    version: definition.version,
    description: definition.description,
    ...(definition.capabilities === undefined ? {} : { capabilities: [...definition.capabilities] }),
  };
}

export class MyguiScannersService extends Service<never> {
  private readonly scanners = new Map<string, ScannerEntry>();

  constructor(ctx: Context) {
    super(ctx, 'myguiScanners');
  }

  /**
   * Register a scanner. Fails on duplicate ids. Returns a disposer that
   * unregisters the scanner; scanner plugins must bind it to their Cordis
   * lifecycle via `ctx.effect(...)`.
   */
  register(scanner: ScannerDefinition): () => void {
    validateDefinition(scanner);
    if (this.scanners.has(scanner.id)) {
      throw new ScannerRegistryError(
        'DUPLICATE_SCANNER',
        `scanner ${JSON.stringify(scanner.id)} is already registered`,
      );
    }
    let disposed = false;
    const entry: ScannerEntry = {
      definition: scanner,
      disposer: () => {
        if (disposed) return;
        disposed = true;
        this.scanners.delete(scanner.id);
      },
    };
    this.scanners.set(scanner.id, entry);
    return entry.disposer;
  }

  /** Stable, sorted descriptors (id, version, description, capabilities). */
  list(): ScannerDescriptor[] {
    return [...this.scanners.keys()]
      .sort()
      .map((id) => toDescriptor(this.scanners.get(id)!.definition));
  }

  /** Return the scanner definition; throws `UNKNOWN_SCANNER` when absent. */
  get(id: string): ScannerDefinition {
    const entry = this.scanners.get(id);
    if (entry === undefined) {
      throw new ScannerRegistryError('UNKNOWN_SCANNER', `scanner ${JSON.stringify(id)} is not registered`);
    }
    return entry.definition;
  }

  /** Return stable metadata; throws `UNKNOWN_SCANNER` when absent. */
  describe(id: string): ScannerDescriptor {
    return toDescriptor(this.get(id));
  }

  /**
   * Run a scanner. Unknown ids and scanner exceptions propagate; results are
   * validated against the contract, and a contract violation is a
   * programmer error that fails loudly instead of producing a fake success.
   */
  async run(id: string, request: ScannerRequest): Promise<ScannerResult> {
    const definition = this.get(id);
    if (typeof request !== 'object' || request === null || typeof request.workspace !== 'string' || request.workspace === '') {
      throw new ScannerRegistryError('INVALID_REQUEST', `run(${id}) requires a request with a non-empty workspace`);
    }
    const result = await definition.run(request);
    validateScannerResult(result, id);
    return result;
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    myguiScanners: MyguiScannersService;
  }
}

export type { ScannerDiagnostic };

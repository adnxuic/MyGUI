/** Lifecycle-bound scanner registry with strict ScannerResult v2 validation. */

import { Service, type Context } from '@deepseek-ai/cordis';
import {
  ScannerContractError,
  ScannerRegistryError,
  type ScannerDefinition,
  type ScannerDiagnostic,
  type ScannerRequest,
  type ScannerResult,
} from '../contracts.ts';
import { validateScannerResult } from '../validation.ts';

export interface ScannerDescriptor {
  id: string;
  version: string;
  description: string;
  capabilities?: string[];
}

interface ScannerEntry {
  definition: ScannerDefinition;
  disposer: () => void;
}

function validateDefinition(scanner: ScannerDefinition): void {
  if (typeof scanner !== 'object' || scanner === null) throw new ScannerContractError('scanner definition is not an object');
  if (typeof scanner.id !== 'string' || scanner.id === '') throw new ScannerContractError('scanner id must be non-empty');
  if (typeof scanner.version !== 'string' || scanner.version === '') throw new ScannerContractError(`scanner ${scanner.id} version must be non-empty`);
  if (typeof scanner.description !== 'string') throw new ScannerContractError(`scanner ${scanner.id} description must be a string`);
  if (scanner.capabilities !== undefined && (!Array.isArray(scanner.capabilities) || scanner.capabilities.some((item) => typeof item !== 'string' || item === ''))) {
    throw new ScannerContractError(`scanner ${scanner.id} capabilities must be non-empty strings`);
  }
  if (typeof scanner.run !== 'function') throw new ScannerContractError(`scanner ${scanner.id} must declare run(request)`);
}

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

  register(scanner: ScannerDefinition): () => void {
    validateDefinition(scanner);
    if (this.scanners.has(scanner.id)) {
      throw new ScannerRegistryError('DUPLICATE_SCANNER', `scanner ${JSON.stringify(scanner.id)} is already registered`);
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

  list(): ScannerDescriptor[] {
    return [...this.scanners.keys()].sort().map((id) => toDescriptor(this.scanners.get(id)!.definition));
  }

  get(id: string): ScannerDefinition {
    const entry = this.scanners.get(id);
    if (!entry) throw new ScannerRegistryError('UNKNOWN_SCANNER', `scanner ${JSON.stringify(id)} is not registered`);
    return entry.definition;
  }

  describe(id: string): ScannerDescriptor {
    return toDescriptor(this.get(id));
  }

  async run(id: string, request: ScannerRequest): Promise<ScannerResult> {
    const definition = this.get(id);
    if (typeof request !== 'object' || request === null || typeof request.workspace !== 'string' || request.workspace === '') {
      throw new ScannerRegistryError('INVALID_REQUEST', `run(${id}) requires a non-empty workspace`);
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

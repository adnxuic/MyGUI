/**
 * Registry service tests: register/list/get/describe/run, duplicate and
 * unknown ids, lifecycle binding (unload ⇒ unregister), deterministic
 * ordering, and result-contract enforcement.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Context } from '@deepseek-ai/cordis';
import {
  SCANNER_CONTRACT_VERSION,
  ScannerContractError,
  ScannerRegistryError,
  type ScannerDefinition,
  type ScannerResult,
} from '../src/contracts.ts';
import { MyguiScannersService } from '../src/registry/service.ts';
import myguiScannerRegistryPlugin from '../src/registry/plugin.ts';
import myguiScannerArchitecturePlugin from '../src/scanners/architecture/plugin.ts';

function makeScanner(id: string, overrides: Partial<ScannerDefinition> = {}): ScannerDefinition {
  return {
    id,
    version: '1.0.0',
    description: `scanner ${id}`,
    async run(request) {
      const startedAt = new Date().toISOString();
      const findings: never[] = [];
      return {
        contractVersion: SCANNER_CONTRACT_VERSION,
        scanner: { id, version: '1.0.0' },
        status: 'completed',
        verdict: 'clean',
        scope: { workspace: request.workspace, include: [], exclude: [], changedFiles: [] },
        startedAt,
        durationMs: 1,
        findings,
        grayBoundaries: [],
        coverage: { filesVisited: ['sample.py'], filesSkipped: [], limitations: [] },
        errors: [],
        summary: { findings: 0, grayBoundaries: 0, errors: 0, bySeverity: {} },
        diagnostics: [],
      };
    },
    ...overrides,
  };
}

function plainContext(): Context {
  return new Context();
}

test('register, list, get, describe, run', async () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  const scanner = makeScanner('mygui.alpha');
  ctx.myguiScanners.register(scanner);

  assert.deepEqual(ctx.myguiScanners.list(), [
    { id: 'mygui.alpha', version: '1.0.0', description: 'scanner mygui.alpha' },
  ]);
  assert.equal(ctx.myguiScanners.get('mygui.alpha'), scanner);
  assert.deepEqual(ctx.myguiScanners.describe('mygui.alpha'), {
    id: 'mygui.alpha',
    version: '1.0.0',
    description: 'scanner mygui.alpha',
  });

  const result = await ctx.myguiScanners.run('mygui.alpha', { workspace: '/ws' });
  assert.equal(result.scanner.id, 'mygui.alpha');
  assert.equal(result.scope.workspace, '/ws');
  assert.equal(result.summary.findings, 0);
});

test('list() is sorted by id deterministically', () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  for (const id of ['mygui.zeta', 'mygui.alpha', 'mygui.mid']) {
    ctx.myguiScanners.register(makeScanner(id));
  }
  const ids = ctx.myguiScanners.list().map((entry) => entry.id);
  assert.deepEqual(ids, ['mygui.alpha', 'mygui.mid', 'mygui.zeta']);
  // Repeating the call yields the same order.
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ids,
  );
});

test('capabilities metadata rides through list() and describe()', () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  const capabilities = ['ui_artist_mutation', 'ui_matplotlib_global_state_mutation', 'matplotlib_rcparams_mutation'];
  ctx.myguiScanners.register(makeScanner('mygui.cap', { capabilities }));

  assert.deepEqual(ctx.myguiScanners.list(), [
    { id: 'mygui.cap', version: '1.0.0', description: 'scanner mygui.cap', capabilities },
  ]);
  assert.deepEqual(ctx.myguiScanners.describe('mygui.cap'), {
    id: 'mygui.cap',
    version: '1.0.0',
    description: 'scanner mygui.cap',
    capabilities,
  });

  // Invalid capabilities are rejected at registration.
  assert.throws(
    () => ctx.myguiScanners.register(makeScanner('mygui.badcap', { capabilities: ['ok', ''] })),
    ScannerContractError,
  );
});

test('duplicate registration is rejected', () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  ctx.myguiScanners.register(makeScanner('mygui.dup'));
  assert.throws(
    () => ctx.myguiScanners.register(makeScanner('mygui.dup')),
    (error: unknown) =>
      error instanceof ScannerRegistryError &&
      error.code === 'DUPLICATE_SCANNER' &&
      error.message.includes('mygui.dup'),
  );
});

test('unknown id fails with a clear error', async () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  assert.throws(
    () => ctx.myguiScanners.get('mygui.missing'),
    (error: unknown) =>
      error instanceof ScannerRegistryError &&
      error.code === 'UNKNOWN_SCANNER' &&
      error.message.includes('mygui.missing'),
  );
  assert.throws(() => ctx.myguiScanners.describe('mygui.missing'), ScannerRegistryError);
  await assert.rejects(
    ctx.myguiScanners.run('mygui.missing', { workspace: '/ws' }),
    ScannerRegistryError,
  );
});

test('register() disposer removes the scanner; idempotent', () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  const disposer = ctx.myguiScanners.register(makeScanner('mygui.tmp'));
  assert.equal(ctx.myguiScanners.list().length, 1);
  disposer();
  assert.equal(ctx.myguiScanners.list().length, 0);
  disposer(); // no-op
  assert.equal(ctx.myguiScanners.list().length, 0);
});

test('run() propagates scanner exceptions (never swallowed)', async () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  ctx.myguiScanners.register(
    makeScanner('mygui.boom', {
      async run() {
        throw new Error('boom');
      },
    }),
  );
  await assert.rejects(ctx.myguiScanners.run('mygui.boom', { workspace: '/ws' }), /boom/);
});

test('run() rejects contract violations instead of faking success', async () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);

  ctx.myguiScanners.register(
    makeScanner('mygui.bad', {
      async run(request) {
        const result = await makeScanner('mygui.bad').run(request);
        return { ...result, summary: { ...result.summary, findings: 42 } };
      },
    }),
  );
  await assert.rejects(
    ctx.myguiScanners.run('mygui.bad', { workspace: '/ws' }),
    (error: unknown) => error instanceof ScannerContractError,
  );

  ctx.myguiScanners.register(
    makeScanner('mygui.badfile', {
      async run(request) {
        const result = await makeScanner('mygui.badfile').run(request);
        return {
          ...result,
          findings: [
            {
              id: 'x',
              scannerId: 'mygui.badfile',
              ruleId: 'R',
              severity: 'high',
              confidence: 1,
              file: '/abs/path.py', // absolute — contract violation
              title: 't',
              evidence: 'e',
              reason: 'r',
              suggestedAction: 'a',
              tags: [],
              fingerprint: 'f',
            },
          ],
          summary: { ...result.summary, findings: 1, bySeverity: { high: 1 } },
        };
      },
    }),
  );
  await assert.rejects(
    ctx.myguiScanners.run('mygui.badfile', { workspace: '/ws' }),
    (error: unknown) => error instanceof ScannerContractError && error.message.includes('workspace-relative'),
  );

  ctx.myguiScanners.register(
    makeScanner('mygui.badconf', {
      async run(request) {
        const result = await makeScanner('mygui.badconf').run(request);
        return {
          ...result,
          findings: [
            {
              id: 'y',
              scannerId: 'mygui.badconf',
              ruleId: 'R',
              severity: 'high',
              confidence: 1.5, // out of [0, 1]
              file: 'a.py',
              title: 't',
              evidence: 'e',
              reason: 'r',
              suggestedAction: 'a',
              tags: [],
              fingerprint: 'f',
            },
          ],
          summary: { ...result.summary, findings: 1, bySeverity: { high: 1 } },
        };
      },
    }),
  );
  await assert.rejects(
    ctx.myguiScanners.run('mygui.badconf', { workspace: '/ws' }),
    (error: unknown) => error instanceof ScannerContractError && error.message.includes('confidence'),
  );

  ctx.myguiScanners.register(
    makeScanner('mygui.v1', {
      async run(request) {
        const result = await makeScanner('mygui.v1').run(request);
        return { ...result, contractVersion: 1 } as unknown as ScannerResult;
      },
    }),
  );
  await assert.rejects(
    ctx.myguiScanners.run('mygui.v1', { workspace: '/ws' }),
    (error: unknown) => error instanceof ScannerContractError && error.message.includes('exactly 2'),
  );

  ctx.myguiScanners.register(
    makeScanner('mygui.extra', {
      async run(request) {
        const result = await makeScanner('mygui.extra').run(request);
        return { ...result, legacyField: true } as ScannerResult;
      },
    }),
  );
  await assert.rejects(
    ctx.myguiScanners.run('mygui.extra', { workspace: '/ws' }),
    (error: unknown) => error instanceof ScannerContractError && error.message.includes('unknown fields'),
  );
});

test('gray and partial ScannerResult v2 states remain explicit', async () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  ctx.myguiScanners.register(makeScanner('mygui.gray', {
    async run(request) {
      const result = await makeScanner('mygui.gray').run(request);
      return {
        ...result,
        verdict: 'gray_boundary',
        grayBoundaries: [{
          id: 'gray-1', scannerId: 'mygui.gray', category: 'receiver-type', confidence: 0.5,
          file: 'sample.py', line: 2, evidence: 'target.set_color(...)',
          whyNotViolation: 'The receiver type cannot be resolved statically.',
          evolutionCandidate: 'Classify the receiver before evolving the rule.', fingerprint: 'gray-1',
        }],
        summary: { ...result.summary, grayBoundaries: 1 },
      };
    },
  }));
  const gray = await ctx.myguiScanners.run('mygui.gray', { workspace: '/ws' });
  assert.equal(gray.verdict, 'gray_boundary');

  ctx.myguiScanners.register(makeScanner('mygui.partial', {
    async run(request) {
      const result = await makeScanner('mygui.partial').run(request);
      return {
        ...result,
        status: 'partial',
        verdict: 'unknown',
        coverage: { ...result.coverage, filesSkipped: [{ file: 'unreadable.py', reason: 'permission denied' }] },
        errors: [{ code: 'READ_ERROR', message: 'permission denied', recoverable: true, file: 'unreadable.py' }],
        summary: { ...result.summary, errors: 1 },
      };
    },
  }));
  const partial = await ctx.myguiScanners.run('mygui.partial', { workspace: '/ws' });
  assert.equal(partial.status, 'partial');
  assert.equal(partial.verdict, 'unknown');
});

test('invalid scanner definitions are rejected at registration', () => {
  const ctx = plainContext();
  new MyguiScannersService(ctx);
  assert.throws(() => ctx.myguiScanners.register({} as ScannerDefinition), ScannerContractError);
  assert.throws(
    () => ctx.myguiScanners.register({ id: 'x', version: '', description: '', run: async () => ({}) as ScannerResult }),
    ScannerContractError,
  );
});

test('plugin lifecycle: load ⇒ registered, unload ⇒ auto-removed', async () => {
  const ctx = plainContext();
  const registryFiber = await ctx.plugin(myguiScannerRegistryPlugin, {});
  assert.ok(ctx.myguiScanners, 'myguiScanners service is available');

  const architectureFiber = await ctx.plugin(myguiScannerArchitecturePlugin, {});
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ['mygui.architecture'],
  );

  // Unload the architecture plugin: the scanner must disappear.
  await architectureFiber.dispose();
  assert.deepEqual(ctx.myguiScanners.list(), []);
  assert.throws(() => ctx.myguiScanners.get('mygui.architecture'), ScannerRegistryError);

  // Unload the registry plugin: the service must disappear.
  await registryFiber.dispose();
  assert.equal(ctx.get('myguiScanners'), undefined);
});

test('registry plugin can be loaded and unloaded without scanners', async () => {
  const ctx = plainContext();
  const fiber = await ctx.plugin(myguiScannerRegistryPlugin, {});
  assert.deepEqual(ctx.myguiScanners.list(), []);
  await fiber.dispose();
  assert.equal(ctx.get('myguiScanners'), undefined);
});

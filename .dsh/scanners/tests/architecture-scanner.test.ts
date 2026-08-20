/**
 * Scanner integration tests: end-to-end `ScannerResult` shape, deterministic
 * ordering, default test-file exclusion, explicit test inclusion, and
 * cancellation.
 */

import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { test } from 'node:test';
import { createArchitectureScanner } from '../src/scanners/architecture/scanner.ts';

const FIXTURES = resolve(import.meta.dirname, 'fixtures');

test('full scan of the positive workspace returns a valid, deterministic result', async () => {
  const scanner = createArchitectureScanner();
  const workspace = resolve(FIXTURES, 'ws_basic');

  const first = await scanner.run({ workspace });
  const second = await scanner.run({ workspace });

  assert.equal(first.scannerId, 'mygui.architecture');
  assert.equal(first.scannerVersion, '0.2.0');
  assert.equal(first.workspace, workspace);
  assert.ok(Number.isInteger(first.filesScanned) && first.filesScanned > 0);
  assert.ok(Number.isFinite(first.durationMs) && first.durationMs >= 0);
  assert.ok(!Number.isNaN(Date.parse(first.startedAt)));

  const { summary } = first;
  assert.equal(summary.total, first.findings.length);
  const counted = Object.values(summary.bySeverity).reduce((sum, count) => sum + (count ?? 0), 0);
  assert.equal(counted, summary.total);

  // Deterministic: identical findings (same order, same ids/fingerprints).
  assert.deepEqual(
    first.findings.map((f) => [f.id, f.fingerprint]),
    second.findings.map((f) => [f.id, f.fingerprint]),
  );

  // Every finding obeys the contract.
  for (const finding of first.findings) {
    assert.equal(finding.scannerId, 'mygui.architecture');
    assert.ok(!finding.file.startsWith('/') && !finding.file.startsWith('..'));
    assert.ok(finding.confidence >= 0 && finding.confidence <= 1);
    assert.ok(finding.evidence.length > 0 && finding.evidence.length <= 200);
    assert.ok(finding.reason.length > 0);
    assert.equal(typeof finding.fingerprint, 'string');
  }
});

test('test files are excluded by default and included on explicit request', async () => {
  const scanner = createArchitectureScanner();
  const workspace = resolve(FIXTURES, 'ws_with_tests');

  const production = await scanner.run({ workspace });
  const productionFiles = production.findings.filter((f) => f.file.startsWith('tests/'));
  assert.equal(productionFiles.length, 0, 'test files must not pollute the production scan');

  const withTests = await scanner.run({ workspace, include: ['tests/**'] });
  const testFindings = withTests.findings.filter((f) => f.file.startsWith('tests/'));
  assert.ok(testFindings.length > 0, 'explicit include must bring test files in');
  for (const finding of testFindings) {
    assert.ok(finding.tags.includes('test-code'), 'test findings carry the test-code tag');
  }
});

test('changedFiles restricts the scan', async () => {
  const scanner = createArchitectureScanner();
  const workspace = resolve(FIXTURES, 'ws_basic');
  const result = await scanner.run({
    workspace,
    changedFiles: ['mygui/widgets/ui/panel.py'],
  });
  assert.ok(result.filesScanned >= 1);
  assert.ok(
    result.findings.every((finding) => finding.file === 'mygui/widgets/ui/panel.py'),
    'findings must come only from changed files',
  );
});

test('abort signal cancels the scan', async () => {
  const scanner = createArchitectureScanner();
  const workspace = resolve(FIXTURES, 'ws_basic');
  const controller = new AbortController();
  controller.abort();
  const result = await scanner.run({ workspace, signal: controller.signal });
  assert.equal(result.filesScanned, 0);
  assert.deepEqual(result.findings, []);
});

test('missing workspace directory yields diagnostics, not a crash', async () => {
  const scanner = createArchitectureScanner();
  const result = await scanner.run({ workspace: resolve(FIXTURES, 'does-not-exist') });
  assert.equal(result.filesScanned, 0);
  assert.equal(result.summary.total, 0);
});

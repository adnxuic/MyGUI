/**
 * Qt-lifecycle scanner integration tests: rule hits on positive fixtures,
 * no false positives on legitimate Qt patterns, line numbers, workspace-
 * relative paths, stable fingerprints, deterministic ordering, and
 * changedFiles restriction.
 */

import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { test } from 'node:test';
import { createQtLifecycleScanner } from '../src/scanners/qt-lifecycle/scanner.ts';

const FIXTURES = resolve(import.meta.dirname, 'fixtures');

test('full scan of ws_qt hits exactly the three positive fixtures with correct lines', async () => {
  const scanner = createQtLifecycleScanner();
  const workspace = resolve(FIXTURES, 'ws_qt');

  const result = await scanner.run({ workspace });

  assert.equal(result.scannerId, 'mygui.qt-lifecycle');
  assert.equal(result.scannerVersion, '0.1.0');
  assert.equal(result.workspace, workspace);
  assert.ok(result.filesScanned >= 7);

  const byRule = new Map(result.findings.map((finding) => [finding.ruleId, finding]));

  // R1: parentless timer without stop path, at the construction line.
  const timer = byRule.get('QT-TIMER-OWNERSHIP');
  assert.ok(timer, 'timer_leak.py must be reported');
  assert.equal(timer.file, 'mygui/widgets/ui/timer_leak.py');
  assert.equal(timer.line, 8, 'line must be the `self._timer = QTimer()` line');
  assert.equal(timer.severity, 'medium');
  assert.ok(timer.confidence >= 0 && timer.confidence <= 1);
  assert.ok(timer.evidence.length > 0 && timer.evidence.length <= 200);
  assert.ok(timer.reason.includes('QTimer'));
  assert.ok(timer.tags.includes('qt'));
  assert.equal(typeof timer.fingerprint, 'string');

  // R2: started thread without shutdown path.
  const thread = byRule.get('QT-THREAD-LIFECYCLE');
  assert.ok(thread, 'thread_leak.py must be reported');
  assert.equal(thread.file, 'mygui/widgets/ui/thread_leak.py');
  assert.equal(thread.line, 8);

  // R3: repeatable lambda connect without class-level disconnect.
  const rebind = byRule.get('QT-SIGNAL-REBIND');
  assert.ok(rebind, 'signal_rebind.py must be reported');
  assert.equal(rebind.file, 'mygui/widgets/ui/signal_rebind.py');
  assert.equal(rebind.line, 8);

  assert.equal(result.findings.length, 3, 'exactly one finding per rule');
  for (const finding of result.findings) {
    assert.equal(finding.scannerId, 'mygui.qt-lifecycle');
    assert.ok(!finding.file.startsWith('/') && !finding.file.startsWith('..'));
    assert.ok(!Number.isNaN(Date.parse(result.startedAt)));
  }
});

test('legitimate Qt patterns never report (parent, stop path, disconnect contract, init-time lambda)', async () => {
  const scanner = createQtLifecycleScanner();
  const workspace = resolve(FIXTURES, 'ws_qt');

  const result = await scanner.run({ workspace, changedFiles: [
    'mygui/widgets/ui/timer_parented.py',
    'mygui/widgets/ui/timer_stopped.py',
    'mygui/widgets/ui/thread_ok.py',
    'mygui/widgets/ui/signal_ok.py',
  ] });

  assert.deepEqual(result.findings, [], 'no false positives on legitimate Qt lifecycle patterns');
  assert.equal(result.filesScanned, 4);
});

test('deterministic result and stable fingerprints across runs', async () => {
  const scanner = createQtLifecycleScanner();
  const workspace = resolve(FIXTURES, 'ws_qt');

  const first = await scanner.run({ workspace });
  const second = await scanner.run({ workspace });

  assert.deepEqual(
    first.findings.map((f) => [f.id, f.fingerprint, f.line, f.file]),
    second.findings.map((f) => [f.id, f.fingerprint, f.line, f.file]),
    'findings must be identical across runs',
  );
  assert.deepEqual(first.summary, second.summary);
});

test('changedFiles restricts the scan to exactly the listed files', async () => {
  const scanner = createQtLifecycleScanner();
  const workspace = resolve(FIXTURES, 'ws_qt');

  const result = await scanner.run({
    workspace,
    changedFiles: ['mygui/widgets/ui/timer_leak.py'],
  });
  assert.equal(result.filesScanned, 1);
  assert.ok(
    result.findings.every((finding) => finding.file === 'mygui/widgets/ui/timer_leak.py'),
    'findings must come only from changed files',
  );
});

test('abort signal cancels the scan', async () => {
  const scanner = createQtLifecycleScanner();
  const controller = new AbortController();
  controller.abort();
  const result = await scanner.run({
    workspace: resolve(FIXTURES, 'ws_qt'),
    signal: controller.signal,
  });
  assert.equal(result.filesScanned, 0);
  assert.equal(result.findings.length, 0);
});

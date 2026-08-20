/**
 * Scanner selection tests: metadata-based selection, requested-id
 * validation, missing-capability behavior, deterministic ordering.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  scoreScanner,
  selectScanners,
  type ScannerMetadata,
} from '../src/select.ts';

const REGISTRY: ScannerMetadata[] = [
  {
    id: 'mygui.architecture',
    version: '0.1.0',
    description:
      'Static architecture-rule checks for the MyGUI repository: container-private access, UI artist mutation, second component state, controller bypass.',
  },
  {
    id: 'mygui.qt-lifecycle',
    version: '0.1.0',
    description: 'Qt object lifecycle checks: parent/child ownership and signal cleanup.',
  },
];

test('selects the architecture scanner for an architecture task', () => {
  const { selected } = selectScanners(
    REGISTRY,
    'Check MyGUI for violations of the documented Figure component architecture boundaries.',
  );
  assert.deepEqual(selected, ['mygui.architecture']);
});

test('selection is deterministic and stable for the same task', () => {
  const task = 'Verify the Qt lifecycle of inspector widgets.';
  const first = selectScanners(REGISTRY, task);
  const second = selectScanners(REGISTRY, task);
  assert.deepEqual(first, second);
  assert.deepEqual(first.selected, ['mygui.qt-lifecycle']);
});

test('no match returns an empty selection (missing capability, not ad-hoc scan)', () => {
  const { selected } = selectScanners(REGISTRY, 'Analyze the pandas data frame serialization format.');
  assert.deepEqual(selected, []);
});

test('requestedScanners are validated against the registry', () => {
  const { selected, unknownRequested } = selectScanners(REGISTRY, 'anything', [
    'mygui.architecture',
    'mygui.does-not-exist',
  ]);
  assert.deepEqual(selected, ['mygui.architecture']);
  assert.deepEqual(unknownRequested, ['mygui.does-not-exist']);
});

test('duplicate requested ids are deduplicated', () => {
  const { selected } = selectScanners(REGISTRY, 'anything', ['mygui.architecture', 'mygui.architecture']);
  assert.deepEqual(selected, ['mygui.architecture']);
});

test('requestedScanners win over metadata scoring', () => {
  const { selected } = selectScanners(REGISTRY, 'Qt lifecycle', ['mygui.architecture']);
  assert.deepEqual(selected, ['mygui.architecture']);
});

test('empty registry with requested id reports it unknown', () => {
  const { selected, unknownRequested } = selectScanners([], 'anything', ['mygui.architecture']);
  assert.deepEqual(selected, []);
  assert.deepEqual(unknownRequested, ['mygui.architecture']);
});

test('scoreScanner ignores stop words', () => {
  const task = 'Please check the repository for detection only';
  assert.equal(scoreScanner(REGISTRY[0]!, task), 0);
});

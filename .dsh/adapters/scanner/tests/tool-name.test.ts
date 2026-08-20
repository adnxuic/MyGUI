/**
 * Tool-name mapping tests: deterministic, stable, collision-free, legal.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  findToolNameCollisions,
  isLegalToolName,
  toolNameFor,
} from '../src/tool-name.ts';

test('mygui.architecture maps to mygui_architecture_scan', () => {
  assert.equal(toolNameFor('mygui.architecture'), 'mygui_architecture_scan');
});

test('mygui.qt-lifecycle maps to mygui_qt_lifecycle_scan', () => {
  assert.equal(toolNameFor('mygui.qt-lifecycle'), 'mygui_qt_lifecycle_scan');
});

test('mapping is deterministic and stable across calls', () => {
  const first = toolNameFor('mygui.architecture');
  for (let i = 0; i < 10; i += 1) {
    assert.equal(toolNameFor('mygui.architecture'), first);
  }
});

test('case is normalized to lowercase', () => {
  assert.equal(toolNameFor('MyGUI.Architecture'), 'mygui_architecture_scan');
  assert.equal(toolNameFor('MYGUI.QT-LIFECYCLE'), 'mygui_qt_lifecycle_scan');
});

test('other separators map to underscores', () => {
  assert.equal(toolNameFor('mygui:architecture'), 'mygui_architecture_scan');
  assert.equal(toolNameFor('mygui architecture'), 'mygui_architecture_scan');
});

test('empty id is rejected', () => {
  assert.throws(() => toolNameFor(''), /non-empty/);
  assert.throws(() => toolNameFor('   '), /cannot be mapped/);
});

test('unmappable id (symbols only) is rejected', () => {
  assert.throws(() => toolNameFor('!!!'), /cannot be mapped/);
});

test('every mapped name is a legal tool name', () => {
  for (const id of ['mygui.architecture', 'mygui.qt-lifecycle', 'mygui.a1']) {
    assert.ok(isLegalToolName(toolNameFor(id)), `${id} -> ${toolNameFor(id)}`);
  }
  assert.ok(!isLegalToolName('1leading-digit'));
  assert.ok(!isLegalToolName('has space'));
  assert.ok(!isLegalToolName(''));
});

test('collision detection flags ids that map to the same tool name', () => {
  const collisions = findToolNameCollisions([
    'mygui.qt-lifecycle',
    'mygui.qt_lifecycle',
    'mygui.architecture',
  ]);
  assert.deepEqual(collisions, {
    mygui_qt_lifecycle_scan: ['mygui.qt-lifecycle', 'mygui.qt_lifecycle'],
  });
});

test('no collisions for distinct ids', () => {
  const collisions = findToolNameCollisions(['mygui.architecture', 'mygui.qt-lifecycle']);
  assert.deepEqual(collisions, {});
});

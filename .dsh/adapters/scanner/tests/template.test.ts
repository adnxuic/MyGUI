/**
 * Adapter template tests: the generated host code is a thin bridge, stays in
 * sync with the on-disk template, injects values safely, and never contains
 * scanner rules.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import {
  buildAdapterHostCode,
  buildToolDescription,
} from '../src/template.ts';

const TEMPLATE_PATH = fileURLToPath(new URL('../templates/adapter.host.js', import.meta.url));

function config(overrides: Record<string, string> = {}) {
  return {
    scannerId: 'mygui.architecture',
    toolName: 'mygui_architecture_scan',
    toolDescription: 'Runs the registered MyGUI scanner.',
    workspace: '/ws/mygui',
    ...overrides,
  };
}

test('generated code contains the injected tool name, id, description and workspace', () => {
  const code = buildAdapterHostCode(config());
  assert.ok(code.includes('name: "mygui_architecture_scan"'), 'tool name injected');
  assert.ok(code.includes('"mygui.architecture"'), 'scanner id injected');
  assert.ok(code.includes('Runs the registered MyGUI scanner.'), 'description injected');
  assert.ok(code.includes('"/ws/mygui"'), 'workspace injected');
});

test('generated code is exactly the on-disk template with markers substituted', () => {
  const disk = readFileSync(TEMPLATE_PATH, 'utf8');
  const generated = buildAdapterHostCode(config());
  // Substitute the four markers in the disk template with the JSON-escaped
  // values and compare with the generated code.
  const expected = disk
    .split('__TOOL_NAME__').join(JSON.stringify('mygui_architecture_scan'))
    .split('__TOOL_DESCRIPTION__').join(JSON.stringify('Runs the registered MyGUI scanner.'))
    .split('__WORKSPACE__').join(JSON.stringify('/ws/mygui'))
    .split('__SCANNER_ID__').join(JSON.stringify('mygui.architecture'));
  assert.equal(generated, expected, 'generated code must match the on-disk template');
});

test('template contains no scanner rules and no ad-hoc analysis', () => {
  const code = buildAdapterHostCode(config());
  for (const forbidden of [
    'controller-bypass',
    'private-container-access',
    'ui-artist-mutation',
    'second-component-state',
    'ARCH-',
    'regexp',
    'execFile',
  ]) {
    assert.ok(!code.includes(forbidden), `template must not contain ${forbidden}`);
  }
});

test('template registers exactly one tool and calls only myguiScanners.run', () => {
  const code = buildAdapterHostCode(config());
  assert.equal((code.match(/harness\.registerTool/g) ?? []).length, 1);
  assert.equal((code.match(/harness\.defineTool/g) ?? []).length, 1);
  assert.ok(code.includes('scanners.run('), 'execute must call registry run');
  assert.ok(!code.includes('scanners.register('), 'adapter must not register scanners');
});

test('adapter adds no shell/write/network capability', () => {
  const code = buildAdapterHostCode(config());
  for (const forbidden of ['shell', 'subprocess', 'fetch(', 'writeText', 'http', 'socket']) {
    assert.ok(!code.includes(forbidden), `template must not include ${forbidden}`);
  }
});

test('injected values are JSON-escaped so caller input cannot escape the template', () => {
  const nasty = 'say "hi" \\ and ${exec}';
  const code = buildAdapterHostCode(config({ toolDescription: nasty }));
  assert.ok(code.includes(JSON.stringify(nasty)));
  // The literal raw string must not appear unescaped.
  assert.ok(!code.includes('say "hi" \\ and'), 'raw text must be escaped');
});

test('invalid config is rejected', () => {
  assert.throws(() => buildAdapterHostCode(config({ scannerId: '' })), /non-empty/);
  assert.throws(() => buildAdapterHostCode(config({ toolName: '' })), /non-empty/);
  assert.throws(() => buildAdapterHostCode(config({ toolDescription: '' })), /non-empty/);
  assert.throws(() => buildAdapterHostCode(config({ workspace: '' })), /non-empty/);
});

test('tool description includes scanner id, version, description and read-only declaration', () => {
  const description = buildToolDescription({
    scannerId: 'mygui.architecture',
    scannerVersion: '0.1.0',
    scannerDescription: 'Static architecture checks.',
  });
  assert.ok(description.includes('mygui.architecture'));
  assert.ok(description.includes('0.1.0'));
  assert.ok(description.includes('Static architecture checks.'));
  assert.ok(description.includes('detection only'));
  assert.ok(description.includes('does not modify repository files'));
});

/**
 * Non-model-facing + registry-discovery invariants for the Qt-lifecycle
 * scanner plugin:
 *
 *   1. loading registry + architecture + qt-lifecycle yields the sorted
 *      registry [mygui.architecture, mygui.qt-lifecycle];
 *   2. unloading the qt-lifecycle plugin unregisters the scanner;
 *   3. remounting registers it again;
 *   4. no plugin ever registers a model-facing tool named
 *      `mygui_qt_lifecycle_scan` (or any scanner tool);
 *   5. production scanner sources never reference the model-facing tool
 *      registry.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Context, Service, type Context as CordisContext } from '@deepseek-ai/cordis';
import myguiScannerQtLifecyclePlugin from '../src/scanners/qt-lifecycle/plugin.ts';
import myguiScannerArchitecturePlugin from '../src/scanners/architecture/plugin.ts';
import myguiScannerRegistryPlugin from '../src/registry/plugin.ts';

/** A minimal tools service that fails loudly on any registration. */
class ToolsTrapService extends Service<never> {
  readonly registered: string[] = [];

  constructor(ctx: CordisContext) {
    super(ctx, 'tools');
  }

  register(definition: { name: string }): () => void {
    this.registered.push(definition.name);
    throw new Error(`TOOLS-TRAP: model-facing tool registration attempted: ${definition.name}`);
  }

  view(): { visible: Map<string, unknown> } {
    return { visible: new Map() };
  }
}

test('registry discovers architecture + qt-lifecycle; unload unregisters; remount restores', async () => {
  const ctx = new Context();

  await ctx.plugin(myguiScannerRegistryPlugin, {});
  await ctx.plugin(myguiScannerArchitecturePlugin, {});
  const qtHandle = await ctx.plugin(myguiScannerQtLifecyclePlugin, {});

  // Both scanners are visible, sorted deterministically.
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => `${entry.id}@${entry.version}`),
    ['mygui.architecture@0.2.0', 'mygui.qt-lifecycle@0.1.0'],
  );

  // The qt scanner runs and produces the expected contract.
  const qtScannerModule = await import('../src/scanners/qt-lifecycle/scanner.ts');
  const result = await ctx.myguiScanners.run('mygui.qt-lifecycle', { workspace: process.cwd() });
  assert.equal(result.scannerId, 'mygui.qt-lifecycle');
  assert.equal(qtScannerModule.DEFAULT_EXCLUDE.length, 3);

  // Unloading the qt-lifecycle plugin unregisters its scanner.
  await qtHandle.dispose();
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ['mygui.architecture'],
    'unloading the qt-lifecycle plugin must unregister the scanner',
  );

  // Remounting restores it without touching the worker.
  await ctx.plugin(myguiScannerQtLifecyclePlugin, {});
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ['mygui.architecture', 'mygui.qt-lifecycle'],
    'remounting must register the scanner again',
  );
});

test('loading the qt-lifecycle plugin registers no model-facing tools', async () => {
  const ctx = new Context();
  const trap = new ToolsTrapService(ctx);

  await ctx.plugin(myguiScannerRegistryPlugin, {});
  await ctx.plugin(myguiScannerQtLifecyclePlugin, {});

  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ['mygui.qt-lifecycle'],
  );

  assert.deepEqual(trap.registered, [], 'plugins must never call ctx.tools.register');
  const visible = [...trap.view().visible.keys()];
  for (const banned of ['mygui_qt_lifecycle_scan', 'mygui_architecture_scan', 'scanner_run', 'scanner_list']) {
    assert.ok(!visible.includes(banned), `${banned} must not exist`);
  }
  assert.ok(visible.every((name) => !name.startsWith('mygui') && !name.startsWith('scanner')));
});

test('qt-lifecycle scanner sources never reference the model-facing tool registry', async () => {
  const { readFileSync, readdirSync, statSync } = await import('node:fs');
  const { join, resolve } = await import('node:path');
  const srcRoot = resolve(import.meta.dirname, '../src/scanners/qt-lifecycle');
  const offenders: string[] = [];
  const stack = [srcRoot];
  while (stack.length > 0) {
    const current = stack.pop()!;
    let isDir = false;
    try {
      isDir = statSync(current).isDirectory();
    } catch {
      continue;
    }
    if (isDir) {
      for (const entry of readdirSync(current)) stack.push(join(current, entry));
      continue;
    }
    if (!current.endsWith('.ts')) continue;
    const source = readFileSync(current, 'utf8');
    if (/dsh-tools|ctx\.tools|defineTool|tools\.register/.test(source)) {
      offenders.push(current.slice(srcRoot.length + 1));
    }
  }
  assert.deepEqual(offenders, [], 'no qt-lifecycle scanner source may reference the model-facing tool registry');
});

/**
 * Non-model-facing invariant tests.
 *
 * Loading `mygui-scanner-registry` + `mygui-scanner-architecture` must never
 * register anything on `ctx.tools` and must never create tools named
 * `mygui_architecture_scan`, `scanner_run`, `scanner_list`, or any other
 * scanner tool. Two checks:
 *
 *   1. a trap `tools` service whose `register()` throws — plugin load
 *      succeeding proves no tool registration is attempted;
 *   2. the trap's visible tool surface stays empty of scanner tools.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Context, Service, type Context as CordisContext } from '@deepseek-ai/cordis';
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

test('loading both scanner plugins registers no model-facing tools', async () => {
  const ctx = new Context();
  const trap = new ToolsTrapService(ctx);

  await ctx.plugin(myguiScannerRegistryPlugin, {});
  await ctx.plugin(myguiScannerArchitecturePlugin, {});

  // The scanner is registered and runnable.
  assert.deepEqual(
    ctx.myguiScanners.list().map((entry) => entry.id),
    ['mygui.architecture'],
  );
  const result = await ctx.myguiScanners.run('mygui.architecture', { workspace: process.cwd() });
  assert.equal(result.scanner.id, 'mygui.architecture');

  // No tool registration was ever attempted, and the tool surface has no
  // scanner tools.
  assert.deepEqual(trap.registered, [], 'plugins must never call ctx.tools.register');
  const visible = [...trap.view().visible.keys()];
  for (const banned of ['mygui_architecture_scan', 'scanner_run', 'scanner_list']) {
    assert.ok(!visible.includes(banned), `${banned} must not exist`);
  }
  assert.ok(visible.every((name) => !name.startsWith('mygui') && !name.startsWith('scanner')));
});

test('the scanner plugins never import dsh-tools', async () => {
  // Static check: the production scanner plugin sources (registry +
  // scanners) must not reference the model-facing tool registry at all.
  // The e2e-exit verification plugin is excluded: it is not a scanner
  // plugin, only reads ctx.tools to assert the invariant.
  const { readFileSync, readdirSync, statSync } = await import('node:fs');
  const { join, resolve } = await import('node:path');
  const srcRoot = resolve(import.meta.dirname, '../src');
  const offenders: string[] = [];
  const stack = [join(srcRoot, 'registry'), join(srcRoot, 'scanners')];
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
  assert.deepEqual(offenders, [], 'no production scanner source may reference the model-facing tool registry');
});

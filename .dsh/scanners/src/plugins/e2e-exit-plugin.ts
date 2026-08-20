/**
 * E2E verification plugin (loaded only by `dsh/verify-e2e.sh` via the
 * `e2e-exit.patch.yml` overlay — never part of a production composition).
 *
 * Runs inside a real `dsh` boot and verifies the persistent scanner
 * composition end to end:
 *
 *   1. `mygui.architecture` is registered with `myguiScanners`;
 *   2. no model-facing scanner tool exists on `ctx.tools`;
 *   3. `run()` produces a valid `ScannerResult` for the workspace;
 *   4. unloading the architecture entry removes the scanner;
 *   5. unloading the registry entry removes the service.
 *
 * Then exits the process (0 = success, 1 = failure).
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';

export const name = 'mygui-scanners-e2e-exit';

/** Minimal view of the tools service and the loader used by this check. */
interface ToolsService {
  view(scope?: unknown): { visible: Map<string, unknown> };
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    loader: {
      entries(): Iterable<{ options: { id: string }; update(options: { disabled?: boolean }): Promise<void> }>;
    };
  }
}

/** Find a loader entry by id anywhere in the loader tree (incl. subtrees). */
function findEntry(ctx: Context, id: string): { options: { id: string }; update(options: { disabled?: boolean }): Promise<void> } {
  for (const entry of ctx.loader.entries()) {
    if (entry.options.id === id) return entry;
  }
  fail(`loader entry ${JSON.stringify(id)} not found`);
}

const BANNED_TOOL_NAMES = ['mygui_architecture_scan', 'scanner_run', 'scanner_list'];

function fail(message: string): never {
  process.stderr.write(`E2E-FAIL: ${message}\n`);
  process.exit(1);
}

function assertNoScannerTools(ctx: Context): void {
  const tools = (ctx as unknown as { get(name: string): unknown }).get('tools') as ToolsService | undefined;
  if (tools === undefined) fail('ctx.tools is not available in the booted composition');
  const visible = tools.view(undefined).visible;
  const names = [...visible.keys()];
  for (const banned of BANNED_TOOL_NAMES) {
    if (names.includes(banned)) fail(`model-facing tool ${JSON.stringify(banned)} is registered`);
  }
  for (const name of names) {
    if (name.startsWith('mygui') || name.startsWith('scanner')) {
      fail(`unexpected model-facing scanner tool ${JSON.stringify(name)} is registered`);
    }
  }
  process.stdout.write(`E2E-OK: no model-facing scanner tools (${names.length} tools visible, 0 scanner tools)\n`);
}

async function waitForScanner(ctx: Context, timeoutMs = 15000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const ids = ctx.myguiScanners.list().map((scanner) => scanner.id);
    if (ids.includes('mygui.architecture')) return;
    if (Date.now() > deadline) {
      fail(`mygui.architecture never registered (list: ${ids.join(', ') || '(empty)'})`);
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

const e2eExitPlugin: Plugin.Function<object> = async (ctx: Context) => {
  const workspace = process.env.MYGUI_SCANNERS_WORKSPACE;
  if (workspace === undefined || workspace === '') fail('MYGUI_SCANNERS_WORKSPACE is not set');

  await waitForScanner(ctx);
  const listed = ctx.myguiScanners.list().map((scanner) => `${scanner.id}@${scanner.version}`);
  process.stdout.write(`E2E-OK: myguiScanners.list() = [${listed.join(', ')}]\n`);

  const described = ctx.myguiScanners.describe('mygui.architecture');
  process.stdout.write(`E2E-OK: describe(mygui.architecture) = ${described.id} v${described.version}\n`);

  assertNoScannerTools(ctx);

  // Real scan of the workspace through the registry.
  const result = await ctx.myguiScanners.run('mygui.architecture', { workspace });
  process.stdout.write(`E2E-OK: run(mygui.architecture) files=${result.coverage.filesVisited.length} findings=${result.summary.findings} `);
  process.stdout.write(`${JSON.stringify(result.summary.bySeverity)}\n`);
  process.stdout.write(`E2E-SCAN-JSON ${JSON.stringify({
    contractVersion: result.contractVersion,
    scannerId: result.scanner.id,
    scannerVersion: result.scanner.version,
    revision: result.scope.revision ?? null,
    filesScanned: result.coverage.filesVisited.length,
    findings: result.summary.findings,
    grayBoundaries: result.summary.grayBoundaries,
    status: result.status,
    verdict: result.verdict,
    bySeverity: result.summary.bySeverity,
    durationMs: result.durationMs,
  })}\n`);

  // Unload the architecture scanner plugin; the scanner must disappear.
  const architectureEntry = findEntry(ctx, 'mygui-scanner-architecture');
  await architectureEntry.update({ disabled: true });
  const afterUnload = ctx.myguiScanners.list().map((scanner) => scanner.id);
  if (afterUnload.includes('mygui.architecture')) {
    fail('mygui.architecture still registered after plugin unload');
  }
  process.stdout.write(`E2E-OK: after architecture plugin unload, list() = [${afterUnload.join(', ')}]\n`);

  // Unload the registry plugin; the service must disappear. This starts the
  // teardown of this plugin's own fiber (it injects myguiScanners), so the
  // update is fired without awaiting. The final assertion runs on a detached
  // timer, and this fiber is held open so boot()'s entry audit never
  // observes the transient pending state; the timer owns process exit.
  const registryEntry = findEntry(ctx, 'mygui-scanner-registry');
  registryEntry.update({ disabled: true }).catch((error: unknown) => {
    process.stderr.write(`E2E-FAIL: registry entry update failed: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
  setTimeout(() => {
    const service = ctx.get('myguiScanners');
    if (service !== undefined) {
      process.stderr.write('E2E-FAIL: myguiScanners service still provided after registry plugin unload\n');
      process.exit(1);
    }
    process.stdout.write('E2E-OK: myguiScanners service removed after registry plugin unload\n');
    process.stdout.write('E2E-ALL-PASS\n');
    process.exit(0);
  }, 1500);
  await new Promise<void>(() => {});
};

e2eExitPlugin.inject = ['myguiScanners'];

export default e2eExitPlugin;

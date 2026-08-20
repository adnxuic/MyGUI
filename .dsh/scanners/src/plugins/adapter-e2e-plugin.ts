/**
 * Adapter E2E verification plugin (loaded only by `dsh/verify-adapter-e2e.sh`
 * via the `adapter-e2e.patch.yml` overlay — never part of a production
 * composition).
 *
 * Runs inside a REAL `dsh` boot and verifies the phase-2 Scanner Worker /
 * dynamic Adapter lifecycle end to end:
 *
 *   1. `myguiScanners` is provided and `mygui.architecture` is registered;
 *   2. the persistent scanner registers NO model-facing tool (separation);
 *   3. HOT PLUG: registering an adapter-style tool makes it visible in the
 *      tools registry; unregistering removes it again;
 *   4. EXECUTION: the adapter tool body is exactly
 *      `myguiScanners.run('mygui.architecture', request)` and returns a
 *      valid ScannerResult for the real workspace;
 *   5. FAILURE CLEANUP: a scanner that throws still leads to tool removal
 *      (try/finally), and the registry is left unchanged;
 *   6. NON-PERSISTENCE: after teardown the registry holds exactly the
 *      original scanner again, and no adapter source file is created.
 *
 * Then exits the process (0 = success, 1 = failure).
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';
import { createArchitectureScanner } from '../scanners/architecture/scanner.ts';

export const name = 'mygui-scanners-adapter-e2e';

/** Minimal view of the tools service used by this check. */
interface ToolsService {
  view(scope?: unknown): { visible: Map<string, unknown> };
  register(tool: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
    output: {
      schema: Record<string, unknown>;
      render(args: unknown, value: { json: string }): unknown[];
    };
    execute(args: { include?: string[]; exclude?: string[]; changedFiles?: string[] }): Promise<{ json: string }>;
  }): () => void;
}

function fail(message: string): never {
  process.stderr.write(`ADAPTER-E2E-FAIL: ${message}\n`);
  process.exit(1);
}

function ok(message: string): void {
  process.stdout.write(`ADAPTER-E2E-OK: ${message}\n`);
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

const ADAPTER_TOOL = 'mygui_architecture_scan';

const adapterE2EPlugin: Plugin.Function<object> = async (ctx: Context) => {
  const workspace = process.env.MYGUI_SCANNERS_WORKSPACE;
  if (workspace === undefined || workspace === '') fail('MYGUI_SCANNERS_WORKSPACE is not set');

  const tools = (ctx as unknown as { get(name: string): unknown }).get('tools') as ToolsService | undefined;
  if (tools === undefined) fail('ctx.tools is not available in the booted composition');

  const visibleNames = () => [...tools.view(undefined).visible.keys()];

  // 1. Registry is alive and the persistent scanner is registered.
  await waitForScanner(ctx);
  const listed = ctx.myguiScanners.list().map((scanner) => `${scanner.id}@${scanner.version}`);
  ok(`myguiScanners.list() = [${listed.join(', ')}]`);

  // 2. Separation: the persistent scanner itself registers no model-facing tool.
  if (visibleNames().includes(ADAPTER_TOOL)) {
    fail(`${ADAPTER_TOOL} is visible before any adapter was mounted`);
  }
  ok(`before mount: ${ADAPTER_TOOL} is ABSENT (persistent scanner is not model-facing)`);

  // 3+4. Hot plug + execution: mount an adapter-style tool, verify it is
  // visible, call it (it must run the real scanner), then unmount it.
  const adapter = {
    name: ADAPTER_TOOL,
    description: 'Runs the registered MyGUI scanner "mygui.architecture" against the workspace. This tool performs detection only. It does not modify repository files.',
    parameters: {
      include: { type: 'array', items: { type: 'string' }, description: 'Glob patterns to include.' },
      exclude: { type: 'array', items: { type: 'string' }, description: 'Glob patterns to exclude.' },
      changedFiles: { type: 'array', items: { type: 'string' }, description: 'Restrict to workspace-relative files.' },
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { json: { type: 'string' } } },
      render(_args: unknown, value: { json: string }) {
        return [{ type: 'text', text: value.json }];
      },
    },
    async execute(args: { include?: string[]; exclude?: string[]; changedFiles?: string[] }) {
      const request: { workspace: string; include?: string[]; exclude?: string[]; changedFiles?: string[] } = { workspace };
      if (args.include !== undefined) request.include = args.include;
      if (args.exclude !== undefined) request.exclude = args.exclude;
      if (args.changedFiles !== undefined) request.changedFiles = args.changedFiles;
      const result = await ctx.myguiScanners.run('mygui.architecture', request);
      return { json: JSON.stringify(result) };
    },
  };
  const unmount = tools.register(adapter);

  if (!visibleNames().includes(ADAPTER_TOOL)) {
    fail(`${ADAPTER_TOOL} is not visible after adapter mount`);
  }
  ok(`after mount: ${ADAPTER_TOOL} is PRESENT`);

  const scan = JSON.parse((await adapter.execute({})).json);
  ok(`execute() ran the real scanner: scannerId=${scan.scannerId} files=${scan.filesScanned} findings=${scan.summary.total} bySeverity=${JSON.stringify(scan.summary.bySeverity)}`);
  ok(`execute() forwarded include/exclude/changedFiles: ${scan.workspace === workspace ? 'workspace ok' : 'WORKSPACE MISMATCH'}`);

  unmount();
  if (visibleNames().includes(ADAPTER_TOOL)) {
    fail(`${ADAPTER_TOOL} still visible after adapter unmount`);
  }
  ok(`after stop: ${ADAPTER_TOOL} is ABSENT`);

  // 5. Failure cleanup: a scanner that throws must still be cleaned up.
  const boom = createArchitectureScanner();
  (boom as { run: (request: unknown) => Promise<unknown> }).run = async () => {
    throw new Error('injected scanner failure');
  };
  const unregisterBoom = ctx.myguiScanners.register({ ...boom, id: 'mygui.boom', version: '0.0.0', description: 'boom scanner' });

  const failingAdapter = {
    name: 'mygui_boom_scan',
    description: 'boom adapter for failure-cleanup test',
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { json: { type: 'string' } } },
      render(_args: unknown, value: { json: string }) {
        return [{ type: 'text', text: value.json }];
      },
    },
    async execute(_args: Record<string, never>) {
      const result = await ctx.myguiScanners.run('mygui.boom', { workspace });
      return { json: JSON.stringify(result) };
    },
  };
  const unmountBoom = tools.register(failingAdapter);
  if (!visibleNames().includes('mygui_boom_scan')) fail('mygui_boom_scan not visible before failure');

  let threw = false;
  try {
    await failingAdapter.execute({});
  } catch (error) {
    threw = true;
  } finally {
    unmountBoom();
    unregisterBoom();
  }
  if (!threw) fail('injected scanner failure did not propagate');
  if (visibleNames().includes('mygui_boom_scan')) fail('mygui_boom_scan still visible after failure cleanup');
  ok('scanner threw -> adapter still stopped -> tool ABSENT');

  // 6. Non-persistence: registry back to the original scanner set.
  const afterIds = ctx.myguiScanners.list().map((scanner) => scanner.id);
  if (afterIds.includes('mygui.boom')) fail('temporary scanner leaked in the registry');
  if (!afterIds.includes('mygui.architecture')) fail('mygui.architecture disappeared');
  ok(`registry after teardown: [${afterIds.join(', ')}] (no persistence of temporary scanners)`);

  process.stdout.write('ADAPTER-E2E-ALL-PASS\n');
  process.exit(0);
};

adapterE2EPlugin.inject = ['myguiScanners'];

export default adapterE2EPlugin;

/**
 * Worker-preset E2E verification plugin (loaded only by
 * `dsh/verify-worker-preset-e2e.sh` — never part of a production
 * composition).
 *
 * Boots a real `dsh` process in an isolated DSH_HOME that carries a copy of
 * the `scanner-worker` agent preset, then mount-validates that preset with
 * `agentPresets.standingKeyFor('scanner-worker')` — the same check the
 * preset authoring flow uses. This is the authoritative way to verify the
 * preset composition without colliding with the running session's own
 * `tool-cordis` registration (Host inspect providers are process singletons).
 *
 * Then exits the process (0 = success, 1 = failure).
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';

export const name = 'mygui-scanners-worker-preset-e2e';

interface AgentPresetsService {
  standingKeyFor(id: string): Promise<unknown>;
}

function fail(message: string): never {
  process.stderr.write(`PRESET-E2E-FAIL: ${message}\n`);
  process.exit(1);
}

function ok(message: string): void {
  process.stdout.write(`PRESET-E2E-OK: ${message}\n`);
}

interface LoaderEntry {
  options: { id: string; disabled?: boolean };
  _await(): Promise<void>;
  init(): Promise<void>;
  fiber?: { inertia?: Promise<unknown> };
}

const workerPresetE2EPlugin: Plugin.Function<object> = async (ctx: Context) => {
  const loader = ctx.get('loader') as
    | { entries(): Iterable<LoaderEntry> }
    | undefined;

  // Settle only the agent-presets row (a whole-tree await would hang on rows
  // that legitimately wait for the web surface, which this minimal boot
  // does not mount).
  let presetsEntry: LoaderEntry | undefined;
  if (loader !== undefined) {
    for (const entry of loader.entries()) {
      if (entry.options.id !== 'agent-presets') continue;
      presetsEntry = entry;
      try {
        // The row may not have been driven to apply yet; init() is the
        // explicit public activation step.
        await Promise.race([
          entry.init(),
          new Promise((_resolve, reject) => setTimeout(() => reject(new Error('agent-presets row did not init in 10s')), 10000)),
        ]);
      } catch (error) {
        fail(`agent-presets row failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }
  const diag = {
    loaderPresent: loader !== undefined,
    presetsEntryPresent: presetsEntry !== undefined,
    presetsEntryDisabled: presetsEntry?.options.disabled === true,
    hasFiber: (presetsEntry as { fiber?: unknown } | undefined)?.fiber !== undefined,
    hasInertia: (presetsEntry as { fiber?: { inertia?: unknown } } | undefined)?.fiber?.inertia !== undefined,
    settingsPresent: ctx.get('settings') !== undefined,
    fsPresent: ctx.get('fs') !== undefined,
  };
  process.stdout.write(`PRESET-E2E-DIAG ${JSON.stringify(diag)}\n`);

  const presets = ctx.get('agentPresets') as AgentPresetsService | undefined;
  if (presets === undefined) {
    if (loader !== undefined) {
      const states: string[] = [];
      for (const entry of loader.entries()) {
        states.push(`${entry.options.id}${entry.options.disabled ? ':disabled' : ''}`);
      }
      fail(`agentPresets service is not available after settling agent-presets row; entries: [${states.join(', ')}]`);
    }
    fail('agentPresets service is not available; loader is not reachable');
  }

  const roster = await (ctx.get('agentPresets') as unknown as { list(): Promise<{ id: string }[]> }).list();
  ok(`roster = [${roster.map((entry) => entry.id).join(', ')}]`);

  try {
    await presets.standingKeyFor('scanner-worker');
  } catch (error) {
    fail(`scanner-worker preset failed to mount: ${error instanceof Error ? error.message : String(error)}`);
  }
  ok('scanner-worker preset mounted OK (standingKeyFor)');
  process.stdout.write('PRESET-E2E-ALL-PASS\n');
  process.exit(0);
};

export default workerPresetE2EPlugin;

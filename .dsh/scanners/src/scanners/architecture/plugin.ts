/**
 * `mygui-scanner-architecture` — Cordis plugin entry point.
 *
 * Registers the `mygui.architecture` scanner with the `myguiScanners`
 * registry. The plugin declares `inject: ['myguiScanners']`, so it loads
 * only when the registry service is available. Registration is bound to this
 * plugin's fiber through `ctx.effect(...)`: unloading the plugin
 * automatically unregisters the scanner.
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';
import { createArchitectureScanner } from './scanner.ts';

export const name = 'mygui-scanner-architecture';

export interface ArchitectureScannerConfig {
  /** Reserved for future tuning; unused in v0.1.0. */
  [key: string]: unknown;
}

const architecturePlugin: Plugin.Function<ArchitectureScannerConfig> = (ctx: Context) => {
  const scanner = createArchitectureScanner();
  ctx.effect(() => ctx.myguiScanners.register(scanner));
  ctx.logger('mygui.scanners').info('registered scanner %s v%s', scanner.id, scanner.version);
};

// Load only once the registry service is provided; unload automatically when
// the registry plugin unloads (the fiber is re-evaluated on service change).
architecturePlugin.inject = ['myguiScanners'];

export default architecturePlugin;

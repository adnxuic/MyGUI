/**
 * `mygui-scanner-qt-lifecycle` — Cordis plugin entry point.
 *
 * Registers the `mygui.qt-lifecycle` scanner with the `myguiScanners`
 * registry. The plugin declares `inject: ['myguiScanners']`, so it loads
 * only when the registry service is available. Registration is bound to this
 * plugin's fiber through `ctx.effect(...)`: unloading the plugin
 * automatically unregisters the scanner.
 *
 * This plugin is NEVER model-facing: it registers no tools, only the scanner
 * definition behind the registry service. The Scanner Worker reaches it
 * exclusively through `myguiScanners.run(...)` via a temporary dynamic
 * Adapter.
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';
import { createQtLifecycleScanner } from './scanner.ts';

export const name = 'mygui-scanner-qt-lifecycle';

export interface QtLifecycleScannerConfig {
  /** Reserved for future tuning; unused in v0.1.0. */
  [key: string]: unknown;
}

const qtLifecyclePlugin: Plugin.Function<QtLifecycleScannerConfig> = (ctx: Context) => {
  const scanner = createQtLifecycleScanner();
  ctx.effect(() => ctx.myguiScanners.register(scanner));
  ctx.logger('mygui.scanners').info('registered scanner %s v%s', scanner.id, scanner.version);
};

// Load only once the registry service is provided; unload automatically when
// the registry plugin unloads (the fiber is re-evaluated on service change).
qtLifecyclePlugin.inject = ['myguiScanners'];

export default qtLifecyclePlugin;

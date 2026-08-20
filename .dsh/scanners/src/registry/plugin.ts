/**
 * `mygui-scanner-registry` — Cordis plugin entry point.
 *
 * Provides the `myguiScanners` service. The service is a Cordis `Service`,
 * so it is registered with this plugin's fiber and automatically removed
 * when the plugin unloads.
 */

import type { Context, Plugin } from '@deepseek-ai/cordis';
import { MyguiScannersService } from './service.ts';

export const name = 'mygui-scanner-registry';

/** Metadata for tooling: this plugin provides the `myguiScanners` service. */
export const provide = ['myguiScanners'] as const;

const registryPlugin: Plugin.Function<object> = (ctx: Context) => {
  // The Service constructor registers `myguiScanners` on the current fiber;
  // it disappears automatically when this plugin unloads.
  new MyguiScannersService(ctx);
  ctx.logger('mygui.scanners').info('scanner registry service ready');
};

export default registryPlugin;

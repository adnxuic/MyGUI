// EVAL-ONLY fixture (Case 10): registers `mygui.eval-boom` into the LIVE
// `myguiScanners` registry for the lifetime of this Cordis plugin. Its
// run() always throws a deterministic error.
//
// Isolation: lifecycle-bound via ctx.effect -> unloading (or undefining)
// the plugin unregisters the scanner; the scanner then disappears from the
// registry completely. This file is NOT production code: it never enters
// the production registry config, the web profile, or
// .dsh/scanners/src/scanners/.
//
// Usage: paste this file's content into `code.host` of cordis_define.

return {
  name: 'mygui-eval-boom-fixture',
  apply(ctx) {
    const scanners = ctx.get('myguiScanners')
    if (scanners === undefined) {
      throw new Error('myguiScanners service is not available')
    }
    const disposer = scanners.register({
      id: 'mygui.eval-boom',
      version: '0.0.1-eval',
      description: 'EVAL-ONLY fixture scanner that always throws a deterministic error.',
      async run() {
        throw new Error('EVAL-BOOM deterministic failure (mygui.eval-boom)')
      },
    })
    ctx.effect(() => disposer)
  },
}

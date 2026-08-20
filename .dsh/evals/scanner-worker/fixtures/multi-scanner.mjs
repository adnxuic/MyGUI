// EVAL-ONLY fixture (Case 22, OPTIONAL): registers `mygui.eval-a` and
// `mygui.eval-b` (deterministic tiny success scanners) plus `mygui.eval-c`
// (deterministic throw) into the LIVE registry for the lifetime of this
// Cordis plugin. Lifecycle-bound: unloading the plugin unregisters all.
// NOT production code.
//
// Usage: paste this file's content into `code.host` of cordis_define.

return {
  name: 'mygui-eval-multi-fixture',
  apply(ctx) {
    const scanners = ctx.get('myguiScanners')
    if (scanners === undefined) {
      throw new Error('myguiScanners service is not available')
    }
    const disposers = [
      scanners.register({
        id: 'mygui.eval-a',
        version: '0.0.1-eval',
        description: 'EVAL-ONLY scanner A: emits one deterministic info finding.',
        async run(request) {
          return {
            scannerId: 'mygui.eval-a',
            scannerVersion: '0.0.1-eval',
            workspace: request.workspace,
            startedAt: new Date().toISOString(),
            durationMs: 1,
            filesScanned: 0,
            findings: [{
              id: 'eval-a@fixture#1',
              scannerId: 'mygui.eval-a',
              ruleId: 'eval-a',
              severity: 'info',
              confidence: 1,
              file: '.dsh/evals/scanner-worker/fixtures/multi-scanner.mjs',
              line: 1,
              title: 'eval-a deterministic finding',
              evidence: 'eval-a',
              reason: 'eval fixture',
              tags: ['eval'],
              fingerprint: 'eval-a::fixture::1',
            }],
            summary: { total: 1, bySeverity: { info: 1 } },
            diagnostics: [],
          }
        },
      }),
      scanners.register({
        id: 'mygui.eval-b',
        version: '0.0.1-eval',
        description: 'EVAL-ONLY scanner B: emits one deterministic info finding.',
        async run(request) {
          return {
            scannerId: 'mygui.eval-b',
            scannerVersion: '0.0.1-eval',
            workspace: request.workspace,
            startedAt: new Date().toISOString(),
            durationMs: 1,
            filesScanned: 0,
            findings: [{
              id: 'eval-b@fixture#1',
              scannerId: 'mygui.eval-b',
              ruleId: 'eval-b',
              severity: 'info',
              confidence: 1,
              file: '.dsh/evals/scanner-worker/fixtures/multi-scanner.mjs',
              line: 1,
              title: 'eval-b deterministic finding',
              evidence: 'eval-b',
              reason: 'eval fixture',
              tags: ['eval'],
              fingerprint: 'eval-b::fixture::1',
            }],
            summary: { total: 1, bySeverity: { info: 1 } },
            diagnostics: [],
          }
        },
      }),
      scanners.register({
        id: 'mygui.eval-c',
        version: '0.0.1-eval',
        description: 'EVAL-ONLY scanner C: always throws a deterministic error.',
        async run() {
          throw new Error('EVAL-C deterministic failure (mygui.eval-c)')
        },
      }),
    ]
    ctx.effect(() => disposers.forEach((disposer) => disposer()))
  },
}

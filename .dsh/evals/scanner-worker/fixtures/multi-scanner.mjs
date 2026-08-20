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
            contractVersion: 2,
            scanner: { id: 'mygui.eval-a', version: '0.0.1-eval' },
            status: 'completed',
            verdict: 'violation',
            scope: {
              workspace: request.workspace,
              include: request.include ?? [],
              exclude: request.exclude ?? [],
              changedFiles: request.changedFiles ?? [],
            },
            startedAt: new Date().toISOString(),
            durationMs: 1,
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
              suggestedAction: 'Use the result only to verify multi-scanner orchestration.',
              tags: ['eval'],
              fingerprint: 'eval-a::fixture::1',
            }],
            grayBoundaries: [],
            coverage: { filesVisited: [], filesSkipped: [], limitations: [] },
            errors: [],
            diagnostics: [],
            summary: { findings: 1, grayBoundaries: 0, errors: 0, bySeverity: { info: 1 } },
          }
        },
      }),
      scanners.register({
        id: 'mygui.eval-b',
        version: '0.0.1-eval',
        description: 'EVAL-ONLY scanner B: emits one deterministic info finding.',
        async run(request) {
          return {
            contractVersion: 2,
            scanner: { id: 'mygui.eval-b', version: '0.0.1-eval' },
            status: 'completed',
            verdict: 'violation',
            scope: {
              workspace: request.workspace,
              include: request.include ?? [],
              exclude: request.exclude ?? [],
              changedFiles: request.changedFiles ?? [],
            },
            startedAt: new Date().toISOString(),
            durationMs: 1,
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
              suggestedAction: 'Use the result only to verify multi-scanner orchestration.',
              tags: ['eval'],
              fingerprint: 'eval-b::fixture::1',
            }],
            grayBoundaries: [],
            coverage: { filesVisited: [], filesSkipped: [], limitations: [] },
            errors: [],
            diagnostics: [],
            summary: { findings: 1, grayBoundaries: 0, errors: 0, bySeverity: { info: 1 } },
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

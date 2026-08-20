// EVAL-ONLY probe (Case 1 + registry discovery): mounts one temporary tool
// `mygui_eval_probe_list` that returns `myguiScanners.list()` as JSON.
// This is NOT a scanner tool and adds no capability beyond reading the
// registry. Stop (and keep defined) the plugin after use.
//
// Usage: paste this file's content into `code.host` of cordis_define.

return {
  name: 'mygui-eval-registry-probe',
  apply(ctx) {
    const scanners = ctx.get('myguiScanners')
    if (scanners === undefined) {
      throw new Error('myguiScanners service is not available')
    }
    const disposer = harness.registerTool(ctx, harness.defineTool({
      name: 'mygui_eval_probe_list',
      description: 'EVAL-ONLY probe: returns the myguiScanners registry descriptor list (id/version/description) as JSON. Not a scanner tool.',
      parameters: {},
      output: {
        schema: { type: 'object', additionalProperties: false, properties: { json: { type: 'string' } } },
        render(_args, value) { return [{ type: 'text', text: value.json }] },
      },
      async execute() {
        return { json: JSON.stringify(scanners.list()) }
      },
    }))
    ctx.effect(() => disposer)
  },
}

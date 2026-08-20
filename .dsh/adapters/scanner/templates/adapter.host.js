// MYGUI DYNAMIC SCANNER ADAPTER — FIXED TEMPLATE (do not modify)
//
// This is the ONLY source of the dynamic host code a Scanner Worker mounts
// via cordis_define. The Worker replaces the four __PLACEHOLDER__ markers
// with JSON string literals (JSON.stringify escaping):
//
//   __TOOL_NAME__        e.g. "mygui_architecture_scan"
//   __TOOL_DESCRIPTION__      the model-facing description
//   __WORKSPACE__             absolute workspace root
//   __SCANNER_ID__            registry scanner id, e.g. "mygui.architecture"
//
// The template is a pure bridge: it registers ONE model-facing tool whose
// execute() is exactly myguiScanners.run(scannerId, request). It contains no
// scanner rules and adds no extra capability (no process execution, no
// filesystem writes, no network). Test suite: tests/template.test.ts asserts
// this file stays in sync with src/template.ts.

return {
  name: 'mygui-scanner-adapter',
  apply(ctx) {
    const scanners = ctx.get('myguiScanners')
    if (scanners === undefined) {
      throw new Error('myguiScanners service is not available; the persistent scanner composition is not mounted')
    }
    const disposer = harness.registerTool(ctx, harness.defineTool({
      name: __TOOL_NAME__,
      description: __TOOL_DESCRIPTION__,
      parameters: {
        include: {
          type: 'array',
          items: { type: 'string' },
          description: 'Glob patterns to include (defaults to the scanner defaults).',
        },
        exclude: {
          type: 'array',
          items: { type: 'string' },
          description: 'Glob patterns to exclude (scanner defaults still apply).',
        },
        changedFiles: {
          type: 'array',
          items: { type: 'string' },
          description: 'Restrict scanning to these workspace-relative files.',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: { json: { type: 'string' } },
        },
        render(_args, value) {
          return [{ type: 'text', text: value.json }]
        },
      },
      async execute(args) {
        const request = { workspace: __WORKSPACE__ }
        if (args.include !== undefined) request.include = args.include
        if (args.exclude !== undefined) request.exclude = args.exclude
        if (args.changedFiles !== undefined) request.changedFiles = args.changedFiles
        const result = await scanners.run(__SCANNER_ID__, request)
        return { json: JSON.stringify(result) }
      },
    }))
    ctx.effect(() => disposer)
  },
}

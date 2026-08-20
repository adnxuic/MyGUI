/**
 * scanner-cordis.mjs — MyGUI Scanner Worker 的本地 Cordis 动态工具（薄插件）。
 *
 * 为什么存在：`@deepseek-ai/dsh-tool-cordis` 在 apply 时把 Host inspect
 * providers（Service / Event / Builtin / Tool）注册进 `cordisInspect`，
 * 而这些 provider 是**进程单例**（重复 id 直接抛错）。同一进程里只要已有
 * 任意 cordis 类 preset（例如「创造模式」会话），第二个 tool-cordis 实例的
 * 挂载就必然失败：
 *
 *   Host Cordis inspect provider "Service" is already registered
 *
 * 本插件只提供 Scanner Worker 编排所需的最小工具集（cordis_define /
 * cordis_run / cordis_stop / cordis_undefine / cordis_inspect_self），
 * **不注册任何 Host inspect provider**，因此不与任何其他会话冲突。所有
 * 工具直接调用 host 单例服务 `dynamicCordisRunner`（通过 inject 获取），
 * 语义与官方 tool-cordis 一致。
 *
 * 零外部 import：本文件不引用任何 `@deepseek-ai/*` 包（本地插件按文件位置
 * 解析裸 specifier，无法到达部署的 node_modules），工具定义以标准 JSON
 * Schema 形式直接交给 `ctx.tools.register`。
 *
 * 安全边界：本插件只暴露动态 Cordis 生命周期操作，不增加任何 shell /
 * 文件 / 网络能力；Worker 仍通过固定模板生成 Adapter 代码。
 */

export const name = 'scanner-worker-cordis';

export const inject = ['tools', 'systemPrompt', 'dynamicCordisRunner'];

function requireAgent(exec) {
  if (exec.agent === undefined) throw new Error('Cordis dynamic tools require an Agent-backed session');
  return exec.agent;
}

/** JSON output declaration shared by every tool (standard JSON Schema). */
function jsonOutput() {
  return {
    schema: { type: 'object', additionalProperties: true },
    render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
  };
}

/** Standard JSON-Schema object root with required names. */
function objectSchema(properties, required) {
  return {
    type: 'object',
    additionalProperties: false,
    properties,
    ...required.length === 0 ? {} : { required },
  };
}

/** Register the Scanner Worker's minimal Cordis toolset. */
export function apply(ctx) {
  ctx.systemPrompt.section({
    name: 'tool:cordis:scanner-worker',
    order: 115,
    text: [
      'You have a minimal Cordis dynamic-package toolset (cordis_define / cordis_run /',
      'cordis_stop / cordis_undefine / cordis_inspect_self). It mounts and unmounts',
      'temporary Scanner Adapters only. Host inspect providers are NOT registered by',
      'this preset, so cordis_inspect_list/cordis_inspect_query are unavailable here;',
      'discover the myguiScanners registry by calling its service directly from',
      'adapter/probe code.',
    ].join(' '),
  });

  ctx.tools.register({
    name: 'cordis_inspect_self',
    description: 'Inspect dynamic Cordis objects owned by the current Session at increasing levels of detail. With no IDs, list only Plugin summaries. With pluginId alone, return version pointers, the latest Run, and every Package summary. Only pluginId plus packageId returns that immutable Package\'s Host/Client source and runtime diagnostics. packageId cannot be supplied alone. This Tool is read-only: it neither executes code nor changes version pointers.',
    parameters: objectSchema({
      pluginId: { type: 'string', description: 'Stable Plugin ID returned by cordis_define; omit it to list every current Plugin.' },
      packageId: { type: 'string', description: 'Exact immutable Package ID owned by pluginId; when specified, source is returned.' },
    }, []),
    output: jsonOutput(),
    execute(args, exec) {
      const agent = requireAgent(exec);
      if (args.packageId !== undefined && args.pluginId === undefined) {
        throw new Error('cordis_inspect_self packageId requires pluginId');
      }
      if (args.pluginId === undefined) {
        return Promise.resolve({
          mode: 'plugins',
          plugins: ctx.dynamicCordisRunner.listPlugins(agent).map((plugin) => ({
            pluginId: String(plugin.pluginId),
            name: plugin.name,
            packageCount: plugin.packages.length,
            ...plugin.currentPackageId === undefined ? {} : { currentPackageId: String(plugin.currentPackageId) },
            ...plugin.nextPackageId === undefined ? {} : { nextPackageId: String(plugin.nextPackageId) },
          })),
        });
      }
      if (args.packageId === undefined) {
        const plugin = ctx.dynamicCordisRunner.inspectPlugin(agent, args.pluginId);
        return Promise.resolve({ mode: 'plugin', ...simplifyPlugin(plugin) });
      }
      return Promise.resolve({
        mode: 'package',
        ...simplifyPackage(ctx.dynamicCordisRunner.inspectPackage(agent, args.pluginId, args.packageId)),
      });
    },
  });

  ctx.tools.register({
    name: 'cordis_define',
    description: 'Define an immutable Cordis Package. For a new Plugin, use kind:"new" and provide only a semantic prefix of 3–6 lowercase English letters; the Host returns the final pluginId and packageId. To modify an existing Plugin, use kind:"existing" with its exact pluginId to append a Package without overwriting older versions. Provide at least one of code.host and code.client. Each value is a plain JavaScript function body that returns a Cordis Plugin; no TypeScript, JSX, or import transformation occurs. Define only validates parameters and syntax and records source: it does not request approval, execute apply, or change currentPackageId. On success, call cordis_run with the returned IDs.',
    parameters: objectSchema({
      plugin: {
        oneOf: [
          objectSchema({
            kind: { type: 'string', const: 'new' },
            idPrefix: { type: 'string', description: 'Suggested semantic prefix of 3–6 lowercase English letters; the Host adds a unique numeric suffix.' },
          }, ['kind', 'idPrefix']),
          objectSchema({
            kind: { type: 'string', const: 'existing' },
            pluginId: { type: 'string', description: 'Exact ID of an existing Plugin; the new Package is appended to that instance.' },
          }, ['kind', 'pluginId']),
        ],
      },
      name: { type: 'string', description: 'Short, readable Package name.' },
      purpose: { type: 'string', description: 'One-sentence, user-facing description of the Package purpose.' },
      code: objectSchema({
        host: { type: 'string', description: 'Plain JavaScript function body that returns the Host-half Cordis Plugin.' },
        client: { type: 'string', description: 'Plain JavaScript function body that returns the browser Client-half Cordis Plugin.' },
      }, []),
    }, ['plugin', 'name', 'purpose', 'code']),
    output: jsonOutput(),
    execute(args, exec) {
      const plugin = args.plugin.kind === 'new'
        ? { kind: 'new', idPrefix: args.plugin.idPrefix }
        : { kind: 'existing', pluginId: args.plugin.pluginId };
      const receipt = ctx.dynamicCordisRunner.define({
        sessionId: requireAgent(exec).id,
        plugin,
        name: args.name,
        purpose: args.purpose,
        code: {
          ...args.code.host === undefined ? {} : { host: args.code.host },
          ...args.code.client === undefined ? {} : { client: args.code.client },
        },
      });
      return Promise.resolve({
        pluginId: String(receipt.pluginId),
        packageId: String(receipt.packageId),
        name: receipt.name,
        purpose: receipt.purpose,
        hasHostHalf: receipt.hasHostHalf,
        hasClientHalf: receipt.hasClientHalf,
      });
    },
  });

  ctx.tools.register({
    name: 'cordis_run',
    description: 'Activate one exact Package of a dynamic Plugin. Use mode:"run" for the first activation, restarting currentPackageId, or rollback. When current exists, use mode:"update" to switch to a different Package, even if the Plugin is currently stopped. An unauthorized Client Package creates an approval request and returns awaiting-approval; an authorized Package returns starting and continues asynchronously in the browser. Neither result waits for the final outcome inside the Tool. currentPackageId changes only after complete success; on failure, the old current and target next remain. Asynchronous success, rejection, or technical failure is reported through state and steering. After a technical failure, read diagnostics with cordis_inspect_self, correct the same Plugin, and retry autonomously. Do not request approval again after the user rejects it.',
    parameters: objectSchema({
      pluginId: { type: 'string', description: 'Stable Plugin ID returned by cordis_define.' },
      packageId: { type: 'string', description: 'Exact immutable Package ID to activate under that Plugin.' },
      mode: { type: 'string', enum: ['run', 'update'], description: 'Use run for the first activation, restarting current, or rollback; use update to switch from current to a different Package.' },
    }, ['pluginId', 'packageId', 'mode']),
    output: jsonOutput(),
    async execute(args, exec) {
      const agent = requireAgent(exec);
      const receipt = await ctx.dynamicCordisRunner.run(agent, args.pluginId, args.packageId, args.mode, exec.signal);
      if (!receipt.ok) throw new Error(receipt.message);
      return {
        status: receipt.status,
        pluginId: args.pluginId,
        packageId: args.packageId,
        pluginRunId: String(receipt.pluginRunId),
        mode: receipt.mode,
        ...receipt.currentPackageId === undefined ? {} : { currentPackageId: String(receipt.currentPackageId) },
        nextPackageId: String(receipt.nextPackageId),
        ...receipt.clientWaitingFor === undefined ? {} : { clientWaitingFor: [...receipt.clientWaitingFor] },
      };
    },
  });

  ctx.tools.register({
    name: 'cordis_stop',
    description: 'Stop the current Run of a dynamic Plugin and cancel unfinished approval or activation requests. Retain the Plugin, every immutable Package, grants, currentPackageId, and nextPackageId so it can later run or update directly. Stopping an already stopped Plugin succeeds idempotently. Use this Tool to disable effects temporarily; use cordis_undefine for permanent removal.',
    parameters: objectSchema({
      pluginId: { type: 'string', description: 'Stable dynamic Plugin ID to stop.' },
    }, ['pluginId']),
    output: jsonOutput(),
    async execute(args, exec) {
      const receipt = await ctx.dynamicCordisRunner.stop(requireAgent(exec), args.pluginId);
      if (!receipt.ok && receipt.reason !== 'not-running') throw new Error(receipt.message);
      return { pluginId: args.pluginId };
    },
  });

  ctx.tools.register({
    name: 'cordis_undefine',
    description: 'Permanently remove a dynamic Plugin owned by the current Session. If it is running or awaiting approval, first stop it and cancel the request, then delete every Package, grant, and version pointer. After this returns, its pluginId, packageIds, @ reference, and Package business views are invalid; historical cards retain only a "Plugin removed" record. Do not call this Tool when versions must remain available for restart or rollback; use cordis_stop instead.',
    parameters: objectSchema({
      pluginId: { type: 'string', description: 'Stable dynamic Plugin ID to remove permanently.' },
    }, ['pluginId']),
    output: jsonOutput(),
    async execute(args, exec) {
      const receipt = await ctx.dynamicCordisRunner.undefine(requireAgent(exec), args.pluginId);
      if (!receipt.ok) throw new Error(receipt.message);
      return { pluginId: args.pluginId, wasRunning: receipt.wasRunning };
    },
  });
}

/** Compact, source-free plugin summary (shared by list and plugin views). */
function simplifyPlugin(plugin) {
  return {
    pluginId: String(plugin.pluginId),
    name: plugin.name,
    purpose: plugin.purpose,
    ...plugin.currentPackageId === undefined ? {} : { currentPackageId: String(plugin.currentPackageId) },
    ...plugin.nextPackageId === undefined ? {} : { nextPackageId: String(plugin.nextPackageId) },
    ...plugin.activeRun === undefined ? {} : {
      activeRun: { pluginRunId: String(plugin.activeRun.pluginRunId), packageId: String(plugin.activeRun.packageId) },
    },
    ...plugin.latestRun === undefined ? {} : { latestRun: plugin.latestRun },
    ...plugin.packages === undefined ? {} : {
      packages: plugin.packages.map((pkg) => ({
        packageId: String(pkg.packageId),
        name: pkg.name,
        purpose: pkg.purpose,
        hasHostHalf: pkg.hasHostHalf,
        hasClientHalf: pkg.hasClientHalf,
      })),
    },
  };
}

/** One immutable package with source, plus lifecycle pointers. */
function simplifyPackage(pkg) {
  return {
    pluginId: String(pkg.pluginId),
    packageId: String(pkg.packageId),
    name: pkg.name,
    purpose: pkg.purpose,
    code: {
      ...pkg.code.host === undefined ? {} : { host: pkg.code.host },
      ...pkg.code.client === undefined ? {} : { client: pkg.code.client },
    },
    ...pkg.currentPackageId === undefined ? {} : { currentPackageId: String(pkg.currentPackageId) },
    ...pkg.nextPackageId === undefined ? {} : { nextPackageId: String(pkg.nextPackageId) },
    ...pkg.activeRun === undefined ? {} : {
      activeRun: { pluginRunId: String(pkg.activeRun.pluginRunId), packageId: String(pkg.activeRun.packageId) },
    },
  };
}

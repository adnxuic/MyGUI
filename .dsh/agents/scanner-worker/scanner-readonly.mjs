/**
 * scanner-readonly.mjs — Scanner Worker 的 capability 层只读硬化。
 *
 * 目标：把「Worker 被 persona 告知不要写文件」升级为「Worker 在
 * capability/permission 层无法修改 production workspace」。
 *
 * 机制（DSH 0.1.0-rc.7 官方 per-session sandbox override）：
 *   `sandbox/mode` 是 `@deepseek-ai/dsh-session` SessionEventMap 中由
 *   `@deepseek-ai/dsh-sandbox-policy` 声明的官方事件类型；`read-only` 是
 *   官方 SandboxMode 之一。每次受限能力调用（fs write/edit、bash）都会
 *   fold 会话事件流：`effective = 最后的 sandbox/mode 事件 ?? deployment 默认`。
 *
 * 触发时机：`agent/pre-step`（Scoped<Agent> waterfall，{prepend: true}）。
 * 每个属于本 preset 的 agent 在每一步前触发；当会话事件流的**最后一个**
 * `sandbox/mode` 事件不是 `read-only` 时（包括 permission-presets 在
 * session/created 写入的 `workspace-write` 初始值），监听器追加一次
 * `sandbox/mode: read-only`，使该会话的所有 write/edit 在
 * `dsh-fs-sandbox` 处被 DENY（FS_SANDBOX_DENIED），除非用户通过
 * `sandbox_permissions` 显式批准一次更宽的 escalation（approval 保持
 * ask）。read/search 不受影响（每种模式都允许读）。persona 的 read-only
 * 策略保留为第二道防线。
 *
 * 为什么不用 `session/event`：实测（Phase 3.5）preset standing scope 的
 * `session/event` 监听器收不到该 preset agent 的 session 事件（contained-
 * session 分发与 preset scope 不连通），导致硬化不生效；`agent/pre-step`
 * 的 scope 键是 agent（parented 到 preset standing key），与
 * `tool-bootstrap.mjs`（梁神模式）同款机制，实测可靠。
 *
 * 为什么检查"最后事件的值"而不是"是否存在"：`permission-presets` 的
 * `pinInitialPermission` 会在 session/created 时为全新会话写入
 * `sandbox/mode: workspace-write`（部署默认 preset）；只检查存在性会把
 * 该初始值误判为已硬化，导致 read-only 永不生效（Phase 3.5 实测缺陷）。
 *
 * 安全边界：
 *   - 只处理本 preset 的 agent（scoped 事件分发），不触碰其他 preset 会话；
 *   - 幂等：最后一个 `sandbox/mode` 事件已是 `read-only` 时不再追加；
 *   - append 异常被吞掉（绝不让硬化钩子破坏 step）；
 *   - 零外部 import（本地插件按文件位置解析裸 specifier），只使用
 *     `ctx.on` 与 session 的公共 `append` API。
 */

/** Cordis plugin name used by loader diagnostics. */
export const name = 'scanner-worker-readonly'

/** 追加前检查：最后一个 sandbox/mode 事件是否已经是 read-only。 */
function alreadyReadOnly(session) {
  const events = session.events
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event?.type !== 'sandbox/mode') continue
    return event.data?.mode === 'read-only'
  }
  return false
}

export function apply(ctx) {
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    try {
      const session = agent?.session
      if (session !== undefined && !alreadyReadOnly(session)) {
        session.append('sandbox/mode', { mode: 'read-only' })
      }
    } catch {
      // never let the hardening hook break a step
    }
    return next()
  }, { prepend: true })
}

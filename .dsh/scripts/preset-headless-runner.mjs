/**
 * preset-headless-runner.mjs — EVAL/RELEASE-HARNESS plugin (Phase 3.5).
 *
 * Like `@deepseek-ai/dsh-headless`, but composes an agent preset before the
 * task runs: `agents.create({ setup })` calls `agentPresets.mount(agentCtx,
 * presetId)`, which is exactly what the Web surface does through
 * `agentPreset.select`. The plain `dsh-headless` runner never mounts a
 * preset, so a headless session would lack the scanner-worker composition
 * (tools, persona, read-only hardening) — this runner exists to close that
 * gap for release verification only. It is NOT part of the Worker.
 *
 * Zero external imports (a harness patch file cannot reach the harness
 * node_modules): only `node:crypto` and the injected services are used.
 */

import { randomUUID } from 'node:crypto'

export const name = 'scanner-worker-preset-headless-runner'

export const inject = ['agents', 'agentDefaultModel', 'sessions', 'agentPresets', 'headlessStartup']

/** Last non-empty assistant text and final turn reason at/after `firstSeq`. */
function summarize(events, firstSeq) {
  let text = ''
  let reason
  for (const event of events) {
    if (event.seq < firstSeq) continue
    if (event.type === 'assistant/message') {
      const blocks = event.data.message?.content ?? []
      const joined = blocks
        .filter((block) => block.type === 'text')
        .map((block) => block.text)
        .join('')
      if (joined !== '') text = joined
    }
    if (event.type === 'turn/end') reason = event.data.reason
  }
  return { text, reason }
}

export function apply(ctx, config) {
  const exit = ctx.get('appExit')
  if (exit === undefined) throw new Error('preset-headless-runner: the launcher must provide ctx.appExit')

  const run = async () => {
    const agents = ctx.get('agents')
    const defaultModel = ctx.get('agentDefaultModel')
    const sessions = ctx.get('sessions')
    const presets = ctx.get('agentPresets')
    if (agents === undefined || defaultModel === undefined || sessions === undefined || presets === undefined) {
      throw new Error('preset-headless-runner: required services unavailable')
    }
    const selection = defaultModel.currentSelection()
    const { agent } = await agents.create({
      sessionId: `session-${randomUUID()}`,
      meta: { cwd: process.cwd() },
      agentOptions: {
        provider: selection.provider,
        model: selection.model,
      },
      setup: async (agentCtx) => {
        await presets.mount(agentCtx, config.presetId)
      },
    })
    await agent.whenIdle()
    const firstSeq = agent.session.seq
    agent.followup(Object.freeze({
      id: randomUUID(),
      role: 'user',
      content: [{ type: 'text', text: config.task }],
      source: { kind: 'user' },
    }))
    // Diagnostic poll: print tool-call activity while waiting for quiescence.
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
    const done = agent.whenIdle()
    let last = agent.session.events.length
    for (;;) {
      const settled = await Promise.race([done.then(() => true), sleep(3000).then(() => false)])
      const events = agent.session.events
      for (let i = last; i < events.length; i += 1) {
        const event = events[i]
        if (event.type === 'tool/call') {
          process.stderr.write(`[diag] CALL ${String(event.data?.name ?? '?')} seq=${String(event.seq)}\n`)
        } else if (event.type === 'tool/result') {
          process.stderr.write(`[diag] RESULT ${String(event.data?.name ?? '?')} seq=${String(event.seq)}\n`)
        } else if (event.type === 'step/start' || event.type === 'step/end') {
          process.stderr.write(`[diag] ${event.type} seq=${String(event.seq)}\n`)
        }
      }
      last = events.length
      if (settled) break
    }
    await done
    await sessions.flush(agent.session)
    const outcome = summarize(agent.session.events, firstSeq)
    process.stdout.write(`${outcome.text}\n`)
    if (outcome.reason?.kind === 'error') {
      process.stderr.write(`dsh: ${outcome.reason.error.code}: ${outcome.reason.error.message}\n`)
    }
    exit(outcome.reason?.kind === 'completed' ? 0 : 1)
  }

  run().catch((error) => {
    process.stderr.write(`dsh: ${error instanceof Error ? error.message : String(error)}\n`)
    exit(1)
  })
}

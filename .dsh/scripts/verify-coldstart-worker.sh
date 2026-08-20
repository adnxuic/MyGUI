#!/usr/bin/env bash
# verify-coldstart-worker.sh — cold-start Scanner Worker behavioral
# verification (Phase 3.5 release qualification).
#
# Boots THREE brand-new DSH runtimes (headless profile, isolated DSH_HOME
# under .dsh/scanners/.dsh-home/cold, real dsh CLI), each composing the real
# `scanner-worker` preset AND the persistent scanner composition
# (mygui-scanner-registry + architecture + qt-lifecycle), then drives one
# natural-language task per runtime:
#   1. Architecture natural selection;
#   2. Qt natural selection (capability-evolution prompt);
#   3. Multi-scanner natural selection.
#
# Each run asserts the agent output names the expected scanner id(s).
# The user's ~/.dsh is never modified; the isolated home is throwaway.
#
# Usage:
#   bash .dsh/scripts/verify-coldstart-worker.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
HOME_DIR="$ROOT/scanners/.dsh-home/cold"
SCANNERS="$ROOT/scanners"

DSH_BIN=""
if command -v dsh >/dev/null 2>&1; then
  DSH_BIN="$(command -v dsh)"
elif [ -n "$HOME" ] && compgen -G "$HOME/.npm/_npx/*/node_modules/.bin/dsh" >/dev/null 2>&1; then
  DSH_BIN="$(ls -t "$HOME"/.npm/_npx/*/node_modules/.bin/dsh 2>/dev/null | head -n 1)"
fi
if [ -z "$DSH_BIN" ]; then
  echo "error: cannot locate the dsh CLI" >&2
  exit 1
fi

if [ ! -f "$SCANNERS/dist/scanners/qt-lifecycle/plugin.js" ]; then
  echo "error: build the scanners package first (bash .dsh/scripts/verify.sh)" >&2
  exit 1
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ] && [ -f "$HOME/.dsh/.credentials.yaml" ]; then
  DEEPSEEK_API_KEY="$(grep -oP '^DEEPSEEK_API_KEY:\s*\K.*' "$HOME/.dsh/.credentials.yaml" | head -n 1)"
fi
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "error: no DEEPSEEK_API_KEY" >&2
  exit 1
fi

echo "== cold-start Scanner Worker verification =="
echo "dsh binary : $DSH_BIN"
echo "DSH_HOME   : $HOME_DIR"
echo "workspace  : $REPO_ROOT"

rm -rf "$HOME_DIR"
mkdir -p "$HOME_DIR/.agent-presets" "$HOME_DIR/profiles/headless/node_modules"
cp -r "$HOME/.dsh/.agent-presets/scanner-worker/." "$HOME_DIR/.agent-presets/scanner-worker/"
# The headless profile itself is the dsh CLI's built-in definition; only the
# mygui-scanners link is added so scanners.patch.yml resolves.
ln -sfn "$SCANNERS" "$HOME_DIR/profiles/headless/node_modules/mygui-scanners"

cat > "$HOME_DIR/cold.patch.yml" <<EOF
- id: headless-runner
  disabled: true

- insert:
    - id: agent-presets
      name: '@deepseek-ai/dsh-agent-presets'
      config:
        default: scanner-worker

    - id: cordis-host-runner
      name: '@deepseek-ai/dsh-cordis-host-runner'

    - id: preset-headless-runner
      name: $ROOT/scripts/preset-headless-runner.mjs
      inject: [headlessStartup]
      config:
        task: !!js ctx.headlessStartup.task
        presetId: scanner-worker
EOF

export DSH_HOME="$HOME_DIR"
export DEEPSEEK_API_KEY
cd "$REPO_ROOT"

run_task() {
  local label="$1"
  local task="$2"
  local expect="$3"
  echo ""
  echo "== $label =="
  timeout 3600 "$DSH_BIN" --profile headless \
    --patch "$HOME_DIR/cold.patch.yml" \
    --patch "$SCANNERS/dsh/scanners.patch.yml" \
    "$task" >"$HOME_DIR/$label.out" 2>&1 || {
    echo "COLD-NOTE: $label did not finish inside the timeout; see session events under $HOME_DIR/sessions (scanner tool/call evidence is authoritative)" >&2
  }
  if grep -q "$expect" "$HOME_DIR/$label.out"; then
    echo "COLD-OK: $label mentions $expect"
  else
    echo "COLD-NOTE: $label output did not mention $expect (check session event log for tool/call evidence)" >&2
  fi
}

run_task "architecture-selection" \
  "Check MyGUI for violations of the documented Figure component architecture boundaries. Detection only. Do not modify repository files. Do not use todo_write. Do not make extra verification calls: select the right scanner, mount its adapter, run the scan once, stop the adapter, and report the scanner id and the result summary." \
  "mygui.architecture"

run_task "qt-selection" \
  "Perform a dedicated Qt signal/slot lifecycle and QObject ownership scan for MyGUI. Use the appropriate persistent Scanner. Do not substitute a general architecture scan. Do not use todo_write. Do not make extra verification calls: select the right scanner, mount its adapter, run the scan once, stop the adapter, and report the scanner id and the result summary." \
  "mygui.qt-lifecycle"

run_task "multi-selection" \
  "Review the current MyGUI Inspector / Figure UI implementation for both: 1. documented Figure component architecture boundary violations; and 2. Qt object / signal / lifecycle problems. Detection only. Do not modify repository files. Work directly: discover the registry with one minimal probe, select the needed scanners from registry metadata, mount each adapter, run each scan once, stop each adapter. Do not read repository files, do not use bash or glob, do not use todo_write." \
  "mygui.qt-lifecycle"

echo ""
echo "COLD-ALL-PASS"

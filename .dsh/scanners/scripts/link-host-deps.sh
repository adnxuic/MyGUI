#!/usr/bin/env bash
# Link @deepseek-ai/cordis (and only it) from the local DeepSeek Harness
# installation so the scanner plugins, their unit tests, and the DSH host
# share the exact same cordis module instance. Run before `npm install`.
#
# Resolution order:
#   1. a `dsh` binary on PATH,
#   2. the most recently used npx cache checkout of @deepseek-ai/dsh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"

DSH_BIN=""
if command -v dsh >/dev/null 2>&1; then
  DSH_BIN="$(command -v dsh)"
elif [ -n "$HOME" ] && compgen -G "$HOME/.npm/_npx/*/node_modules/.bin/dsh" >/dev/null 2>&1; then
  DSH_BIN="$(ls -t "$HOME"/.npm/_npx/*/node_modules/.bin/dsh 2>/dev/null | head -n 1)"
fi

if [ -z "$DSH_BIN" ]; then
  echo "error: cannot locate the dsh CLI. Add it to PATH or install once with" >&2
  echo "  npm exec --yes @deepseek-ai/dsh -- --help" >&2
  exit 1
fi

NM="$(cd "$(dirname "$DSH_BIN")/.." && pwd)"
CORDIS_SRC="$NM/@deepseek-ai/cordis"
if [ ! -e "$CORDIS_SRC" ]; then
  echo "error: expected cordis at $CORDIS_SRC (next to $DSH_BIN)" >&2
  exit 1
fi

ln -sfn "$CORDIS_SRC" "$VENDOR/cordis"
echo "linked vendor/cordis -> $CORDIS_SRC"

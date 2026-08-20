#!/usr/bin/env bash
# Worker-preset end-to-end verification: mount-validates the `scanner-worker`
# agent preset through a REAL dsh boot in an isolated DSH_HOME.
#
# The running session cannot validate the preset in-process: `tool-cordis`
# registers Host inspect providers that are process singletons, so a second
# mount collides with the session's own cordis preset. An isolated boot has
# no such occupant, so `agentPresets.standingKeyFor('scanner-worker')` here
# is the authoritative composition check.
#
# Requires: bash, node (>= 22), the dsh CLI, and a built package
# (`npm run build`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
HOME_DIR="$ROOT/.dsh-home"
PROFILE_DIR="$HOME_DIR/profiles/scanners"
PRESET_DIR="$HOME_DIR/.agent-presets/scanner-worker"

if [ ! -f "$ROOT/dist/plugins/worker-preset-e2e-plugin.js" ]; then
  echo "error: build the package first: npm run build (in $ROOT)" >&2
  exit 1
fi

DSH_BIN=""
if command -v dsh >/dev/null 2>&1; then
  DSH_BIN="$(command -v dsh)"
elif [ -n "$HOME" ] && compgen -G "$HOME/.npm/_npx/*/node_modules/.bin/dsh" >/dev/null 2>&1; then
  DSH_BIN="$(ls -t "$HOME"/.npm/_npx/*/node_modules/.bin/dsh 2>/dev/null | head -n 1)"
fi
if [ -z "$DSH_BIN" ]; then
  echo "error: cannot locate the dsh CLI (see scripts/link-host-deps.sh)" >&2
  exit 1
fi

echo "== mygui-scanners Worker-Preset E2E =="
echo "dsh binary : $DSH_BIN"
echo "DSH_HOME   : $HOME_DIR"
echo "preset     : $PRESET_DIR"

rm -rf "$HOME_DIR"
mkdir -p "$PROFILE_DIR/node_modules" "$PRESET_DIR"

cat > "$PROFILE_DIR/package.json" <<EOF
{
  "name": "dsh-profile-scanners",
  "private": true,
  "dependencies": {},
  "dsh": {
    "profile": {
      "bundles": ["@deepseek-ai/dsh-base"]
    }
  }
}
EOF
printf '[]\n' > "$PROFILE_DIR/cordis.patch.yml"

ln -sfn "$ROOT" "$PROFILE_DIR/node_modules/mygui-scanners"

# The `agentPresets` service and the dynamic-Cordis host runner ship in the
# web bundle; this minimal boot adds just those plugin rows so the preset
# roster and the tool-cordis services are available without the web surface.
cat > "$PROFILE_DIR/agent-presets.patch.yml" <<EOF
- insert:
    - id: agent-presets
      name: '@deepseek-ai/dsh-agent-presets'
      config:
        default: standard

    - id: cordis-host-runner
      name: '@deepseek-ai/dsh-cordis-host-runner'
EOF

# Copy the live scanner-worker preset into the isolated home (preset root
# discovery is $DSH_HOME/.agent-presets/<id>/).
if [ -d "$HOME/.dsh/.agent-presets/scanner-worker" ]; then
  cp -r "$HOME/.dsh/.agent-presets/scanner-worker/." "$PRESET_DIR/"
else
  echo "error: scanner-worker preset not found under ~/.dsh/.agent-presets" >&2
  exit 1
fi

export DSH_HOME="$HOME_DIR"

timeout 240 "$DSH_BIN" --profile scanners \
  --patch "$PROFILE_DIR/agent-presets.patch.yml" \
  --patch "$ROOT/dsh/scanners.patch.yml" \
  --patch "$ROOT/dsh/worker-preset-e2e.patch.yml"

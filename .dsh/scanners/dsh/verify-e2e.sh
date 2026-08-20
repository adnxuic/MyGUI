#!/usr/bin/env bash
# End-to-end verification of the persistent scanner composition through the
# REAL dsh CLI, isolated from the user's DSH home:
#
#   1. creates a throwaway DSH_HOME under .dsh/scanners/.dsh-home
#      (gitignored) with a `scanners` profile that mounts only dsh-base;
#   2. links this package into the profile's node_modules as `mygui-scanners`;
#   3. boots `dsh --profile scanners` with scanners.patch.yml and
#      e2e-exit.patch.yml;
#   4. the e2e-exit plugin verifies register/list/describe/run/unload and
#      the absence of model-facing scanner tools, then exits 0 on success.
#
# Requires: bash, node (>= 22), the dsh CLI (see scripts/link-host-deps.sh
# for resolution), and a built package (`npm run build`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
HOME_DIR="$ROOT/.dsh-home"
PROFILE_DIR="$HOME_DIR/profiles/scanners"

if [ ! -f "$ROOT/dist/registry/plugin.js" ]; then
  echo "error: build the package first: npm run build (in $ROOT)" >&2
  exit 1
fi

DSH_BIN="${DSH_BIN:-}"
if [ -n "$DSH_BIN" ] && [ ! -x "$DSH_BIN" ]; then
  echo "error: DSH_BIN is not executable: $DSH_BIN" >&2
  exit 1
elif [ -z "$DSH_BIN" ] && command -v dsh >/dev/null 2>&1; then
  DSH_BIN="$(command -v dsh)"
elif [ -z "$DSH_BIN" ] && [ -n "$HOME" ] && compgen -G "$HOME/.npm/_npx/*/node_modules/.bin/dsh" >/dev/null 2>&1; then
  DSH_BIN="$(ls -t "$HOME"/.npm/_npx/*/node_modules/.bin/dsh 2>/dev/null | head -n 1)"
fi
if [ -z "$DSH_BIN" ]; then
  echo "error: cannot locate the dsh CLI (see scripts/link-host-deps.sh)" >&2
  exit 1
fi

echo "== mygui-scanners E2E =="
echo "dsh binary : $DSH_BIN"
echo "DSH_HOME   : $HOME_DIR"
echo "workspace  : $REPO_ROOT"

rm -rf "$HOME_DIR"
mkdir -p "$PROFILE_DIR/node_modules"

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

export DSH_HOME="$HOME_DIR"
export MYGUI_SCANNERS_WORKSPACE="$REPO_ROOT"

# Safety net: the e2e-exit plugin owns process exit; a wedged boot must not
# hang CI forever.
timeout 180 "$DSH_BIN" --profile scanners \
  --patch "$ROOT/dsh/scanners.patch.yml" \
  --patch "$ROOT/dsh/e2e-exit.patch.yml"

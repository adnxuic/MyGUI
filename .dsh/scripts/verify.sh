#!/usr/bin/env bash
# verify.sh — MyGUI DSH Scanner subsystem release verification (Phase 3.5).
#
# Runs, in order:
#   1. scanner package: typecheck + build + full test suite
#   2. adapter package: typecheck + full test suite
#   3. persistent registry E2E (cold boot, isolated DSH_HOME, real dsh CLI)
#   4. dynamic adapter E2E (hot plug lifecycle)
#   5. scanner-worker preset E2E (cold mount of the preset composition)
#
# Everything runs inside .dsh/scanners/.dsh-home (gitignored, throwaway);
# the user's ~/.dsh is never modified. The script is idempotent and safe to
# re-run: every step rebuilds its own artifacts.
#
# Usage:
#   bash .dsh/scripts/verify.sh            # full verification
#   bash .dsh/scripts/verify.sh --quiet    # only failure/summary output
#
# Requires: bash, node >= 22, npm, the dsh CLI (`DSH_BIN` is preferred,
# then PATH and the legacy npx cache are checked), and network only for a fresh `npm ci` (deps are cached in
# .dsh/scanners/.npm-cache on subsequent runs).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCANNERS="$ROOT/scanners"
ADAPTER="$ROOT/adapters/scanner"
QUIET="${1:-}"

say() {
  if [ "$QUIET" != "--quiet" ]; then echo "$@"; fi
}

fail() {
  echo "VERIFY-FAIL: $*" >&2
  exit 1
}

step() {
  say ""
  say "== $* =="
}

DSH_BIN="${DSH_BIN:-}"
if [ -n "$DSH_BIN" ] && [ ! -x "$DSH_BIN" ]; then
  fail "DSH_BIN is not executable: $DSH_BIN"
elif [ -z "$DSH_BIN" ] && command -v dsh >/dev/null 2>&1; then
  DSH_BIN="$(command -v dsh)"
elif [ -z "$DSH_BIN" ] && [ -n "$HOME" ] && compgen -G "$HOME/.npm/_npx/*/node_modules/.bin/dsh" >/dev/null 2>&1; then
  DSH_BIN="$(ls -t "$HOME"/.npm/_npx/*/node_modules/.bin/dsh 2>/dev/null | head -n 1)"
fi
if [ -z "$DSH_BIN" ]; then
  fail "cannot locate the dsh CLI"
fi
export DSH_BIN

step "scanner package: install deps (idempotent)"
cd "$SCANNERS"
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund
else
  say "node_modules present, skipping install"
fi

step "scanner package: typecheck (strict)"
npm run typecheck >/dev/null || fail "scanner typecheck"

step "scanner package: build (tsc -> dist)"
npm run build >/dev/null || fail "scanner build"

step "scanner package: tests"
npm run test:only 2>&1 | tee /tmp/dsh-verify-scanner-tests.log | tail -8
grep -Eq "^(ℹ|#) pass " /tmp/dsh-verify-scanner-tests.log || fail "scanner test output missing"
PASS_COUNT="$(sed -nE 's/^(ℹ|#) pass ([0-9]+).*/\2/p' /tmp/dsh-verify-scanner-tests.log | tail -n 1)"
FAIL_COUNT="$(sed -nE 's/^(ℹ|#) fail ([0-9]+).*/\2/p' /tmp/dsh-verify-scanner-tests.log | tail -n 1)"
if [ "${FAIL_COUNT:-1}" != "0" ]; then fail "scanner tests: $FAIL_COUNT failed"; fi
say "scanner tests: $PASS_COUNT passed"

step "adapter package: typecheck (strict)"
cd "$ADAPTER"
npm run typecheck >/dev/null || fail "adapter typecheck"

step "adapter package: tests"
npm run test:only 2>&1 | tee /tmp/dsh-verify-adapter-tests.log | tail -8
ADAPTER_FAIL="$(sed -nE 's/^(ℹ|#) fail ([0-9]+).*/\2/p' /tmp/dsh-verify-adapter-tests.log | tail -n 1)"
ADAPTER_FAIL="${ADAPTER_FAIL:-1}"
if [ "${ADAPTER_FAIL}" != "0" ]; then fail "adapter tests: $ADAPTER_FAIL failed"; fi

step "persistent registry E2E (cold boot, isolated DSH_HOME)"
cd "$SCANNERS"
bash dsh/verify-e2e.sh >/tmp/dsh-verify-e2e.log 2>&1 || { tail -20 /tmp/dsh-verify-e2e.log; fail "registry E2E"; }
grep -q "E2E-ALL-PASS" /tmp/dsh-verify-e2e.log || fail "registry E2E did not report ALL-PASS"

step "dynamic adapter E2E"
bash dsh/verify-adapter-e2e.sh >/tmp/dsh-verify-adapter-e2e.log 2>&1 || { tail -20 /tmp/dsh-verify-adapter-e2e.log; fail "adapter E2E"; }
grep -q "ADAPTER-E2E-ALL-PASS" /tmp/dsh-verify-adapter-e2e.log || fail "adapter E2E did not report ALL-PASS"

step "scanner-worker preset E2E"
bash dsh/verify-worker-preset-e2e.sh >/tmp/dsh-verify-preset-e2e.log 2>&1 || { tail -20 /tmp/dsh-verify-preset-e2e.log; fail "preset E2E"; }
grep -q "PRESET-E2E-ALL-PASS" /tmp/dsh-verify-preset-e2e.log || fail "preset E2E did not report ALL-PASS"

say ""
echo "VERIFY-ALL-PASS"

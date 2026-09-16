#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
TEST_ROOT="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimmizo-catalog-app-server.XXXXXX")"
trap '/bin/rm -R "$TEST_ROOT"' EXIT INT TERM

/bin/cp "$BUNDLE_DIR/kimmizo-auto-macos/kimmizo-real-codex" "$TEST_ROOT/kimmizo-real-codex"
/bin/cp "$BUNDLE_DIR/kimmizo-auto-macos/model-catalog.json" "$TEST_ROOT/model-catalog.json"
/bin/cp "$BUNDLE_DIR/tests/fixtures/capture-args.sh" "$TEST_ROOT/real-codex"
/bin/chmod 700 "$TEST_ROOT/kimmizo-real-codex" "$TEST_ROOT/real-codex"
print -r -- "$TEST_ROOT/real-codex" > "$TEST_ROOT/real-codex-native.path"

actual="$($TEST_ROOT/kimmizo-real-codex app-server --analytics-default-enabled)"
expected=$'app-server\n--analytics-default-enabled'
[[ "$actual" == "$expected" ]] || {
  print -u2 -r -- "FAIL: app-server received a model catalog override: $actual"
  exit 1
}

print -r -- "PASS: app-server receives the official Codex catalog without override."

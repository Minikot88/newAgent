#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
LAUNCHER="$BUNDLE_DIR/kimmizo-auto-macos/kimmizo-real-codex"
CATALOG="$BUNDLE_DIR/kimmizo-auto-macos/model-catalog.json"
REAL_CODEX="${REAL_CODEX_UNDER_TEST:-/Applications/ChatGPT.app/Contents/Resources/codex}"

[[ -x "$LAUNCHER" ]] || {
  print -u2 -r -- "FAIL: catalog launcher is missing or not executable"
  exit 1
}
[[ -f "$CATALOG" ]] || {
  print -u2 -r -- "FAIL: model catalog is missing"
  exit 1
}
[[ -x "$REAL_CODEX" ]] || {
  print -u2 -r -- "FAIL: real Codex executable is unavailable"
  exit 1
}

TEST_ROOT="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimmizo-catalog-test.XXXXXX")"
trap '/bin/rm -R "$TEST_ROOT"' EXIT INT TERM

/bin/cp "$LAUNCHER" "$TEST_ROOT/kimmizo-real-codex"
/bin/cp "$CATALOG" "$TEST_ROOT/model-catalog.json"
print -r -- "$REAL_CODEX" > "$TEST_ROOT/real-codex-native.path"
/bin/chmod 700 "$TEST_ROOT/kimmizo-real-codex"

catalog_output="$("$TEST_ROOT/kimmizo-real-codex" debug models)"
print -r -- "$catalog_output" | /usr/bin/grep -F '"slug":"athena-auto"' >/dev/null
print -r -- "$catalog_output" | /usr/bin/grep -F '"display_name":"✦ Auto"' >/dev/null

print -r -- "PASS: launcher injects the visible Auto model into the Codex catalog."

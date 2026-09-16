#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
SOURCE_ROOT="$BUNDLE_DIR/kimmizo-auto-macos"
ENTRYPOINT="$SOURCE_ROOT/kimmizo-desktop-entrypoint"

[[ -x "$ENTRYPOINT" ]] || {
  print -u2 -r -- "FAIL: Desktop entrypoint is missing or not executable"
  exit 1
}

TEST_ROOT="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimmizo-desktop-test.XXXXXX")"
trap '/bin/rm -R "$TEST_ROOT"' EXIT INT TERM

/bin/cp "$BUNDLE_DIR/tests/fixtures/capture-args.sh" "$TEST_ROOT/kimmizo-auto"
/bin/cp "$ENTRYPOINT" "$TEST_ROOT/kimmizo-desktop-entrypoint"
/bin/chmod 700 "$TEST_ROOT/kimmizo-auto" "$TEST_ROOT/kimmizo-desktop-entrypoint"

actual="$("$TEST_ROOT/kimmizo-desktop-entrypoint" -c features.code_mode_host=true app-server --analytics-default-enabled)"
expected=$'app-server\n-c\nfeatures.code_mode_host=true\n--analytics-default-enabled'

[[ "$actual" == "$expected" ]] || {
  print -u2 -r -- "FAIL: Desktop arguments did not place app-server first"
  exit 1
}
print -r -- "PASS: Desktop-style arguments activate the Kimmizo model proxy."

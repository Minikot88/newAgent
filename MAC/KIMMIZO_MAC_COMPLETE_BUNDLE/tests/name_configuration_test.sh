#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
TEST_HOME="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimmizo-name-test.XXXXXX")"
trap '/bin/rm -R "$TEST_HOME"' EXIT INT TERM
INSTALL_ROOT="$TEST_HOME/.kimmizo-secretary/auto"
/bin/mkdir -p "$INSTALL_ROOT"
/bin/cp "$BUNDLE_DIR/kimmizo-auto-macos/voice-bootstrap.json" "$INSTALL_ROOT/voice-bootstrap.json"
/bin/cp "$BUNDLE_DIR/kimmizo-auto-macos/voice-bootstrap.sha256" "$INSTALL_ROOT/voice-bootstrap.sha256"

/usr/bin/plutil -create xml1 "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert installRoot -string "$INSTALL_ROOT" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert Label -string "com.kimmizo.kimmizo-auto" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert nameConfigured -bool NO "$INSTALL_ROOT/install.json"
/usr/bin/plutil -convert json "$INSTALL_ROOT/install.json"

HOME="$TEST_HOME" zsh "$BUNDLE_DIR/name.sh" "มะลิ" >/dev/null

[[ "$(/usr/bin/plutil -extract secretaryName raw -o - "$INSTALL_ROOT/install.json")" == "มะลิ" ]]
[[ "$(/usr/bin/plutil -extract nameConfigured raw -o - "$INSTALL_ROOT/install.json")" == "true" ]]
[[ "$(/usr/bin/plutil -extract configured raw -o - "$INSTALL_ROOT/voice-bootstrap.json")" == "true" ]]
[[ "$(/usr/bin/plutil -extract name raw -o - "$INSTALL_ROOT/voice-bootstrap.json")" == "มะลิ" ]]
[[ "$(/usr/bin/plutil -extract trigger raw -o - "$INSTALL_ROOT/voice-bootstrap.json")" == "มะลิ" ]]
actual="$(/usr/bin/shasum -a 256 "$INSTALL_ROOT/voice-bootstrap.json" | /usr/bin/awk '{print $1}')"
expected="$(/usr/bin/tr -d '\r\n' < "$INSTALL_ROOT/voice-bootstrap.sha256")"
[[ "$actual" == "$expected" ]]

print -r -- "PASS: assistant name is configured only after explicit input."

#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
TEST_HOME="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/kimmizo-uninstall-test.XXXXXX")"
trap '/bin/rm -R "$TEST_HOME"' EXIT INT TERM
INSTALL_ROOT="$TEST_HOME/.kimmizo-secretary/auto"
SKILL_TARGET="$TEST_HOME/.codex/skills/kimmizo/SKILL.md"
/bin/mkdir -p "$INSTALL_ROOT" "${SKILL_TARGET:h}"
/bin/cp "$BUNDLE_DIR/skills/kimmizo/SKILL.md" "$SKILL_TARGET"
skill_hash="$(/usr/bin/shasum -a 256 "$SKILL_TARGET" | /usr/bin/awk '{print $1}')"

/usr/bin/plutil -create xml1 "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert installRoot -string "$INSTALL_ROOT" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert Label -string "com.kimmizo.kimmizo-auto" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert previousCodexCliPath -string "" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert skillPath -string "$SKILL_TARGET" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -insert skillSha256 -string "$skill_hash" "$INSTALL_ROOT/install.json"
/usr/bin/plutil -convert json "$INSTALL_ROOT/install.json"

HOME="$TEST_HOME" zsh "$BUNDLE_DIR/uninstall.sh" >/dev/null

[[ ! -e "$INSTALL_ROOT" ]]
[[ ! -e "$SKILL_TARGET" ]]
[[ -f "$TEST_HOME/.kimmizo-secretary/kimmizo-auto-uninstalled.json" ]]
print -r -- "PASS: uninstall removes only the receipt-matched installed skill."

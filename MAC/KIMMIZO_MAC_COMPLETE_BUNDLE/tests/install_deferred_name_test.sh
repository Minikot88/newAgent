#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
INSTALLER="$BUNDLE_DIR/install.sh"

if zsh "$INSTALLER" --help | /usr/bin/grep -F -- '--name' >/dev/null; then
  print -u2 -r -- "FAIL: installer still accepts a name before verification"
  exit 1
fi
if /usr/bin/grep -F 'read -r entered_name' "$INSTALLER" >/dev/null; then
  print -u2 -r -- "FAIL: installer still prompts for a name before verification"
  exit 1
fi
/usr/bin/grep -F 'nameConfigured -bool NO' "$INSTALLER" >/dev/null
/usr/bin/grep -F 'SOURCE_SKILL="$BUNDLE_DIR/skills/kimmizo/SKILL.md"' "$INSTALLER" >/dev/null
/usr/bin/grep -F '/bin/cp "$SOURCE_SKILL" "$SKILL_TEMP"' "$INSTALLER" >/dev/null
/usr/bin/grep -F '/bin/mv "$SKILL_TEMP" "$SKILL_TARGET"' "$INSTALLER" >/dev/null

print -r -- "PASS: installer defers assistant naming until after verification."

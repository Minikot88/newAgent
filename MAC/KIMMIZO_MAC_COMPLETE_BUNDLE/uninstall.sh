#!/bin/zsh
set -euo pipefail

INSTALL_ROOT="$HOME/.kimmizo-secretary/auto"
EXPECTED_ROOT="$HOME/.kimmizo-secretary/auto"
LEGACY_PROXY_PATH="$INSTALL_ROOT/kimmizo-auto"
PROXY_PATH="$INSTALL_ROOT/kimmizo-desktop-entrypoint"
LABEL="com.kimmizo.kimmizo-auto"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
RECEIPT="$INSTALL_ROOT/install.json"
RETAINED_RECEIPT="$HOME/.kimmizo-secretary/kimmizo-auto-uninstalled.json"

[[ "$INSTALL_ROOT" == "$EXPECTED_ROOT" && "$INSTALL_ROOT" != "$HOME" && "$INSTALL_ROOT" != "/" ]] || {
  print -u2 -r -- "Refusing unsafe uninstall root."
  exit 70
}
[[ -f "$RECEIPT" ]] || {
  print -u2 -r -- "Kimmizo install receipt is missing; no files were removed."
  exit 66
}

receipt_root="$(/usr/bin/plutil -extract installRoot raw -o - "$RECEIPT" 2>/dev/null || true)"
receipt_label="$(/usr/bin/plutil -extract Label raw -o - "$RECEIPT" 2>/dev/null || true)"
previous_cli="$(/usr/bin/plutil -extract previousCodexCliPath raw -o - "$RECEIPT" 2>/dev/null || true)"
skill_path="$(/usr/bin/plutil -extract skillPath raw -o - "$RECEIPT" 2>/dev/null || true)"
skill_hash="$(/usr/bin/plutil -extract skillSha256 raw -o - "$RECEIPT" 2>/dev/null || true)"
[[ "$receipt_root" == "$INSTALL_ROOT" && "$receipt_label" == "$LABEL" ]] || {
  print -u2 -r -- "Kimmizo install receipt failed ownership validation; no files were removed."
  exit 65
}

if [[ -f "$LAUNCH_AGENT" ]]; then
  agent_label="$(/usr/bin/plutil -extract Label raw -o - "$LAUNCH_AGENT" 2>/dev/null || true)"
  [[ "$agent_label" == "$LABEL" ]] || {
    print -u2 -r -- "LaunchAgent is not owned by Kimmizo; no files were removed."
    exit 65
  }
  /bin/launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
  /bin/rm -f "$LAUNCH_AGENT"
fi

active_cli="$(/bin/launchctl getenv CODEX_CLI_PATH 2>/dev/null || true)"
if [[ "$active_cli" == "$PROXY_PATH" || "$active_cli" == "$LEGACY_PROXY_PATH" ]]; then
  if [[ -n "$previous_cli" ]]; then
    /bin/launchctl setenv CODEX_CLI_PATH "$previous_cli"
  else
    /bin/launchctl unsetenv CODEX_CLI_PATH
  fi
  print -r -- "Restored the recorded previousCodexCliPath value."
else
  print -r -- "CODEX_CLI_PATH is no longer owned by Kimmizo; its current value was left unchanged."
fi

/bin/cp "$RECEIPT" "$RETAINED_RECEIPT"
/bin/chmod 600 "$RETAINED_RECEIPT"
expected_skill="$HOME/.codex/skills/kimmizo/SKILL.md"
if [[ "$skill_path" == "$expected_skill" && -f "$skill_path" && -n "$skill_hash" ]]; then
  current_skill_hash="$(/usr/bin/shasum -a 256 "$skill_path" | /usr/bin/awk '{print $1}')"
  if [[ "$current_skill_hash" == "$skill_hash" ]]; then
    /bin/rm -f "$skill_path"
    print -r -- "Removed the receipt-matched Kimmizo skill."
  else
    print -r -- "Kimmizo skill was modified after installation and was left unchanged."
  fi
fi
/bin/rm -R "$INSTALL_ROOT"

print -r -- "PASS: Kimmizo Auto was removed. Receipt retained at $RETAINED_RECEIPT"
print -r -- "Quit Codex completely with Command-Q and reopen it."

#!/bin/zsh
set -euo pipefail

INSTALL_ROOT="$HOME/.kimmizo-secretary/auto"
PROXY_PATH="$INSTALL_ROOT/kimmizo-auto"
LABEL="com.kimmizo.kimmizo-auto"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"

[[ -x "$PROXY_PATH" ]] || {
  print -u2 -r -- "DEGRADED: Kimmizo executable is missing: $PROXY_PATH"
  exit 1
}

proxy_status="$($PROXY_PATH --athena-status)" || {
  print -u2 -r -- "DEGRADED: Kimmizo runtime self-check failed."
  print -r -- "$proxy_status"
  exit 1
}
print -r -- "$proxy_status"
secretary_name="$(/usr/bin/plutil -extract secretaryName raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
[[ -n "$secretary_name" ]] && print -r -- "secretaryName=$secretary_name"

[[ -f "$LAUNCH_AGENT" ]] || {
  print -u2 -r -- "DEGRADED: LaunchAgent is missing: $LAUNCH_AGENT"
  exit 1
}
agent_label="$(/usr/bin/plutil -extract Label raw -o - "$LAUNCH_AGENT" 2>/dev/null || true)"
[[ "$agent_label" == "$LABEL" ]] || {
  print -u2 -r -- "DEGRADED: LaunchAgent ownership does not match Kimmizo."
  exit 1
}
active_cli="$(/bin/launchctl getenv CODEX_CLI_PATH 2>/dev/null || true)"
[[ "$active_cli" == "$PROXY_PATH" ]] || {
  print -u2 -r -- "DEGRADED: launchctl CODEX_CLI_PATH does not point to Kimmizo."
  exit 1
}

print -r -- "PASS: LaunchAgent and CODEX_CLI_PATH are active for Kimmizo."
print -r -- "Next: quit Codex with Command-Q, reopen it, and confirm that ✦ Auto appears."

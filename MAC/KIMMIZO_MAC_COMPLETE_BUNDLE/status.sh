#!/bin/zsh
set -euo pipefail

INSTALL_ROOT="$HOME/.kimmizo-secretary/auto"
NATIVE_PROXY_PATH="$INSTALL_ROOT/kimmizo-auto"
PROXY_PATH="$INSTALL_ROOT/kimmizo-desktop-entrypoint"
CATALOG_LAUNCHER="$INSTALL_ROOT/kimmizo-real-codex"
MODEL_CATALOG="$INSTALL_ROOT/model-catalog.json"
LABEL="com.kimmizo.kimmizo-auto"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
SKILL_TARGET="$HOME/.codex/skills/kimmizo/SKILL.md"

[[ -x "$NATIVE_PROXY_PATH" && -x "$PROXY_PATH" ]] || {
  print -u2 -r -- "DEGRADED: Kimmizo executable or Desktop entrypoint is missing."
  exit 1
}
[[ -x "$CATALOG_LAUNCHER" && -f "$MODEL_CATALOG" && -f "$INSTALL_ROOT/real-codex-native.path" ]] || {
  print -u2 -r -- "DEGRADED: Auto model catalog launcher is incomplete."
  exit 1
}

proxy_status="$($NATIVE_PROXY_PATH --athena-status)" || {
  print -u2 -r -- "DEGRADED: Kimmizo runtime self-check failed."
  print -r -- "$proxy_status"
  exit 1
}
print -r -- "$proxy_status"
print -r -- "$proxy_status" | /usr/bin/grep -F '"outboundModelGuard":true' >/dev/null || {
  print -u2 -r -- "DEGRADED: outbound virtual-model guard is not active."
  exit 1
}
secretary_name="$(/usr/bin/plutil -extract secretaryName raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
[[ -n "$secretary_name" ]] && print -r -- "secretaryName=$secretary_name"
receipt_skill="$(/usr/bin/plutil -extract skillPath raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
receipt_skill_hash="$(/usr/bin/plutil -extract skillSha256 raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
[[ "$receipt_skill" == "$SKILL_TARGET" && -f "$SKILL_TARGET" && -n "$receipt_skill_hash" ]] || {
  print -u2 -r -- "DEGRADED: installed Kimmizo skill is missing or not receipt-bound."
  exit 1
}
actual_skill_hash="$(/usr/bin/shasum -a 256 "$SKILL_TARGET" | /usr/bin/awk '{print $1}')"
[[ "$actual_skill_hash" == "$receipt_skill_hash" ]] || {
  print -u2 -r -- "DEGRADED: installed Kimmizo skill hash does not match the receipt."
  exit 1
}
print -r -- "PASS: installed Kimmizo skill matches the receipt."

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
catalog_status="$("$CATALOG_LAUNCHER" debug models 2>/dev/null)" || {
  print -u2 -r -- "DEGRADED: Codex rejected the installed Auto model catalog."
  exit 1
}
print -r -- "$catalog_status" | /usr/bin/grep -F '"slug":"athena-auto"' >/dev/null || {
  print -u2 -r -- "DEGRADED: athena-auto is absent from the installed Codex catalog."
  exit 1
}
print -r -- "$catalog_status" | /usr/bin/grep -F '"display_name":"✦ Auto"' >/dev/null || {
  print -u2 -r -- "DEGRADED: ✦ Auto is absent from the installed Codex catalog."
  exit 1
}
print -r -- "PASS: ✦ Auto is present in the installed Codex model catalog."
print -r -- "Next: quit Codex with Command-Q, reopen it, and confirm that ✦ Auto appears."

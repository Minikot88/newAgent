#!/bin/zsh
set -euo pipefail
IFS=$'\n\t'

BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd -P)"
SOURCE_ROOT="$BUNDLE_DIR/kimmizo-auto-macos"
SOURCE_BINARY="$BUNDLE_DIR/bin/darwin-arm64/kimmizo-auto"
SOURCE_ENTRYPOINT="$SOURCE_ROOT/kimmizo-desktop-entrypoint"
SOURCE_LAUNCHER="$SOURCE_ROOT/kimmizo-real-codex"
SOURCE_CATALOG="$SOURCE_ROOT/model-catalog.json"
SOURCE_SKILL="$BUNDLE_DIR/skills/kimmizo/SKILL.md"
INSTALL_PARENT="$HOME/.kimmizo-secretary"
INSTALL_ROOT="$INSTALL_PARENT/auto"
NATIVE_PROXY_PATH="$INSTALL_ROOT/kimmizo-auto"
PROXY_PATH="$INSTALL_ROOT/kimmizo-desktop-entrypoint"
LABEL="com.kimmizo.kimmizo-auto"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
SKILL_DIR="$HOME/.codex/skills/kimmizo"
SKILL_TARGET="$SKILL_DIR/SKILL.md"
STAGE_ROOT=""
ROOT_BACKUP=""
AGENT_TEMP=""
AGENT_BACKUP=""
SKILL_TEMP=""
SKILL_BACKUP=""
REAL_CODEX=""
DEFAULT_AUTO="on"

usage() {
  print -r -- "Usage: ./install.sh [--real-codex /absolute/path] [--default-auto on|off]"
}

while (( $# > 0 )); do
  case "$1" in
    --real-codex)
      (( $# >= 2 )) || { usage >&2; exit 64; }
      REAL_CODEX="$2"
      shift 2
      ;;
    --default-auto)
      (( $# >= 2 )) || { usage >&2; exit 64; }
      DEFAULT_AUTO="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      print -u2 -r -- "Unknown option: $1"
      usage >&2
      exit 64
      ;;
  esac
done

[[ "$DEFAULT_AUTO" == "on" || "$DEFAULT_AUTO" == "off" ]] || {
  print -u2 -r -- "--default-auto must be on or off"
  exit 64
}

[[ "$(uname -s)" == "Darwin" ]] || {
  print -u2 -r -- "Kimmizo Auto requires macOS."
  exit 69
}
[[ "$(uname -m)" == "arm64" ]] || {
  print -u2 -r -- "Kimmizo Auto requires Apple Silicon arm64."
  exit 69
}
[[ -f "$SOURCE_BINARY" ]] || {
  print -u2 -r -- "Missing binary: $SOURCE_BINARY"
  exit 66
}
[[ -f "$SOURCE_SKILL" ]] || {
  print -u2 -r -- "Missing skill: $SOURCE_SKILL"
  exit 66
}
for required in kimmizo-desktop-entrypoint kimmizo-real-codex model-catalog.json model-policy.json model-policy.sha256 voice-bootstrap.json voice-bootstrap.sha256; do
  [[ -f "$SOURCE_ROOT/$required" ]] || {
    print -u2 -r -- "Missing runtime file: $required"
    exit 66
  }
done
[[ -f "$BUNDLE_DIR/BUNDLE-MANIFEST.sha256" ]] || {
  print -u2 -r -- "Missing BUNDLE-MANIFEST.sha256"
  exit 66
}
(cd "$BUNDLE_DIR" && /usr/bin/shasum -a 256 -c BUNDLE-MANIFEST.sha256 >/dev/null)

/bin/mkdir -p "$INSTALL_PARENT" "$HOME/Library/LaunchAgents" "$SKILL_DIR"
/bin/chmod 700 "$INSTALL_PARENT"

ACTIVE_CLI="$(/bin/launchctl getenv CODEX_CLI_PATH 2>/dev/null || true)"
if [[ -z "$ACTIVE_CLI" && -n "${CODEX_CLI_PATH:-}" ]]; then
  ACTIVE_CLI="$CODEX_CLI_PATH"
fi
ORIGINAL_ACTIVE_CLI="$ACTIVE_CLI"
MANAGED_EXISTING=0
PREVIOUS_CLI="$ACTIVE_CLI"

if [[ -f "$INSTALL_ROOT/install.json" ]]; then
  receipt_root="$(/usr/bin/plutil -extract installRoot raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
  receipt_label="$(/usr/bin/plutil -extract Label raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
  agent_label=""
  [[ ! -f "$LAUNCH_AGENT" ]] || agent_label="$(/usr/bin/plutil -extract Label raw -o - "$LAUNCH_AGENT" 2>/dev/null || true)"
  if [[ "$receipt_root" == "$INSTALL_ROOT" && "$receipt_label" == "$LABEL" && ( ! -f "$LAUNCH_AGENT" || "$agent_label" == "$LABEL" ) ]]; then
    MANAGED_EXISTING=1
    PREVIOUS_CLI="$(/usr/bin/plutil -extract previousCodexCliPath raw -o - "$INSTALL_ROOT/install.json" 2>/dev/null || true)"
  fi
fi

if [[ -n "$ACTIVE_CLI" && "$ACTIVE_CLI" != "$PROXY_PATH" && "$ACTIVE_CLI" != "$NATIVE_PROXY_PATH" ]]; then
  print -u2 -r -- "CODEX_CLI_PATH is controlled by another executable: $ACTIVE_CLI"
  print -u2 -r -- "Kimmizo did not change it. Remove that override first, then run this installer again."
  exit 73
fi
if [[ -e "$INSTALL_ROOT" && $MANAGED_EXISTING -ne 1 ]]; then
  print -u2 -r -- "Existing install root is not owned by this Kimmizo installer: $INSTALL_ROOT"
  exit 73
fi
if [[ -e "$LAUNCH_AGENT" && $MANAGED_EXISTING -ne 1 ]]; then
  print -u2 -r -- "Existing LaunchAgent is not owned by this Kimmizo installer: $LAUNCH_AGENT"
  exit 73
fi

if [[ -z "$REAL_CODEX" && $MANAGED_EXISTING -eq 1 && -f "$INSTALL_ROOT/real-codex-native.path" ]]; then
  REAL_CODEX="$(<"$INSTALL_ROOT/real-codex-native.path")"
elif [[ -z "$REAL_CODEX" && $MANAGED_EXISTING -eq 1 && -f "$INSTALL_ROOT/real-codex.path" ]]; then
  REAL_CODEX="$(<"$INSTALL_ROOT/real-codex.path")"
fi
if [[ -z "$REAL_CODEX" ]]; then
  discovered="$(command -v codex 2>/dev/null || true)"
  if [[ -n "$discovered" && "$discovered" != "$PROXY_PATH" && -f "$discovered" && -x "$discovered" ]]; then
    REAL_CODEX="$discovered"
  fi
fi
if [[ -z "$REAL_CODEX" ]]; then
  candidates=(
    "/Applications/Codex.app/Contents/Resources/codex"
    "/Applications/Codex.app/Contents/Resources/codex-cli"
    "$HOME/Applications/Codex.app/Contents/Resources/codex"
    "$HOME/Applications/Codex.app/Contents/Resources/codex-cli"
  )
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" && -x "$candidate" ]]; then
      REAL_CODEX="$candidate"
      break
    fi
  done
fi
if [[ -z "$REAL_CODEX" ]]; then
  resource_roots=(
    "/Applications/Codex.app/Contents/Resources"
    "$HOME/Applications/Codex.app/Contents/Resources"
  )
  for resource_root in "${resource_roots[@]}"; do
    [[ -d "$resource_root" ]] || continue
    while IFS= read -r candidate; do
      if [[ -f "$candidate" && -x "$candidate" ]]; then
        REAL_CODEX="$candidate"
        break 2
      fi
    done < <(/usr/bin/find "$resource_root" -type f \( -name codex -o -name codex-cli \) -perm -111 -print 2>/dev/null)
  done
fi
[[ -n "$REAL_CODEX" ]] || {
  print -u2 -r -- "Could not locate the real Codex executable."
  print -u2 -r -- "Run again with: ./install.sh --real-codex /absolute/path/to/codex"
  exit 66
}
[[ "$REAL_CODEX" == /* && -f "$REAL_CODEX" && -x "$REAL_CODEX" ]] || {
  print -u2 -r -- "The real Codex path must be an absolute executable file: $REAL_CODEX"
  exit 66
}
[[ "$REAL_CODEX" != "$SOURCE_BINARY" && "$REAL_CODEX" != "$PROXY_PATH" && "$REAL_CODEX" != "$NATIVE_PROXY_PATH" ]] || {
  print -u2 -r -- "The real Codex path points to Kimmizo itself."
  exit 66
}

STAGE_ROOT="$(/usr/bin/mktemp -d "$INSTALL_PARENT/.auto-stage.XXXXXX")"
ROOT_BACKUP="$INSTALL_PARENT/.auto-backup.$$.${RANDOM}"
AGENT_TEMP="$(/usr/bin/mktemp "$HOME/Library/LaunchAgents/.$LABEL.tmp.XXXXXX")"
AGENT_BACKUP="$HOME/Library/LaunchAgents/.$LABEL.backup.$$.${RANDOM}.plist"
SKILL_TEMP="$(/usr/bin/mktemp "$SKILL_DIR/.SKILL.md.tmp.XXXXXX")"
SKILL_BACKUP="$SKILL_DIR/.SKILL.md.backup.$$.${RANDOM}"
[[ ! -e "$ROOT_BACKUP" && ! -e "$AGENT_BACKUP" && ! -e "$SKILL_BACKUP" ]] || {
  /bin/rm -R "$STAGE_ROOT"
  /bin/rm -f "$AGENT_TEMP" "$SKILL_TEMP"
  print -u2 -r -- "Could not allocate safe backup paths."
  exit 73
}

SUCCESS=0
ROOT_REPLACED=0
ROOT_WAS_BACKED_UP=0
AGENT_WAS_BACKED_UP=0
NEW_AGENT_INSTALLED=0
SKILL_INSTALLED=0
SKILL_WAS_BACKED_UP=0

restore_launch_environment() {
  if [[ -n "$ORIGINAL_ACTIVE_CLI" ]]; then
    /bin/launchctl setenv CODEX_CLI_PATH "$ORIGINAL_ACTIVE_CLI" >/dev/null 2>&1 || true
  else
    /bin/launchctl unsetenv CODEX_CLI_PATH >/dev/null 2>&1 || true
  fi
}

rollback() {
  exit_code=$?
  set +e
  if (( SUCCESS == 0 )); then
    if (( NEW_AGENT_INSTALLED == 1 )); then
      /bin/launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
      [[ -f "$LAUNCH_AGENT" ]] && /bin/rm -f "$LAUNCH_AGENT"
    fi
    if (( AGENT_WAS_BACKED_UP == 1 )) && [[ -f "$AGENT_BACKUP" ]]; then
      /bin/mv "$AGENT_BACKUP" "$LAUNCH_AGENT"
      /bin/launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
    fi
    if (( SKILL_INSTALLED == 1 )) && [[ -f "$SKILL_TARGET" ]]; then
      /bin/rm -f "$SKILL_TARGET"
    fi
    if (( SKILL_WAS_BACKED_UP == 1 )) && [[ -f "$SKILL_BACKUP" ]]; then
      /bin/mv "$SKILL_BACKUP" "$SKILL_TARGET"
    fi
    if (( ROOT_REPLACED == 1 )) && [[ -d "$INSTALL_ROOT" ]]; then
      /bin/rm -R "$INSTALL_ROOT"
    fi
    if (( ROOT_WAS_BACKED_UP == 1 )) && [[ -d "$ROOT_BACKUP" ]]; then
      /bin/mv "$ROOT_BACKUP" "$INSTALL_ROOT"
    fi
    [[ -n "$STAGE_ROOT" && -d "$STAGE_ROOT" ]] && /bin/rm -R "$STAGE_ROOT"
    [[ -n "$AGENT_TEMP" && -f "$AGENT_TEMP" ]] && /bin/rm -f "$AGENT_TEMP"
    [[ -n "$SKILL_TEMP" && -f "$SKILL_TEMP" ]] && /bin/rm -f "$SKILL_TEMP"
    restore_launch_environment
    print -u2 -r -- "Kimmizo installation failed and completed rollback."
  fi
  return $exit_code
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

/bin/cp "$SOURCE_BINARY" "$STAGE_ROOT/kimmizo-auto"
/bin/cp "$SOURCE_ENTRYPOINT" "$STAGE_ROOT/kimmizo-desktop-entrypoint"
/bin/cp "$SOURCE_LAUNCHER" "$STAGE_ROOT/kimmizo-real-codex"
/bin/cp "$SOURCE_CATALOG" "$STAGE_ROOT/model-catalog.json"
/bin/cp "$SOURCE_ROOT/model-policy.json" "$STAGE_ROOT/model-policy.json"
/bin/cp "$SOURCE_ROOT/model-policy.sha256" "$STAGE_ROOT/model-policy.sha256"
/bin/cp "$SOURCE_ROOT/voice-bootstrap.json" "$STAGE_ROOT/voice-bootstrap.json"
/bin/cp "$SOURCE_ROOT/voice-bootstrap.sha256" "$STAGE_ROOT/voice-bootstrap.sha256"
/bin/cp "$BUNDLE_DIR/KIMMIZO_SECRETARY_PORTABLE_SPEC.md" "$STAGE_ROOT/KIMMIZO_SECRETARY_PORTABLE_SPEC.md"
/bin/cp "$SOURCE_SKILL" "$SKILL_TEMP"
/bin/chmod 644 "$SKILL_TEMP"
if [[ $MANAGED_EXISTING -eq 1 && -f "$INSTALL_ROOT/state.json" ]]; then
  /bin/cp "$INSTALL_ROOT/state.json" "$STAGE_ROOT/state.json"
fi
print -r -- "$REAL_CODEX" > "$STAGE_ROOT/real-codex-native.path"
print -r -- "$STAGE_ROOT/kimmizo-real-codex" > "$STAGE_ROOT/real-codex.path"
/bin/chmod 700 "$STAGE_ROOT" "$STAGE_ROOT/kimmizo-auto" "$STAGE_ROOT/kimmizo-desktop-entrypoint" "$STAGE_ROOT/kimmizo-real-codex"
/bin/chmod 600 "$STAGE_ROOT"/*.json "$STAGE_ROOT"/*.sha256 "$STAGE_ROOT/real-codex.path" "$STAGE_ROOT/real-codex-native.path" "$STAGE_ROOT/KIMMIZO_SECRETARY_PORTABLE_SPEC.md"
/usr/bin/xattr -d com.apple.quarantine "$STAGE_ROOT/kimmizo-auto" >/dev/null 2>&1 || true

RECEIPT="$STAGE_ROOT/install.json"
/usr/bin/plutil -create xml1 "$RECEIPT"
/usr/bin/plutil -insert schemaVersion -integer 1 "$RECEIPT"
/usr/bin/plutil -insert nameConfigured -bool NO "$RECEIPT"
/usr/bin/plutil -insert Label -string "$LABEL" "$RECEIPT"
/usr/bin/plutil -insert installRoot -string "$INSTALL_ROOT" "$RECEIPT"
/usr/bin/plutil -insert proxyPath -string "$PROXY_PATH" "$RECEIPT"
/usr/bin/plutil -insert skillPath -string "$SKILL_TARGET" "$RECEIPT"
/usr/bin/plutil -insert skillSha256 -string "$(/usr/bin/shasum -a 256 "$SOURCE_SKILL" | /usr/bin/awk '{print $1}')" "$RECEIPT"
/usr/bin/plutil -insert previousCodexCliPath -string "$PREVIOUS_CLI" "$RECEIPT"
/usr/bin/plutil -insert installedAtUtc -string "$(/bin/date -u +'%Y-%m-%dT%H:%M:%SZ')" "$RECEIPT"
/usr/bin/plutil -convert json "$RECEIPT"
/bin/chmod 600 "$RECEIPT"

ATHENA_HOME="$STAGE_ROOT" "$STAGE_ROOT/kimmizo-auto" --athena-self-test >/dev/null
print -r -- "$INSTALL_ROOT/kimmizo-real-codex" > "$STAGE_ROOT/real-codex.path"

/usr/bin/plutil -create xml1 "$AGENT_TEMP"
/usr/bin/plutil -insert Label -string "$LABEL" "$AGENT_TEMP"
/usr/bin/plutil -insert ProgramArguments -array "$AGENT_TEMP"
/usr/bin/plutil -insert ProgramArguments.0 -string "/bin/launchctl" "$AGENT_TEMP"
/usr/bin/plutil -insert ProgramArguments.1 -string "setenv" "$AGENT_TEMP"
/usr/bin/plutil -insert ProgramArguments.2 -string "CODEX_CLI_PATH" "$AGENT_TEMP"
/usr/bin/plutil -insert ProgramArguments.3 -string "$PROXY_PATH" "$AGENT_TEMP"
/usr/bin/plutil -insert RunAtLoad -bool YES "$AGENT_TEMP"
/bin/chmod 600 "$AGENT_TEMP"
/usr/bin/plutil -lint "$AGENT_TEMP" >/dev/null

if [[ -f "$LAUNCH_AGENT" ]]; then
  /bin/cp "$LAUNCH_AGENT" "$AGENT_BACKUP"
  AGENT_WAS_BACKED_UP=1
  /bin/launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
fi
if [[ -f "$SKILL_TARGET" ]]; then
  /bin/cp "$SKILL_TARGET" "$SKILL_BACKUP"
  SKILL_WAS_BACKED_UP=1
fi
if [[ -d "$INSTALL_ROOT" ]]; then
  /bin/mv "$INSTALL_ROOT" "$ROOT_BACKUP"
  ROOT_WAS_BACKED_UP=1
fi
/bin/mv "$STAGE_ROOT" "$INSTALL_ROOT"
ROOT_REPLACED=1
/bin/mv "$AGENT_TEMP" "$LAUNCH_AGENT"
NEW_AGENT_INSTALLED=1
/bin/mv "$SKILL_TEMP" "$SKILL_TARGET"
SKILL_INSTALLED=1
/bin/launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT" >/dev/null 2>&1 || true
/bin/launchctl setenv CODEX_CLI_PATH "$PROXY_PATH"
[[ "$(/bin/launchctl getenv CODEX_CLI_PATH 2>/dev/null || true)" == "$PROXY_PATH" ]] || {
  print -u2 -r -- "Could not activate CODEX_CLI_PATH for the current GUI session."
  exit 1
}

if [[ "$DEFAULT_AUTO" == "on" ]]; then
  "$NATIVE_PROXY_PATH" --athena-default-auto-on >/dev/null
else
  "$NATIVE_PROXY_PATH" --athena-default-auto-off >/dev/null
fi
"$NATIVE_PROXY_PATH" --athena-self-test >/dev/null

SUCCESS=1
trap - EXIT INT TERM
[[ -d "$ROOT_BACKUP" ]] && /bin/rm -R "$ROOT_BACKUP" || true
[[ -f "$AGENT_BACKUP" ]] && /bin/rm -f "$AGENT_BACKUP" || true
[[ -f "$SKILL_BACKUP" ]] && /bin/rm -f "$SKILL_BACKUP" || true

print -r -- "PASS: Kimmizo Auto installed at $INSTALL_ROOT"
print -r -- "CODEX_CLI_PATH=$PROXY_PATH"
print -r -- "Quit Codex completely with Command-Q, reopen it, then select ✦ Auto."
print -r -- "Run ./status.sh after reopening Codex."

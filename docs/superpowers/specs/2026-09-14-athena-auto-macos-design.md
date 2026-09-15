# Athena Auto for macOS Design

**Date:** 2026-09-14  
**Status:** Proposed for final user review  
**Target:** Codex Desktop on macOS Apple Silicon (`darwin/arm64`)  
**Distribution:** new self-contained folder `ATHENA_MAC_COMPLETE_BUNDLE`

## Goal

Create a new self-contained `ATHENA_MAC_COMPLETE_BUNDLE` containing the Athena persona and a portable native `athena-auto` model router so that Codex Desktop on an Apple Silicon Mac can display `✦ Auto`, route each task to an available Codex model and reasoning effort, and be installed or removed with one command without copying secrets or requiring a language runtime.

## Context

The existing Windows Auto feature is not a prompt or an official OpenAI model. It is a Windows-specific JSON-RPC proxy compiled from `KimmizoCodexAuto.cs`, activated through `CODEX_CLI_PATH`, and coupled to PowerShell, .NET Framework, Windows paths, Authenticode, and the signed Windows Codex runtime bundle. The current `ATHENA_SECRETARY_BUNDLE` installs only the persona specification, so it cannot expose or execute Auto routing on macOS.

The macOS implementation will be independent of the Windows binary and installer. It will reuse the behavioral contract and policy concepts, not Windows runtime-management code. It will also be independent of `ATHENA_SECRETARY_BUNDLE`; that existing folder will remain unchanged.

## Chosen Approach

Build a small native Go proxy and cross-compile it to `darwin/arm64`. The proxy will run the real Codex CLI as a child process. For `app-server` mode it will transparently proxy newline-delimited JSON-RPC, advertise a virtual `athena-auto` model, and rewrite Auto requests to a verified model and reasoning effort selected from the real runtime catalog.

Go is chosen because it produces a single native executable with no Python, Node, .NET, Homebrew, or Xcode runtime requirement. A catalog-only solution is rejected because it can display a model name but cannot perform routing. A Python proxy is rejected because modern macOS installations do not guarantee a usable system Python.

## Components

### Native proxy

The proxy will live under `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/` and expose:

- normal CLI passthrough for non-`app-server` invocations;
- bidirectional JSON-RPC line proxying for `app-server`;
- virtual model id `athena-auto`;
- display name `✦ Auto`;
- description `ปรับโมเดลตามช่วงงาน`;
- `--athena-self-test`, `--athena-status`, `--athena-default-auto-on`, and `--athena-default-auto-off` commands;
- process exit-code and signal forwarding;
- state writes using atomic temporary-file replacement;
- no prompt or response persistence.

The proxy will receive the real Codex path from its verified installation record. It will remove `CODEX_CLI_PATH` from the child environment to prevent recursive launch.

### Routing policy

Routing policy will be stored as versioned JSON plus a SHA-256 sidecar. The proxy will verify the policy before routing. It will select only models and reasoning efforts observed in the real Codex `model/list` response.

The initial tiers are:

- fast: short summaries, translation, simple inspection;
- balanced: ordinary implementation and project work;
- deep: architecture, debugging, review, or multi-step analysis;
- critical: security, database, production, destructive, or high-impact work;
- ultra: broad multi-agent or exceptionally expensive work, requiring explicit approval before escalation.

Policy entries define ordered model preferences and allowed reasoning efforts. If a preferred model is absent, routing falls back to the next verified candidate. If no safe candidate exists, the request fails closed with a concise error instead of inventing a model id.

### Athena voice bootstrap

The bundle will include a signed-by-hash local voice bootstrap using the trigger `อาเทน่า`. It will require Thai responses, first-person pronoun `ฉัน`, and polite ending `ค่ะ` when the user invokes Athena. The proxy will verify this sidecar before starting a secretary-triggered turn. It will not store the triggering prompt.

### Installer

`install-athena-auto.sh` will:

1. require macOS and `arm64`;
2. verify bundled file hashes before installation;
3. locate the real Codex CLI from an explicit `--real-codex` argument, an existing non-Athena `CODEX_CLI_PATH`, `command -v codex`, or known Codex application-bundle candidates;
4. reject a missing, non-executable, recursive, or Athena-owned real CLI candidate;
5. install under `~/.athena-secretary/auto/` without `sudo`;
6. save a non-secret installation record and the previous `CODEX_CLI_PATH` value;
7. run offline self-test and real CLI version passthrough before activation;
8. set the current login-session environment with `launchctl setenv CODEX_CLI_PATH <proxy>`;
9. install a user LaunchAgent so Finder-launched Codex inherits the variable after login;
10. report that Codex Desktop must be fully quit and reopened.

If another tool already controls `CODEX_CLI_PATH`, the installer will stop without changing it unless the existing value is the currently managed Athena installation. Reinstallation will be idempotent.

### Status and uninstall

`athena-auto-status.sh` will verify binary presence, policy/voice hashes, installation ownership, saved real CLI path, executable status, current `launchctl` value, LaunchAgent state, self-test, and passthrough version.

`uninstall-athena-auto.sh` will unload and remove only the Athena LaunchAgent, restore the exact previous `CODEX_CLI_PATH` when Athena still owns the active value, and preserve unrelated user configuration. It will retain a small uninstall receipt unless the user explicitly requests complete removal.

## Files

Planned additions and updates:

- `ATHENA_MAC_COMPLETE_BUNDLE/ATHENA_SECRETARY_PORTABLE_SPEC.md`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/go.mod`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/cmd/athena-auto/main.go`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/proxy/*`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/policy/*`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/state/*`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/**/*_test.go`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/model-policy.json`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/model-policy.sha256`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/voice-bootstrap.json`
- `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/voice-bootstrap.sha256`
- `ATHENA_MAC_COMPLETE_BUNDLE/install.sh`
- `ATHENA_MAC_COMPLETE_BUNDLE/status.sh`
- `ATHENA_MAC_COMPLETE_BUNDLE/uninstall.sh`
- `ATHENA_MAC_COMPLETE_BUNDLE/bin/darwin-arm64/athena-auto`
- `ATHENA_MAC_COMPLETE_BUNDLE/STEP_BY_STEP_MAC.md`
- `ATHENA_MAC_COMPLETE_BUNDLE/README.md`
- `ATHENA_MAC_COMPLETE_BUNDLE/BUNDLE-MANIFEST.sha256`
- focused Go and installer tests under the repository `tests/` directory where practical.

## Data Flow

1. Codex Desktop launches the configured Athena proxy.
2. The proxy loads and verifies the installation record, routing policy, and voice bootstrap.
3. The proxy starts the recorded real Codex CLI with `CODEX_CLI_PATH` removed from the child environment.
4. `model/list` is forwarded to the real CLI; its response seeds the verified runtime catalog and receives one virtual `athena-auto` entry.
5. When a thread or turn selects `athena-auto`, the proxy classifies the in-memory task text and rewrites the request to a model/effort supported by the observed catalog.
6. The real response is rewritten only where needed so the desktop continues to display `athena-auto` for that thread.
7. State stores thread ids, selected tiers/models, approval flags, and verification metadata only. Prompt and response bodies are never written.

## Safety and Failure Handling

- Fail closed when policy, voice, installation record, real CLI, or catalog verification fails.
- Never copy authentication files, API keys, ChatGPT tokens, `.env`, or Codex session databases.
- Never require `sudo` or write outside the user's home directory.
- Never overwrite a third-party `CODEX_CLI_PATH` silently.
- Never claim a Mac installation succeeded solely from Windows cross-build results.
- Preserve the previous environment value and provide deterministic uninstall.
- Log diagnostics to stderr without prompt contents or credentials.
- Bound JSON line size and reject malformed control messages while passing unrelated lines through safely.

## Testing

### Host-independent tests

- policy hash verification and tamper rejection;
- model/effort selection from observed catalogs;
- tier classification and phase escalation/reset;
- explicit Ultra approval behavior;
- virtual model insertion without duplication;
- request rewrite and response display rewrite;
- prompt non-persistence;
- atomic state behavior;
- recursion prevention and child environment filtering;
- malformed JSON and oversized-line behavior.

### Build verification

- `go test ./...` on the development host;
- `GOOS=darwin GOARCH=arm64 go build` producing a Mach-O arm64 executable;
- inspect the binary format and SHA-256;
- shell syntax checks for install/status/uninstall scripts;
- bundle manifest verification.

### Mac acceptance verification

The Mac user will run one installer command. Acceptance requires:

- installer exit code `0`;
- `athena-auto --athena-self-test` reports `passed`;
- status reports policy and voice verified, real CLI executable, and active `CODEX_CLI_PATH` owned by Athena;
- Codex Desktop fully quits and reopens;
- `✦ Auto` appears in the model selector;
- a fast prompt and a deep prompt produce different verified routes in status without storing prompt text;
- uninstall restores the prior environment and Codex launches normally.

## Non-goals

- Modifying or replacing the official Codex model service.
- Circumventing account model availability, rate limits, permissions, or admin policy.
- Copying the Windows Codex runtime or Windows executable to macOS.
- Installing Homebrew, Xcode, Docker, Node, Python, or .NET.
- Guaranteeing that models unavailable to the signed-in account can be selected.
- Changing the existing Windows Kimmizo Auto implementation.

## Delivery Constraint

The native binary can be cross-built and structurally verified on Windows, but final integration with Codex Desktop must be validated on the target Mac. The installer therefore remains fail-closed and reversible, and its final report distinguishes cross-build success from live Mac acceptance.

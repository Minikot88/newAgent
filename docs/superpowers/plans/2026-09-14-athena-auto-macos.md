# Athena Auto for macOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new self-contained `ATHENA_MAC_COMPLETE_BUNDLE` with a native `darwin/arm64` Auto model router, reversible installer, status/uninstall tools, persona, and Mac instructions.

**Architecture:** A standard-library-only Go executable proxies Codex app-server JSON-RPC, inserts the virtual `athena-auto` catalog entry, and rewrites Auto requests to routes verified against the real model catalog. User-scoped zsh installers activate the proxy through `launchctl` and a reversible LaunchAgent while preserving the previous `CODEX_CLI_PATH` value.

**Tech Stack:** Go 1.24+, newline-delimited JSON-RPC, zsh, launchctl/LaunchAgents, PowerShell host-side packaging checks, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-14-athena-auto-macos-design.md`

## Global Constraints

- Target operating system and architecture are exactly `darwin/arm64`.
- The delivered executable has no Python, Node, .NET, Homebrew, or Xcode runtime dependency.
- The implementation never stores prompt or response bodies.
- The implementation never copies credentials, authentication databases, private keys, `.env`, or tokens.
- Routing uses only model ids and efforts observed from the real Codex `model/list` response.
- Missing or invalid policy, voice bootstrap, real CLI, or verified catalog causes fail-closed behavior.
- Installation is user-scoped, uses no `sudo`, preserves the previous `CODEX_CLI_PATH`, and is reversibly uninstallable.
- `ATHENA_SECRETARY_BUNDLE` and the Windows Kimmizo Auto implementation remain unchanged.
- Cross-build success is not presented as live Mac acceptance.

---

### Task 1: Create the independent bundle and verified policy assets

**Files:**
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/ATHENA_SECRETARY_PORTABLE_SPEC.md`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/go.mod`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/model-policy.json`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/model-policy.sha256`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/voice-bootstrap.json`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/voice-bootstrap.sha256`
- Test: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/policy/policy_test.go`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/policy/policy.go`

**Interfaces:**
- Produces: `policy.LoadVerified(policyPath, hashPath string) (Policy, error)`
- Produces: `policy.LoadVoiceVerified(voicePath, hashPath string) (Voice, error)`
- Produces: `Policy.Choose(task string, catalog Catalog, ultraApproved bool) (Route, error)`

- [ ] **Step 1: Create the Go module and copy the portable persona into the new bundle**

Use module declaration:

```go
module athena-auto

go 1.24
```

Copy the existing persona text as an independent file, replacing no files in `ATHENA_SECRETARY_BUNDLE`.

- [ ] **Step 2: Write failing policy verification and routing tests**

```go
func TestLoadVerifiedRejectsTamperedPolicy(t *testing.T) {
    policyPath, hashPath := writePolicyFixture(t)
    os.WriteFile(policyPath, []byte(`{"schema_version":1}`), 0o600)
    if _, err := LoadVerified(policyPath, hashPath); err == nil {
        t.Fatal("tampered policy was accepted")
    }
}

func TestChooseUsesOnlyObservedModelAndEffort(t *testing.T) {
    p := fixturePolicy(t)
    route, err := p.Choose("วิเคราะห์ architecture และ root cause", Catalog{
        Models: map[string][]string{"gpt-5.6-sol": {"high", "xhigh"}},
    }, false)
    if err != nil { t.Fatal(err) }
    if route.Model != "gpt-5.6-sol" || route.Effort != "high" {
        t.Fatalf("unexpected route: %#v", route)
    }
}
```

- [ ] **Step 3: Run the policy tests and verify RED**

Run:

```powershell
go test ./internal/policy -run 'TestLoadVerifiedRejectsTamperedPolicy|TestChooseUsesOnlyObservedModelAndEffort' -v
```

Expected: compilation fails because `LoadVerified`, `Policy`, `Catalog`, and `Choose` do not exist.

- [ ] **Step 4: Implement minimal hash verification, typed policy loading, tier classification, and verified fallback selection**

Core signatures:

```go
type Route struct { Tier, Model, Effort string; RequiresApproval bool }
type Catalog struct { Models map[string][]string; DefaultModel string }
type Policy struct { SchemaVersion int `json:"schema_version"`; Routes map[string]RoutePolicy `json:"routes"` }

func LoadVerified(path, hashPath string) (Policy, error) {
    raw, err := os.ReadFile(path)
    if err != nil { return Policy{}, err }
    expectedRaw, err := os.ReadFile(hashPath)
    if err != nil { return Policy{}, err }
    actual := fmt.Sprintf("%x", sha256.Sum256(raw))
    if !strings.EqualFold(strings.TrimSpace(string(expectedRaw)), actual) {
        return Policy{}, errors.New("policy SHA-256 mismatch")
    }
    var p Policy
    if err := json.Unmarshal(raw, &p); err != nil { return Policy{}, err }
    if p.SchemaVersion != 1 { return Policy{}, errors.New("unsupported policy schema") }
    return p, nil
}
```

- [ ] **Step 5: Run all policy tests and verify GREEN**

Run `go test ./internal/policy -v`.

Expected: all tests pass with exit code `0`.

### Task 2: Implement prompt-free state and phase routing

**Files:**
- Test: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/state/state_test.go`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/state/state.go`

**Interfaces:**
- Produces: `state.Load(path string) (*Store, error)`
- Produces: `(*Store).SetRoute(threadID string, route policy.Route) error`
- Produces: `(*Store).Route(threadID string) (policy.Route, bool)`
- Produces: `(*Store).SetDefaultAuto(enabled bool) error`

- [ ] **Step 1: Write failing tests proving prompts are absent and writes are atomic**

```go
func TestStateNeverSerializesPromptText(t *testing.T) {
    path := filepath.Join(t.TempDir(), "state.json")
    store, _ := Load(path)
    err := store.SetRoute("thread-1", policy.Route{Tier:"deep", Model:"gpt-5.6-sol", Effort:"high"})
    if err != nil { t.Fatal(err) }
    raw, _ := os.ReadFile(path)
    if bytes.Contains(raw, []byte("prompt")) || bytes.Contains(raw, []byte("taskText")) {
        t.Fatalf("state contains prompt fields: %s", raw)
    }
}
```

- [ ] **Step 2: Run the state test and verify RED**

Run `go test ./internal/state -v`.

Expected: compilation fails because `Load` and `Store` do not exist.

- [ ] **Step 3: Implement a mutex-protected metadata-only store with temp-file rename**

Persist only schema version, default Auto preference, Auto thread ids, secretary thread ids, approval flags, last routes, and verification timestamps. Write to `state.json.tmp-<pid>` with mode `0600`, `Sync`, close, then `Rename`.

- [ ] **Step 4: Run the state tests and verify GREEN**

Run `go test ./internal/state -v`.

Expected: all tests pass and temporary files are cleaned.

### Task 3: Implement JSON-RPC transformations

**Files:**
- Test: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/proxy/transform_test.go`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/proxy/transform.go`

**Interfaces:**
- Consumes: `policy.Policy`, `policy.Catalog`, and `state.Store`
- Produces: `proxy.NewTransformer(...) *Transformer`
- Produces: `(*Transformer).ClientLine([]byte) (forward []byte, immediate []byte, err error)`
- Produces: `(*Transformer).ServerLine([]byte) ([]byte, error)`

- [ ] **Step 1: Write failing tests for model insertion and Auto request rewriting**

```go
func TestModelListAddsAthenaAutoOnce(t *testing.T) {
    tr := newFixtureTransformer(t)
    tr.ClientLine([]byte(`{"id":1,"method":"model/list","params":{}}`))
    got, err := tr.ServerLine([]byte(`{"id":1,"result":{"data":[{"id":"gpt-5.6-sol","supportedReasoningEfforts":["high"]}]}}`))
    if err != nil { t.Fatal(err) }
    if bytes.Count(got, []byte(`"athena-auto"`)) != 2 {
        t.Fatalf("virtual model not inserted exactly once: %s", got)
    }
}

func TestTurnStartRoutesAutoWithoutPersistingPrompt(t *testing.T) {
    tr := newFixtureTransformer(t)
    input := []byte(`{"id":2,"method":"turn/start","params":{"threadId":"t1","model":"athena-auto","input":[{"type":"text","text":"วิเคราะห์ architecture และ root cause"}]}}`)
    forward, _, err := tr.ClientLine(input)
    if err != nil { t.Fatal(err) }
    if !bytes.Contains(forward, []byte(`"model":"gpt-5.6-sol"`)) { t.Fatalf("not routed: %s", forward) }
    stateRaw := readState(t, tr)
    if bytes.Contains(stateRaw, []byte("root cause")) { t.Fatal("prompt was persisted") }
}
```

- [ ] **Step 2: Run transformer tests and verify RED**

Run `go test ./internal/proxy -run 'TestModelListAddsAthenaAutoOnce|TestTurnStartRoutesAutoWithoutPersistingPrompt' -v`.

Expected: compilation fails because `Transformer` does not exist.

- [ ] **Step 3: Implement pending request correlation and catalog capture**

Support `model/list`, `config/read`, `config/value/write`, `config/batchWrite`, `thread/start`, `thread/read`, `thread/resume`, `thread/list`, and `turn/start`. Use `json.RawMessage` to preserve unknown fields and correlate responses by normalized JSON-RPC id.

- [ ] **Step 4: Implement virtual display rewriting and fail-closed errors**

Use JSON-RPC errors with stable private codes:

```go
const (
    codeVoiceUnverified = -32071
    codeModelUnverified = -32072
    codeContextInvalid  = -32073
)
```

Add `athena-auto` only to the first model page. Rewrite displayed thread/config model values back to `athena-auto` only for threads owned by Auto.

- [ ] **Step 5: Add malformed JSON, duplicate model, Ultra approval, phase escalation, and prompt non-persistence tests**

Each test must assert output behavior and inspect the serialized state file for absence of prompt text.

- [ ] **Step 6: Run transformer tests and verify GREEN**

Run `go test ./internal/proxy -v`.

Expected: all tests pass.

### Task 4: Build the process proxy and control commands

**Files:**
- Test: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/proxy/process_test.go`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/internal/proxy/process.go`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/athena-auto-macos/cmd/athena-auto/main.go`

**Interfaces:**
- Produces executable commands: passthrough, `app-server`, `--athena-self-test`, `--athena-status`, `--athena-default-auto-on`, `--athena-default-auto-off`

- [ ] **Step 1: Write a failing helper-process test for child environment filtering and exit propagation**

```go
func TestRunChildRemovesCodexCLIPathAndPropagatesExit(t *testing.T) {
    t.Setenv("CODEX_CLI_PATH", "/tmp/athena-auto")
    code, observed := runHelperChild(t, 23)
    if code != 23 { t.Fatalf("exit=%d", code) }
    if observed["CODEX_CLI_PATH"] != "" { t.Fatal("recursive environment leaked") }
}
```

- [ ] **Step 2: Run process tests and verify RED**

Run `go test ./internal/proxy -run TestRunChildRemovesCodexCLIPathAndPropagatesExit -v`.

Expected: compilation fails because process runner does not exist.

- [ ] **Step 3: Implement child execution and line proxying**

Use `exec.Command`, explicit environment filtering, `io.Pipe`, `bufio.Reader` with a configured maximum line size, goroutines for stdout/stderr, and signal forwarding for `os.Interrupt` and `SIGTERM`.

- [ ] **Step 4: Implement main command parsing and machine-readable status/self-test JSON**

Status must include `virtualModel`, `displayName`, `storesPrompts:false`, policy/voice verification, real CLI status, default Auto state, and overall `ready|degraded` status without sensitive environment dumps.

- [ ] **Step 5: Run the complete Go suite and verify GREEN**

Run `go test ./... -race` on a native supported Go host and `go test ./...` on Windows if the race detector cannot run there.

Expected: all tests pass.

### Task 5: Implement reversible macOS installation

**Files:**
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/install.sh`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/status.sh`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/uninstall.sh`
- Test: `tests/test_athena_auto_macos_bundle.ps1`

**Interfaces:**
- Consumes: `bin/darwin-arm64/athena-auto` and verified policy/voice assets
- Produces: user install at `~/.athena-secretary/auto/`
- Produces: LaunchAgent `~/Library/LaunchAgents/com.kimmizo.athena-auto.plist`

- [ ] **Step 1: Write failing structural tests for safe installer contracts**

```powershell
$install = Get-Content -Raw "$Bundle/install.sh"
$install | Should -Match 'uname -s'
$install | Should -Match 'uname -m'
$install | Should -Match 'launchctl setenv CODEX_CLI_PATH'
$install | Should -Match 'previousCodexCliPath'
$install | Should -Not -Match '\bsudo\b'
$install | Should -Not -Match 'auth\.json|\.env|token|private.key'
```

- [ ] **Step 2: Run installer structural tests and verify RED**

Run:

```powershell
pwsh -NoProfile -File tests/test_athena_auto_macos_bundle.ps1
```

The test file uses a local `Assert-True` helper, writes failures to stderr, and exits `1` when any assertion fails so it requires no Pester dependency.

Expected: failures because installer scripts do not exist.

- [ ] **Step 3: Implement `install.sh` with discovery, preflight, backup, activation, and rollback trap**

The script accepts `--real-codex <absolute-path>`. Discovery order is explicit argument, existing non-Athena `CODEX_CLI_PATH`, `command -v codex`, then a fixed allowlist of executable candidates under `/Applications/Codex.app` and `~/Applications/Codex.app`. The script writes a mode-`0600` JSON receipt, generates a mode-`0600` LaunchAgent plist, loads it, sets the current launchctl environment, and rolls back every completed step if validation fails.

- [ ] **Step 4: Implement `status.sh` and `uninstall.sh`**

`status.sh` calls the proxy status and verifies launchctl/LaunchAgent ownership. `uninstall.sh` restores the exact saved value only when the current value still points to the Athena proxy; otherwise it leaves the external value unchanged and reports the divergence.

- [ ] **Step 5: Run structural tests and verify GREEN**

Run `pwsh -NoProfile -File tests/test_athena_auto_macos_bundle.ps1`.

Expected: all safety-contract assertions pass.

### Task 6: Cross-build the native Mac binary and assemble hashes

**Files:**
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/bin/darwin-arm64/athena-auto`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/BUNDLE-MANIFEST.sha256`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/BUILD-RECEIPT.json`

**Interfaces:**
- Consumes: completed Go source and tests
- Produces: executable Mach-O arm64 artifact and verifiable distribution manifest

- [ ] **Step 1: Install a pinned Go toolchain on the build host after explicit approval**

The current Windows host has no Go compiler. Download or install a pinned official Go release only after the environment requests and receives network/write approval. Record version and installer SHA-256 in the build receipt.

- [ ] **Step 2: Run all tests using the pinned toolchain**

Run:

```powershell
go test ./...
```

Expected: exit code `0` and no failed packages.

- [ ] **Step 3: Cross-compile deterministically for Apple Silicon**

Run:

```powershell
$env:CGO_ENABLED='0'
$env:GOOS='darwin'
$env:GOARCH='arm64'
go build -trimpath -ldflags='-s -w' -o ..\bin\darwin-arm64\athena-auto .\cmd\athena-auto
```

Expected: exit code `0` and a non-empty output binary.

- [ ] **Step 4: Inspect and hash the binary and every distributed control file**

Verify the Mach-O arm64 magic from the binary header, calculate SHA-256 values, and write sorted relative-path entries to `BUNDLE-MANIFEST.sha256`. Do not include the manifest itself.

- [ ] **Step 5: Re-run tests after packaging**

Run Go tests plus installer structural tests again.

Expected: all pass.

### Task 7: Write one-command Mac guidance and final verification prompt

**Files:**
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/README.md`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/STEP_BY_STEP_MAC.md`
- Create: `ATHENA_MAC_COMPLETE_BUNDLE/VERIFY_ON_MAC.md`

**Interfaces:**
- Produces: copy-and-paste installation command and live Mac acceptance checklist

- [ ] **Step 1: Document the exact install command**

```zsh
cd ~/Desktop/Codex/ATHENA_MAC_COMPLETE_BUNDLE
chmod +x install.sh status.sh uninstall.sh
./install.sh
```

- [ ] **Step 2: Document restart and status verification**

Require the user to fully quit Codex with `Command-Q`, reopen it, select `✦ Auto`, and run `./status.sh`. Explicitly distinguish build-host verification from live Mac acceptance.

- [ ] **Step 3: Document deterministic rollback**

```zsh
cd ~/Desktop/Codex/ATHENA_MAC_COMPLETE_BUNDLE
./uninstall.sh
```

Explain that uninstall restores the saved prior `CODEX_CLI_PATH` only if Athena still owns the active value.

- [ ] **Step 4: Run documentation and bundle consistency checks**

Verify every referenced file exists, every command uses the new folder name, no documentation tells users to copy secrets, and no reference points to `ATHENA_SECRETARY_BUNDLE` except the explicit non-modification statement.

### Task 8: Final evidence and handoff

**Files:**
- Modify: `ATHENA_MAC_COMPLETE_BUNDLE/BUILD-RECEIPT.json`

**Interfaces:**
- Produces: final Windows build evidence and Mac acceptance instructions

- [ ] **Step 1: Run the full fresh verification suite**

Run all Go tests, installer safety tests, hash verification, Mach-O inspection, and documentation consistency checks in one recorded pass.

- [ ] **Step 2: Inspect Git status and diff scope**

Confirm only the new bundle, design/plan documents, and explicitly intended test files are part of this work. Do not stage or modify unrelated dirty files.

- [ ] **Step 3: Report the cross-build result without claiming Mac acceptance**

Provide the bundle path, test counts, binary SHA-256, known limitation, and the one Mac command. Final acceptance remains pending until the user returns the Mac `status.sh` output and confirms `✦ Auto` appears.

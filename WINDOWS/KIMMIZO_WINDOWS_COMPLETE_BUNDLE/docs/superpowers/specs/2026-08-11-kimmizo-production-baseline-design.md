# Kimmizo Production Baseline Design

**Status:** Approved  
**Date:** 2026-08-11  
**Target:** `D:\git\kimmizo_setup`

## Context

Kimmizo Setup already provides a Thai secretary persona, project-local custom agents, capability routing, memory, checkpoints, an approval gate, reversible capability installation, and a Windows Codex Auto host extension. The repository validator passes, but the current workstation exposes a `py.exe` launcher without an installed Python interpreter. The installer currently treats the launcher's presence as sufficient, so test and setup commands can fail after prerequisite detection has reported success. The bundled Codex Python runtime can run the dependency-free validator but does not contain pytest.

The production baseline must harden the installer first and then use that hardened installer to deploy Kimmizo into this repository. Readiness must be supported by repeatable evidence, not inferred from a single successful command.

## Goals

1. Make prerequisite detection prove that a usable Python 3.11 or newer interpreter can execute Kimmizo.
2. Preserve the existing project, managed-block, identity, approval, integrity, and rollback contracts.
3. Run the repository's validation and test suite with a supported development interpreter.
4. Install the Kimmizo project capsule and baseline capabilities into `D:\git\kimmizo_setup`.
5. Install and verify the reversible Kimmizo Auto extension when its signed Windows prerequisites are available.
6. Produce explicit evidence for dry-run safety, setup, doctor, idempotency, repair, Auto integrity, rollback, and secret hygiene.

## Non-goals

- Automatically authorizing connectors, authentication, MCP servers, hooks, sandbox expansion, or external writes.
- Installing every registry capability regardless of project need.
- Storing prompts, responses, credentials, tokens, images, files, telemetry, vectors, or cross-project memory.
- Modifying signed Codex Desktop files, patching its renderer/model picker, or writing the virtual Auto model to `config.toml`.
- Guaranteeing that no future defect can exist. “100% ready” means every acceptance check in this document passes in the target environment.

## Architecture

The work has two ordered phases:

```text
Repository audit
  -> installer/runtime hardening
  -> static validation and regression tests
  -> target dry-run
  -> project capsule and core capability installation
  -> Kimmizo Auto installation/integrity verification
  -> doctor, idempotency, repair, and rollback exercises
  -> readiness report
```

Phase 2 must not begin until Phase 1 validation and regression tests pass. This prevents an installer with a known prerequisite-detection defect from mutating the target environment.

## Components and Responsibilities

### PowerShell entry point

`install.ps1` owns workstation prerequisite discovery and orchestration. Python resolution must test execution and version, not command presence alone. An unusable `py` launcher is treated as missing. Normal setup may install the locked Python 3.13 prerequisite through the signed winget source; dry-run must report the missing prerequisite without changing the machine. The resolved command and required launcher arguments are passed consistently to every Kimmizo invocation.

The entry point continues to own optional local marketplace registration and Kimmizo Auto install/status/uninstall orchestration. Existing switches remain backward compatible.

### Python setup engine

`plugins/kimmizo-setup/scripts/kimmizo.py` remains the source of truth for project inspection, doctor results, routing, managed blocks, team identity/profile lifecycle, memory, checkpoints, capability approvals, receipts, installation, repair, and rollback. Changes are limited to behavior required by the production baseline and must follow existing safe-path, atomic-write, redaction, and allowlist patterns.

### Registry and baseline lock

`capabilities.json`, `baseline-lock.json`, and `conflicts.json` define detectable capabilities, approved installation sources/integrity, and conflict policy. Automatic installation is restricted to exact locked entries with no new authority. Capabilities requiring authentication, MCP, hooks, new permissions, sandbox expansion, or external writes remain `approval_required` until the Codex host already reports the exact package installed and enabled and Kimmizo records a matching approval fingerprint.

### Project capsule

The generated `AGENTS.md`, `.codex/config.toml`, `.codex/agents`, `.agents/skills/kimmizo-*`, and `.kimmizo` state are merged into the current repository. Project-owned text outside managed blocks is preserved. Agent names and IDs remain stable across repeated setup. Machine-local memory, runtime state, approvals, receipts, and backups remain ignored by Git.

### Kimmizo Auto

The Windows extension may set the user-scoped `CODEX_CLI_PATH` only when the variable is empty or already controlled by Kimmizo. Installation records the prior value. The runtime sync accepts only a complete Codex runtime bundle whose files pass Authenticode and SHA256 checks, performs single-writer transactional replacement, and retains the last verified bundle after a failed or locked update. Status, self-test, and uninstall remain available.

## Data Flow

1. Preflight resolves a functioning interpreter and other host prerequisites.
2. Doctor combines the user and project Codex configuration, active host plugin inventory, registry metadata, lock entries, conflict rules, and project detection.
3. Setup creates or merges the capsule, selects project-relevant capabilities, and writes sanitized project-local receipts/checkpoints.
4. Baseline capabilities with no authority expansion may be installed from locked sources. Privileged capabilities stop for system approval.
5. Kimmizo Auto copies and verifies the signed runtime bundle, compiles the transparent proxy, records hashes and the previous environment value, and activates the user-scoped proxy.
6. Verification reruns doctor and the acceptance scenarios, then reports exact pass, pending-approval, restart-required, or failed states.

## Failure Handling and Recovery

- Preflight failure occurs before target or machine mutation whenever possible.
- Dry-run never creates the target or changes project, user, or machine state.
- Managed-block drift is backed up before repair.
- Important project writes use atomic replacement and scoped locks.
- Capability receipts are written before restart-sensitive execution and redact common credential/token forms.
- Failed capability installation does not expand the allowlist.
- Pinned-skill and plugin restoration stage and verify backups before replacement.
- Plugin rollback refuses to overwrite a Codex config modified after installation.
- Kimmizo Auto uninstall restores the exact previous `CODEX_CLI_PATH` value when Kimmizo still owns the current value.
- A failed Auto runtime update retains only a previously verified complete bundle and records a non-current status.
- No recovery path deletes project memory or user-owned content.

## Verification Strategy

### Static and automated checks

- Dependency-free repository validator.
- Python syntax/compile validation.
- PowerShell parser validation for all PowerShell entry points.
- Full pytest suite on an installed supported interpreter.
- Existing CI matrix remains Windows and Ubuntu with Python 3.11 and 3.13.

### Installation acceptance checks

1. Dry-run reports intended actions and leaves Git/file state unchanged.
2. Real setup creates the expected capsule, team profiles, routing skills, memory/checkpoint structure, and managed configuration.
3. Doctor reports no broken or integrity-failed core capability. An expected `approval_required` state is acceptable and is not silently bypassed.
4. A second setup produces no new agent identity or unnecessary profile revision and does not overwrite project-owned content.
5. Repair restores a deliberately missing managed artifact while preserving an existing memory note.
6. Kimmizo Auto status/self-test passes, records no prompt content, and reports a verified runtime bundle. A required application restart is reported explicitly rather than treated as complete.
7. A safe rollback exercise restores the exact prior state for a reversible test artifact or capability without deleting unrelated files.
8. `git diff`, ignored-file checks, and secret-pattern scans show that no credential, machine-local receipt, runtime bundle, or memory content is staged or tracked.

## Readiness Decision

The final report uses these states:

- **Ready:** every acceptance check passes and no required restart or approval remains for the core baseline.
- **Ready after restart:** all checks pass but Codex must restart to load the verified Auto extension.
- **Core ready, optional approval pending:** the core baseline passes and only explicitly optional privileged connectors are pending.
- **Not ready:** any core test, integrity check, idempotency check, repair check, or rollback check fails.

No report may collapse a failure, required restart, or privileged approval into “Ready.”

## Implementation Boundaries

- Preserve unrelated user changes and the current Git history.
- Add regression tests before or with each behavior change.
- Do not install optional authenticated/external-write connectors as part of the baseline.
- Do not weaken integrity verification to make installation pass.
- Do not modify files outside the target repository or Kimmizo's documented user-scoped install roots except through the approved signed prerequisite installers.
- Record exact commands, versions, results, and remaining restart/approval requirements in the final evidence summary.

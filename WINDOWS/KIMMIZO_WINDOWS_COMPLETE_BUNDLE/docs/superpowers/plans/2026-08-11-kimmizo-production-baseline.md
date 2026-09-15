# Kimmizo Production Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Kimmizo's Python prerequisite detection, then install and prove the production baseline in `D:\git\kimmizo_setup`.

**Architecture:** A small PowerShell prerequisite module will probe candidate interpreters by execution and return a normalized command descriptor to `install.ps1`. After TDD and repository-wide validation pass, the hardened entry point will deploy the existing Python setup engine, locked capability registry, project capsule, and reversible Kimmizo Auto extension into the target repository; acceptance exercises then prove dry-run safety, idempotency, repair, rollback, integrity, and secret hygiene.

**Tech Stack:** PowerShell 7/Windows PowerShell, Python 3.11–3.13, pytest 8–9, Codex CLI/Desktop, winget, JSON/TOML, GitHub Actions.

## Global Constraints

- Target exactly `D:\git\kimmizo_setup`.
- Python must be version 3.11 or newer; the locked workstation prerequisite is `Python.Python.3.13` from winget.
- Preserve project-owned content outside managed blocks and preserve agent names and IDs across repeated setup.
- Automatic installation is restricted to exact entries in `plugins/kimmizo-setup/registry/baseline-lock.json`.
- Do not silently authorize authentication, MCP servers, hooks, sandbox expansion, new permissions, or external writes.
- Do not install every registry capability regardless of project need.
- Do not weaken Authenticode, SHA256, package-fingerprint, safe-path, atomic-write, redaction, receipt, backup, or rollback checks.
- Do not modify signed Codex Desktop files, patch its renderer/model picker, or write the virtual Auto model to `config.toml`.
- Do not store prompts, responses, credentials, tokens, images, files, telemetry, vectors, or cross-project memory.
- A required restart, privileged approval, or failed core check must remain visible and must not be reported as `Ready`.

## File Map

- Create `scripts/KimmizoPrerequisites.ps1`: execution-based Python candidate discovery and normalized command descriptor.
- Modify `install.ps1`: consume the prerequisite module, install Python only after probes fail, and emit a non-mutating blocked dry-run report when Python is absent.
- Create `tests/test_installer_prerequisites.py`: cross-platform PowerShell tests for usable, unusable, and unsupported-version candidates plus dry-run behavior.
- Modify `tests/test_auto_model_extension.py`: assert the entry point is wired to the prerequisite module and continues to wire Auto correctly.
- Modify `README.md`: document execution-based Python detection, dry-run blocked output, and readiness meanings.
- Modify `scripts/validate_repo.py`: require and syntax-check the new prerequisite module when PowerShell is available.
- Generate project-local managed/runtime files during deployment; only documented managed configuration may be tracked, while `.kimmizo` runtime evidence, receipts, memory, backups, and installed runtime files remain ignored.

---

### Task 1: Provision the Supported Test Runtime

**Files:**
- Verify only: `pyproject.toml`

**Interfaces:**
- Consumes: `requires-python = ">=3.11"` and `dev = ["pytest>=8,<10"]`.
- Produces: a working `python` command and pytest installation used by Tasks 2–8.

- [ ] **Step 1: Confirm the current failure before changing the machine**

Run:

```powershell
python --version
py -3 --version
```

Expected: `python` is not found and `py -3` reports `No installed Python found!` on the current workstation. If either command already reports Python 3.11–3.13, record that version and skip Step 2.

- [ ] **Step 2: Install the locked Python prerequisite**

Run with system approval:

```powershell
winget install --id Python.Python.3.13 --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
```

Expected: exit code 0 and a signed winget installation of Python 3.13.x.

- [ ] **Step 3: Open a refreshed process environment and verify the interpreter**

Run:

```powershell
$machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$user = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:Path = @($machine, $user) -join [IO.Path]::PathSeparator
python -c "import json,sys; print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:3])}))"
```

Expected: JSON with a real executable path and a version beginning `[3, 13, ...]`.

- [ ] **Step 4: Install only the declared development dependency**

Run:

```powershell
python -m pip install "pytest>=8,<10"
python -m pytest --version
```

Expected: pytest 8.x or 9.x.

- [ ] **Step 5: Capture the pre-change baseline**

Run:

```powershell
python scripts/validate_repo.py
python -m pytest -q
git status --short
```

Expected: validator passes, the existing test suite passes, and only the already committed design plus uncommitted plan state is present. If tests fail, stop and use `superpowers:systematic-debugging` before Task 2.

### Task 2: Add Execution-Based Python Resolution

**Files:**
- Create: `scripts/KimmizoPrerequisites.ps1`
- Modify: `install.ps1`
- Create: `tests/test_installer_prerequisites.py`
- Modify: `tests/test_auto_model_extension.py`

**Interfaces:**
- Consumes: PowerShell command discovery and Python's `sys.version_info`/`sys.executable`.
- Produces: `Resolve-KimmizoPython -Candidates` accepting `object[]` and returning either `$null` or a `PSCustomObject` with `Path: string`, `PrefixArguments: string[]`, and `Version: string`.
- Produces: `Invoke-Kimmizo` execution as `& $Python.Path @($Python.PrefixArguments + $Arguments)`.

- [ ] **Step 1: Write the PowerShell test harness and failing resolver tests**

Create `tests/test_installer_prerequisites.py` with a PowerShell locator and helper:

```python
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "KimmizoPrerequisites.ps1"
INSTALLER = ROOT / "install.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    if not POWERSHELL:
        pytest.skip("PowerShell is required for installer integration tests")
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def ps_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"
```

Add tests that create fake `.ps1` probes and inject candidate descriptors:

```python
def test_resolver_rejects_broken_launcher_and_uses_working_candidate(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ps1"
    broken.write_text("[Console]::Error.WriteLine('No installed Python found!'); exit 103\n", encoding="utf-8")
    working = tmp_path / "working.ps1"
    working.write_text(
        "[Console]::Out.WriteLine('{\"executable\":\"C:/Python313/python.exe\",\"version\":[3,13,7]}'); exit 0\n",
        encoding="utf-8",
    )
    script = f"""
. {ps_quote(MODULE)}
$broken = [pscustomobject]@{{ Path = {ps_quote(broken)}; PrefixArguments = @('-3') }}
$working = [pscustomobject]@{{ Path = {ps_quote(working)}; PrefixArguments = @() }}
Resolve-KimmizoPython -Candidates @($broken, $working) | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["Path"]) == working
    assert payload["Version"] == "3.13.7"
    assert payload["PrefixArguments"] is None or payload["PrefixArguments"] == []


def test_resolver_rejects_python_310(tmp_path: Path) -> None:
    old = tmp_path / "old.ps1"
    old.write_text(
        "[Console]::Out.WriteLine('{\"executable\":\"C:/Python310/python.exe\",\"version\":[3,10,14]}'); exit 0\n",
        encoding="utf-8",
    )
    script = f"""
. {ps_quote(MODULE)}
$candidate = [pscustomobject]@{{ Path = {ps_quote(old)}; PrefixArguments = @() }}
$resolved = Resolve-KimmizoPython -Candidates @($candidate)
if ($null -eq $resolved) {{ 'null' }} else {{ $resolved | ConvertTo-Json -Compress }}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "null"
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
python -m pytest tests/test_installer_prerequisites.py -v
```

Expected: FAIL because `scripts/KimmizoPrerequisites.ps1` does not exist.

- [ ] **Step 3: Implement the minimal prerequisite module**

Create `scripts/KimmizoPrerequisites.ps1` with strict, side-effect-free functions:

```powershell
Set-StrictMode -Version Latest

function Get-KimmizoPythonCandidates {
    $Candidates = @()
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        $Candidates += [pscustomobject]@{ Path = $Python.Source; PrefixArguments = @() }
    }
    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        $Candidates += [pscustomobject]@{ Path = $Py.Source; PrefixArguments = @('-3') }
    }
    return $Candidates
}

function Resolve-KimmizoPython {
    param([Parameter()][object[]]$Candidates = @(Get-KimmizoPythonCandidates))

    $Probe = "import json,sys; print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:3])}))"
    foreach ($Candidate in $Candidates) {
        try {
            $Output = (& $Candidate.Path @($Candidate.PrefixArguments) -c $Probe 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or -not $Output) { continue }
            $Data = $Output | ConvertFrom-Json
            $Parts = @($Data.version)
            if ($Parts.Count -ne 3 -or [int]$Parts[0] -ne 3 -or [int]$Parts[1] -lt 11) { continue }
            return [pscustomobject]@{
                Path = [string]$Candidate.Path
                PrefixArguments = [string[]]@($Candidate.PrefixArguments)
                Version = ($Parts -join '.')
            }
        }
        catch {
            continue
        }
    }
    return $null
}
```

- [ ] **Step 4: Integrate the normalized descriptor into `install.ps1`**

Immediately after `$AutoModelInstaller`, define and dot-source the module:

```powershell
$PrerequisiteScript = Join-Path $PSScriptRoot 'scripts\KimmizoPrerequisites.ps1'
if (-not (Test-Path -LiteralPath $PrerequisiteScript -PathType Leaf)) {
    throw "Kimmizo prerequisite helper was not found: $PrerequisiteScript"
}
. $PrerequisiteScript
```

Replace command-presence resolution with:

```powershell
$Python = Resolve-KimmizoPython
```

After winget installation and `Update-ProcessPath`, resolve again with `Resolve-KimmizoPython`. In `Invoke-Kimmizo`, replace `$Python.Name`/`$Python.Source` branching with:

```powershell
$InvocationArguments = @($Python.PrefixArguments) + $Arguments
```

and invoke `$Python.Path` for both captured and uncaptured calls.

- [ ] **Step 5: Extend the existing wiring test**

In `tests/test_auto_model_extension.py`, add:

```python
    assert "KimmizoPrerequisites.ps1" in installer
    assert "Resolve-KimmizoPython" in installer
    assert "$Python.Path" in installer
    assert "$Python.Source" not in installer
```

- [ ] **Step 6: Run focused tests and then the full suite**

Run:

```powershell
python -m pytest tests/test_installer_prerequisites.py tests/test_auto_model_extension.py -v
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the resolver change**

```powershell
git add scripts/KimmizoPrerequisites.ps1 install.ps1 tests/test_installer_prerequisites.py tests/test_auto_model_extension.py
git commit -m "fix: verify Python runtime before Kimmizo setup"
```

### Task 3: Make Missing-Python Dry-Run Safe and Observable

**Files:**
- Modify: `install.ps1`
- Modify: `tests/test_installer_prerequisites.py`

**Interfaces:**
- Consumes: `$Python = Resolve-KimmizoPython`, `$DryRun`, `$SkipInstall`.
- Produces: JSON `{status:"blocked", mode:"dry-run", missing:["python"], would_install:["Python.Python.3.13"]}` with exit code 0 and no target creation when no usable interpreter exists during dry-run.

- [ ] **Step 1: Write the failing dry-run integration test**

Append:

```python
def test_dry_run_without_python_reports_blocked_without_creating_target(tmp_path: Path) -> None:
    target = tmp_path / "must-not-exist"
    script = f"""
$env:Path = ''
& {ps_quote(INSTALLER)} -Mode setup -Target {ps_quote(target)} -DryRun -NoPluginRegistration -NoAutoModel
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "blocked",
        "mode": "dry-run",
        "missing": ["python"],
        "would_install": ["Python.Python.3.13"],
    }
    assert not target.exists()
```

- [ ] **Step 2: Verify the test fails for the old throw behavior**

Run:

```powershell
python -m pytest tests/test_installer_prerequisites.py::test_dry_run_without_python_reports_blocked_without_creating_target -v
```

Expected: FAIL because the installer throws instead of returning structured JSON.

- [ ] **Step 3: Implement the blocked dry-run branch**

Before the existing final missing-Python throw, add:

```powershell
if (-not $Python -and $DryRun) {
    [ordered]@{
        status = 'blocked'
        mode = 'dry-run'
        missing = @('python')
        would_install = @('Python.Python.3.13')
    } | ConvertTo-Json -Depth 4
    exit 0
}
```

Keep normal setup installing the locked prerequisite and keep `-SkipInstall` without a usable interpreter as a hard error.

- [ ] **Step 4: Run focused and full tests**

```powershell
python -m pytest tests/test_installer_prerequisites.py -v
python -m pytest -q
```

Expected: all tests pass and the target directory remains absent in the integration test.

- [ ] **Step 5: Commit the dry-run behavior**

```powershell
git add install.ps1 tests/test_installer_prerequisites.py
git commit -m "fix: report blocked Python prerequisite in dry run"
```

### Task 4: Extend Repository Validation and Operator Documentation

**Files:**
- Modify: `scripts/validate_repo.py`
- Modify: `README.md`
- Test: `tests/test_installer_prerequisites.py`

**Interfaces:**
- Consumes: the new prerequisite module and readiness states from the approved design.
- Produces: validator coverage for the module and operator-facing documentation of probe/install/dry-run behavior.

- [ ] **Step 1: Write a failing validator contract test**

Append:

```python
def test_repository_validator_requires_prerequisite_module() -> None:
    validator = (ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8")
    assert 'ROOT / "scripts" / "KimmizoPrerequisites.ps1"' in validator
    assert "ParseFile" in validator
```

- [ ] **Step 2: Run the test and verify it fails**

```powershell
python -m pytest tests/test_installer_prerequisites.py::test_repository_validator_requires_prerequisite_module -v
```

Expected: FAIL because the validator does not reference the module or PowerShell parser.

- [ ] **Step 3: Require the module and parse all PowerShell files**

Add `shutil` and `subprocess` imports to `scripts/validate_repo.py`. Add the module to `required`. When `pwsh` or `powershell` is available, run one parser command per `*.ps1` file using:

```powershell
$tokens = $null
$errors = $null
[Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }
```

Append an error in the exact format `invalid PowerShell {relative_path}: {stderr}` to `errors` for non-zero results. If PowerShell is unavailable, retain the dependency-free checks without failing solely for the missing optional parser.

- [ ] **Step 4: Document the operational contract**

Update `README.md` to state:

- `python` and `py -3` are execution-probed and Python 3.10 or a launcher without an interpreter is rejected.
- Normal setup may install locked Python 3.13 via winget.
- Dry-run with no interpreter returns `status: blocked`, `missing: [python]`, and `would_install: [Python.Python.3.13]` without mutation.
- Readiness is reported as `Ready`, `Ready after restart`, `Core ready, optional approval pending`, or `Not ready`.

- [ ] **Step 5: Run validator and full suite**

```powershell
python scripts/validate_repo.py
python -m pytest -q
git diff --check
```

Expected: validator and all tests pass; no whitespace errors.

- [ ] **Step 6: Commit validation and documentation**

```powershell
git add scripts/validate_repo.py README.md tests/test_installer_prerequisites.py
git commit -m "test: validate Kimmizo PowerShell prerequisites"
```

### Task 5: Prove Dry-Run Safety on the Real Target

**Files:**
- Read: all tracked repository files
- Evidence only: `.kimmizo/runtime/acceptance/pre-dry-run.json` after setup creates the ignored runtime root; until then retain command output in the task log.

**Interfaces:**
- Consumes: hardened `install.ps1 -DryRun`.
- Produces: before/after tracked-file hashes and Git status proving no mutation.

- [ ] **Step 1: Record the exact pre-dry-run state**

```powershell
$beforeStatus = git status --porcelain=v1
$beforeHashes = git ls-files | ForEach-Object { Get-FileHash -Algorithm SHA256 -LiteralPath $_ } | Sort-Object Path
```

- [ ] **Step 2: Run the target dry-run**

```powershell
.\install.ps1 -Mode setup -Target 'D:\git\kimmizo_setup' -DryRun
```

Expected: structured setup plan, no exception, and no filesystem mutation.

- [ ] **Step 3: Compare state exactly**

```powershell
$afterStatus = git status --porcelain=v1
$afterHashes = git ls-files | ForEach-Object { Get-FileHash -Algorithm SHA256 -LiteralPath $_ } | Sort-Object Path
Compare-Object $beforeStatus $afterStatus
Compare-Object ($beforeHashes | ConvertTo-Json -Depth 3) ($afterHashes | ConvertTo-Json -Depth 3)
```

Expected: both comparisons produce no output.

### Task 6: Install the Project Capsule and Core Baseline

**Files:**
- Generate/merge: `AGENTS.md`
- Generate/merge: `.codex/config.toml`
- Generate: `.codex/agents/*.toml`
- Generate: `.agents/skills/kimmizo-*`
- Generate ignored state: `.kimmizo/**`
- Modify/merge: `.gitignore`
- User-scoped reversible install: Kimmizo Auto roots documented by its install record.

**Interfaces:**
- Consumes: locked registry, capsule templates, working Python/Git/Codex host, and signed Codex Desktop runtime.
- Produces: ready project capsule, core capabilities, receipts/checkpoints, and Auto status or explicit restart/block reason.

- [ ] **Step 1: Capture pre-install user and project state**

Record `git status --short`, the current user-scoped `CODEX_CLI_PATH`, `codex --version`, active plugin inventory, and Auto status if present. Do not print secret environment values other than the exact CLI path variable governed by this installer.

- [ ] **Step 2: Run real setup with approved system mutation**

```powershell
.\install.ps1 -Mode setup -Target 'D:\git\kimmizo_setup'
```

Expected: exit code 0, capsule creation, locked no-authority capabilities installed or already present, privileged capabilities left as `approval_required`, and Auto installed/current or explicitly `pending_restart`.

- [ ] **Step 3: Inspect generated source-of-truth files**

```powershell
Get-Content -Raw -Encoding UTF8 .kimmizo\project-profile.json
Get-Content -Raw -Encoding UTF8 .kimmizo\team\identities.json
Get-Content -Raw -Encoding UTF8 .kimmizo\team\active.json
Get-Content -Raw -Encoding UTF8 .kimmizo\runtime\checkpoints\latest.json
```

Expected: valid JSON, stable UUID identities, active revision 1 profiles, and a setup checkpoint with sanitized evidence.

- [ ] **Step 4: Verify managed and ignored artifacts**

```powershell
git check-ignore -v .kimmizo\runtime\checkpoints\latest.json .kimmizo\memory\current.md .kimmizo\capabilities\receipts\*.json
git status --short
```

Expected: machine-local runtime/memory/receipts are ignored; only intentional managed project files appear as source changes.

### Task 7: Verify Doctor and Idempotency

**Files:**
- Read: `.kimmizo/project-profile.json`
- Read: `.kimmizo/team/identities.json`
- Read: `.kimmizo/team/active.json`
- Evidence: ignored `.kimmizo/runtime/acceptance/doctor.json` and `idempotency.json`

**Interfaces:**
- Consumes: installed capsule and host state from Task 6.
- Produces: sanitized doctor report and exact identity/profile stability comparison.

- [ ] **Step 1: Run doctor and team report**

```powershell
.\install.ps1 -Mode doctor -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode team-report -Target 'D:\git\kimmizo_setup'
```

Expected: no broken or integrity-failed core capability; optional privileged entries may be `approval_required`.

- [ ] **Step 2: Snapshot identity and active-profile hashes**

```powershell
$identityBefore = (Get-FileHash -Algorithm SHA256 .kimmizo\team\identities.json).Hash
$activeBefore = (Get-FileHash -Algorithm SHA256 .kimmizo\team\active.json).Hash
```

- [ ] **Step 3: Run setup a second time**

```powershell
.\install.ps1 -Mode setup -Target 'D:\git\kimmizo_setup'
```

Expected: exit code 0 with no unnecessary new team revision.

- [ ] **Step 4: Prove identity and active profile stability**

```powershell
$identityAfter = (Get-FileHash -Algorithm SHA256 .kimmizo\team\identities.json).Hash
$activeAfter = (Get-FileHash -Algorithm SHA256 .kimmizo\team\active.json).Hash
if ($identityBefore -ne $identityAfter -or $activeBefore -ne $activeAfter) { throw 'Kimmizo setup was not idempotent' }
```

Expected: no throw.

### Task 8: Exercise Repair, Auto Recovery, and Rollback

**Files:**
- Temporarily remove/restore: `.agents/skills/kimmizo-memory/SKILL.md`
- Preserve: `.kimmizo/memory/acceptance-note.md`
- Read: Kimmizo Auto install/status record and user-scoped `CODEX_CLI_PATH`.

**Interfaces:**
- Consumes: `repair`, Auto status/uninstall/install, unit rollback tests.
- Produces: evidence that managed repair preserves memory and reversible Auto activation restores/reapplies the previous environment contract.

- [ ] **Step 1: Create a machine-local preservation marker and backup**

```powershell
New-Item -ItemType Directory -Force .kimmizo\memory | Out-Null
Set-Content -LiteralPath .kimmizo\memory\acceptance-note.md -Encoding UTF8 -Value 'preserve-kimmizo-acceptance'
$managed = '.agents\skills\kimmizo-memory\SKILL.md'
$backup = Join-Path $env:TEMP 'kimmizo-memory-SKILL.acceptance.bak'
Copy-Item -LiteralPath $managed -Destination $backup -Force
```

- [ ] **Step 2: Remove one exact managed artifact and run repair**

```powershell
Remove-Item -LiteralPath $managed -Force
.\install.ps1 -Mode repair -Target 'D:\git\kimmizo_setup'
```

Expected: repair recreates the skill. Compare its SHA256 to `$backup` and confirm the acceptance note still contains the exact marker. If repair fails, copy `$backup` back immediately.

- [ ] **Step 3: Run transactional rollback regression tests**

```powershell
python -m pytest tests/test_kimmizo.py -k "rollback or transactional or repair" -v
```

Expected: pinned-skill rollback, plugin snapshot restoration, tamper safety, and repair tests pass.

- [ ] **Step 4: Capture and exercise Kimmizo Auto ownership recovery**

Record the current user `CODEX_CLI_PATH` and run:

```powershell
.\install.ps1 -Mode auto-status -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode auto-uninstall -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode auto-status -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode update -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode auto-status -Target 'D:\git\kimmizo_setup'
```

Expected: uninstall restores the recorded previous value only while Kimmizo owns the current value; update reinstalls a hash-verified proxy/runtime; the final status is `current` or explicitly `pending_restart`. Do not report `pending_restart` as ready.

- [ ] **Step 5: Remove only the temporary backup**

```powershell
Remove-Item -LiteralPath $backup -Force
```

Keep the ignored acceptance note as repair evidence unless the boss requests removal.

### Task 9: Final Verification and Readiness Report

**Files:**
- Evidence: ignored `.kimmizo/runtime/acceptance/production-baseline.json`
- Review: all intentional tracked changes

**Interfaces:**
- Consumes: every task's command output, doctor/Auto status, Git state, and test results.
- Produces: one readiness state from `Ready`, `Ready after restart`, `Core ready, optional approval pending`, or `Not ready`.

- [ ] **Step 1: Run all automated checks from a fresh command context**

```powershell
python scripts/validate_repo.py
python -m pytest -q
git diff --check
```

Expected: validator passes, every test passes, and no whitespace error is reported.

- [ ] **Step 2: Run final operational checks**

```powershell
.\install.ps1 -Mode doctor -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode team-report -Target 'D:\git\kimmizo_setup'
.\install.ps1 -Mode auto-status -Target 'D:\git\kimmizo_setup'
```

Expected: no broken/integrity-failed core item and explicit restart/approval states.

- [ ] **Step 3: Scan tracked changes for forbidden machine-local or secret material**

```powershell
git status --short
git ls-files .kimmizo
git diff -- . ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*'
rg -n --hidden -g '!/.git/**' -g '!/.kimmizo/**' "Bearer\s+\S+|api[_-]?key\s*[:=]|github_pat_|password\s*[:=]|token\s*[:=]" .
```

Expected: `git ls-files .kimmizo` prints nothing; no real secret appears. Test fixtures containing synthetic secret patterns are reviewed as fixtures, not treated as credentials.

- [ ] **Step 4: Record the evidence JSON without secrets**

Write `.kimmizo/runtime/acceptance/production-baseline.json` atomically with UTC timestamp, Git commit, Python/pytest/Codex versions, validator/test counts, doctor core status, Auto status, idempotency hashes, repair result, rollback result, tracked-change list, and final readiness state. Pass the object through Kimmizo's existing `redact_value` behavior before writing.

- [ ] **Step 5: Commit intentional source and managed project changes**

Review each tracked path, then run:

```powershell
git add -- AGENTS.md .gitignore .codex/config.toml .codex/agents .agents/skills/kimmizo-capability-router .agents/skills/kimmizo-memory .agents/skills/kimmizo-secretary
git commit -m "feat: install Kimmizo production baseline"
```

If one of these paths is unchanged or absent, omit only that exact path after comparing the list with `git status --short`. Never use `git add -A` for generated installation output.

- [ ] **Step 6: Report the exact readiness state**

Report the outcome in Thai with links to the implementation files and ignored evidence path, exact test/validator results, installed core capabilities, optional approvals, restart requirement, rollback result, and Git commit. If any core check failed, use `Not ready` and name the failed check.

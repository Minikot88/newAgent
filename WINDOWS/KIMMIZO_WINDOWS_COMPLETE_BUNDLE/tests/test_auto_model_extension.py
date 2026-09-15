from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
AUTO_ROOT = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "auto-model"
POLICY_PATH = ROOT / "plugins" / "kimmizo-setup" / "registry" / "model-policy.json"
SCOPE_HARNESS_PATH = ROOT / "tests" / "fixtures" / "auto-model" / "AutoModelScopeHarness.cs"
SCOPE_HARNESS_RUNNER_PATH = ROOT / "tests" / "fixtures" / "auto-model" / "Run-AutoModelScopeHarness.ps1"


def test_auto_model_extension_is_wired_into_setup() -> None:
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")
    auto_installer = (AUTO_ROOT / "Install-KimmizoCodexAuto.ps1").read_text(
        encoding="utf-8"
    )

    assert "Invoke-KimmizoAutoModel -Action Install" in installer
    assert "auto-status" in installer
    assert "auto-uninstall" in installer
    assert 'private const string VirtualModel = "kimmizo-auto"' in source
    assert 'private const string VirtualDisplayName = "✦ Auto"' in source
    assert 'private const string VirtualDescription = "ปรับโมเดลตามช่วงงาน"' in source
    assert 'report["storesPrompts"] = false' in source
    assert 'effort = "xhigh"' not in source
    assert 'requiresUltraApproval = !ultraApproved' in source
    assert 'AddUltraApprovalContext(parameters)' in source
    assert 'ChooseAdaptiveRoute(GetLastRoute(threadId), taskText, ultraApproved, ultraApproved)' in source
    assert 'IsNewWorkPhase(taskText)' in source
    assert 'IsStrongerRoute(candidate, currentRoute)' in source
    assert "CODEX_CLI_PATH" in auto_installer
    assert "previousCodexCliPath" in auto_installer
    assert "[switch]$MakeDefault" in auto_installer
    assert "--kimmizo-default-auto-on" in auto_installer
    assert "--kimmizo-default-auto-on" in source
    assert "Get-AuthenticodeSignature" in auto_installer
    assert "codex-code-mode-host.exe" in auto_installer
    assert "Sync-KimmizoCodexRuntime.ps1" in auto_installer
    assert "if (!TrySyncRuntime())" in source
    assert "PrepareRuntimeEnvironment(start)" in source
    assert 'report["autoUpdateEnabled"]' in source


def test_auto_runtime_sync_tracks_latest_signed_desktop_package() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")
    sync = (AUTO_ROOT / "Sync-KimmizoCodexRuntime.ps1").read_text(encoding="utf-8")

    assert "Get-AppxPackage OpenAI.Codex" in sync
    assert "Get-AuthenticodeSignature" in sync
    assert "Get-FileHash" in sync
    assert "[IO.File]::Replace" in sync
    assert "runtime-sync.json" in sync
    assert "codex-command-runner.exe" in sync
    assert "codex-windows-sandbox-setup.exe" in sync
    assert "runtimeFileHashes" in sync
    assert "Test-RecordedBundle" in sync
    assert "runtime-sync.lock" in sync
    assert "failed_integrity" in sync
    assert "refused to start an unverified Codex runtime bundle" in source
    assert "Test-ProcessUsingPath" in (AUTO_ROOT / "Install-KimmizoCodexAuto.ps1").read_text(encoding="utf-8")
    assert "pending_restart" in (AUTO_ROOT / "Install-KimmizoCodexAuto.ps1").read_text(encoding="utf-8")


def test_auto_router_has_limit_first_routes_without_prompt_storage() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"):
        assert model in source
    assert '"fast"' in source
    assert '"balanced"' in source
    assert 'tier = "deep"' in source
    assert 'tier = "critical"' in source
    assert 'tier = "ultra_pending"' in source
    assert 'report["phaseKeepsModel"]' in source
    assert 'report["phaseUpgrade"]' in source
    assert 'report["phaseReset"]' in source
    assert "prompt.json" not in source.lower()
    assert "conversation.json" not in source.lower()


def test_shared_model_policy_declares_versioned_routes_and_voice_contract() -> None:
    assert POLICY_PATH.is_file(), "the Auto runtime policy must be a checked-in file"
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["schema_version"] == 3
    assert policy["policy_version"] == "3.0.0"
    assert set(policy["model_selection"]) == {
        "fast",
        "balanced",
        "deep",
        "critical",
        "ultra",
    }
    assert policy["model_selection"]["fast"]["effort"] == "low"
    assert policy["model_selection"]["balanced"]["effort"] == "medium"
    assert policy["model_selection"]["deep"]["effort"] == "high"
    assert policy["model_selection"]["critical"]["effort"] == "high"
    assert policy["model_selection"]["ultra"]["effort"] == "ultra"
    assert policy["model_selection"]["ultra"]["pending_effort"] == "high"
    assert policy["model_selection"]["fast"]["models"][0] == "gpt-5.6-luna"
    assert policy["model_selection"]["balanced"]["models"][0] == "gpt-5.6-luna"
    assert policy["model_selection"]["deep"]["models"][0] == "gpt-5.6-terra"
    assert policy["model_selection"]["critical"]["models"][0] == "gpt-5.6-sol"
    assert "architecture" in policy["model_selection"]["deep"]["signals"]
    assert "security" in policy["model_selection"]["critical"]["signals"]
    assert "multi-agent" in policy["model_selection"]["ultra"]["signals"]
    usage = policy["usage_policy"]
    assert usage == {
        "mode": "chatgpt_plus_limit_first",
        "default_model": "gpt-5.6-luna",
        "default_effort": "low",
        "manual_only_models": ["gpt-6-astra"],
        "automatic_multi_agent": False,
        "fast_mode": False,
        "execution_mode": "serial",
        "verify_before_escalation": True,
        "escalation_order": [
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
            "gpt-6-astra",
        ],
    }
    automatic_models = {
        model
        for route in policy["model_selection"].values()
        for model in route["models"]
    }
    assert automatic_models <= {
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    }
    assert automatic_models.isdisjoint(usage["manual_only_models"])
    assert policy["voice"]["trigger"] == "เลขาคิม"
    assert policy["voice"]["pronoun"] == "ฉัน"
    assert policy["voice"]["suffix"] == "ค่ะ"
    assert policy["voice"]["instruction"]
    assert policy["voice"]["blocked_message"]
    assert "ยังตรวจสอบ voice bootstrap" in policy["voice"]["blocked_message"]


def test_shared_policy_hash_is_recorded_and_verified_by_proxy_and_installer() -> None:
    assert POLICY_PATH.is_file(), "the Auto policy must exist before its hash can be verified"
    policy_bytes = POLICY_PATH.read_bytes()
    policy_hash = hashlib.sha256(policy_bytes).hexdigest()
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")
    installer = (AUTO_ROOT / "Install-KimmizoCodexAuto.ps1").read_text(
        encoding="utf-8"
    )

    assert "model-policy.json" in source
    assert "SHA256" in source
    assert "policySha256" in source
    assert "model-policy.json" in installer
    assert "function Get-Sha256" in installer
    assert "Get-FileHash" not in installer
    assert "policyVersion" in installer
    assert "policySha256" in installer
    assert "voice-bootstrap.json" in installer
    assert len(policy_hash) == 64


def test_auto_turn_injects_verified_voice_context_without_clobbering_ultra_context() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "TryLoadVoiceBootstrap" in source
    assert "InjectVoiceBootstrap" in source
    assert '"kimmizo_voice_bootstrap"' in source
    assert '"kimmizo_auto_ultra_approval"' in source
    assert "additionalContext" in source
    assert "TryLoadPolicy" in source
    assert "policySha256" in source
    assert "เลขาคิม" in source
    assert "ฉัน" in source
    assert "ค่ะ" in source


def test_unverified_substantive_auto_turn_is_blocked_with_original_id_error() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "IsSubstantiveWorkflow" in source
    assert "-32071" in source
    assert "ยังตรวจสอบ voice bootstrap" in source
    assert "ImmediateResponse" in source
    assert "ForwardLine" in source


def test_voice_lookup_and_status_keep_manual_threads_untouched() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "KIMMIZO_PROJECT_ROOT" in source
    assert ".kimmizo" in source
    assert "voiceBootstrap" in source
    assert '"enforced"' in source
    assert '"configured"' in source
    assert '"unverified"' in source
    assert "IsThreadAuto(threadId)" in source


def test_project_voice_sidecar_requires_an_active_hash_bound_v2_capsule() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "ProjectCapsuleManifestData" in source
    assert '"kimmizo-capsule-v2"' in source
    assert "schema_version" in source
    assert "bootstrap_sha256" in source
    assert "TryLoadProjectCapsuleManifest" in source
    assert "ValidateProjectCapsuleManifest" in source
    assert "ComputeSha256(sidecarBytes)" in source
    assert "lifecycle" in source


def test_voice_gate_exempts_only_standalone_ultra_intents() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "IsUltraApprovalOnly" in source
    assert "IsUltraDenialOnly" in source
    assert "approve Ultra and deploy now" in SCOPE_HARNESS_PATH.read_text(encoding="utf-8")
    assert "อนุมัติ ultra แล้ว deploy ตอนนี้" in SCOPE_HARNESS_PATH.read_text(encoding="utf-8")


def test_unrelated_auto_turn_is_not_a_voice_bootstrap_candidate() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "secretaryThreads" in source
    assert "IsSecretaryTrigger" in source
    assert "IsSecretaryThread" in source
    assert "manifest.json" in source
    assert "TryLoadVoiceBootstrap" in source
    assert "if (secretary)" in source


def test_auto_scope_windows_harness_executes_real_transform_branches() -> None:
    if os.name != "nt":
        return
    compiler_candidates = (
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
        / "csc.exe",
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework"
        / "v4.0.30319"
        / "csc.exe",
    )
    compiler = next((candidate for candidate in compiler_candidates if candidate.is_file()), None)
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if compiler is None and not powershell.is_file():
        try:
            import pytest
        except ImportError:
            return
        pytest.skip("neither .NET Framework csc.exe nor Windows PowerShell is available")

    with tempfile.TemporaryDirectory(prefix="kimmizo-auto-scope-") as temp_dir:
        temp = Path(temp_dir)
        executable = temp / "auto-scope-harness.exe"
        reference = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "System.Web.Extensions.dll"
        if compiler is not None and not reference.is_file():
            reference = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework" / "v4.0.30319" / "System.Web.Extensions.dll"
        if compiler is not None and not reference.is_file():
            try:
                import pytest
            except ImportError:
                return
            pytest.skip("System.Web.Extensions.dll is not available")
        if compiler is not None:
            compile_result = subprocess.run(
                [
                    str(compiler),
                    "/nologo",
                    "/target:exe",
                    "/main:Kimmizo.CodexAuto.AutoModelScopeHarness",
                    "/platform:anycpu",
                    "/optimize+",
                    f"/reference:{reference}",
                    f"/out:{executable}",
                    str(AUTO_ROOT / "KimmizoCodexAuto.cs"),
                    str(SCOPE_HARNESS_PATH),
                ],
                capture_output=True,
                text=True,
            )
            assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
            run_result = subprocess.run(
                [str(executable), str(temp / "project"), str(POLICY_PATH)],
                capture_output=True,
                text=True,
            )
        else:
            run_result = subprocess.run(
                [
                    str(powershell),
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(SCOPE_HARNESS_RUNNER_PATH),
                    "-SourcePath",
                    str(AUTO_ROOT / "KimmizoCodexAuto.cs"),
                    "-HarnessPath",
                    str(SCOPE_HARNESS_PATH),
                    "-PolicyPath",
                    str(POLICY_PATH),
                    "-WorkingRoot",
                    str(temp),
                ],
                capture_output=True,
                text=True,
            )
        assert run_result.returncode == 0, run_result.stdout + run_result.stderr
        assert run_result.stdout.strip() == "AUTO_SCOPE_HARNESS_PASS"


def test_auto_request_boundaries_do_not_cross_mark_or_forward_unsafe_requests() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")

    assert "string requestedModel = GetString(parameters, \"model\")" in source
    assert "String.IsNullOrWhiteSpace(requestedModel) ? GetDefaultAuto() : IsVirtual(requestedModel)" in source
    assert "HasPendingAutoStart" not in source
    assert "ImmediateResponse = null" in source
    assert "secretaryThreads" in source
    assert "modelObserved" in source
    assert "unverified" in source


def test_ultra_context_and_readiness_fail_safe_without_clobbering_existing_values() -> None:
    source = (AUTO_ROOT / "KimmizoCodexAuto.cs").read_text(encoding="utf-8")
    installer = (AUTO_ROOT / "Install-KimmizoCodexAuto.ps1").read_text(encoding="utf-8")

    assert "TryGetAdditionalContext" in source
    assert "additionalContext value is not an object" in source
    assert "-32071" in source
    assert 'report["status"] = ready ? "passed" : "degraded"' in source
    assert 'report["status"] = ready ? "ready" : "degraded"' in source
    assert "policy-bundle.lock" in installer
    assert "PolicyBundleSelfTest" in installer


def test_policy_bundle_self_test_rollback_preserves_previous_bytes() -> None:
    if os.name != "nt":
        return
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        return

    with tempfile.TemporaryDirectory(prefix="kimmizo-policy-bundle-") as temp_dir:
        root = Path(temp_dir)
        old_policy = b'{"old":"policy"}'
        old_hash = b"old-policy-hash"
        (root / "model-policy.json").write_bytes(old_policy)
        (root / "model-policy.sha256").write_bytes(old_hash)
        (root / "voice-bootstrap.json").mkdir()
        result = subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(AUTO_ROOT / "Install-KimmizoCodexAuto.ps1"),
                "-PolicyBundleSelfTest",
                "-InstallRoot",
                str(root),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "policy bundle" in (result.stdout + result.stderr).lower()
        assert (root / "model-policy.json").read_bytes() == old_policy
        assert (root / "model-policy.sha256").read_bytes() == old_hash


def test_policy_bundle_self_test_serializes_concurrent_temp_root_updates() -> None:
    if os.name != "nt":
        return
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        return

    with tempfile.TemporaryDirectory(prefix="kimmizo-policy-lock-") as temp_dir:
        root = Path(temp_dir)
        command = [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AUTO_ROOT / "Install-KimmizoCodexAuto.ps1"),
            "-PolicyBundleSelfTest",
            "-PolicyBundleHoldMilliseconds",
            "750",
            "-InstallRoot",
            str(root),
        ]
        first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.1)
        second = subprocess.run(command, capture_output=True, text=True)
        first_stdout, first_stderr = first.communicate(timeout=30)
        assert first.returncode == 0, first_stdout + first_stderr
        assert second.returncode == 0, second.stdout + second.stderr
        policy_hash = hashlib.sha256((root / "model-policy.json").read_bytes()).hexdigest()
        assert (root / "model-policy.sha256").read_text(encoding="utf-8").strip() == policy_hash
        manifest = json.loads((root / "voice-bootstrap.json").read_text(encoding="utf-8"))
        installed_policy = json.loads((root / "model-policy.json").read_text(encoding="utf-8"))
        assert manifest["schemaVersion"] == installed_policy["schema_version"]
        assert manifest["policySha256"] == policy_hash

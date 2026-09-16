from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import platform
import tomllib
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "kimmizo.py"


def load_kimmizo():
    spec = importlib.util.spec_from_file_location("kimmizo", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def kimmizo():
    return load_kimmizo()


@pytest.fixture(autouse=True)
def clear_kimmizo_auto_host(monkeypatch):
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fake_machine(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    config = home / ".codex" / "config.toml"
    write(
        config,
        '\n'.join(
            [
                'model = "gpt-5.6-sol"',
                'model_reasoning_effort = "ultra"',
                '[plugins."superpowers@openai-curated"]',
                'enabled = true',
                '[plugins."browser@openai-bundled"]',
                'enabled = true',
                '[plugins."chrome@openai-bundled"]',
                'enabled = true',
                '[plugins."computer-use@openai-bundled"]',
                'enabled = true',
                '[plugins."github@openai-curated"]',
                'enabled = true',
                '[plugins."spreadsheets@openai-primary-runtime"]',
                'enabled = true',
                '[plugins."presentations@openai-primary-runtime"]',
                'enabled = true',
            ]
        )
        + '\n',
    )
    write(home / ".codex" / "skills" / "grill-me" / "SKILL.md", "---\nname: grill-me\n---\n")
    write(home / ".agents" / "skills" / "adhd" / "SKILL.md", "---\nname: adhd\n---\n")
    write(home / ".agents" / "skills" / "computer-use" / "SKILL.md", "Linux Xvfb desktop")
    write(
        home
        / ".codex"
        / "plugins"
        / "cache"
        / "openai-curated-remote"
        / "data-analytics"
        / "0.2.8"
        / "skills"
        / "index"
        / "SKILL.md",
        "cached",
    )
    return home, config


def fake_model_catalog() -> dict:
    return {
        "source": "test",
        "catalog_path": "test-models.json",
        "configured_model": "model-balanced",
        "configured_reasoning": "medium",
        "codex_cli_version": "0.136.0",
        "supported_reasoning": ["low", "medium", "high"],
        "cli_supported_reasoning": ["low", "medium", "high"],
        "compatibility_warnings": [],
        "catalog_complete": True,
        "models": [
            {
                "slug": "model-fast",
                "display_name": "Fast",
                "description": "",
                "priority": 2,
                "supported_reasoning": ["low", "medium"],
            },
            {
                "slug": "model-balanced",
                "display_name": "Balanced",
                "description": "",
                "priority": 1,
                "supported_reasoning": ["low", "medium", "high"],
            },
            {
                "slug": "model-deep",
                "display_name": "Deep",
                "description": "",
                "priority": 0,
                "supported_reasoning": ["medium", "high"],
            },
        ],
        "note": "test catalog",
    }


def plus_model_catalog() -> dict:
    efforts = ["low", "medium", "high", "xhigh", "max", "ultra"]
    return {
        "source": "test",
        "catalog_path": "test-models.json",
        "configured_model": "gpt-5.6-luna",
        "configured_reasoning": "low",
        "codex_cli_version": "0.136.0",
        "supported_reasoning": efforts,
        "cli_supported_reasoning": efforts,
        "compatibility_warnings": [],
        "catalog_complete": True,
        "models": [
            {
                "slug": model,
                "display_name": model,
                "description": "",
                "priority": priority,
                "supported_reasoning": efforts,
            }
            for priority, model in enumerate(
                (
                    "gpt-6-astra",
                    "gpt-5.6-sol",
                    "gpt-5.6-terra",
                    "gpt-5.6-luna",
                )
            )
        ],
        "note": "Plus limit-first test catalog",
    }


def test_plus_limit_first_routes_use_the_lowest_sufficient_model(kimmizo):
    catalog = plus_model_catalog()

    routine = kimmizo.route_task("แก้คำสะกดใน README", model_catalog=catalog)
    feature = kimmizo.route_task("เพิ่มระบบตั้งค่าพร้อม tests", model_catalog=catalog)
    deep = kimmizo.route_task("วิเคราะห์ architecture และ root cause", model_catalog=catalog)
    critical = kimmizo.route_task(
        "ตรวจ security ก่อน production deploy",
        model_catalog=catalog,
    )

    assert routine["model_recommendation"] == {
        "tier": "fast",
        "model": "gpt-5.6-luna",
        "reasoning": "low",
    }
    assert feature["model_recommendation"] == {
        "tier": "balanced",
        "model": "gpt-5.6-luna",
        "reasoning": "medium",
    }
    assert deep["model_recommendation"] == {
        "tier": "deep",
        "model": "gpt-5.6-terra",
        "reasoning": "high",
    }
    assert critical["model_recommendation"] == {
        "tier": "critical",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
    }
    assert all(
        result["model_recommendation"]["model"] != "gpt-6-astra"
        for result in (routine, feature, deep, critical)
    )
    assert kimmizo.SPECIALIST_TEAM["trading"]["model_tier"] == "critical"
    assert kimmizo.SPECIALIST_TEAM["finance"]["model_tier"] == "critical"


def test_route_selects_capabilities_without_tool_names(kimmizo):
    feature = kimmizo.route_task("เพิ่มระบบสมัครสมาชิกพร้อม tests")
    assert feature["workflow"] == [
        "superpowers:brainstorming",
        "superpowers:writing-plans",
        "superpowers:test-driven-development",
        "implementer",
        "reviewer",
        "superpowers:verification-before-completion",
    ]
    assert "adhd" not in feature["capabilities"]

    ambiguous = kimmizo.route_task("ช่วยออกแบบ architecture API ใหม่ ยังไม่รู้ requirement")
    assert "grill-me" in ambiguous["capabilities"]
    assert "adhd" not in ambiguous["capabilities"]

    explicit_adhd = kimmizo.route_task("/adhd ช่วยคิด architecture หลายทาง")
    assert "adhd" in explicit_adhd["capabilities"]

    simple = kimmizo.route_task("แก้คำสะกดใน README")
    assert "adhd" not in simple["capabilities"]
    assert "using-superpowers" not in simple["capabilities"]
    assert "implicit-using-superpowers" in simple["routing_guards"]


def test_route_separates_secretary_manual_advice_from_worker_auto_selection(kimmizo):
    catalog = fake_model_catalog()
    important = kimmizo.route_task(
        "ออกแบบ architecture ระบบ production ที่สำคัญ",
        model_catalog=catalog,
    )

    secretary = important["secretary_model_advice"]
    worker = important["worker_model_selection"]
    assert important["importance"] == "important"
    assert secretary["selection_mode"] == "boss_changes_manually"
    assert secretary["ui_model_mode"] == "specific"
    assert secretary["recommended_ui_model"] == "model-balanced"
    assert secretary["auto_select_each_message"] is False
    assert secretary["notify_before_start"] is True
    assert secretary["must_not_auto_change_main_model"] is True
    assert secretary["recommendation"]["reasoning"] == "high"
    assert secretary["observed_host_default"] == {
        "model": "model-balanced",
        "reasoning": "medium",
    }
    assert worker["selection_mode"] == "automatic_by_kimmizo"
    assert worker["recommendation"]["model"] != "Auto"
    assert worker["recommendation"]["reasoning"] == "high"
    assert important["model_recommendation"] == worker["recommendation"]

    routine = kimmizo.route_task("แก้คำสะกดใน README", model_catalog=catalog)
    assert routine["importance"] == "routine"
    routine_secretary = routine["secretary_model_advice"]
    assert routine_secretary["ui_model_mode"] == "auto"
    assert routine_secretary["recommended_ui_model"] == "Auto"
    assert routine_secretary["auto_select_each_message"] is True
    assert routine_secretary["notify_before_start"] is False
    assert "Model = Auto" in routine_secretary["message_th"]
    assert routine["worker_model_selection"]["selection_mode"] == "automatic_by_kimmizo"
    assert routine["worker_model_selection"]["recommendation"]["model"] != "Auto"
    assert routine["worker_model_selection"]["recommendation"]["reasoning"] == "low"


def test_route_uses_installed_auto_host_for_important_main_task(
    kimmizo, tmp_path, monkeypatch
):
    proxy = tmp_path / "codex-kimmizo-auto.exe"
    proxy.write_bytes(b"proxy")
    monkeypatch.setenv("CODEX_CLI_PATH", str(proxy))

    result = kimmizo.route_task("ตรวจ security ก่อน production deploy")
    secretary = result["secretary_model_advice"]

    assert secretary["selection_mode"] == "automatic_by_kimmizo_auto"
    assert secretary["recommended_ui_model"] == "Auto"
    assert secretary["auto_select_each_message"] is True
    assert secretary["host_auto_extension_active"] is True
    assert secretary["notify_before_start"] is False
    assert secretary["must_not_auto_change_main_model"] is False
    assert "อัตโนมัติ" in secretary["message_th"]


@pytest.mark.parametrize(
    ("task", "expected", "excluded"),
    [
        ("ทดสอบเว็บ localhost แบบอัตโนมัติ", "browser", "computer-use"),
        ("เปิดแท็บ Chrome ที่ล็อกอินบัญชีบอสอยู่", "chrome", "computer-use"),
        ("เปิดแท็บ Chrome ที่ล็อกอินอยู่", "chrome", "computer-use"),
        ("ทำ repeatable headless web QA ด้วย CLI", "agent-browser", "chrome"),
        ("กดเมนูในโปรแกรม Windows ที่ไม่มี API", "computer-use", "community-computer-use"),
        ("ตรวจ pull request และ CI ใน GitHub", "github", "computer-use"),
        ("ตรวจ auth secrets ก่อน deploy", "codex-security", "adhd"),
    ],
)
def test_route_backend_precedence(kimmizo, task, expected, excluded):
    result = kimmizo.route_task(task)
    assert expected in result["capabilities"]
    assert excluded not in result["capabilities"]


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("แก้ Supabase migration", "supabase"),
        ("deploy Cloudflare Workers", "cloudflare"),
        ("ตรวจ error monitoring ใน Sentry", "sentry"),
        ("ทำวิดีโอด้วย Remotion", "remotion"),
        ("อ่านเอกสารจาก Notion", "notion"),
        ("ตรวจ OpenAI Responses API", "openai-developers"),
        ("ตรวจ EA MQL5 สำหรับงาน trading", "domain-trading"),
    ],
)
def test_route_selects_project_conditional_capabilities(kimmizo, task, expected):
    assert expected in kimmizo.route_task(task)["capabilities"]


def test_doctor_distinguishes_enabled_cached_and_blocked(kimmizo, tmp_path):
    home, config = fake_machine(tmp_path)
    result = kimmizo.doctor(tmp_path / "project", home=home, codex_config=config)
    states = {item["id"]: item["state"] for item in result["capabilities"]}

    assert states["superpowers"] == "enabled"
    assert states["grill-me"] == "integrity_drift"
    assert states["adhd"] == "integrity_drift"
    assert states["data-analytics"] == "cached_only"
    assert states["spreadsheets"] == "enabled"
    assert states["presentations"] == "enabled"
    assert states["computer-use"] == "enabled"
    if platform.system().casefold() == "windows":
        assert states["community-computer-use"] == "blocked_conflict"
    else:
        assert "community-computer-use" not in states
    assert next(item for item in result["install_plan"] if item["id"] == "data-analytics")["action"] == "request_system_approval"
    assert result["model_catalog"]["configured_model"] == "gpt-5.6-sol"
    assert result["model_catalog"]["configured_reasoning"] == "ultra"


def test_doctor_consumes_context_conflict_policy(kimmizo, tmp_path):
    home, config = fake_machine(tmp_path)
    with config.open("a", encoding="utf-8") as handle:
        handle.write('[plugins."context-pack@awesome-codex-plugins"]\nenabled = true\n')
    result = kimmizo.doctor(tmp_path / "project", home=home, codex_config=config)
    assert any(item["id"] == "duplicate-context-manager" for item in result["conflicts"])


def test_system_approval_can_only_adopt_exact_enabled_host_package(kimmizo, tmp_path):
    home, _ = fake_machine(tmp_path)
    plugin = tmp_path / "host-plugin"
    write(
        plugin / ".codex-plugin" / "plugin.json",
        json.dumps(
            {
                "name": "data-analytics",
                "version": "0.2.8",
                "apps": "./.app.json",
                "mcpServers": "./.mcp.json",
                "interface": {"capabilities": ["Interactive", "Read", "Write"]},
            }
        ),
    )
    write(plugin / ".app.json", '{"name":"analytics"}')
    write(plugin / ".mcp.json", '{"endpoint":"https://approved.example"}')
    host_plugins = {
        "data-analytics@openai-curated": {
            "selector": "data-analytics@openai-curated",
            "state": "enabled",
            "version": "0.2.8",
            "path": str(plugin),
        }
    }

    with pytest.raises(PermissionError):
        kimmizo.grant_capability_approval("data-analytics", home=home, host_plugins={})

    granted = kimmizo.grant_capability_approval(
        "data-analytics",
        home=home,
        host_plugins=host_plugins,
    )
    assert granted["status"] == "host_approval_adopted"
    assert kimmizo._has_valid_capability_approval(
        home, "data-analytics", host_plugins=host_plugins
    )

    write(plugin / ".mcp.json", '{"endpoint":"https://changed.example"}')
    assert not kimmizo._has_valid_capability_approval(
        home, "data-analytics", host_plugins=host_plugins
    )


def test_doctor_probes_tier0_host_features(kimmizo, tmp_path, monkeypatch):
    home, config = fake_machine(tmp_path)
    monkeypatch.setattr(kimmizo, "_codex_features", lambda: {"multi_agent": False, "plugins": False})
    result = kimmizo.doctor(
        tmp_path / "project",
        home=home,
        codex_config=config,
        host_plugins={},
    )
    assert {"multi-agent", "skill-discovery"} <= set(result["missing_tier0"])


def test_doctor_plans_installable_tier0_prerequisite(kimmizo, tmp_path, monkeypatch):
    home, config = fake_machine(tmp_path)
    real_which = kimmizo.shutil.which
    monkeypatch.setattr(
        kimmizo.shutil,
        "which",
        lambda command: None if command == "git" else real_which(command),
    )
    monkeypatch.setattr(kimmizo, "_codex_features", lambda: {"multi_agent": True, "plugins": True})
    result = kimmizo.doctor(
        tmp_path / "project", home=home, codex_config=config, host_plugins={}
    )
    planned = next(item for item in result["install_plan"] if item["id"] == "git")
    assert planned["action"] == "auto_install"
    assert "git" in result["missing_tier0"]


def test_doctor_accepts_python3_on_non_windows_hosts(kimmizo, tmp_path, monkeypatch):
    home, config = fake_machine(tmp_path)
    real_which = kimmizo.shutil.which

    def python3_only(command):
        if command in {"python", "py"}:
            return None
        if command == "python3":
            return "/opt/homebrew/bin/python3"
        return real_which(command)

    monkeypatch.setattr(kimmizo.shutil, "which", python3_only)
    monkeypatch.setattr(kimmizo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(kimmizo, "_codex_features", lambda: {"multi_agent": True, "plugins": True})

    result = kimmizo.doctor(
        tmp_path / "project", home=home, codex_config=config, host_plugins={}
    )

    python = next(item for item in result["capabilities"] if item["id"] == "python")
    assert python["state"] == "installed"
    assert "python" not in result["missing_tier0"]


def test_doctor_uses_host_active_version_not_any_cached_version(kimmizo, tmp_path):
    home, config = fake_machine(tmp_path)
    manifest = (
        home
        / ".codex"
        / "plugins"
        / "cache"
        / "awesome-codex-plugins"
        / "codex-reviewer"
        / "0.9.0"
        / ".codex-plugin"
        / "plugin.json"
    )
    write(manifest, '{"name":"codex-reviewer","version":"0.9.0"}')
    active_path = tmp_path / "active-reviewer"
    write(
        active_path / ".codex-plugin" / "plugin.json",
        '{"name":"codex-reviewer","version":"9.9.9"}',
    )
    result = kimmizo.doctor(
        tmp_path / "project",
        home=home,
        codex_config=config,
        host_plugins={
            "codex-reviewer@awesome-codex-plugins": {
                "selector": "codex-reviewer@awesome-codex-plugins",
                "state": "enabled",
                "version": "9.9.9",
                "path": str(active_path),
            }
        },
    )
    reviewer = next(item for item in result["capabilities"] if item["id"] == "codex-reviewer")
    assert reviewer["state"] == "version_drift"
    assert reviewer["observed_versions"] == ["9.9.9"]


def test_doctor_reports_enabled_plugin_with_missing_cli_dependency(kimmizo, tmp_path, monkeypatch):
    home, config = fake_machine(tmp_path)
    with config.open("a", encoding="utf-8") as handle:
        handle.write('[plugins."codex-reviewer@awesome-codex-plugins"]\nenabled = true\n')
    real_which = kimmizo.shutil.which
    monkeypatch.setattr(
        kimmizo.shutil,
        "which",
        lambda command: None if command == "gh" else real_which(command),
    )
    result = kimmizo.doctor(tmp_path / "project", home=home, codex_config=config)
    states = {item["id"]: item["state"] for item in result["capabilities"]}
    assert states["codex-reviewer"] == "enabled_dependency_missing"


def test_doctor_merges_project_scoped_config(kimmizo, tmp_path):
    home = tmp_path / "home"
    global_config = home / ".codex" / "config.toml"
    write(global_config, 'model = "global-model"\n')
    project = tmp_path / "project"
    write(
        project / ".codex" / "config.toml",
        'model = "project-model"\n[plugins."browser@openai-bundled"]\nenabled = true\n',
    )
    result = kimmizo.doctor(project, home=home, codex_config=global_config)
    states = {item["id"]: item["state"] for item in result["capabilities"]}
    assert states["browser"] == "enabled"
    assert result["model_catalog"]["configured_model"] == "project-model"
    assert len(result["config_sources"]) == 2


def test_setup_preserves_user_files_and_creates_project_capsule(kimmizo, tmp_path):
    project = tmp_path / "project"
    write(project / "AGENTS.md", "# User rules\nKeep this line.\n")
    write(project / ".codex" / "config.toml", 'model = "boss-model"\n')

    result = kimmizo.setup_project(project, skip_install=True)

    agents_text = (project / "AGENTS.md").read_text(encoding="utf-8")
    config_text = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "Keep this line." in agents_text
    assert 'model = "boss-model"' in config_text
    assert agents_text.count("BEGIN KIMMIZO MANAGED BLOCK") == 1
    assert config_text.count("BEGIN KIMMIZO MANAGED BLOCK") == 1
    assert "checksum:" in agents_text
    tomllib.loads(config_text)

    required = [
        ".kimmizo/BOOT.md",
        ".kimmizo/manifest.json",
        ".kimmizo/project-profile.json",
        ".kimmizo/capabilities/available.json",
        ".kimmizo/capabilities/active.json",
        ".kimmizo/team/identities.json",
        ".kimmizo/team/active.json",
        ".kimmizo/runtime/checkpoints/latest.json",
        ".agents/skills/kimmizo-secretary/SKILL.md",
        ".agents/skills/kimmizo-capability-router/SKILL.md",
        ".agents/skills/kimmizo-memory/SKILL.md",
    ]
    for rel in required:
        assert (project / rel).is_file(), rel

    identities = read_json(project / ".kimmizo" / "team" / "identities.json")
    assert {a["role"] for a in identities["agents"]} >= {
        "explorer",
        "implementer",
        "reviewer",
        "context_keeper",
    }
    assert len(list((project / ".codex" / "agents").glob("*.toml"))) >= 4
    implementer_toml = next(
        path.read_text(encoding="utf-8")
        for path in (project / ".codex" / "agents").glob("*.toml")
        if 'name = "arin"' in path.read_text(encoding="utf-8")
    )
    assert "superpowers:test-driven-development" in implementer_toml
    assert "external_write=false" in implementer_toml
    assert result["status"] == "ready"
    manifest = read_json(project / ".kimmizo" / "manifest.json")
    assert manifest["model_policy"] == {
        "secretary": "native_or_kimmizo_auto_each_message_with_manual_fallback",
        "workers": "kimmizo_selects_automatically_from_live_host_catalog_per_task",
    }
    assert "Kimmizo Auto host extension" in agents_text
    assert "Launcher แยก" in agents_text
    assert "ให้บอสเลือกใน Codex" in agents_text
    assert "ผู้ช่วยเลือก Model/Reasoning ของลูกน้องอัตโนมัติ" in agents_text
    assert "ก่อนเริ่มงานแต่ละส่วน" in agents_text
    assert "ห้ามเดาชื่อโมเดล" in agents_text
    assert "แจ้งชื่อ Agent, Model และ Reasoning ก่อน spawn" in agents_text
    assert "เลขาคิม" not in agents_text
    assert "แทนตัวเองว่า “คิม”" not in agents_text
    secretary_skill = (
        project / ".agents" / "skills" / "kimmizo-secretary" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "เลขาคิม" not in secretary_skill
    assert "Refer to yourself as **คิม**" not in secretary_skill


def test_setup_blocks_when_tier0_prerequisite_is_missing(kimmizo, tmp_path, monkeypatch):
    project = tmp_path / "project"
    report = kimmizo.doctor(project)
    report["missing_tier0"] = ["git"]
    report["status"] = "degraded"
    monkeypatch.setattr(kimmizo, "doctor", lambda target: report)
    result = kimmizo.setup_project(project, skip_install=True)
    assert result["status"] == "blocked_missing_prerequisites"
    assert result["missing_tier0"] == ["git"]


def test_setup_is_idempotent_and_keeps_agent_identity(kimmizo, tmp_path):
    project = tmp_path / "project"
    first = kimmizo.setup_project(project, skip_install=True)
    before = read_json(project / ".kimmizo" / "team" / "identities.json")
    second = kimmizo.setup_project(project, skip_install=True)
    after = read_json(project / ".kimmizo" / "team" / "identities.json")

    assert first["status"] == "ready"
    assert second["actions"] == []
    assert before == after
    assert (project / "AGENTS.md").read_text(encoding="utf-8").count(
        "BEGIN KIMMIZO MANAGED BLOCK"
    ) == 1
    for agent in after["agents"]:
        profile_dir = project / ".kimmizo" / "team" / "profiles" / agent["name"]
        assert [p.name for p in profile_dir.glob("v*.json")] == ["v001.json"]


def test_managed_block_drift_is_backed_up_before_repair(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("orchestrator", "tampered-orchestrator", 1),
        encoding="utf-8",
    )
    result = kimmizo.setup_project(project, skip_install=True)
    assert result["managed_block_drifts"]
    backup = Path(result["managed_block_drifts"][0]["backup"])
    assert backup.is_file()
    assert "tampered-orchestrator" in backup.read_text(encoding="utf-8")
    assert "tampered-orchestrator" not in agents.read_text(encoding="utf-8")


def test_dry_run_reports_actions_without_creating_target(kimmizo, tmp_path):
    project = tmp_path / "future-project"
    result = kimmizo.setup_project(project, skip_install=True, dry_run=True)
    assert result["actions"]
    assert not project.exists()


def test_project_profile_recommends_only_matching_tier2(kimmizo, tmp_path, monkeypatch):
    project = tmp_path / "web-project"
    write(project / "package.json", '{"dependencies":{"openai":"latest","react":"latest"}}')
    write(project / "wrangler.toml", "name = 'worker'\n")
    write(project / ".github" / "workflows" / "ci.yml", "name: CI\n")
    (project / ".git").mkdir(parents=True)
    monkeypatch.setattr(kimmizo, "_git_commit_count", lambda target: 10)
    profile = kimmizo._detect_project(project)
    assert {"sites", "build-web-apps", "agent-browser", "cloudflare", "openai-developers", "codex-reviewer", "codebase-recon"} <= set(
        profile["tier2_recommendations"]
    )
    assert "supabase" not in profile["tier2_recommendations"]


def test_setup_hires_project_specific_specialists_with_new_ids(kimmizo, tmp_path):
    web = tmp_path / "web"
    write(web / "package.json", '{"dependencies":{"react":"latest"}}')
    kimmizo.setup_project(web, skip_install=True)
    web_ids = read_json(web / ".kimmizo" / "team" / "identities.json")["agents"]
    assert "web_specialist" in {item["role"] for item in web_ids}

    trading = tmp_path / "trading"
    write(trading / "expert.mq5", "// EA")
    kimmizo.setup_project(trading, skip_install=True)
    trading_ids = read_json(trading / ".kimmizo" / "team" / "identities.json")["agents"]
    assert "trading_specialist" in {item["role"] for item in trading_ids}
    assert {item["agent_id"] for item in web_ids}.isdisjoint(
        {item["agent_id"] for item in trading_ids}
    )


def test_profile_revision_changes_model_but_not_name_or_id(kimmizo, tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setattr(kimmizo, "_model_catalog", lambda config, home: fake_model_catalog())
    kimmizo.setup_project(project, skip_install=True)
    identities = read_json(project / ".kimmizo" / "team" / "identities.json")
    implementer = next(a for a in identities["agents"] if a["role"] == "implementer")

    result = kimmizo.update_team_profile(
        project,
        implementer["name"],
        {"model": "model-deep", "reasoning": "high", "personality": "calm"},
    )
    identities_after = read_json(project / ".kimmizo" / "team" / "identities.json")
    current = read_json(
        project / ".kimmizo" / "team" / "profiles" / implementer["name"] / "v002.json"
    )

    active_before_promotion = read_json(project / ".kimmizo" / "team" / "active.json")
    assert result["revision"] == 2
    assert result["status"] == "candidate_pending_evaluation"
    assert active_before_promotion["profiles"][implementer["name"]]["revision"] == 1
    assert identities_after == identities
    assert current["name"] == implementer["name"]
    assert current["agent_id"] == implementer["agent_id"]
    assert current["model"] == "model-deep"
    assert "model-deep" not in (
        project / ".codex" / "agents" / f"{implementer['name']}.toml"
    ).read_text(encoding="utf-8")

    promoted = kimmizo.evaluate_team_profile(
        project,
        implementer["name"],
        2,
        passed=True,
        evidence=["tests/team-eval.json"],
    )
    active_after = read_json(project / ".kimmizo" / "team" / "active.json")
    assert promoted["status"] == "promoted"
    assert active_after["profiles"][implementer["name"]]["revision"] == 2
    assert "model-deep" in (
        project / ".codex" / "agents" / f"{implementer['name']}.toml"
    ).read_text(encoding="utf-8")


def test_team_profile_rejects_unknown_model_and_reasoning(kimmizo, tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setattr(kimmizo, "_model_catalog", lambda config, home: fake_model_catalog())
    kimmizo.setup_project(project, skip_install=True)
    name = next(
        item["name"]
        for item in read_json(project / ".kimmizo" / "team" / "identities.json")["agents"]
        if item["role"] == "implementer"
    )

    with pytest.raises(ValueError, match="model"):
        kimmizo.update_team_profile(project, name, {"model": "no-such-model"})
    with pytest.raises(ValueError, match="reasoning"):
        kimmizo.update_team_profile(project, name, {"reasoning": "banana"})


def test_team_profile_revalidates_tampered_candidate_before_promotion(
    kimmizo, tmp_path, monkeypatch
):
    project = tmp_path / "project"
    monkeypatch.setattr(kimmizo, "_model_catalog", lambda config, home: fake_model_catalog())
    kimmizo.setup_project(project, skip_install=True)
    name = next(
        item["name"]
        for item in read_json(project / ".kimmizo" / "team" / "identities.json")["agents"]
        if item["role"] == "implementer"
    )
    kimmizo.update_team_profile(project, name, {"personality": "calm"})
    candidate_path = project / ".kimmizo" / "team" / "profiles" / name / "v002.json"
    candidate = read_json(candidate_path)
    candidate["model"] = "no-such-model"
    write(candidate_path, json.dumps(candidate))

    with pytest.raises(ValueError, match="model"):
        kimmizo.evaluate_team_profile(
            project, name, 2, passed=True, evidence=["tests/team-eval.json"]
        )


def test_team_profile_rejects_unknown_skill(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    name = read_json(project / ".kimmizo" / "team" / "identities.json")["agents"][0]["name"]
    with pytest.raises(ValueError):
        kimmizo.update_team_profile(project, name, {"allowed_skills": ["unknown-dangerous-skill"]})


def test_checkpoint_keeps_required_state_and_compact_mirror(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    payload = {
        "goal": "ส่ง feature ให้บอส",
        "status": "tests_passed",
        "boss_constraints": ["ห้ามทับไฟล์เดิม"],
        "decisions": ["ใช้ managed block"],
        "files": ["AGENTS.md"],
        "tests": ["pytest: pass"],
        "evidence": ["tests/report.json"],
        "blockers": [],
        "next_actions": ["review"],
    }
    result = kimmizo.write_checkpoint(project, payload)
    checkpoint = read_json(project / ".kimmizo" / "runtime" / "checkpoints" / "latest.json")
    mirror = (project / ".kimmizo" / "memory" / "current.md").read_text(encoding="utf-8")

    assert result["status"] == "checkpointed"
    for key in (
        "goal",
        "boss_constraints",
        "decisions",
        "files",
        "tests",
        "evidence",
        "blockers",
        "next_actions",
    ):
        assert key in checkpoint
    assert "ใช้ managed block" in mirror
    assert "AGENTS.md" in mirror
    assert len(mirror.splitlines()) <= 150


def test_context_packet_enforces_source_and_line_budgets(kimmizo):
    packet = kimmizo.build_context_packet(
        [{"path": f"file-{index}", "content": "one\ntwo"} for index in range(6)]
    )
    assert packet["source_count"] == 6
    assert packet["line_count"] == 12
    with pytest.raises(ValueError):
        kimmizo.build_context_packet(
            [{"path": f"file-{index}", "content": "x"} for index in range(7)]
        )
    with pytest.raises(ValueError):
        kimmizo.build_context_packet([{"path": "huge", "content": "\n".join(["x"] * 301)}])


def test_checkpoint_writes_are_serialized_and_atomic(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)

    def checkpoint(index):
        return kimmizo.write_checkpoint(
            project,
            {"goal": f"goal-{index}", "status": "running", "next_actions": [f"next-{index}"]},
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(checkpoint, range(12)))
    archives = list((project / ".kimmizo" / "runtime" / "checkpoints").glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))
    assert len(archives) == 13
    latest = read_json(project / ".kimmizo" / "runtime" / "checkpoints" / "latest.json")
    assert latest["goal"].startswith("goal-")
    assert not list(project.rglob("*.tmp"))


def test_learning_requires_evidence_root_cause_and_prevention(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    candidate = kimmizo.record_learning_candidate(
        project,
        {
            "title": "bad merge",
            "root_cause": "overwrote user file",
            "evidence": ["failure.log"],
            "prevention_test": "test_setup_preserves_user_files",
        },
    )
    promoted = kimmizo.promote_learning(project, candidate["candidate_id"])
    assert promoted["status"] == "promoted"
    assert (project / ".kimmizo" / "knowledge" / "lessons.jsonl").is_file()

    incomplete = kimmizo.record_learning_candidate(project, {"title": "unknown failure"})
    with pytest.raises(ValueError):
        kimmizo.promote_learning(project, incomplete["candidate_id"])


def test_personal_preference_memory_requires_boss_approval(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    with pytest.raises(PermissionError):
        kimmizo.record_learning_candidate(
            project,
            {"title": "Boss likes terse replies", "category": "personal_preference"},
        )
    approved = kimmizo.record_learning_candidate(
        project,
        {"title": "Boss likes terse replies", "category": "personal_preference"},
        allow_personal=True,
    )
    assert approved["status"] == "candidate"


def test_installer_gates_authority_and_unpinned_sources(kimmizo, tmp_path):
    report = {
        "install_plan": [
            {"id": "github", "current_state": "missing", "action": "request_system_approval", "restart": False},
            {"id": "domain-trading", "current_state": "missing", "action": "auto_install", "restart": False},
        ]
    }
    result = kimmizo.install_missing(tmp_path, report, dry_run=True)
    states = {item["id"]: item["status"] for item in result["results"]}
    assert states == {"github": "approval_required", "domain-trading": "blocked_unpinned"}


def test_implicit_using_superpowers_is_physically_disabled(kimmizo, tmp_path):
    home = tmp_path / "home"
    active = (
        home
        / ".codex"
        / "plugins"
        / "cache"
        / "openai-curated-remote"
        / "superpowers"
        / "6.1.1"
        / "skills"
        / "using-superpowers"
        / "SKILL.md"
    )
    write(active, "always-on body")

    first = kimmizo.enforce_implicit_superpowers_guard(home=home)
    second = kimmizo.enforce_implicit_superpowers_guard(home=home)

    assert first["status"] == "disabled"
    assert not active.exists()
    assert active.with_name("SKILL.md.kimmizo-disabled").read_text(encoding="utf-8") == "always-on body"
    assert second["status"] == "already_disabled"


def test_agent_browser_never_runs_unpinned_runtime_downloader(kimmizo):
    capability = next(
        item for item in kimmizo.load_registry()["capabilities"] if item["id"] == "agent-browser"
    )
    assert capability["install"]["commands"] == [
        ["npm", "install", "-g", "agent-browser@0.29.1"]
    ]
    assert capability["install"]["runtime_policy"] == "use_existing_system_browser"


def test_pinned_skill_installer_verifies_and_backs_up_legacy_copy(kimmizo, tmp_path, monkeypatch):
    capability_id = "grill-me"
    skill = b"---\nname: grill-me\n---\n# Sample\n"
    archive_stream = io.BytesIO()
    with zipfile.ZipFile(archive_stream, "w") as archive:
        archive.writestr("repo-commit/skills/grill-me/SKILL.md", skill)
        archive.writestr("repo-commit/skills/grill-me/references/note.md", "verified")
    archive_data = archive_stream.getvalue()
    monkeypatch.setattr(kimmizo, "_download_pinned_archive", lambda url, expected: archive_data)

    home = tmp_path / "home"
    write(home / ".codex" / "skills" / capability_id / "SKILL.md", "old")
    install = {
        "archive_url": "https://codeload.github.com/example/repo/zip/commit",
        "archive_sha256": hashlib.sha256(archive_data).hexdigest(),
        "skill_subpath": "skills/grill-me",
    }
    lock = {"sha256": hashlib.sha256(skill).hexdigest()}
    result = kimmizo._install_pinned_skill(capability_id, install, lock, home=home)

    assert len(result["installed_targets"]) == 2
    assert (home / ".agents" / "skills" / capability_id / "SKILL.md").read_bytes() == skill
    assert (home / ".codex" / "skills" / capability_id / "SKILL.md").read_bytes() == skill
    assert result["backups"]

    project = tmp_path / "project"
    receipt = project / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
    write(
        receipt,
        json.dumps(
            {"id": capability_id, "status": "installed", "installation": result},
            ensure_ascii=False,
        ),
    )
    rollback = kimmizo.rollback_capability(project, capability_id, home=home)
    assert rollback["status"] == "rolled_back"
    assert not (home / ".agents" / "skills" / capability_id).exists()
    assert (home / ".codex" / "skills" / capability_id / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "old"


def test_pinned_skill_install_is_transactional(kimmizo, tmp_path, monkeypatch):
    capability_id = "grill-me"
    skill = b"---\nname: grill-me\n---\n# New\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("repo/skills/grill-me/SKILL.md", skill)
    monkeypatch.setattr(kimmizo, "_download_pinned_archive", lambda url, expected: stream.getvalue())
    home = tmp_path / "home"
    legacy = home / ".codex" / "skills" / capability_id / "SKILL.md"
    write(legacy, "old")
    real_replace = kimmizo.os.replace
    calls = {"count": 0}

    def fail_second(source, destination):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated second-target failure")
        return real_replace(source, destination)

    monkeypatch.setattr(kimmizo.os, "replace", fail_second)
    with pytest.raises(OSError):
        kimmizo._install_pinned_skill(
            capability_id,
            {
                "archive_url": "https://codeload.github.com/example/repo/zip/commit",
                "archive_sha256": "unused",
                "skill_subpath": "skills/grill-me",
            },
            {"sha256": hashlib.sha256(skill).hexdigest()},
            home=home,
        )
    assert legacy.read_text(encoding="utf-8") == "old"
    assert not (home / ".agents" / "skills" / capability_id).exists()


def test_pinned_skill_rollback_copy_failure_preserves_current(kimmizo, tmp_path, monkeypatch):
    capability_id = "grill-me"
    home = tmp_path / "home"
    current = home / ".agents" / "skills" / capability_id
    backup = home / ".agents" / "skills" / ".kimmizo-backups" / capability_id / "stamp" / "target-0"
    write(current / "SKILL.md", "current")
    write(backup / "SKILL.md", "old")
    project = tmp_path / "project"
    receipt = project / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
    write(
        receipt,
        json.dumps(
            {
                "id": capability_id,
                "status": "installed",
                "installation": {
                    "rollback_entries": [
                        {
                            "target": str(current),
                            "backup": str(backup),
                            "backup_type": "directory",
                        }
                    ]
                },
            }
        ),
    )
    real_copytree = kimmizo.shutil.copytree

    def fail_stage(source, destination, *args, **kwargs):
        if Path(source) == backup:
            raise OSError("simulated staging failure")
        return real_copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(kimmizo.shutil, "copytree", fail_stage)
    with pytest.raises(OSError, match="staging failure"):
        kimmizo.rollback_capability(project, capability_id, home=home)
    assert (current / "SKILL.md").read_text(encoding="utf-8") == "current"


def test_plugin_rollback_restores_exact_previous_config_and_cache(kimmizo, tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    config = home / ".codex" / "config.toml"
    cache_root = home / ".codex" / "plugins" / "cache" / "openai-bundled" / "browser"
    write(config, '# before\n[plugins."browser@openai-bundled"]\nenabled = false\n')
    write(cache_root / "old" / "payload.txt", "old package")

    snapshot = kimmizo._capture_plugin_snapshot(
        project,
        "browser",
        kimmizo._registry_by_id()["browser"],
        home=home,
    )
    write(config, '# after\n[plugins."browser@openai-bundled"]\nenabled = true\n')
    kimmizo._remove_path_safely(cache_root, cache_root.parent)
    write(cache_root / "new" / "payload.txt", "new package")
    snapshot["post_config_sha256"] = kimmizo.sha256_file(config)

    receipt = project / ".kimmizo" / "capabilities" / "receipts" / "browser.json"
    write(
        receipt,
        json.dumps(
            {
                "id": "browser",
                "status": "installed",
                    "rollback": {
                        "method": "restore_plugin_snapshot",
                        "selector": "browser@openai-bundled",
                        "snapshot": snapshot,
                    },
            }
        ),
    )

    result = kimmizo.rollback_capability(project, "browser", home=home)
    assert result["status"] == "rolled_back"
    assert config.read_text(encoding="utf-8").startswith("# before")
    assert (cache_root / "old" / "payload.txt").read_text(encoding="utf-8") == "old package"
    assert not (cache_root / "new").exists()


def test_secret_redaction_covers_receipt_patterns(kimmizo):
    value = "Bearer abc.def token=secret123 api_key:xyz github_pat_abcdefghijklmnopqrstuvwxyz"
    redacted = kimmizo.redact_secrets(value)
    assert "abc.def" not in redacted
    assert "secret123" not in redacted
    assert "xyz" not in redacted
    assert "github_pat_" not in redacted


def test_restart_install_checkpoints_before_running(kimmizo, tmp_path, monkeypatch):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    monkeypatch.setattr(kimmizo.shutil, "which", lambda command: command)
    monkeypatch.setattr(
        kimmizo.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    browser_root = (
        Path.home()
        / ".codex"
        / ".tmp"
        / "bundled-marketplaces"
        / "openai-bundled"
        / "plugins"
        / "browser"
    )
    monkeypatch.setattr(
        kimmizo,
        "_host_plugin_inventory",
        lambda *args, **kwargs: {
            "browser@openai-bundled": {
                "selector": "browser@openai-bundled",
                "state": "enabled",
                "version": "26.707.31428",
                "manifest_version": "26.707.31428",
                "path": str(browser_root),
            }
        },
    )
    monkeypatch.setattr(
        kimmizo,
        "_capture_plugin_snapshot",
        lambda *args, **kwargs: {
            "selector": "browser@openai-bundled",
            "home": str(Path.home().resolve()),
            "snapshot_root": str(project / ".kimmizo" / "capabilities" / "receipts" / "backups" / "test"),
            "config": {"original": str(Path.home() / ".codex" / "config.toml"), "existed": False},
            "cache_roots": [],
        },
    )
    monkeypatch.setattr(
        kimmizo,
        "_preflight_plugin_install",
        lambda *args, **kwargs: {"ok": True, "status": "verified"},
    )
    report = {
        "install_plan": [
            {"id": "browser", "current_state": "missing", "action": "auto_install", "restart": True}
        ]
    }
    result = kimmizo.install_missing(project, report)
    assert result["restart_required"] is True
    latest = read_json(project / ".kimmizo" / "runtime" / "checkpoints" / "latest.json")
    assert latest["status"] == "before_restart_capability_install"
    assert (project / ".kimmizo" / "capabilities" / "receipts" / "browser.json").is_file()


def test_two_verification_failures_roll_back_profile(kimmizo, tmp_path, monkeypatch):
    monkeypatch.setattr(kimmizo, "_model_catalog", lambda *args, **kwargs: fake_model_catalog())
    monkeypatch.setattr(kimmizo, "_project_model_catalog", lambda *args, **kwargs: fake_model_catalog())
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    identities = read_json(project / ".kimmizo" / "team" / "identities.json")
    agent = next(item for item in identities["agents"] if item["role"] == "implementer")
    kimmizo.update_team_profile(project, agent["name"], {"personality": "candidate personality"})
    kimmizo.evaluate_team_profile(project, agent["name"], 2, passed=True, evidence=["eval-pass"])
    first = kimmizo.record_agent_outcome(project, agent["name"], verification_passed=False)
    second = kimmizo.record_agent_outcome(project, agent["name"], verification_passed=False)
    active = read_json(project / ".kimmizo" / "team" / "active.json")
    assert first["rollback"] is False
    assert second["rollback"] is True
    assert active["profiles"][agent["name"]]["revision"] == 1


def test_tampered_active_profile_path_cannot_escape_project(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    active_path = project / ".kimmizo" / "team" / "active.json"
    active = read_json(active_path)
    name = next(iter(active["profiles"]))
    active["profiles"][name]["path"] = "../../outside.json"
    write(active_path, json.dumps(active))
    with pytest.raises(ValueError):
        kimmizo.setup_project(project, skip_install=True)
    assert not (project / "outside.json").exists()


def test_user_controlled_ids_cannot_traverse_paths(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    with pytest.raises(ValueError):
        kimmizo.record_agent_outcome(project, "../../escape", verification_passed=False)
    with pytest.raises(ValueError):
        kimmizo.promote_learning(project, "../../escape")
    with pytest.raises(ValueError):
        kimmizo.rollback_capability(project, "../../escape")
    assert not (tmp_path / "escape.json").exists()


def test_repair_restores_managed_artifacts_without_deleting_memory(kimmizo, tmp_path):
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    write(project / ".kimmizo" / "memory" / "boss-note.md", "keep forever")
    (project / ".agents" / "skills" / "kimmizo-memory" / "SKILL.md").unlink()

    result = kimmizo.repair_project(project)

    assert result["status"] == "repaired"
    assert (project / ".agents" / "skills" / "kimmizo-memory" / "SKILL.md").is_file()
    assert (project / ".kimmizo" / "memory" / "boss-note.md").read_text(
        encoding="utf-8"
    ) == "keep forever"


def test_cli_contract_outputs_json(kimmizo, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(kimmizo, "_model_catalog", lambda *args, **kwargs: fake_model_catalog())
    monkeypatch.setattr(kimmizo, "_project_model_catalog", lambda *args, **kwargs: fake_model_catalog())
    project = tmp_path / "project"
    assert kimmizo.main(["setup", "--target", str(project), "--skip-install", "--json"]) == 0
    setup_output = json.loads(capsys.readouterr().out)
    assert setup_output["status"] == "ready"

    assert kimmizo.main(["route", "--target", str(project), "--task", "ตรวจ auth", "--json"]) == 0
    route_output = json.loads(capsys.readouterr().out)
    assert "codex-security" in route_output["capabilities"]
    assert route_output["model_recommendation"]["model"]
    assert route_output["model_recommendation"]["reasoning"] in {"high", "xhigh", "max", "ultra"}
    assert route_output["secretary_model_advice"]["selection_mode"] == "boss_changes_manually"
    assert route_output["secretary_model_advice"]["ui_model_mode"] == "specific"
    assert route_output["secretary_model_advice"]["notify_before_start"] is True
    assert route_output["worker_model_selection"]["selection_mode"] == "automatic_by_kimmizo"

    identities = read_json(project / ".kimmizo" / "team" / "identities.json")
    name = next(item["name"] for item in identities["agents"] if item["role"] == "explorer")
    assert (
        kimmizo.main(
            [
                "team-update",
                "--target",
                str(project),
                "--name",
                name,
                "--reasoning",
                "medium",
                "--json",
            ]
        )
        == 0
    )
    update_output = json.loads(capsys.readouterr().out)
    assert update_output["revision"] == 2

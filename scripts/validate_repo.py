#!/usr/bin/env python3
"""Dependency-free repository, plugin, registry and capsule validator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "kimmizo-setup"
ENTRYPOINT = PLUGIN / "scripts" / "kimmizo.py"
V2_RUNTIME = PLUGIN / "scripts" / "kimmizo_v2" / "capsule.py"
VENDOR = PLUGIN / "vendor" / "kimweaver"


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    required = [
        ROOT / "install.ps1",
        ROOT / ".agents" / "plugins" / "marketplace.json",
        PLUGIN / ".codex-plugin" / "plugin.json",
        PLUGIN / "registry" / "capabilities.json",
        PLUGIN / "registry" / "baseline-lock.json",
        PLUGIN / "registry" / "conflicts.json",
        PLUGIN / "skills" / "kimmizo-setup" / "SKILL.md",
        PLUGIN / "templates" / "project-capsule" / "BOOT.md",
        PLUGIN / "templates" / "project-capsule" / "AGENTS.v2.block.md",
        V2_RUNTIME,
        VENDOR / "SKILL.md",
        VENDOR / "references" / "contracts.md",
        VENDOR / "references" / "runtime-smoke-test.md",
        VENDOR / "references" / "v2-contracts.md",
        VENDOR / "bootstrap" / "model-policy.json",
        VENDOR / "bootstrap" / "voice-bootstrap.json",
        ENTRYPOINT,
    ]
    for path in required:
        if not path.is_file():
            fail(f"missing required file: {path.relative_to(ROOT)}", errors)

    json_files = list(ROOT.rglob("*.json"))
    parsed: dict[Path, object] = {}
    for path in json_files:
        try:
            parsed[path] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            fail(f"invalid JSON {path.relative_to(ROOT)}: {error}", errors)

    plugin_path = PLUGIN / ".codex-plugin" / "plugin.json"
    plugin = parsed.get(plugin_path, {})
    if isinstance(plugin, dict) and not str(plugin.get("version", "")).startswith("1.0.0"):
        fail("plugin version must keep the 1.0.0 stable base", errors)

    registry_path = PLUGIN / "registry" / "capabilities.json"
    lock_path = PLUGIN / "registry" / "baseline-lock.json"
    registry = parsed.get(registry_path, {})
    lock = parsed.get(lock_path, {})
    if isinstance(registry, dict) and isinstance(lock, dict):
        capabilities = registry.get("capabilities", [])
        ids = [item.get("id") for item in capabilities if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            fail("capability ids must be unique", errors)
        locked = {item.get("id") for item in lock.get("entries", []) if isinstance(item, dict)}
        missing_locks = [item["id"] for item in capabilities if item.get("tier") == 1 and item.get("id") not in locked]
        if missing_locks:
            fail(f"Tier 1 capabilities missing from baseline lock: {missing_locks}", errors)
        missing_tier2_locks = [
            item["id"]
            for item in capabilities
            if item.get("tier") == 2
            and item.get("kind") != "domain_policy"
            and (item.get("install") or {}).get("command") or (item.get("install") or {}).get("commands")
            if item.get("id") not in locked
        ]
        if missing_tier2_locks:
            fail(f"Auto-installable Tier 2 capabilities missing from lock: {missing_tier2_locks}", errors)
        for lock_entry in lock.get("entries", []):
            missing = [key for key in ("source", "version", "integrity") if not lock_entry.get(key)]
            if missing:
                fail(f"lock entry {lock_entry.get('id')} lacks {missing}", errors)
        for item in capabilities:
            install = item.get("install")
            if install is not None and "approval" not in install:
                fail(f"installer lacks explicit approval policy: {item.get('id')}", errors)

    expected_adapters = {"software", "research", "document-data", "secretary-coordination"}
    required_adapter_fields = {
        "id",
        "version",
        "required_skills",
        "risk_overrides",
        "acceptance_template",
        "context_policy",
        "verification_profile",
        "external_action_types",
    }
    adapter_paths = sorted((VENDOR / "adapters").glob("*.json"))
    adapters = {path.stem: parsed.get(path) for path in adapter_paths}
    if set(adapters) != expected_adapters:
        fail("Kimweaver vendor must contain the four canonical adapters", errors)
    for adapter_id, adapter in adapters.items():
        if not isinstance(adapter, dict):
            fail(f"invalid Kimweaver adapter: {adapter_id}", errors)
            continue
        if adapter.get("id") != adapter_id or adapter.get("version") != "2.0.0":
            fail(f"invalid Kimweaver adapter identity/version: {adapter_id}", errors)
        missing = required_adapter_fields - set(adapter)
        if missing:
            fail(f"Kimweaver adapter {adapter_id} misses {sorted(missing)}", errors)

    expected_schemas = {
        "assignment.schema.json",
        "evidence-receipt.schema.json",
        "review-packet.schema.json",
        "routing-decision.schema.json",
        "task-checkpoint.schema.json",
        "task-envelope.schema.json",
    }
    schema_paths = sorted((VENDOR / "schemas").glob("*.json"))
    if {path.name for path in schema_paths} != expected_schemas:
        fail("Kimweaver vendor schema set is incomplete", errors)
    for path in schema_paths:
        schema = parsed.get(path)
        if not isinstance(schema, dict) or schema.get("schema_version") != 2 or not schema.get("$schema"):
            fail(f"invalid Kimweaver vendor schema: {path.relative_to(ROOT)}", errors)

    vendor_policy = VENDOR / "bootstrap" / "model-policy.json"
    registry_policy = PLUGIN / "registry" / "model-policy.json"
    if vendor_policy.is_file() and registry_policy.is_file() and vendor_policy.read_bytes() != registry_policy.read_bytes():
        fail("Kimweaver vendor policy must match registry/model-policy.json byte-for-byte", errors)
    voice_template = parsed.get(VENDOR / "bootstrap" / "voice-bootstrap.json")
    if not isinstance(voice_template, dict) or voice_template.get("schemaVersion") != 2:
        fail("invalid Kimweaver vendor voice bootstrap", errors)

    skill_paths = list(PLUGIN.rglob("SKILL.md"))
    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            fail(f"invalid skill frontmatter: {path.relative_to(ROOT)}", errors)
        if "TODO" in text:
            fail(f"unfinished TODO in skill: {path.relative_to(ROOT)}", errors)

    boot_path = PLUGIN / "templates" / "project-capsule" / "BOOT.md"
    if boot_path.is_file() and len(boot_path.read_text(encoding="utf-8").splitlines()) > 150:
        fail("BOOT template exceeds 150 lines", errors)

    agents_v2_path = PLUGIN / "templates" / "project-capsule" / "AGENTS.v2.block.md"
    if agents_v2_path.is_file():
        agents_v2 = agents_v2_path.read_text(encoding="utf-8")
        if agents_v2.count("BEGIN KIMWEAVER-V2-MANAGED") != 1 or agents_v2.count("END KIMWEAVER-V2-MANAGED") != 1:
            fail("AGENTS v2 template must contain one distinct managed block", errors)

    forbidden_paths = {
        "D:" + "\\TK-Project\\" + "เลขาคิม",
        "D:" + "/TK-Project/" + "เลขาคิม",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix in {".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if any(forbidden.casefold() in text.casefold() for forbidden in forbidden_paths):
            fail(f"forbidden Home Base path in {path.relative_to(ROOT)}", errors)

    try:
        compile(ENTRYPOINT.read_text(encoding="utf-8"), str(ENTRYPOINT), "exec")
        compile(V2_RUNTIME.read_text(encoding="utf-8"), str(V2_RUNTIME), "exec")
        spec = importlib.util.spec_from_file_location("kimmizo_validate", ENTRYPOINT)
        if not spec or not spec.loader:
            raise RuntimeError("could not create module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        routed = module.route_task("เปิดโปรแกรม Windows ที่ไม่มี API")
        if "computer-use" not in routed["capabilities"] or "community-computer-use" in routed["capabilities"]:
            fail("Windows Computer Use routing smoke test failed", errors)
        v2 = module._load_v2_package()
        if not callable(v2.capsule_status) or not callable(v2.materialize_capsule):
            fail("v2 capsule public facade is unavailable", errors)
    except Exception as error:  # validator should aggregate the failure
        fail(f"entrypoint validation failed: {error}", errors)

    if errors:
        print("Kimmizo validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Kimmizo validation passed: {len(json_files)} JSON files, {len(skill_paths)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

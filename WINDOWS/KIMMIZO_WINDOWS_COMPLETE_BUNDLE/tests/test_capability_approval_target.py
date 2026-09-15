from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "kimmizo.py"


def load_kimmizo():
    spec = importlib.util.spec_from_file_location("kimmizo_capability_target_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def enabled_data_analytics_plugin(tmp_path: Path) -> dict[str, dict[str, str]]:
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
    return {
        "data-analytics@openai-curated": {
            "selector": "data-analytics@openai-curated",
            "state": "enabled",
            "version": "0.2.8",
            "path": str(plugin),
        }
    }


def test_capability_approval_receipt_is_project_local_and_consumed_by_doctor(tmp_path):
    """Catches approval adoption that ignores --target and writes machine-global state."""
    kimmizo = load_kimmizo()
    target = tmp_path / "project"
    host_plugins = enabled_data_analytics_plugin(tmp_path)

    granted = kimmizo.grant_capability_approval(
        "data-analytics",
        target=target,
        host_plugins=host_plugins,
    )

    expected = target / ".kimmizo" / "capabilities" / "receipts" / "approval-data-analytics.json"
    assert Path(granted["path"]) == expected
    assert expected.is_file()
    doctor = kimmizo.doctor(target, home=tmp_path / "home", host_plugins=host_plugins)
    assert "data-analytics" in doctor["approved_capabilities"]


def test_capability_approve_cli_passes_target_to_receipt_writer(tmp_path, monkeypatch, capsys):
    """Catches the CLI accepting --target while silently adopting approval elsewhere."""
    kimmizo = load_kimmizo()
    target = tmp_path / "project"
    observed: dict[str, Path | None] = {"target": None}

    def safe_receipt_writer(capability_id: str, *, target: str | Path | None = None, **_kwargs):
        observed["target"] = Path(target).resolve() if target is not None else None
        return {
            "status": "host_approval_adopted",
            "id": capability_id,
            "path": str(
                observed["target"]
                / ".kimmizo"
                / "capabilities"
                / "receipts"
                / f"approval-{capability_id}.json"
            )
            if observed["target"] is not None
            else "missing-target",
        }

    monkeypatch.setattr(kimmizo, "grant_capability_approval", safe_receipt_writer)

    assert (
        kimmizo.main(
            [
                "capability-approve",
                "--target",
                str(target),
                "--id",
                "data-analytics",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert observed["target"] == target.resolve()
    assert Path(result["path"]).parent == target / ".kimmizo" / "capabilities" / "receipts"


def test_capability_approval_rejects_receipt_root_that_resolves_outside_project(tmp_path):
    """Catches project-local approval writes escaping through a symlinked receipt directory."""
    kimmizo = load_kimmizo()
    target = tmp_path / "project"
    outside = tmp_path / "outside"
    receipts = target / ".kimmizo" / "capabilities" / "receipts"
    receipts.parent.mkdir(parents=True)
    outside.mkdir()
    try:
        receipts.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("directory symlinks are unavailable")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(receipts), str(outside)],
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip("directory junctions are unavailable")
    try:
        with pytest.raises(PermissionError, match="escapes the project"):
            kimmizo.grant_capability_approval(
                "data-analytics",
                target=target,
                host_plugins=enabled_data_analytics_plugin(tmp_path),
            )
        assert not (outside / "approval-data-analytics.json").exists()
    finally:
        if receipts.is_symlink():
            receipts.unlink()
        elif receipts.exists():
            os.rmdir(receipts)


def test_capability_approval_refuses_linked_receipt_leaf_targeting_project_authority(tmp_path):
    """Catches an approval receipt overwriting AGENTS.md through an in-project hard link."""
    kimmizo = load_kimmizo()
    target = tmp_path / "project"
    agents = target / "AGENTS.md"
    write(agents, "# Project authority\nDo not replace.\n")
    original = agents.read_bytes()
    receipt = target / ".kimmizo" / "capabilities" / "receipts" / "approval-data-analytics.json"
    receipt.parent.mkdir(parents=True)
    os.link(agents, receipt)

    with pytest.raises(PermissionError, match="linked|owned receipt"):
        kimmizo.grant_capability_approval(
            "data-analytics",
            target=target,
            host_plugins=enabled_data_analytics_plugin(tmp_path),
        )

    assert agents.read_bytes() == original

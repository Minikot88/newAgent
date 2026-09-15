from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "kimmizo.py"


def load_kimmizo():
    spec = importlib.util.spec_from_file_location("kimmizo_setup_transaction_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def kimmizo():
    return load_kimmizo()


def tree_bytes(path: Path):
    """Fingerprint existence and raw bytes without following a linked directory."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return ("missing",)
    is_reparse = bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    if stat.S_ISLNK(info.st_mode) or is_reparse:
        return ("linked",)
    if stat.S_ISDIR(info.st_mode):
        return (
            "directory",
            tuple((child.name, tree_bytes(child)) for child in sorted(path.iterdir(), key=lambda item: item.name)),
        )
    if stat.S_ISREG(info.st_mode):
        return ("file", path.read_bytes())
    return ("other", info.st_mode)


def make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.skip("directory symlinks are unavailable")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("directory junctions are unavailable")


def remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        os.rmdir(link)


def setup_publication_state(project: Path) -> dict[str, object]:
    """Capture every v1/v2 setup publication root, excluding v2's transient staging area."""
    paths = (
        "AGENTS.md",
        ".gitignore",
        ".codex",
        ".agents/skills",
        ".kimmizo/BOOT.md",
        ".kimmizo/manifest.json",
        ".kimmizo/project-profile.json",
        ".kimmizo/capabilities",
        ".kimmizo/knowledge",
        ".kimmizo/team",
        ".kimmizo/runtime",
        ".kimmizo/voice-bootstrap.json",
        ".kimmizo/core/manifest.json",
        ".kimmizo/core/migration.json",
        ".kimmizo/core/runtime/kimmizo_v2",
        ".kimmizo/core/revisions",
    )
    return {relative: tree_bytes(project / relative) for relative in paths}


@pytest.mark.parametrize("relative", ("AGENTS.md", ".codex/config.toml", ".gitignore"))
@pytest.mark.parametrize("link_kind", ("symlink", "hardlink"))
def test_setup_rejects_linked_authority_leaf_before_any_other_project_write(
    kimmizo, tmp_path, relative, link_kind
):
    """Catches setup following a linked authority leaf before it has changed another project file."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / f"outside-{relative.replace('/', '-')}.txt"
    outside.write_bytes(b"outside authority bytes\n")
    leaf = project / relative
    leaf.parent.mkdir(parents=True, exist_ok=True)
    if link_kind == "symlink":
        try:
            leaf.symlink_to(outside)
        except OSError:
            pytest.skip("file symlinks are unavailable")
    else:
        os.link(outside, leaf)
    before_project = tree_bytes(project)
    before_outside = outside.read_bytes()

    with pytest.raises(PermissionError, match="linked|reparse|regular|owned|authority"):
        kimmizo.setup_project(project, skip_install=True)

    assert tree_bytes(project) == before_project
    assert outside.read_bytes() == before_outside


@pytest.mark.parametrize("relative", ("AGENTS.md", ".codex/config.toml", ".gitignore"))
def test_setup_rejects_authority_file_when_the_target_parent_is_a_linked_directory(
    kimmizo, tmp_path, relative
):
    """Catches resolve() hiding a symlink/junction parent before setup writes authority files."""
    actual_project = tmp_path / "actual-project"
    actual_project.mkdir()
    linked_project = tmp_path / "linked-project"
    make_directory_link(linked_project, actual_project)
    before = tree_bytes(actual_project)
    try:
        with pytest.raises(PermissionError, match="linked|reparse|authority|target"):
            kimmizo.setup_project(linked_project, skip_install=True)

        assert tree_bytes(actual_project) == before
    finally:
        remove_directory_link(linked_project)


def test_setup_rejects_config_under_a_linked_dot_codex_parent_before_other_writes(kimmizo, tmp_path):
    """Catches a project-local junction that redirects only the .codex authority subtree."""
    project = tmp_path / "project"
    outside = tmp_path / "outside-codex"
    project.mkdir()
    outside.mkdir()
    codex = project / ".codex"
    make_directory_link(codex, outside)
    before_project = tree_bytes(project)
    before_outside = tree_bytes(outside)
    try:
        with pytest.raises(PermissionError, match="linked|reparse|authority|config"):
            kimmizo.setup_project(project, skip_install=True)

        assert tree_bytes(project) == before_project
        assert tree_bytes(outside) == before_outside
    finally:
        remove_directory_link(codex)


def test_setup_rechecks_the_lexical_target_after_an_initial_guard_then_junction_swap(
    kimmizo, tmp_path, monkeypatch
):
    """Catches resolve() hiding a target junction inserted immediately after the first target guard."""
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    before_outside = tree_bytes(outside)
    original_guard = kimmizo._assert_setup_target_safe

    def swap_target_after_guard(path):
        guarded = original_guard(path)
        os.rmdir(project)
        make_directory_link(project, outside)
        return guarded

    monkeypatch.setattr(kimmizo, "_assert_setup_target_safe", swap_target_after_guard)
    try:
        with pytest.raises(PermissionError, match="linked|reparse|target"):
            kimmizo.setup_project(project, skip_install=True)

        assert tree_bytes(outside) == before_outside
    finally:
        remove_directory_link(project)


def test_unowned_v2_conflict_rolls_back_every_v1_setup_path(kimmizo, tmp_path):
    """Catches v1 setup files being published before a v2 ownership conflict is discovered."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    assert kimmizo.rollback_core_capsule(project)["status"] == "removed"

    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("orchestrator", "tampered-orchestrator", 1),
        encoding="utf-8",
    )
    unowned = project / ".agents" / "skills" / "kimweaver" / "SKILL.md"
    unowned.parent.mkdir(parents=True, exist_ok=True)
    unowned.write_bytes(b"unowned v2 skill\n")
    before = tree_bytes(project)

    with pytest.raises(ValueError, match="capsule_conflict.*unowned v2"):
        kimmizo.setup_project(project, skip_install=True)

    assert tree_bytes(project) == before


def test_setup_activation_failure_restores_preexisting_v1_and_v2_bytes(kimmizo, tmp_path, monkeypatch):
    """Catches a v2 activation error leaving any v1 or v2 publish path changed by this setup call."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)

    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("orchestrator", "tampered-orchestrator", 1),
        encoding="utf-8",
    )
    voice = project / ".kimmizo" / "voice-bootstrap.json"
    voice.write_bytes(voice.read_bytes() + b"\ncorrupted preexisting v2 bytes\n")
    before = setup_publication_state(project)
    v2 = kimmizo._load_v2_package()

    def fail_activation(*_args, **_kwargs):
        raise OSError("injected activation failure")

    monkeypatch.setattr(v2.capsule, "_activate_candidate", fail_activation)
    with pytest.raises(OSError, match="injected activation failure"):
        kimmizo.setup_project(project, skip_install=True, repair_capsule=True)

    assert setup_publication_state(project) == before


def test_setup_rollback_preserves_a_concurrent_authority_edit_and_reports_divergence(
    kimmizo, tmp_path, monkeypatch
):
    """Catches rollback overwriting a user edit made after setup's v1 snapshot and before v2 failure."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)

    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("orchestrator", "tampered-orchestrator", 1),
        encoding="utf-8",
    )
    voice = project / ".kimmizo" / "voice-bootstrap.json"
    voice.write_bytes(voice.read_bytes() + b"\ncorrupted preexisting v2 bytes\n")
    concurrent_bytes = b"# Concurrent user authority edit\nDo not overwrite.\n"
    v2 = kimmizo._load_v2_package()

    def concurrent_edit_then_fail(*_args, **_kwargs):
        agents.write_bytes(concurrent_bytes)
        raise OSError("injected activation failure")

    monkeypatch.setattr(v2.capsule, "_activate_candidate", concurrent_edit_then_fail)
    with pytest.raises(RuntimeError, match="rollback.*diverged.*preserved"):
        kimmizo.setup_project(project, skip_install=True, repair_capsule=True)

    assert agents.read_bytes() == concurrent_bytes
    assert voice.read_bytes().endswith(b"corrupted preexisting v2 bytes\n")


def test_setup_refuses_to_steal_an_old_initial_checkpoint_lock(kimmizo, tmp_path):
    """Catches setup removing a stale live/sentinel checkpoint lock before later activation can fail."""
    project = tmp_path / "project"
    lock = project / ".kimmizo" / "runtime" / "checkpoints" / ".checkpoint.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"live owner sentinel\n")
    old = time.time() - 120
    os.utime(lock, (old, old))
    before = tree_bytes(project)

    with pytest.raises(TimeoutError, match="refuses to steal.*checkpoint lock"):
        kimmizo.setup_project(project, skip_install=True)

    assert tree_bytes(project) == before
    assert lock.read_bytes() == b"live owner sentinel\n"

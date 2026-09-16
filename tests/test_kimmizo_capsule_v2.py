from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "kimmizo.py"
POLICY_PATH = ROOT / "plugins" / "kimmizo-setup" / "registry" / "model-policy.json"


def load_kimmizo():
    spec = importlib.util.spec_from_file_location("kimmizo_capsule_v2_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def kimmizo():
    return load_kimmizo()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_hash(files: dict[str, str]) -> str:
    # This literal projection catches an implementation that omits a file or
    # computes an aggregate from decoded/reformatted content rather than bytes.
    payload = "".join(f"{relative}:{files[relative]}\n" for relative in sorted(files))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def v2_agents_block(data: bytes) -> bytes:
    begin = b"<!-- BEGIN KIMWEAVER-V2-MANAGED -->"
    end = b"<!-- END KIMWEAVER-V2-MANAGED -->"
    start = data.index(begin)
    stop = data.index(end, start) + len(end)
    return data[start:stop]


def replace_v2_agents_block(data: bytes, block: bytes) -> bytes:
    begin = b"<!-- BEGIN KIMWEAVER-V2-MANAGED -->"
    end = b"<!-- END KIMWEAVER-V2-MANAGED -->"
    start = data.index(begin)
    stop = data.index(end, start) + len(end)
    return data[:start] + block + data[stop:]


def test_setup_materializes_a_self_contained_hash_verified_capsule(kimmizo, tmp_path):
    """Catches setup that leaves v2 dependent on its source package or misses a copied owned file."""
    project = tmp_path / "project"

    result = kimmizo.setup_project(project, skip_install=True)

    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    manifest = read_json(manifest_path)
    expected_project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{project.resolve()}"))
    assert result["core_capsule"]["status"] == "active"
    assert result["project_id"] == expected_project_id
    assert read_json(project / ".kimmizo" / "manifest.json")["project_id"] == expected_project_id
    assert manifest["project_id"] == expected_project_id
    assert manifest["schema"] == "kimmizo-capsule-v2"
    assert manifest["lifecycle"] == "active"
    assert manifest["aggregate_sha256"] == aggregate_hash(manifest["file_hashes"])
    assert manifest["file_hashes"]
    for relative, expected in manifest["file_hashes"].items():
        assert raw_sha256(project / relative) == expected

    runtime_capsule = project / ".kimmizo" / "core" / "runtime" / "kimmizo_v2" / "capsule.py"
    assert runtime_capsule.is_file()
    assert (project / ".agents" / "skills" / "kimweaver" / "SKILL.md").is_file()
    assert (project / ".kimmizo" / "voice-bootstrap.json").is_file()

    # Load only the copied runtime. Its validation path must not need the setup
    # package, vendor tree, or any external Kimweaver source.
    runtime_spec = importlib.util.spec_from_file_location("project_runtime_capsule", runtime_capsule)
    assert runtime_spec and runtime_spec.loader
    runtime = importlib.util.module_from_spec(runtime_spec)
    runtime_spec.loader.exec_module(runtime)
    assert runtime.capsule_status(project)["status"] == "healthy"


def test_runtime_bytecode_cache_does_not_invalidate_a_verified_capsule(kimmizo, tmp_path):
    """Catches Linux import caches being mistaken for unowned capsule files."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    cache = project / ".kimmizo" / "core" / "runtime" / "kimmizo_v2" / "__pycache__"
    cache.mkdir()
    (cache / "capsule.cpython-313.pyc").write_bytes(b"generated-bytecode-cache")

    assert kimmizo.capsule_status(project)["status"] == "healthy"


def test_v2_capsule_contains_all_adapter_contracts_and_local_voice_policy(kimmizo, tmp_path):
    """Catches a partial capsule with an adapter contract or voice bootstrap missing from the local payload."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)

    adapter_root = project / ".agents" / "skills" / "kimweaver" / "adapters"
    expected_ids = {"software", "research", "document-data", "secretary-coordination"}
    assert {path.stem for path in adapter_root.glob("*.json")} == expected_ids
    required = {
        "id",
        "version",
        "required_skills",
        "risk_overrides",
        "acceptance_template",
        "context_policy",
        "verification_profile",
        "external_action_types",
    }
    for path in adapter_root.glob("*.json"):
        adapter = read_json(path)
        assert required <= set(adapter)
        assert adapter["id"] == path.stem
        assert adapter["version"] == "2.0.0"

    # The canonical bundle carries its own policy/bootstrap inputs; a project
    # must not reach into the setup source once materialized.
    assert (project / ".agents" / "skills" / "kimweaver" / "bootstrap" / "model-policy.json").read_bytes() == POLICY_PATH.read_bytes()

    policy_bytes = POLICY_PATH.read_bytes()
    policy = json.loads(policy_bytes.decode("utf-8"))
    voice = read_json(project / ".kimmizo" / "voice-bootstrap.json")
    assert voice["schemaVersion"] == 3
    assert voice["policyVersion"] == policy["policy_version"]
    assert voice["policySha256"] == hashlib.sha256(policy_bytes).hexdigest()
    assert voice == {
        "schemaVersion": 3,
        "policyVersion": policy["policy_version"],
        "policySha256": hashlib.sha256(policy_bytes).hexdigest(),
        "configured": False,
        "trigger": policy["voice"]["trigger"],
        "pronoun": policy["voice"]["pronoun"],
        "suffix": policy["voice"]["suffix"],
        "instruction": policy["voice"]["instruction"],
        "blockedMessage": policy["voice"]["blocked_message"],
    }
    vendor_voice = read_json(
        ROOT
        / "plugins"
        / "kimmizo-setup"
        / "vendor"
        / "kimweaver"
        / "bootstrap"
        / "voice-bootstrap.json"
    )
    assert vendor_voice == voice
    boot = (project / ".kimmizo" / "BOOT.md").read_text(encoding="utf-8")
    assert "gpt-5.6-luna" in boot
    assert "gpt-5.6-terra" in boot
    assert "gpt-5.6-sol" in boot
    assert "gpt-6-astra" in boot
    assert "อนุกรม" in boot
    assert "อนุมัติ" in boot


def test_capsule_status_accepts_an_installed_older_model_policy_schema(kimmizo, tmp_path):
    vendor_source = ROOT / "plugins" / "kimmizo-setup" / "vendor" / "kimweaver"
    legacy_vendor = tmp_path / "legacy-vendor"
    shutil.copytree(vendor_source, legacy_vendor)
    legacy_policy = read_json(POLICY_PATH)
    legacy_policy["schema_version"] = 2
    legacy_policy["policy_version"] = "2.0.0"
    legacy_policy_path = legacy_vendor / "bootstrap" / "model-policy.json"
    legacy_policy_path.write_text(
        json.dumps(legacy_policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    project = tmp_path / "legacy-project"
    v2 = kimmizo._load_v2_package()
    installed = v2.materialize_capsule(
        project,
        vendor_root=legacy_vendor,
        policy_path=legacy_policy_path,
    )

    assert installed["status"] == "active"
    assert v2.capsule_status(project)["status"] == "healthy"


def test_migration_receipt_hashes_v1_without_rewriting_or_copying_v1_artifacts(kimmizo, tmp_path):
    """Catches migration that changes or embeds legacy user data rather than recording a hash-only projection."""
    project = tmp_path / "project"
    user_agents = "# User authority\nKeep this exact rule.\n"
    (project / "AGENTS.md").parent.mkdir(parents=True)
    (project / "AGENTS.md").write_text(user_agents, encoding="utf-8")
    raw_user_agents = (project / "AGENTS.md").read_bytes()

    kimmizo.setup_project(project, skip_install=True)

    migration = read_json(project / ".kimmizo" / "core" / "migration.json")
    artifacts = migration["v1_artifacts"]
    assert migration["schema"] == "kimmizo-v2-migration"
    assert all(set(item) == {"relative_path", "sha256"} for item in artifacts)
    indexed = {item["relative_path"]: item["sha256"] for item in artifacts}
    assert indexed[".kimmizo/manifest.json"] == raw_sha256(project / ".kimmizo" / "manifest.json")
    assert indexed["AGENTS.md#user-content"] == hashlib.sha256(raw_user_agents).hexdigest()
    assert "Keep this exact rule." not in json.dumps(migration, ensure_ascii=False)
    assert (project / "AGENTS.md").read_text(encoding="utf-8").startswith(user_agents)


def test_first_install_rejects_a_valid_migration_receipt_preseeded_from_another_project(kimmizo, tmp_path):
    """Catches first activation binding an unowned receipt from project A into project B's new capsule."""
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    kimmizo.setup_project(project_a, skip_install=True)
    receipt = (project_a / ".kimmizo" / "core" / "migration.json").read_bytes()
    preseeded = project_b / ".kimmizo" / "core" / "migration.json"
    preseeded.parent.mkdir(parents=True)
    preseeded.write_bytes(receipt)

    with pytest.raises(ValueError, match="capsule_conflict.*migration"):
        kimmizo.setup_project(project_b, skip_install=True)

    assert preseeded.read_bytes() == receipt
    assert not (project_b / ".kimmizo" / "core" / "manifest.json").exists()
    assert not (project_b / ".agents" / "skills" / "kimweaver").exists()
    assert not (project_b / ".kimmizo" / "voice-bootstrap.json").exists()


def test_project_id_mismatched_but_rehashed_receipt_fails_status_and_update(kimmizo, tmp_path):
    """Catches a copied receipt becoming trusted after an attacker updates only its manifest migration hash."""
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    kimmizo.setup_project(project_a, skip_install=True)
    kimmizo.setup_project(project_b, skip_install=True)
    receipt = (project_a / ".kimmizo" / "core" / "migration.json").read_bytes()
    migration_b = project_b / ".kimmizo" / "core" / "migration.json"
    migration_b.write_bytes(receipt)
    manifest_path = project_b / ".kimmizo" / "core" / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["migration_sha256"] = hashlib.sha256(receipt).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kimmizo.capsule_status(project_b)

    assert status["status"] == "invalid"
    assert "project_id" in status["detail"]
    with pytest.raises(ValueError, match="project_id"):
        kimmizo._load_v2_package().materialize_capsule(project_b, force_revision=True)


def test_complete_capsule_copied_from_another_project_fails_status_and_unchanged_setup(kimmizo, tmp_path):
    """Catches a complete internally valid A capsule bypassing B setup because source hashes alone match."""
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    kimmizo.setup_project(project_a, skip_install=True)
    kimmizo.setup_project(project_b, skip_install=True)
    assert read_json(project_a / ".kimmizo" / "manifest.json")["project_id"] != read_json(
        project_b / ".kimmizo" / "manifest.json"
    )["project_id"]

    shutil.copytree(
        project_a / ".agents" / "skills" / "kimweaver",
        project_b / ".agents" / "skills" / "kimweaver",
        dirs_exist_ok=True,
    )
    shutil.copytree(project_a / ".kimmizo" / "core", project_b / ".kimmizo" / "core", dirs_exist_ok=True)
    shutil.copyfile(
        project_a / ".kimmizo" / "voice-bootstrap.json",
        project_b / ".kimmizo" / "voice-bootstrap.json",
    )
    agents_b = project_b / "AGENTS.md"
    agents_b.write_bytes(
        replace_v2_agents_block(
            agents_b.read_bytes(),
            v2_agents_block((project_a / "AGENTS.md").read_bytes()),
        )
    )

    status = kimmizo.capsule_status(project_b)

    assert status["status"] == "invalid"
    assert "project_id" in status["detail"]
    with pytest.raises(ValueError, match="project_id"):
        kimmizo.setup_project(project_b, skip_install=True)


@pytest.mark.parametrize("v1_manifest", (None, b"not valid JSON"))
def test_installed_capsule_requires_a_readable_authoritative_v1_manifest(kimmizo, tmp_path, v1_manifest):
    """Catches status treating a self-consistent v2 manifest as authoritative when the target v1 identity is absent."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    authoritative = project / ".kimmizo" / "manifest.json"
    if v1_manifest is None:
        authoritative.unlink()
    else:
        authoritative.write_bytes(v1_manifest)

    status = kimmizo.capsule_status(project)

    assert status["status"] == "invalid"
    assert "authoritative" in status["detail"]
    with pytest.raises(ValueError, match="authoritative"):
        kimmizo._load_v2_package().materialize_capsule(project, force_revision=True)


def test_fresh_standalone_rejects_a_foreign_explicit_project_id_before_dry_run_or_write(kimmizo, tmp_path):
    """Catches a caller choosing a foreign identity for a fresh target that has no v1 authority."""
    v2 = kimmizo._load_v2_package()
    target = tmp_path / "fresh-target"
    foreign = "00000000-0000-4000-8000-000000000099"

    with pytest.raises(ValueError, match="project_id.*authoritative"):
        v2.materialize_capsule(target, project_id=foreign, dry_run=True)
    assert not target.exists()

    with pytest.raises(ValueError, match="project_id.*authoritative"):
        v2.materialize_capsule(target, project_id=foreign)
    assert not target.exists()


def test_fresh_standalone_uses_its_deterministic_target_uuid_without_an_explicit_id(kimmizo, tmp_path):
    """Catches the foreign-ID guard breaking the supported direct standalone bootstrap path."""
    v2 = kimmizo._load_v2_package()
    target = tmp_path / "fresh-target"

    v2.materialize_capsule(target)

    manifest = read_json(target / ".kimmizo" / "core" / "manifest.json")
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{target.resolve()}"))
    assert manifest["project_id"] == expected
    assert v2.capsule_status(target)["status"] == "healthy"


def test_malformed_v1_authority_fails_before_creating_capsule_paths(kimmizo, tmp_path):
    """Catches _project_id silently falling back to the standalone UUID after a malformed v1 authority."""
    v2 = kimmizo._load_v2_package()
    target = tmp_path / "target"
    authority = target / ".kimmizo" / "manifest.json"
    authority.parent.mkdir(parents=True)
    authority.write_bytes(b"not valid JSON")

    with pytest.raises(ValueError, match="authoritative"):
        v2.materialize_capsule(target)

    assert authority.read_bytes() == b"not valid JSON"
    assert not (target / ".agents" / "skills" / "kimweaver").exists()
    assert not (target / ".kimmizo" / "core").exists()


def test_same_source_is_idempotent_and_dry_run_only_reports_capsule_work(kimmizo, tmp_path):
    """Catches setup creating needless revisions or a dry run creating target-owned v2 paths."""
    project = tmp_path / "project"
    first = kimmizo.setup_project(project, skip_install=True)
    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    migration_path = project / ".kimmizo" / "core" / "migration.json"
    before_manifest = manifest_path.read_bytes()
    before_migration = migration_path.read_bytes()

    second = kimmizo.setup_project(project, skip_install=True)

    assert first["core_capsule"]["status"] == "active"
    assert second["core_capsule"]["status"] == "unchanged"
    assert manifest_path.read_bytes() == before_manifest
    assert migration_path.read_bytes() == before_migration
    assert not list((project / ".kimmizo" / "core" / "revisions").glob("*"))

    future = tmp_path / "future"
    planned = kimmizo.setup_project(future, skip_install=True, dry_run=True)
    assert planned["core_capsule"]["status"] == "planned"
    assert not future.exists()


def test_first_install_refuses_unowned_kimweaver_path_without_mutation(kimmizo, tmp_path):
    """Catches first activation overwriting a pre-existing skill it does not own."""
    project = tmp_path / "project"
    existing = project / ".agents" / "skills" / "kimweaver" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    original = b"---\nname: user-kimweaver\n---\ncustom user bytes\n"
    existing.write_bytes(original)

    with pytest.raises(ValueError, match="capsule_conflict.*unowned"):
        kimmizo.setup_project(project, skip_install=True)

    assert existing.read_bytes() == original
    assert not (project / ".kimmizo" / "core" / "manifest.json").exists()
    assert not (project / ".kimmizo" / "voice-bootstrap.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project_id", "not-a-canonical-uuid"),
        ("active_revision", "v2-not-a-source-token"),
        ("previous_revision", "../../outside"),
    ),
)
def test_manifest_identity_fields_fail_closed_before_revision_paths_are_used(kimmizo, tmp_path, field, value):
    """Catches a manifest identity/path mutation being accepted before revision lookup or activation."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    manifest = read_json(manifest_path)
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kimmizo.capsule_status(project)

    assert status["status"] == "invalid"
    assert status["reason"] == "invalid"
    assert not (tmp_path / "outside").exists()


def test_manifest_source_revision_is_bound_to_aggregate_block_and_policy(kimmizo, tmp_path):
    """Catches a forged source revision and matching revision token being trusted without recomputation."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    manifest = read_json(manifest_path)
    forged = "0" * 64
    manifest["source_revision"] = forged
    manifest["active_revision"] = "v2-0000000000000000"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kimmizo.capsule_status(project)

    assert status["status"] == "invalid"
    assert "source_revision" in status["detail"]


def test_existing_revision_archive_must_match_the_staged_snapshot(kimmizo, tmp_path):
    """Catches an update silently discarding a staged prior revision because its archive directory already exists."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    before = manifest_path.read_bytes()
    revision = read_json(manifest_path)["active_revision"]
    conflicting_archive = project / ".kimmizo" / "core" / "revisions" / revision
    conflicting_archive.mkdir(parents=True)
    (conflicting_archive / "different.txt").write_text("not this revision", encoding="utf-8")

    with pytest.raises(ValueError, match="archive.*conflict"):
        kimmizo._load_v2_package().materialize_capsule(project, force_revision=True)

    assert manifest_path.read_bytes() == before
    assert (conflicting_archive / "different.txt").read_text(encoding="utf-8") == "not this revision"


def test_an_old_live_lock_is_never_stolen_by_mtime(kimmizo, tmp_path):
    """Catches a stale-mtime heuristic deleting a live lock and allowing a concurrent activation."""
    core = tmp_path / "project" / ".kimmizo" / "core"
    core.mkdir(parents=True)
    lock = core / ".capsule.lock"
    lock.write_text("other-process", encoding="utf-8")
    os.utime(lock, (1, 1))

    with pytest.raises(TimeoutError, match="capsule lock"):
        with kimmizo._load_v2_package().capsule._exclusive_capsule_lock(core, timeout_seconds=0.05):
            pass

    assert lock.read_text(encoding="utf-8") == "other-process"


def test_extra_file_under_an_active_owned_root_fails_closed_without_deletion(kimmizo, tmp_path):
    """Catches an update treating user data under a manifest-owned root as disposable capsule content."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    extra = project / ".agents" / "skills" / "kimweaver" / "user-note.md"
    extra.write_bytes(b"user-owned extra content")

    status = kimmizo.capsule_status(project)
    assert status["status"] == "invalid"
    assert "extra" in status["detail"]
    with pytest.raises(ValueError, match="extra"):
        kimmizo._load_v2_package().materialize_capsule(project, force_revision=True)
    with pytest.raises(ValueError, match="extra"):
        kimmizo._load_v2_package().materialize_capsule(project, repair=True)
    assert extra.read_bytes() == b"user-owned extra content"


def test_repair_never_deletes_extra_data_hidden_behind_an_earlier_hash_mismatch(
    kimmizo, tmp_path
):
    """Catches validation order letting repair replace a root that also contains user data."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    skill_root = project / ".agents" / "skills" / "kimweaver"
    extra = skill_root / "user-note.md"
    extra.write_bytes(b"user-owned extra content")
    owned = skill_root / "SKILL.md"
    owned.write_bytes(owned.read_bytes() + b"\ntampered expected file\n")

    status = kimmizo.capsule_status(project)
    assert status["status"] == "invalid"
    assert "extra" in status["detail"]
    with pytest.raises(ValueError, match="extra"):
        kimmizo._load_v2_package().materialize_capsule(project, repair=True)

    assert extra.read_bytes() == b"user-owned extra content"
    assert owned.read_bytes().endswith(b"tampered expected file\n")


def test_capsule_v2_block_lifecycle_preserves_exact_agents_bytes_outside_the_block(kimmizo, tmp_path):
    """Catches install, refresh, or rollback normalizing CRLF/trailing user bytes around the managed v2 block."""
    v2 = kimmizo._load_v2_package()
    original = b"# user rules\r\n\r\n"
    suffix = b"\r\n# user addition after v2\r\n\r\n"

    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_bytes(original)
    v2.materialize_capsule(project)
    first = agents.read_bytes()
    assert first.startswith(original)

    agents.write_bytes(first + suffix)
    v2.materialize_capsule(project, force_revision=True)
    refreshed = agents.read_bytes()
    assert refreshed.startswith(original)
    assert refreshed.endswith(suffix)
    v2.rollback_capsule(project)
    rolled_back = agents.read_bytes()
    assert rolled_back.startswith(original)
    assert rolled_back.endswith(suffix)

    first_only = tmp_path / "first-only"
    first_only.mkdir()
    first_agents = first_only / "AGENTS.md"
    first_agents.write_bytes(original)
    v2.materialize_capsule(first_only)
    v2.rollback_capsule(first_only)
    assert first_agents.read_bytes() == original


def test_manifest_binds_the_exact_migration_receipt_bytes(kimmizo, tmp_path):
    """Catches a modified hash-only migration receipt being accepted because it is only schema-validated."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    manifest = read_json(project / ".kimmizo" / "core" / "manifest.json")
    migration = project / ".kimmizo" / "core" / "migration.json"

    assert manifest["migration_sha256"] == raw_sha256(migration)
    migration.write_bytes(migration.read_bytes() + b" ")

    status = kimmizo.capsule_status(project)
    assert status["status"] == "invalid"
    assert status["reason"] == "hash_mismatch"
    assert "migration" in status["detail"]


def test_replace_path_rejects_an_external_source_before_creating_destination(kimmizo, tmp_path):
    """Catches activation moving a source outside the project into a newly-created destination path."""
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    destination = project / "new-root" / "payload.txt"
    backup = project / ".kimmizo" / "core" / ".staging" / "backup.txt"

    with pytest.raises(ValueError, match="containment"):
        kimmizo._load_v2_package().capsule._replace_path(outside, destination, backup, project)

    assert outside.read_bytes() == b"outside"
    assert not destination.parent.exists()


def test_replace_path_rejects_a_symlink_source_that_resolves_outside_the_project(kimmizo, tmp_path):
    """Catches a junction/symlink source bypassing lexical containment during activation."""
    project = tmp_path / "project"
    project.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside = outside_root / "payload.txt"
    outside.write_bytes(b"outside")
    link = project / "outside-link"
    try:
        link.symlink_to(outside_root, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink creation is unavailable")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside_root)],
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip("directory junction creation is unavailable")
    source = link / "payload.txt"
    destination = project / "new-root" / "payload.txt"
    backup = project / ".kimmizo" / "core" / ".staging" / "backup.txt"
    try:
        with pytest.raises(ValueError, match="containment"):
            kimmizo._load_v2_package().capsule._replace_path(source, destination, backup, project)
        assert outside.read_bytes() == b"outside"
        assert not destination.parent.exists()
    finally:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            os.rmdir(link)


def test_corrupt_active_hash_fails_closed_until_repair(kimmizo, tmp_path):
    """Catches a setup/update path silently accepting a tampered capsule file."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    skill = project / ".agents" / "skills" / "kimweaver" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")

    status = kimmizo.capsule_status(project)
    assert status["status"] == "invalid"
    assert status["reason"] == "hash_mismatch"
    with pytest.raises(ValueError, match="capsule_hash_mismatch.*repair"):
        kimmizo.setup_project(project, skip_install=True)

    repaired = kimmizo.repair_project(project)
    assert repaired["core_capsule"]["status"] == "active"
    assert kimmizo.capsule_status(project)["status"] == "healthy"


def test_staged_materialization_failure_preserves_the_active_capsule(kimmizo, tmp_path, monkeypatch):
    """Catches activation that replaces live files before a complete staged candidate can be committed."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    before = (project / ".kimmizo" / "core" / "manifest.json").read_bytes()
    v2 = kimmizo._load_v2_package()

    def fail_activation(*args, **kwargs):
        raise OSError("injected activation failure")

    monkeypatch.setattr(v2.capsule, "_activate_candidate", fail_activation)
    with pytest.raises(OSError, match="injected activation failure"):
        v2.materialize_capsule(project, force_revision=True)

    assert (project / ".kimmizo" / "core" / "manifest.json").read_bytes() == before
    assert kimmizo.capsule_status(project)["status"] == "healthy"
    assert list((project / ".kimmizo" / "core" / ".staging").glob("*"))


def test_rollback_restores_exact_previous_v2_revision_and_first_install_is_v2_only(kimmizo, tmp_path):
    """Catches rollback that touches v1/user artifacts or cannot restore the prior local capsule exactly."""
    project = tmp_path / "project"
    user_agents = "# User content\nDo not touch.\n"
    project.mkdir()
    (project / "AGENTS.md").write_text(user_agents, encoding="utf-8")
    kimmizo.setup_project(project, skip_install=True)
    first_manifest = (project / ".kimmizo" / "core" / "manifest.json").read_bytes()
    v1_manifest = (project / ".kimmizo" / "manifest.json").read_bytes()

    v2 = kimmizo._load_v2_package()
    source_vendor = ROOT / "plugins" / "kimmizo-setup" / "vendor" / "kimweaver"
    changed_vendor = tmp_path / "changed-vendor"
    shutil.copytree(source_vendor, changed_vendor)
    skill = changed_vendor / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\n# Capsule revision\n", encoding="utf-8")
    updated = v2.materialize_capsule(project, vendor_root=changed_vendor, force_revision=True)
    assert updated["status"] == "active"
    assert (project / ".kimmizo" / "core" / "manifest.json").read_bytes() != first_manifest
    v1_memory = project / ".kimmizo" / "memory" / "boss-note.md"
    v1_memory.write_text("new v1 memory after revision", encoding="utf-8")
    agents = project / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n# New user rule\n", encoding="utf-8")

    rolled_back = kimmizo.rollback_core_capsule(project)
    assert rolled_back["status"] == "rolled_back"
    assert (project / ".kimmizo" / "core" / "manifest.json").read_bytes() == first_manifest
    assert (project / ".kimmizo" / "manifest.json").read_bytes() == v1_manifest
    assert v1_memory.read_text(encoding="utf-8") == "new v1 memory after revision"
    assert "# New user rule" in agents.read_text(encoding="utf-8")

    first_only = tmp_path / "first-only"
    first_only.mkdir()
    (first_only / "AGENTS.md").write_text(user_agents, encoding="utf-8")
    kimmizo.setup_project(first_only, skip_install=True)
    removed = kimmizo.rollback_core_capsule(first_only)
    assert removed["status"] == "removed"
    assert not (first_only / ".kimmizo" / "core").exists()
    assert not (first_only / ".agents" / "skills" / "kimweaver").exists()
    assert not (first_only / ".kimmizo" / "voice-bootstrap.json").exists()
    assert (first_only / ".kimmizo" / "manifest.json").is_file()
    agents_text = (first_only / "AGENTS.md").read_text(encoding="utf-8")
    assert user_agents in agents_text
    assert "KIMWEAVER-V2-MANAGED" not in agents_text
    assert "BEGIN KIMMIZO MANAGED BLOCK" in agents_text


def test_unknown_capsule_major_fails_closed_until_repair(kimmizo, tmp_path):
    """Catches an unsupported capsule major being treated as a compatible update rather than a repair boundary."""
    project = tmp_path / "project"
    kimmizo.setup_project(project, skip_install=True)
    manifest_path = project / ".kimmizo" / "core" / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["schema_version"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kimmizo.capsule_status(project)
    assert status["status"] == "invalid"
    assert status["reason"] == "unknown_major"
    with pytest.raises(ValueError, match="capsule_unknown_major.*repair"):
        kimmizo.setup_project(project, skip_install=True)

    repaired = kimmizo.repair_project(project)
    assert repaired["core_capsule"]["status"] == "active"
    assert kimmizo.capsule_status(project)["status"] == "healthy"


def test_capsule_cli_status_and_rollback_are_machine_readable(kimmizo, tmp_path, capsys):
    """Catches new capsule CLI commands that do not use the established JSON result contract."""
    project = tmp_path / "project"
    assert kimmizo.main(["setup", "--target", str(project), "--skip-install", "--json"]) == 0
    capsys.readouterr()

    assert kimmizo.main(["capsule-status", "--target", str(project), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "healthy"

    assert kimmizo.main(["capsule-rollback", "--target", str(project), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "removed"

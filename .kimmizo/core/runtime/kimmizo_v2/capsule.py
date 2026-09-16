"""Self-contained, hash-verified Kimweaver v2 project capsules.

This module intentionally uses only the Python standard library.  The
materializer is used by the setup plugin, while ``capsule_status`` and the
rollback helpers work from the project-local copied runtime without consulting
the plugin, a user profile, or a Home Base installation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping


CAPSULE_SCHEMA = "kimmizo-capsule-v2"
CAPSULE_SCHEMA_VERSION = 2
MIGRATION_SCHEMA = "kimmizo-v2-migration"
MIGRATION_SCHEMA_VERSION = 1
CAPSULE_VERSION = "2.0.0"
CORE_VERSION = "2.0.0"
ADAPTER_VERSION = "2.0.0"
MIN_SETUP_VERSION = "1.0.0"

V2_BLOCK_BEGIN = "<!-- BEGIN KIMWEAVER-V2-MANAGED -->"
V2_BLOCK_END = "<!-- END KIMWEAVER-V2-MANAGED -->"
_V2_BLOCK_PATTERN = re.compile(
    r"<!-- BEGIN KIMWEAVER-V2-MANAGED -->\r?\n.*?<!-- END KIMWEAVER-V2-MANAGED -->",
    re.DOTALL,
)
_V1_BLOCK_PATTERN = re.compile(
    r"<!-- BEGIN KIMMIZO MANAGED BLOCK.*?<!-- END KIMMIZO MANAGED BLOCK -->",
    re.DOTALL,
)
_V2_BLOCK_BYTES_PATTERN = re.compile(
    br"(?:\r?\n)?<!-- BEGIN KIMWEAVER-V2-MANAGED -->\r?\n.*?<!-- END KIMWEAVER-V2-MANAGED -->(?:\r?\n)?",
    re.DOTALL,
)
_V2_BLOCK_EXACT_BYTES_PATTERN = re.compile(
    br"<!-- BEGIN KIMWEAVER-V2-MANAGED -->\r?\n.*?<!-- END KIMWEAVER-V2-MANAGED -->",
    re.DOTALL,
)
_V1_BLOCK_BYTES_PATTERN = re.compile(
    br"(?:\r?\n)?<!-- BEGIN KIMMIZO MANAGED BLOCK.*?<!-- END KIMMIZO MANAGED BLOCK -->(?:\r?\n)?",
    re.DOTALL,
)
_REVISION_TOKEN_PATTERN = re.compile(r"v2-([0-9a-f]{16})(?:-([0-9a-f]{8}))?\Z")
_EXPECTED_ADAPTER_IDS = {
    "software",
    "research",
    "document-data",
    "secretary-coordination",
}
_ADAPTER_REQUIRED_FIELDS = {
    "id",
    "version",
    "required_skills",
    "risk_overrides",
    "acceptance_template",
    "context_policy",
    "verification_profile",
    "external_action_types",
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aggregate_hash(file_hashes: Mapping[str, str]) -> str:
    payload = "".join(f"{relative}:{file_hashes[relative]}\n" for relative in sorted(file_hashes))
    return _sha256_bytes(payload.encode("utf-8"))


def _block_hash(value: bytes) -> str:
    # AGENTS.md is often rewritten by the legacy setup path through text mode.
    # The v2 block has an independent semantic digest so that a host newline
    # conversion cannot masquerade as a v2-content mutation.
    return _sha256_bytes(value.replace(b"\r\n", b"\n"))


def _source_revision(aggregate_sha256: str, agents_block_sha256: str, policy_sha256: str) -> str:
    return _sha256_bytes(
        (aggregate_sha256 + "\n" + agents_block_sha256 + "\n" + policy_sha256 + "\n").encode("ascii")
    )


def _canonical_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"capsule_invalid: manifest {label} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"capsule_invalid: manifest {label} must be a canonical UUID") from error
    if str(parsed) != value.casefold():
        raise ValueError(f"capsule_invalid: manifest {label} must be a canonical UUID")
    return str(parsed)


def _validate_revision_token(value: Any, label: str, *, source_revision: str | None = None) -> str:
    if not isinstance(value, str):
        raise ValueError(f"capsule_invalid: manifest {label} must be a safe revision token")
    matched = _REVISION_TOKEN_PATTERN.fullmatch(value)
    if not matched:
        raise ValueError(f"capsule_invalid: manifest {label} must be a safe revision token")
    if source_revision is not None and matched.group(1) != source_revision[:16]:
        raise ValueError(f"capsule_invalid: manifest {label} does not match source_revision")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("capsule_invalid: path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"capsule_invalid: unsafe relative path: {value!r}")
    if ":" in path.parts[0]:
        raise ValueError(f"capsule_invalid: unsafe relative path: {value!r}")
    return path


def _at(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    path = root.joinpath(*safe.parts)
    if not _is_within(path, root):
        raise ValueError(f"capsule_invalid: path escapes capsule root: {relative}")
    return path


def _remove_owned_path(path: Path, allowed_root: Path) -> None:
    if not _is_within(path, allowed_root) or path.resolve() == allowed_root.resolve():
        raise ValueError(f"capsule_invalid: refusing to remove outside owned root: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.kimmizo-v2-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive_capsule_lock(core_root: Path, timeout_seconds: float = 15.0) -> Iterator[None]:
    core_root.mkdir(parents=True, exist_ok=True)
    lock = core_root / ".capsule.lock"
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()}".encode("ascii"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for capsule lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock.unlink(missing_ok=True)


def _plugin_root_from_module() -> Path:
    # Source layout: <plugin>/scripts/kimmizo_v2/capsule.py.  A copied runtime
    # has no vendor tree, which is intentional: status/rollback need none.
    return Path(__file__).resolve().parents[2]


def _iter_regular_files(root: Path, *, suffixes: set[str] | None = None) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"capsule_invalid: expected a real directory: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"capsule_invalid: symlink is not allowed in capsule source: {path}")
        if path.is_file() and (suffixes is None or path.suffix in suffixes):
            result.append(path)
    return result


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"capsule_invalid: cannot read {label}: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"capsule_invalid: {label} must be a JSON object")
    return value


def _validate_adapter(adapter: Mapping[str, Any], *, expected_id: str | None = None) -> None:
    missing = _ADAPTER_REQUIRED_FIELDS - set(adapter)
    if missing:
        raise ValueError(f"capsule_invalid: adapter missing fields: {sorted(missing)}")
    adapter_id = adapter.get("id")
    if not isinstance(adapter_id, str) or adapter_id not in _EXPECTED_ADAPTER_IDS:
        raise ValueError("capsule_invalid: adapter id is invalid")
    if expected_id is not None and adapter_id != expected_id:
        raise ValueError("capsule_invalid: adapter id does not match its filename")
    if adapter.get("version") != ADAPTER_VERSION:
        raise ValueError("capsule_invalid: adapter version is unsupported")
    if not isinstance(adapter.get("required_skills"), list) or not all(
        isinstance(item, str) and item for item in adapter["required_skills"]
    ):
        raise ValueError("capsule_invalid: adapter required_skills must be strings")
    if not isinstance(adapter.get("risk_overrides"), dict):
        raise ValueError("capsule_invalid: adapter risk_overrides must be an object")
    if not isinstance(adapter.get("acceptance_template"), (list, dict)):
        raise ValueError("capsule_invalid: adapter acceptance_template is invalid")
    if not isinstance(adapter.get("context_policy"), dict):
        raise ValueError("capsule_invalid: adapter context_policy must be an object")
    if not isinstance(adapter.get("verification_profile"), (list, dict)):
        raise ValueError("capsule_invalid: adapter verification_profile is invalid")
    if not isinstance(adapter.get("external_action_types"), list) or not all(
        isinstance(item, str) for item in adapter["external_action_types"]
    ):
        raise ValueError("capsule_invalid: adapter external_action_types must be strings")


def _validate_vendor_bundle(vendor_root: Path) -> None:
    required = (
        "SKILL.md",
        "references/contracts.md",
        "references/runtime-smoke-test.md",
        "references/v2-contracts.md",
        "bootstrap/model-policy.json",
        "bootstrap/voice-bootstrap.json",
    )
    for relative in required:
        path = _at(vendor_root, relative)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"capsule_invalid: vendor bundle misses {relative}")
    skill = (vendor_root / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n") or "\n---\n" not in skill[4:]:
        raise ValueError("capsule_invalid: vendor skill frontmatter is invalid")
    adapter_root = vendor_root / "adapters"
    adapters = {path.stem: path for path in _iter_regular_files(adapter_root, suffixes={".json"})}
    if set(adapters) != _EXPECTED_ADAPTER_IDS:
        raise ValueError("capsule_invalid: vendor must contain exactly four adapters")
    for adapter_id, path in adapters.items():
        _validate_adapter(_read_json(path, label=f"adapter {adapter_id}"), expected_id=adapter_id)
    schema_root = vendor_root / "schemas"
    schemas = {path.name: path for path in _iter_regular_files(schema_root, suffixes={".json"})}
    expected_schemas = {
        "assignment.schema.json",
        "evidence-receipt.schema.json",
        "review-packet.schema.json",
        "routing-decision.schema.json",
        "task-checkpoint.schema.json",
        "task-envelope.schema.json",
    }
    if set(schemas) != expected_schemas:
        raise ValueError("capsule_invalid: vendor schema set is incomplete")
    for relative, path in schemas.items():
        schema = _read_json(path, label=relative)
        if not isinstance(schema.get("$schema"), str) or not isinstance(schema.get("title"), str):
            raise ValueError(f"capsule_invalid: vendor schema is not versioned: {relative}")


def _voice_bootstrap(policy_path: Path) -> tuple[bytes, str]:
    raw = policy_path.read_bytes()
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("capsule_invalid: model policy is not valid UTF-8 JSON") from error
    if (
        not isinstance(policy, dict)
        or not isinstance(policy.get("schema_version"), int)
        or policy["schema_version"] <= 0
        or not isinstance(policy.get("policy_version"), str)
    ):
        raise ValueError("capsule_invalid: model policy version is missing")
    voice = policy.get("voice")
    if not isinstance(voice, dict) or not all(
        isinstance(voice.get(key), str) and voice[key]
        for key in ("trigger", "pronoun", "suffix", "instruction", "blocked_message")
    ):
        raise ValueError("capsule_invalid: model policy voice is incomplete")
    sidecar: dict[str, Any] = {
        "schemaVersion": policy["schema_version"],
        "policyVersion": policy["policy_version"],
        "policySha256": _sha256_bytes(raw),
        "trigger": voice["trigger"],
        "pronoun": voice["pronoun"],
        "suffix": voice["suffix"],
        "instruction": voice["instruction"],
        "blockedMessage": voice["blocked_message"],
    }
    return _json_bytes(sidecar), sidecar["policySha256"]


def _load_block(template_path: Path) -> bytes:
    raw = template_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("capsule_invalid: AGENTS v2 block is not UTF-8") from error
    # The block's digest is over its marker-delimited bytes, not the optional
    # final newline in a template file.  That makes the digest stable after it
    # is merged into a larger AGENTS.md document.
    normalized = text.rstrip("\r\n")
    matches = list(_V2_BLOCK_PATTERN.finditer(normalized))
    if len(matches) != 1 or matches[0].group(0) != normalized:
        raise ValueError("capsule_invalid: AGENTS v2 block markers are invalid")
    return normalized.encode("utf-8")


def _source_payloads(
    *,
    plugin_root: Path | None,
    vendor_root: Path | None,
    runtime_source: Path | None,
    policy_path: Path | None,
    template_path: Path | None,
) -> tuple[dict[str, bytes], bytes, str]:
    root = plugin_root.resolve() if plugin_root is not None else _plugin_root_from_module()
    vendor = (vendor_root or root / "vendor" / "kimweaver").resolve()
    runtime = (runtime_source or Path(__file__).resolve().parent).resolve()
    policy = (policy_path or root / "registry" / "model-policy.json").resolve()
    template = (template_path or root / "templates" / "project-capsule" / "AGENTS.v2.block.md").resolve()
    _validate_vendor_bundle(vendor)
    if not policy.is_file() or policy.is_symlink():
        raise ValueError("capsule_invalid: model policy source is unavailable")
    if not template.is_file() or template.is_symlink():
        raise ValueError("capsule_invalid: AGENTS v2 template is unavailable")
    if (vendor / "bootstrap" / "model-policy.json").read_bytes() != policy.read_bytes():
        raise ValueError("capsule_invalid: vendored policy does not match the exact registry policy bytes")

    payloads: dict[str, bytes] = {}
    for source in _iter_regular_files(vendor):
        relative = source.relative_to(vendor).as_posix()
        payloads[f".agents/skills/kimweaver/{relative}"] = source.read_bytes()
    for source in _iter_regular_files(runtime, suffixes={".py"}):
        relative = source.relative_to(runtime).as_posix()
        payloads[f".kimmizo/core/runtime/kimmizo_v2/{relative}"] = source.read_bytes()
    if ".kimmizo/core/runtime/kimmizo_v2/capsule.py" not in payloads:
        raise ValueError("capsule_invalid: standalone runtime capsule module is missing")
    bootstrap, policy_hash = _voice_bootstrap(policy)
    payloads[".kimmizo/voice-bootstrap.json"] = bootstrap
    return payloads, _load_block(template), policy_hash


def _project_id(target: Path, provided: str | None) -> str:
    authoritative = _authoritative_project_id(target)
    if provided is None:
        return authoritative
    requested = _canonical_uuid(provided, "provided project_id")
    if requested != authoritative:
        raise ValueError(
            "capsule_conflict: provided project_id does not match authoritative target project_id"
        )
    return requested


def _installed_capsule_expects_v1_manifest(target: Path) -> bool:
    """Use the hash-only migration receipt to distinguish setup from direct standalone mode."""
    receipt_path = target / ".kimmizo" / "core" / "migration.json"
    if not receipt_path.is_file() or receipt_path.is_symlink() or not _is_within(receipt_path, target):
        return False
    try:
        receipt = _read_json(receipt_path, label="migration receipt")
    except ValueError:
        return False
    artifacts = receipt.get("v1_artifacts")
    return isinstance(artifacts, list) and any(
        isinstance(item, dict) and item.get("relative_path") == ".kimmizo/manifest.json"
        for item in artifacts
    )


def _authoritative_project_id(target: Path) -> str:
    manifest_path = target / ".kimmizo" / "manifest.json"
    if not manifest_path.exists() and not manifest_path.is_symlink():
        if _installed_capsule_expects_v1_manifest(target):
            raise ValueError(
                "capsule_conflict: migration receipt requires an authoritative v1 manifest"
            )
        # A capsule can be materialized directly without the v1 adapter.  Its
        # target path is then the independent local authority, so copying that
        # capsule to another path changes the expected identity and fails.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{target.resolve()}"))
    if not manifest_path.is_file() or manifest_path.is_symlink() or not _is_within(manifest_path, target):
        raise ValueError("capsule_conflict: authoritative v1 manifest is unavailable")
    try:
        manifest = _read_json(manifest_path, label="authoritative v1 manifest")
        return _canonical_uuid(manifest.get("project_id"), "authoritative v1 project_id")
    except ValueError as error:
        raise ValueError("capsule_conflict: authoritative v1 manifest project_id is invalid") from error


def _validate_authoritative_project_binding(target: Path, manifest: Mapping[str, Any]) -> None:
    authoritative_project_id = _authoritative_project_id(target)
    if manifest.get("project_id") != authoritative_project_id:
        raise ValueError("capsule_conflict: v2 manifest project_id does not match authoritative v1 project_id")


def _validate_candidate_target_binding(target: Path, manifest: Mapping[str, Any]) -> None:
    """Bind every candidate to v1 authority or the deterministic standalone target authority."""
    _validate_authoritative_project_binding(target, manifest)


def _strip_managed_blocks_bytes(agents_bytes: bytes) -> bytes:
    """Project the raw user-owned AGENTS bytes without decoding/reformatting them."""
    return _V2_BLOCK_EXACT_BYTES_PATTERN.sub(b"", _V1_BLOCK_BYTES_PATTERN.sub(b"", agents_bytes))


def _merge_v2_block(agents_bytes: bytes, block: bytes) -> bytes:
    matches = list(_V2_BLOCK_EXACT_BYTES_PATTERN.finditer(agents_bytes))
    if len(matches) > 1:
        raise ValueError("capsule_invalid: multiple Kimweaver v2 blocks require repair")
    if matches:
        start, end = matches[0].span()
        return agents_bytes[:start] + block + agents_bytes[end:]
    # Keep v2-owned boundary newlines around a newly inserted block.  The v1
    # merger preserves this exact shape, so a later setup does not rewrite the
    # document solely to add whitespace around the independent v2 marker.
    return agents_bytes + b"\n" + block + b"\n"


def _v1_artifacts(target: Path, agents_bytes: bytes) -> list[dict[str, str]]:
    artifacts: dict[str, str] = {}
    static_paths = (
        ".kimmizo/manifest.json",
        ".kimmizo/team/identities.json",
        ".kimmizo/team/active.json",
        ".kimmizo/runtime/checkpoints/latest.json",
    )
    for relative in static_paths:
        path = _at(target, relative)
        if path.is_file() and not path.is_symlink():
            artifacts[relative] = _sha256_file(path)
    for relative_root in (
        ".kimmizo/team/profiles",
        ".kimmizo/memory",
        ".kimmizo/capabilities/receipts",
    ):
        root = _at(target, relative_root)
        if not root.is_dir() or root.is_symlink():
            continue
        for path in _iter_regular_files(root):
            relative = path.relative_to(target).as_posix()
            artifacts[relative] = _sha256_file(path)
    artifacts["AGENTS.md#user-content"] = _sha256_bytes(_strip_managed_blocks_bytes(agents_bytes))
    return [
        {"relative_path": relative, "sha256": artifacts[relative]}
        for relative in sorted(artifacts)
    ]


def _migration_receipt(target: Path, agents_bytes: bytes, project_id: str) -> bytes:
    return _json_bytes(
        {
            "schema": MIGRATION_SCHEMA,
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "project_id": _canonical_uuid(project_id, "migration project_id"),
            "v1_artifacts": _v1_artifacts(target, agents_bytes),
        }
    )


def _migration_bytes_for_target(target: Path, project_id: str) -> bytes:
    path = target / ".kimmizo" / "core" / "migration.json"
    if path.exists() or path.is_symlink():
        if not path.is_file() or path.is_symlink() or not _is_within(path, target):
            raise ValueError("capsule_invalid: migration receipt path is unsafe")
        return path.read_bytes()
    agents_path = target / "AGENTS.md"
    if agents_path.is_symlink() or (agents_path.exists() and not agents_path.is_file()):
        raise ValueError("capsule_invalid: AGENTS.md path is unsafe")
    agents_bytes = agents_path.read_bytes() if agents_path.is_file() else b""
    return _migration_receipt(target, agents_bytes, project_id)


def _parse_manifest(path: Path) -> dict[str, Any]:
    return _read_json(path, label="capsule manifest")


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != CAPSULE_SCHEMA:
        raise ValueError("capsule_unknown_major: expected kimmizo-capsule-v2")
    if manifest.get("schema_version") != CAPSULE_SCHEMA_VERSION:
        raise ValueError("capsule_unknown_major: unsupported capsule schema version")
    for key in ("project_id", "capsule_version", "core_version", "adapter_version", "source_revision", "active_revision"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            raise ValueError(f"capsule_invalid: manifest {key} is required")
    _canonical_uuid(manifest["project_id"], "project_id")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["source_revision"]):
        raise ValueError("capsule_invalid: manifest source_revision is invalid")
    _validate_revision_token(
        manifest["active_revision"], "active_revision", source_revision=manifest["source_revision"]
    )
    if manifest.get("lifecycle") != "active":
        raise ValueError("capsule_invalid: manifest lifecycle is not active")
    if manifest.get("provenance") != "vendored_project_local_snapshot":
        raise ValueError("capsule_invalid: manifest provenance is invalid")
    if manifest.get("previous_revision") is not None:
        _validate_revision_token(manifest["previous_revision"], "previous_revision")
    hashes = manifest.get("file_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("capsule_invalid: manifest file_hashes is required")
    for relative, digest in hashes.items():
        _safe_relative(relative)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("capsule_invalid: manifest file hash is invalid")
    if not isinstance(manifest.get("aggregate_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", manifest["aggregate_sha256"]
    ):
        raise ValueError("capsule_invalid: manifest aggregate hash is invalid")
    for key in ("bootstrap_sha256", "policy_sha256", "agents_block_sha256", "migration_sha256"):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest[key]):
            raise ValueError(f"capsule_invalid: manifest {key} is invalid")
    if manifest.get("bootstrap_hash") != manifest.get("bootstrap_sha256"):
        raise ValueError("capsule_invalid: manifest bootstrap hash is invalid")
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict) or compatibility.get("minimum_setup_version") != MIN_SETUP_VERSION:
        raise ValueError("capsule_invalid: manifest compatibility is invalid")


def _validate_migration_receipt(path: Path, project_id: str) -> None:
    receipt = _read_json(path, label="migration receipt")
    if receipt.get("schema") != MIGRATION_SCHEMA or receipt.get("schema_version") != MIGRATION_SCHEMA_VERSION:
        raise ValueError("capsule_invalid: migration receipt schema is invalid")
    receipt_project_id = _canonical_uuid(receipt.get("project_id"), "migration receipt project_id")
    if receipt_project_id != _canonical_uuid(project_id, "manifest project_id"):
        raise ValueError("capsule_conflict: migration receipt project_id does not match manifest project_id")
    artifacts = receipt.get("v1_artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("capsule_invalid: migration receipt artifacts are invalid")
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"relative_path", "sha256"}:
            raise ValueError("capsule_invalid: migration receipt must be hash-only")
        if not isinstance(item["relative_path"], str) or not isinstance(item["sha256"], str):
            raise ValueError("capsule_invalid: migration receipt entry is invalid")
        if item["relative_path"] != "AGENTS.md#user-content":
            _safe_relative(item["relative_path"])
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("capsule_invalid: migration receipt hash is invalid")


def _installed_adapters(target: Path) -> None:
    root = target / ".agents" / "skills" / "kimweaver" / "adapters"
    try:
        files = {path.stem: path for path in _iter_regular_files(root, suffixes={".json"})}
    except ValueError as error:
        raise ValueError("capsule_invalid: installed adapter root is unavailable") from error
    if set(files) != _EXPECTED_ADAPTER_IDS:
        raise ValueError("capsule_invalid: installed adapter set is incomplete")
    for adapter_id, path in files.items():
        _validate_adapter(_read_json(path, label=f"installed adapter {adapter_id}"), expected_id=adapter_id)


def _validate_owned_roots(payload_root: Path, file_hashes: Mapping[str, str]) -> None:
    """Reject any unmanifested file, directory, link, or junction in active roots."""
    owned_roots = (
        ".agents/skills/kimweaver",
        ".kimmizo/core/runtime/kimmizo_v2",
    )
    expected_files = set(file_hashes)
    expected_directories: set[str] = set()
    for relative in expected_files:
        path = PurePosixPath(relative)
        parent = path.parent
        while str(parent) not in {"", "."}:
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    for root_relative in owned_roots:
        root = _at(payload_root, root_relative)
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"capsule_invalid: active owned root is unavailable: {root_relative}")
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not _is_within(path, payload_root) or path.is_symlink():
                raise ValueError(f"capsule_conflict: unsafe owned path: {path.relative_to(root).as_posix()}")
            relative = path.relative_to(payload_root).as_posix()
            if "__pycache__" in PurePosixPath(relative).parts or path.suffix == ".pyc":
                continue
            if path.is_dir():
                if relative not in expected_directories:
                    raise ValueError(f"capsule_conflict: extra owned path: {relative}")
            elif path.is_file():
                if relative not in expected_files:
                    raise ValueError(f"capsule_conflict: extra owned file: {relative}")
            else:
                raise ValueError(f"capsule_conflict: unsupported owned path: {relative}")


def _validate_payload(
    *,
    root: Path,
    manifest: Mapping[str, Any],
    payload_root: Path,
    block: bytes,
    migration_path: Path,
) -> None:
    _validate_manifest_shape(manifest)
    file_hashes = manifest["file_hashes"]
    # Ownership conflicts outrank repairable integrity drift.  Otherwise an
    # earlier hash mismatch could hide an extra project-owned file and let a
    # repair replace the whole root, deleting data the manifest never owned.
    _validate_owned_roots(payload_root, file_hashes)
    for relative, expected in file_hashes.items():
        path = _at(payload_root, relative)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"capsule_invalid: owned file is missing: {relative}")
        if _sha256_file(path) != expected:
            raise ValueError(f"capsule_hash_mismatch: owned file differs: {relative}")
    if _aggregate_hash(file_hashes) != manifest["aggregate_sha256"]:
        raise ValueError("capsule_hash_mismatch: aggregate hash differs")
    bootstrap_relative = ".kimmizo/voice-bootstrap.json"
    policy_relative = ".agents/skills/kimweaver/bootstrap/model-policy.json"
    if file_hashes.get(bootstrap_relative) != manifest["bootstrap_sha256"]:
        raise ValueError("capsule_hash_mismatch: bootstrap hash differs")
    if file_hashes.get(policy_relative) != manifest["policy_sha256"]:
        raise ValueError("capsule_hash_mismatch: model policy hash differs")
    try:
        sidecar = json.loads(_at(payload_root, bootstrap_relative).read_text(encoding="utf-8"))
        local_policy = json.loads(_at(payload_root, policy_relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("capsule_invalid: local policy bootstrap cannot be read") from error
    policy_schema = local_policy.get("schema_version") if isinstance(local_policy, dict) else None
    policy_version = local_policy.get("policy_version") if isinstance(local_policy, dict) else None
    policy_voice = local_policy.get("voice") if isinstance(local_policy, dict) else None
    if (
        not isinstance(sidecar, dict)
        or not isinstance(policy_schema, int)
        or policy_schema <= 0
        or not isinstance(policy_version, str)
        or not isinstance(policy_voice, dict)
        or sidecar.get("schemaVersion") != policy_schema
        or sidecar.get("policyVersion") != policy_version
        or sidecar.get("policySha256") != manifest["policy_sha256"]
        or not all(
            isinstance(sidecar.get(key), str) and sidecar[key]
            for key in ("trigger", "pronoun", "suffix", "instruction", "blockedMessage")
        )
        or sidecar.get("trigger") != policy_voice.get("trigger")
        or sidecar.get("pronoun") != policy_voice.get("pronoun")
        or sidecar.get("suffix") != policy_voice.get("suffix")
        or sidecar.get("instruction") != policy_voice.get("instruction")
        or sidecar.get("blockedMessage") != policy_voice.get("blocked_message")
    ):
        raise ValueError("capsule_invalid: local voice bootstrap is invalid")
    block_sha256 = _block_hash(block)
    if block_sha256 != manifest["agents_block_sha256"]:
        raise ValueError("capsule_hash_mismatch: AGENTS v2 block differs")
    if _source_revision(
        manifest["aggregate_sha256"], block_sha256, manifest["policy_sha256"]
    ) != manifest["source_revision"]:
        raise ValueError("capsule_hash_mismatch: source_revision differs from aggregate, block, and policy")
    skill_root = _at(payload_root, ".agents/skills/kimweaver")
    if not (skill_root / "SKILL.md").is_file():
        raise ValueError("capsule_invalid: local Kimweaver skill is missing")
    adapter_root = skill_root / "adapters"
    adapters = {path.stem: path for path in _iter_regular_files(adapter_root, suffixes={".json"})}
    if set(adapters) != _EXPECTED_ADAPTER_IDS:
        raise ValueError("capsule_invalid: local adapter set is incomplete")
    for adapter_id, path in adapters.items():
        _validate_adapter(_read_json(path, label=f"local adapter {adapter_id}"), expected_id=adapter_id)
    if not (_at(payload_root, ".kimmizo/core/runtime/kimmizo_v2/capsule.py")).is_file():
        raise ValueError("capsule_invalid: local capsule runtime is missing")
    if not migration_path.is_file() or migration_path.is_symlink():
        raise ValueError("capsule_invalid: migration receipt is unavailable")
    if _sha256_file(migration_path) != manifest["migration_sha256"]:
        raise ValueError("capsule_hash_mismatch: migration receipt differs")
    _validate_migration_receipt(migration_path, manifest["project_id"])
    del root


def _candidate_manifest(
    *,
    project_id: str,
    payloads: Mapping[str, bytes],
    block: bytes,
    policy_hash: str,
    migration_sha256: str,
    previous_revision: str | None,
    force_revision: bool,
) -> dict[str, Any]:
    file_hashes = {relative: _sha256_bytes(payloads[relative]) for relative in sorted(payloads)}
    aggregate = _aggregate_hash(file_hashes)
    source_revision = _source_revision(aggregate, _block_hash(block), policy_hash)
    revision = f"v2-{source_revision[:16]}"
    if force_revision:
        revision = f"{revision}-{uuid.uuid4().hex[:8]}"
    return {
        "schema": CAPSULE_SCHEMA,
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "project_id": project_id,
        "capsule_version": CAPSULE_VERSION,
        "core_version": CORE_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source_revision": source_revision,
        "source_provenance": {
            "kind": "vendored_project_local_snapshot",
            "runtime": "stdlib_only",
        },
        "provenance": "vendored_project_local_snapshot",
        "file_hashes": file_hashes,
        "aggregate_sha256": aggregate,
        "bootstrap_sha256": file_hashes[".kimmizo/voice-bootstrap.json"],
        "bootstrap_hash": file_hashes[".kimmizo/voice-bootstrap.json"],
        "policy_sha256": policy_hash,
        "migration_sha256": migration_sha256,
        "agents_block_sha256": _block_hash(block),
        "active_revision": revision,
        "previous_revision": previous_revision,
        "compatibility": {
            "minimum_setup_version": MIN_SETUP_VERSION,
            "legacy_projection": "hash-only-v1",
        },
        "legacy_projection": "hash-only-v1",
        "lifecycle": "active",
    }


def _prepare_candidate(
    *,
    target: Path,
    stage: Path,
    manifest: Mapping[str, Any],
    payloads: Mapping[str, bytes],
    block: bytes,
    migration_bytes: bytes,
) -> None:
    payload_root = stage / "payload"
    for relative, content in payloads.items():
        path = _at(payload_root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _atomic_write_bytes(stage / "manifest.json", _json_bytes(manifest))
    _atomic_write_bytes(stage / "migration.json", migration_bytes)
    _atomic_write_bytes(stage / "agents-v2-block.md", block)
    _validate_candidate_target_binding(target, manifest)
    _validate_payload(
        root=target,
        manifest=manifest,
        payload_root=payload_root,
        block=(stage / "agents-v2-block.md").read_bytes(),
        migration_path=stage / "migration.json",
    )


def _copy_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        raise ValueError(f"capsule_invalid: symlink cannot be archived: {source}")
    if source.is_dir():
        shutil.copytree(source, destination, copy_function=shutil.copyfile)
    else:
        shutil.copyfile(source, destination)


def _snapshot_fingerprint(root: Path) -> tuple[tuple[str, str], ...]:
    """Return a raw-byte structural fingerprint without following links outside the snapshot."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("capsule_archive_conflict: revision archive is not a real directory")
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not _is_within(path, root) or path.is_symlink():
            raise ValueError("capsule_archive_conflict: revision archive contains an unsafe path")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append(("directory", relative))
        elif path.is_file():
            entries.append(("file", relative + ":" + _sha256_file(path)))
        else:
            raise ValueError("capsule_archive_conflict: revision archive contains an unsupported path")
    return tuple(entries)


def _stage_active_snapshot(target: Path, stage: Path, manifest: Mapping[str, Any]) -> None:
    _validate_authoritative_project_binding(target, manifest)
    payload = stage / "payload"
    sources = {
        ".agents/skills/kimweaver": target / ".agents" / "skills" / "kimweaver",
        ".kimmizo/core/runtime/kimmizo_v2": target / ".kimmizo" / "core" / "runtime" / "kimmizo_v2",
        ".kimmizo/voice-bootstrap.json": target / ".kimmizo" / "voice-bootstrap.json",
    }
    for relative, source in sources.items():
        if not source.exists() and not source.is_symlink():
            raise ValueError(f"capsule_invalid: active owned path is missing: {relative}")
        _copy_path(source, _at(payload, relative))
    _copy_path(target / ".kimmizo" / "core" / "manifest.json", stage / "manifest.json")
    _copy_path(target / ".kimmizo" / "core" / "migration.json", stage / "migration.json")
    agents_path = target / "AGENTS.md"
    try:
        agents_bytes = agents_path.read_bytes()
    except OSError as error:
        raise ValueError("capsule_invalid: active AGENTS.md cannot be archived") from error
    matches = list(_V2_BLOCK_EXACT_BYTES_PATTERN.finditer(agents_bytes))
    if len(matches) != 1:
        raise ValueError("capsule_invalid: active AGENTS v2 block is not unique")
    _atomic_write_bytes(stage / "agents-v2-block.md", matches[0].group(0))
    _validate_payload(
        root=target,
        manifest=manifest,
        payload_root=payload,
        block=(stage / "agents-v2-block.md").read_bytes(),
        migration_path=stage / "migration.json",
    )


def _validate_replace_containment(source: Path, destination: Path, backup: Path, allowed_root: Path) -> None:
    for label, path in (("source", source), ("destination", destination), ("backup", backup)):
        if not _is_within(path, allowed_root) or path.resolve() == allowed_root.resolve():
            raise ValueError(f"capsule_containment: {label} escapes the activation root")
    if not source.exists() or source.is_symlink():
        raise ValueError("capsule_containment: source is unavailable or linked")
    if (destination.exists() or destination.is_symlink()) and destination.is_symlink():
        raise ValueError("capsule_containment: destination is linked")
    if (backup.exists() or backup.is_symlink()) and backup.is_symlink():
        raise ValueError("capsule_containment: backup is linked")


def _replace_path(source: Path, destination: Path, backup: Path, allowed_root: Path) -> tuple[bool, bool]:
    _validate_replace_containment(source, destination, backup, allowed_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_replace_containment(source, destination, backup, allowed_root)
    had_current = destination.exists() or destination.is_symlink()
    moved_current = False
    if had_current:
        if backup.exists() or backup.is_symlink():
            _remove_owned_path(backup, allowed_root)
        backup.parent.mkdir(parents=True, exist_ok=True)
        _validate_replace_containment(source, destination, backup, allowed_root)
        os.replace(destination, backup)
        moved_current = True
    try:
        _validate_replace_containment(source, destination, backup, allowed_root)
        os.replace(source, destination)
        return had_current, moved_current
    except Exception:
        if moved_current and (backup.exists() or backup.is_symlink()):
            os.replace(backup, destination)
        raise


def _activate_candidate(target: Path, stage: Path, previous_manifest: Mapping[str, Any] | None) -> None:
    """Activate a fully validated candidate with an all-or-restore transaction.

    The function is intentionally a narrow seam: failure injection tests patch
    it to prove no active file changes before the activation phase begins.
    """
    core = target / ".kimmizo" / "core"
    candidate_manifest = _parse_manifest(stage / "manifest.json")
    current_agents = target / "AGENTS.md"
    try:
        agents_bytes = current_agents.read_bytes() if current_agents.is_file() else b""
    except OSError as error:
        raise ValueError("capsule_invalid: AGENTS.md cannot be read for activation") from error
    activation_agents = stage / "AGENTS.activation.md"
    _atomic_write_bytes(
        activation_agents,
        _merge_v2_block(agents_bytes, (stage / "agents-v2-block.md").read_bytes()),
    )
    archive_destination: Path | None = None
    archive_created = False
    if previous_manifest is not None:
        previous_revision = previous_manifest["active_revision"]
        archive_stage = stage / "previous"
        _stage_active_snapshot(target, archive_stage, previous_manifest)
        archive_destination = core / "revisions" / previous_revision
        if not archive_destination.exists() and not archive_destination.is_symlink():
            archive_destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(archive_stage, archive_destination)
            archive_created = True
        elif _snapshot_fingerprint(archive_destination) != _snapshot_fingerprint(archive_stage):
            raise ValueError("capsule_archive_conflict: existing revision archive differs from staged snapshot")

    entries = [
        (stage / "payload" / ".agents" / "skills" / "kimweaver", target / ".agents" / "skills" / "kimweaver", "skill"),
        (stage / "payload" / ".kimmizo" / "core" / "runtime" / "kimmizo_v2", core / "runtime" / "kimmizo_v2", "runtime"),
        (stage / "payload" / ".kimmizo" / "voice-bootstrap.json", target / ".kimmizo" / "voice-bootstrap.json", "voice"),
        (stage / "manifest.json", core / "manifest.json", "manifest"),
        (stage / "migration.json", core / "migration.json", "migration"),
        (activation_agents, target / "AGENTS.md", "agents"),
    ]
    backup_root = stage / "backup"
    committed: list[tuple[Path, Path, bool]] = []
    try:
        for source, destination, label in entries:
            had_current, _ = _replace_path(source, destination, backup_root / label, target)
            committed.append((destination, backup_root / label, had_current))
    except Exception:
        for destination, backup, had_current in reversed(committed):
            if destination.exists() or destination.is_symlink():
                _remove_owned_path(destination, target)
            if had_current and (backup.exists() or backup.is_symlink()):
                os.replace(backup, destination)
        if archive_created and archive_destination is not None and archive_destination.exists():
            _remove_owned_path(archive_destination, core)
        raise
    for _, backup, _ in committed:
        if backup.exists() or backup.is_symlink():
            _remove_owned_path(backup, target)
    del candidate_manifest


def _status_from_error(target: Path, error: Exception) -> dict[str, Any]:
    message = str(error)
    if message.startswith("capsule_unknown_major"):
        reason = "unknown_major"
    elif message.startswith("capsule_hash_mismatch"):
        reason = "hash_mismatch"
    else:
        reason = "invalid"
    return {
        "status": "invalid",
        "reason": reason,
        "detail": message,
        "next_action": "run doctor then repair",
        "target": str(target),
    }


def capsule_status(target: str | Path) -> dict[str, Any]:
    """Validate an active capsule using only paths inside ``target``."""
    target_path = Path(target).expanduser().resolve()
    core = target_path / ".kimmizo" / "core"
    manifest_path = core / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {"status": "missing", "reason": "not_installed", "target": str(target_path)}
    try:
        manifest = _parse_manifest(manifest_path)
        _validate_authoritative_project_binding(target_path, manifest)
        agents_path = target_path / "AGENTS.md"
        agents_bytes = agents_path.read_bytes()
        matches = list(_V2_BLOCK_EXACT_BYTES_PATTERN.finditer(agents_bytes))
        if len(matches) != 1:
            raise ValueError("capsule_invalid: active AGENTS v2 block is not unique")
        _validate_payload(
            root=target_path,
            manifest=manifest,
            payload_root=target_path,
            block=matches[0].group(0),
            migration_path=core / "migration.json",
        )
    except (OSError, UnicodeError, ValueError) as error:
        return _status_from_error(target_path, error)
    return {
        "status": "healthy",
        "target": str(target_path),
        "active_revision": manifest["active_revision"],
        "previous_revision": manifest["previous_revision"],
        "aggregate_sha256": manifest["aggregate_sha256"],
        "source_revision": manifest["source_revision"],
    }


def _active_manifest_if_parseable(target: Path) -> dict[str, Any] | None:
    path = target / ".kimmizo" / "core" / "manifest.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return _parse_manifest(path)
    except ValueError:
        return None


def _unowned_v2_paths(target: Path) -> list[str]:
    """Return v2-shaped paths that exist without an active ownership manifest."""
    candidates = (
        ".agents/skills/kimweaver",
        ".kimmizo/core/runtime/kimmizo_v2",
        ".kimmizo/core/migration.json",
        ".kimmizo/voice-bootstrap.json",
    )
    conflicts = [
        relative
        for relative in candidates
        if (_at(target, relative).exists() or _at(target, relative).is_symlink())
    ]
    agents_path = target / "AGENTS.md"
    if agents_path.is_file() and not agents_path.is_symlink():
        try:
            agents_text = agents_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError("capsule_conflict: unowned AGENTS.md cannot be inspected") from error
        if _V2_BLOCK_PATTERN.search(agents_text):
            conflicts.append("AGENTS.md#kimweaver-v2-managed")
    return conflicts


def materialize_capsule(
    target: str | Path,
    *,
    project_id: str | None = None,
    dry_run: bool = False,
    repair: bool = False,
    force_revision: bool = False,
    plugin_root: str | Path | None = None,
    vendor_root: str | Path | None = None,
    runtime_source: str | Path | None = None,
    policy_path: str | Path | None = None,
    template_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build, validate, archive, and activate a local v2 capsule.

    ``dry_run`` validates source inputs and returns the prospective revision but
    never creates a target path.  Existing invalid capsules fail closed unless
    the caller selected the repair lifecycle.
    """
    target_path = Path(target).expanduser().resolve()
    source_plugin = Path(plugin_root).expanduser().resolve() if plugin_root is not None else None
    source_vendor = Path(vendor_root).expanduser().resolve() if vendor_root is not None else None
    source_runtime = Path(runtime_source).expanduser().resolve() if runtime_source is not None else None
    source_policy = Path(policy_path).expanduser().resolve() if policy_path is not None else None
    source_template = Path(template_path).expanduser().resolve() if template_path is not None else None
    payloads, block, policy_hash = _source_payloads(
        plugin_root=source_plugin,
        vendor_root=source_vendor,
        runtime_source=source_runtime,
        policy_path=source_policy,
        template_path=source_template,
    )
    canonical_project_id = _canonical_uuid(_project_id(target_path, project_id), "project_id")
    current_status = capsule_status(target_path)
    current_manifest = _active_manifest_if_parseable(target_path)
    if current_status["status"] == "missing" and current_manifest is None:
        unowned = _unowned_v2_paths(target_path)
        if unowned:
            raise ValueError(
                "capsule_conflict: unowned v2 paths require manual reconciliation: "
                + ", ".join(unowned)
            )
    if current_status["status"] == "invalid" and str(current_status.get("detail", "")).startswith("capsule_conflict"):
        raise ValueError(f"{current_status['detail']}; manual reconciliation is required")
    if current_status["status"] == "invalid" and repair:
        # A repair replaces an untrusted capsule rather than preserving it as a
        # rollback target.  The legacy v1 projection remains untouched.
        current_manifest = None
    migration_bytes = _migration_bytes_for_target(target_path, canonical_project_id)
    previous_revision = current_manifest.get("active_revision") if current_manifest else None
    manifest = _candidate_manifest(
        project_id=canonical_project_id,
        payloads=payloads,
        block=block,
        policy_hash=policy_hash,
        migration_sha256=_sha256_bytes(migration_bytes),
        previous_revision=previous_revision,
        force_revision=force_revision,
    )
    if dry_run:
        return {
            "status": "planned",
            "target": str(target_path),
            "active_revision": manifest["active_revision"],
            "aggregate_sha256": manifest["aggregate_sha256"],
        }
    if current_status["status"] == "invalid" and not repair:
        prefix = "capsule_unknown_major" if current_status["reason"] == "unknown_major" else "capsule_hash_mismatch"
        raise ValueError(f"{prefix}: {current_status['detail']}; run capsule-status then repair")
    if (
        current_status["status"] == "healthy"
        and current_manifest is not None
        and current_manifest.get("project_id") == canonical_project_id
        and current_manifest.get("source_revision") == manifest["source_revision"]
        and current_manifest.get("migration_sha256") == _sha256_bytes(migration_bytes)
        and not force_revision
    ):
        return {
            "status": "unchanged",
            "target": str(target_path),
            "active_revision": current_manifest["active_revision"],
            "aggregate_sha256": current_manifest["aggregate_sha256"],
        }

    target_path.mkdir(parents=True, exist_ok=True)
    core = target_path / ".kimmizo" / "core"
    with _exclusive_capsule_lock(core):
        # Re-evaluate under the lock so concurrent setup/update work cannot
        # silently replace a revision that appeared after source validation.
        current_status = capsule_status(target_path)
        current_manifest = _active_manifest_if_parseable(target_path)
        if current_status["status"] == "missing" and current_manifest is None:
            unowned = _unowned_v2_paths(target_path)
            if unowned:
                raise ValueError(
                    "capsule_conflict: unowned v2 paths require manual reconciliation: "
                    + ", ".join(unowned)
                )
        if current_status["status"] == "invalid" and str(current_status.get("detail", "")).startswith("capsule_conflict"):
            raise ValueError(f"{current_status['detail']}; manual reconciliation is required")
        if current_status["status"] == "invalid" and repair:
            current_manifest = None
        if current_status["status"] == "invalid" and not repair:
            prefix = "capsule_unknown_major" if current_status["reason"] == "unknown_major" else "capsule_hash_mismatch"
            raise ValueError(f"{prefix}: {current_status['detail']}; run capsule-status then repair")
        migration_bytes = _migration_bytes_for_target(target_path, canonical_project_id)
        if (
            current_status["status"] == "healthy"
            and current_manifest is not None
            and current_manifest.get("project_id") == canonical_project_id
            and current_manifest.get("source_revision") == manifest["source_revision"]
            and current_manifest.get("migration_sha256") == _sha256_bytes(migration_bytes)
            and not force_revision
        ):
            return {
                "status": "unchanged",
                "target": str(target_path),
                "active_revision": current_manifest["active_revision"],
                "aggregate_sha256": current_manifest["aggregate_sha256"],
            }
        previous_revision = current_manifest.get("active_revision") if current_manifest else None
        manifest = _candidate_manifest(
            project_id=canonical_project_id,
            payloads=payloads,
            block=block,
            policy_hash=policy_hash,
            migration_sha256=_sha256_bytes(migration_bytes),
            previous_revision=previous_revision,
            force_revision=force_revision,
        )
        stage = core / ".staging" / f"candidate-{uuid.uuid4().hex}"
        stage.mkdir(parents=True, exist_ok=False)
        _prepare_candidate(
            target=target_path,
            stage=stage,
            manifest=manifest,
            payloads=payloads,
            block=block,
            migration_bytes=migration_bytes,
        )
        # An invalid pre-existing capsule may be repaired only after its source
        # candidate is complete and independently hash-validated in staging.
        _activate_candidate(target_path, stage, current_manifest)
        _remove_owned_path(stage, core)
    return {
        "status": "active",
        "target": str(target_path),
        "active_revision": manifest["active_revision"],
        "previous_revision": manifest["previous_revision"],
        "aggregate_sha256": manifest["aggregate_sha256"],
    }


def _remove_v2_block_from_agents(target: Path) -> None:
    path = target / "AGENTS.md"
    if not path.is_file() or path.is_symlink():
        return
    try:
        agents_bytes = path.read_bytes()
    except OSError as error:
        raise ValueError("capsule_invalid: AGENTS.md cannot be read for rollback") from error
    matches = list(_V2_BLOCK_EXACT_BYTES_PATTERN.finditer(agents_bytes))
    if len(matches) > 1:
        raise ValueError("capsule_invalid: multiple Kimweaver v2 blocks require repair")
    if not matches:
        return
    start, end = matches[0].span()
    prefix = agents_bytes[:start]
    suffix = agents_bytes[end:]
    # The first newline immediately following a v2 block is installation-owned
    # (and can be CRLF after a v1 text-mode refresh).  Any later user suffix is
    # retained byte-for-byte.
    if suffix.startswith(b"\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith(b"\n"):
        suffix = suffix[1:]
    if prefix.endswith(b"\r\n"):
        prefix = prefix[:-2]
    elif prefix.endswith(b"\n"):
        prefix = prefix[:-1]
    _atomic_write_bytes(path, prefix + suffix)


def rollback_capsule(target: str | Path) -> dict[str, Any]:
    """Restore the prior v2 revision, or remove only v2-owned artifacts."""
    target_path = Path(target).expanduser().resolve()
    status = capsule_status(target_path)
    if status["status"] == "missing":
        return {"status": "missing", "target": str(target_path)}
    if status["status"] != "healthy":
        raise ValueError(f"capsule_invalid: cannot roll back invalid capsule; run repair first ({status['detail']})")
    core = target_path / ".kimmizo" / "core"
    remove_core_after_unlock = False
    with _exclusive_capsule_lock(core):
        manifest = _parse_manifest(core / "manifest.json")
        _validate_authoritative_project_binding(target_path, manifest)
        previous_revision = manifest.get("previous_revision")
        if not previous_revision:
            _remove_owned_path(target_path / ".agents" / "skills" / "kimweaver", target_path)
            _remove_owned_path(core / "runtime" / "kimmizo_v2", core)
            _remove_owned_path(core / "manifest.json", core)
            _remove_owned_path(core / "migration.json", core)
            _remove_owned_path(core / "revisions", core)
            _remove_owned_path(core / ".staging", core)
            _remove_owned_path(target_path / ".kimmizo" / "voice-bootstrap.json", target_path)
            _remove_v2_block_from_agents(target_path)
            runtime_parent = core / "runtime"
            if runtime_parent.is_dir() and not any(runtime_parent.iterdir()):
                runtime_parent.rmdir()
            remove_core_after_unlock = True
            result = {"status": "removed", "target": str(target_path)}
        else:
            snapshot = core / "revisions" / previous_revision
            if not snapshot.is_dir() or snapshot.is_symlink():
                raise ValueError("capsule_invalid: previous v2 revision is unavailable; run repair")
            snapshot_manifest = _parse_manifest(snapshot / "manifest.json")
            _validate_authoritative_project_binding(target_path, snapshot_manifest)
            _validate_payload(
                root=target_path,
                manifest=snapshot_manifest,
                payload_root=snapshot / "payload",
                block=(snapshot / "agents-v2-block.md").read_bytes(),
                migration_path=snapshot / "migration.json",
            )
            stage = core / ".staging" / f"rollback-{uuid.uuid4().hex}"
            shutil.copytree(snapshot, stage, copy_function=shutil.copyfile)
            current_manifest = _parse_manifest(core / "manifest.json")
            _activate_candidate(target_path, stage, current_manifest)
            _remove_owned_path(stage, core)
            result = {
                "status": "rolled_back",
                "target": str(target_path),
                "active_revision": snapshot_manifest["active_revision"],
            }
    if remove_core_after_unlock and core.is_dir() and not any(core.iterdir()):
        core.rmdir()
    return result


__all__ = [
    "ADAPTER_VERSION",
    "CAPSULE_SCHEMA",
    "CAPSULE_SCHEMA_VERSION",
    "CAPSULE_VERSION",
    "CORE_VERSION",
    "capsule_status",
    "materialize_capsule",
    "rollback_capsule",
]

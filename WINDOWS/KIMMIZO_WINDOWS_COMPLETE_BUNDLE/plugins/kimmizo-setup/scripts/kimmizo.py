#!/usr/bin/env python3
"""Kimmizo Setup v1: project bootstrap, capability doctor, router and memory."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import tomllib
import uuid
import zipfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


VERSION = "1.0.0"
SCHEMA_VERSION = 1
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = PLUGIN_ROOT / "registry"
CAPABILITY_REGISTRY = REGISTRY_DIR / "capabilities.json"
BASELINE_LOCK = REGISTRY_DIR / "baseline-lock.json"
CONFLICT_REGISTRY = REGISTRY_DIR / "conflicts.json"
MODEL_POLICY = REGISTRY_DIR / "model-policy.json"
TEMPLATE_ROOT = PLUGIN_ROOT / "templates" / "project-capsule"

AGENT_BLOCK_BEGIN = "BEGIN KIMMIZO MANAGED BLOCK"
AGENT_BLOCK_END = "END KIMMIZO MANAGED BLOCK"
KIMWEAVER_V2_BLOCK_BEGIN = "<!-- BEGIN KIMWEAVER-V2-MANAGED -->"
KIMWEAVER_V2_BLOCK_END = "<!-- END KIMWEAVER-V2-MANAGED -->"
KIMWEAVER_V2_BLOCK_PATTERN = re.compile(
    r"<!-- BEGIN KIMWEAVER-V2-MANAGED -->\r?\n.*?<!-- END KIMWEAVER-V2-MANAGED -->",
    re.DOTALL,
)
SAFE_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ALLOWED_SUPERPOWER_SKILLS = {
    "superpowers:brainstorming",
    "superpowers:writing-plans",
    "superpowers:test-driven-development",
    "superpowers:systematic-debugging",
    "superpowers:dispatching-parallel-agents",
    "superpowers:subagent-driven-development",
    "superpowers:verification-before-completion",
}
_HOST_FEATURE_CACHE: tuple[float, dict[str, bool]] = (0.0, {})
_HOST_PLUGIN_CACHE: tuple[float, dict[str, dict[str, str]]] = (0.0, {})


def _load_v2_package() -> Any:
    """Load the sibling v2 package without assuming this entrypoint is imported as a package."""
    package_dir = PLUGIN_ROOT / "scripts" / "kimmizo_v2"
    init_path = package_dir / "__init__.py"
    package_name = "_kimmizo_v2_" + hashlib.sha256(
        str(package_dir.resolve()).encode("utf-8")
    ).hexdigest()[:16]
    loaded = sys.modules.get(package_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(
        package_name,
        init_path,
        submodule_search_locations=[str(package_dir)],
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load Kimweaver v2 package: {init_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if sys.modules.get(package_name) is module:
            sys.modules.pop(package_name, None)
        raise
    return module


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_secrets(value: str) -> str:
    redacted = value
    patterns = [
        (r"(?i)\b(bearer)\s+[A-Za-z0-9._~+\-/]+=*", r"\1 [REDACTED]"),
        (r"(?i)\b(ghp_|github_pat_|sk-)[A-Za-z0-9_-]{12,}", "[REDACTED_TOKEN]"),
        (
            r"(?i)(token|api[_-]?key|secret|password|passwd|credential)(\s*[=:]\s*)[^\s,;&]+",
            r"\1\2[REDACTED]",
        ),
        (
            r"(?i)([?&](?:token|key|secret|password)=)[^&#\s]+",
            r"\1[REDACTED]",
        ),
    ]
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def _lexical_absolute(path: Path) -> Path:
    """Make an absolute path without resolving a possibly linked component."""
    return Path(os.path.abspath(os.fspath(path)))


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _is_linked_or_reparse(path: Path, info: os.stat_result | None = None) -> bool:
    """Treat symlinks, Windows junctions, and other reparse points as linked paths."""
    observed = info if info is not None else _lstat_or_none(path)
    if observed is None:
        return False
    reparse = bool(
        getattr(observed, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    return stat.S_ISLNK(observed.st_mode) or reparse


def _assert_unlinked_directory_chain(path: Path, *, label: str) -> None:
    """Reject an existing linked/reparse component in a lexical path chain."""
    absolute = _lexical_absolute(path)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for part in parts:
        current /= part
        info = _lstat_or_none(current)
        if info is None:
            break
        if _is_linked_or_reparse(current, info):
            raise PermissionError(f"{label} is linked or a reparse point: {current}")


def _assert_setup_target_safe(path: Path) -> Path:
    """Validate the caller's lexical target before ``resolve()`` can hide a junction."""
    absolute = _lexical_absolute(path)
    _assert_unlinked_directory_chain(absolute, label="Setup target")
    info = _lstat_or_none(absolute)
    if info is not None and not stat.S_ISDIR(info.st_mode):
        raise PermissionError(f"Setup target is not a regular directory: {absolute}")
    return absolute


def _assert_setup_file_safe(path: Path, target: Path, *, label: str = "setup file") -> Path:
    """Fail closed before reading or replacing a setup-owned regular file.

    The check is deliberately lexical: resolving first would conceal a junction
    beneath the project root.  Existing leaves must be singly linked regular
    files, and every existing ancestor must be a real directory.
    """
    root = _lexical_absolute(target)
    candidate = _lexical_absolute(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise PermissionError(f"{label} escapes the setup target: {candidate}") from error
    if not relative.parts:
        raise PermissionError(f"{label} cannot be the setup target itself: {candidate}")

    root_info = _lstat_or_none(root)
    if root_info is not None:
        if _is_linked_or_reparse(root, root_info):
            raise PermissionError(f"Setup target is linked or a reparse point: {root}")
        if not stat.S_ISDIR(root_info.st_mode):
            raise PermissionError(f"Setup target is not a regular directory: {root}")

    current = root
    for index, part in enumerate(relative.parts):
        current /= part
        info = _lstat_or_none(current)
        if info is None:
            break
        if _is_linked_or_reparse(current, info):
            raise PermissionError(f"{label} is linked or a reparse point: {current}")
        if index < len(relative.parts) - 1:
            if not stat.S_ISDIR(info.st_mode):
                raise PermissionError(f"{label} has a non-directory ancestor: {current}")
            continue
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError(f"{label} is not a regular file: {current}")
        if info.st_nlink != 1:
            raise PermissionError(f"{label} is linked or not singly owned: {current}")
    return candidate


def _assert_setup_directory_safe(path: Path, target: Path, *, label: str) -> Path:
    """Validate a directory tree that setup may atomically replace or remove."""
    root = _lexical_absolute(target)
    candidate = _lexical_absolute(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise PermissionError(f"{label} escapes the setup target: {candidate}") from error
    if not relative.parts:
        raise PermissionError(f"{label} cannot be the setup target itself: {candidate}")
    current = root
    root_info = _lstat_or_none(root)
    if root_info is not None:
        if _is_linked_or_reparse(root, root_info) or not stat.S_ISDIR(root_info.st_mode):
            raise PermissionError(f"Setup target is unsafe: {root}")
    for index, part in enumerate(relative.parts):
        current /= part
        info = _lstat_or_none(current)
        if info is None:
            break
        if _is_linked_or_reparse(current, info):
            raise PermissionError(f"{label} is linked or a reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            if index == len(relative.parts) - 1:
                raise PermissionError(f"{label} is not a regular directory: {current}")
            raise PermissionError(f"{label} has a non-directory ancestor: {current}")
    return candidate


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.kimmizo-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str, *, newline: str | None = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.kimmizo-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline=newline) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_unlinked_path(path: Path, target: Path) -> None:
    """Remove only a real, contained file tree after a fresh linked-path guard."""
    candidate = _lexical_absolute(path)
    root = _lexical_absolute(target)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PermissionError(f"Rollback path escapes the setup target: {candidate}") from error
    info = _lstat_or_none(candidate)
    if info is None:
        return
    if _is_linked_or_reparse(candidate, info):
        raise PermissionError(f"Rollback path is linked or a reparse point: {candidate}")
    if stat.S_ISREG(info.st_mode):
        candidate.unlink()
        return
    if not stat.S_ISDIR(info.st_mode):
        raise PermissionError(f"Rollback path is not a regular file or directory: {candidate}")
    with os.scandir(candidate) as entries:
        children = [Path(entry.path) for entry in entries]
    for child in children:
        _remove_unlinked_path(child, root)
    candidate.rmdir()


class _SetupFileFingerprint:
    """A compare-and-swap token for a singly-owned regular file."""

    __slots__ = ("exists", "device", "inode", "size", "sha256")

    def __init__(
        self,
        exists: bool,
        device: int | None = None,
        inode: int | None = None,
        size: int | None = None,
        sha256: str | None = None,
    ):
        self.exists = exists
        self.device = device
        self.inode = inode
        self.size = size
        self.sha256 = sha256

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _SetupFileFingerprint) and (
            self.exists,
            self.device,
            self.inode,
            self.size,
            self.sha256,
        ) == (
            other.exists,
            other.device,
            other.inode,
            other.size,
            other.sha256,
        )


class _SetupTreeFingerprint:
    """A structural compare-and-swap token for a v2-owned directory root."""

    __slots__ = ("exists", "directories", "files")

    def __init__(
        self,
        exists: bool,
        directories: tuple[tuple[str, int, int], ...],
        files: dict[str, _SetupFileFingerprint],
    ):
        self.exists = exists
        self.directories = directories
        self.files = files

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _SetupTreeFingerprint) and (
            self.exists,
            self.directories,
            self.files,
        ) == (
            other.exists,
            other.directories,
            other.files,
        )


class _SetupRollbackDiverged(RuntimeError):
    """Rollback refused to overwrite an artifact that no longer matches setup output."""

    def __init__(self, paths: Iterable[Path]):
        rendered = ", ".join(str(path) for path in paths)
        super().__init__(f"Setup transaction rollback found diverged path(s); preserved them: {rendered}")


def _fingerprint_setup_file(path: Path, target: Path, *, label: str) -> _SetupFileFingerprint:
    candidate = _assert_setup_file_safe(path, target, label=label)
    info = _lstat_or_none(candidate)
    if info is None:
        return _SetupFileFingerprint(False)
    return _SetupFileFingerprint(
        True,
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        sha256=sha256_file(candidate),
    )


def _fingerprint_regular_tree(path: Path, target: Path, *, label: str) -> _SetupTreeFingerprint:
    """Fingerprint a linked-free v2-owned tree without keeping its bytes for rollback."""
    root = _assert_setup_directory_safe(path, target, label=label)
    if _lstat_or_none(root) is None:
        return _SetupTreeFingerprint(False, (), {})
    root_info = _lstat_or_none(root)
    assert root_info is not None
    directories: list[tuple[str, int, int]] = [("", root_info.st_dev, root_info.st_ino)]
    files: dict[str, _SetupFileFingerprint] = {}

    def visit(current: Path, relative: Path) -> None:
        info = _lstat_or_none(current)
        if info is None:
            raise FileNotFoundError(f"Setup rollback tree changed while being captured: {current}")
        if _is_linked_or_reparse(current, info):
            raise PermissionError(f"{label} is linked or a reparse point: {current}")
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise PermissionError(f"{label} contains a linked or non-owned file: {current}")
            files[relative.as_posix()] = _SetupFileFingerprint(
                True,
                device=info.st_dev,
                inode=info.st_ino,
                size=info.st_size,
                sha256=sha256_file(current),
            )
            return
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError(f"{label} contains an unsupported path: {current}")
        with os.scandir(current) as entries:
            children = sorted((Path(entry.path) for entry in entries), key=lambda item: item.name)
        for child in children:
            child_relative = relative / child.name
            child_info = _lstat_or_none(child)
            if child_info is None:
                raise FileNotFoundError(f"Setup rollback tree changed while being captured: {child}")
            if _is_linked_or_reparse(child, child_info):
                raise PermissionError(f"{label} is linked or a reparse point: {child}")
            if stat.S_ISDIR(child_info.st_mode):
                directories.append((child_relative.as_posix(), child_info.st_dev, child_info.st_ino))
            visit(child, child_relative)

    visit(root, Path("."))
    return _SetupTreeFingerprint(True, tuple(directories), files)


class _SetupTransaction:
    """In-memory compensation for the v1+v2 publication boundary.

    It never creates an on-disk backup of project memory or knowledge.  The v2
    roots are source/runtime material only; all v1 leaf bytes, including a
    preexisting memory mirror when setup would replace it, remain process-local
    until a successful setup commits.
    """

    def __init__(self, target: Path):
        self.target = _lexical_absolute(target)
        self._files: dict[Path, bytes | None] = {}
        self._expected_files: dict[Path, _SetupFileFingerprint] = {}
        self._v2_files: dict[Path, _SetupFileFingerprint] = {}
        self._v2_trees: dict[Path, _SetupTreeFingerprint] = {}
        self._created_directories: set[Path] = set()
        self._created_directory_fingerprints: dict[Path, tuple[int, int]] = {}

    def _record_missing_directories(self, path: Path, *, include_path: bool = False) -> None:
        current = _lexical_absolute(path if include_path else path.parent)
        missing: list[Path] = []
        while True:
            try:
                current.relative_to(self.target)
            except ValueError:
                break
            if _lstat_or_none(current) is not None:
                break
            missing.append(current)
            if current == self.target:
                break
            current = current.parent
        self._created_directories.update(missing)

    def capture_file(self, path: Path, *, label: str = "setup file") -> Path:
        candidate = _assert_setup_file_safe(path, self.target, label=label)
        if candidate in self._files:
            return candidate
        self._record_missing_directories(candidate)
        self._files[candidate] = candidate.read_bytes() if _lstat_or_none(candidate) is not None else None
        return candidate

    def _record_created_directory_fingerprints(self) -> None:
        for directory in self._created_directories:
            info = _lstat_or_none(directory)
            if info is not None and stat.S_ISDIR(info.st_mode) and not _is_linked_or_reparse(directory, info):
                self._created_directory_fingerprints[directory] = (info.st_dev, info.st_ino)

    def record_written_file(self, path: Path, *, label: str) -> None:
        candidate = _assert_setup_file_safe(path, self.target, label=label)
        self._expected_files[candidate] = _fingerprint_setup_file(candidate, self.target, label=label)
        self._record_created_directory_fingerprints()

    def _capture_v2_file(self, path: Path, *, label: str) -> None:
        candidate = _assert_setup_file_safe(path, self.target, label=label)
        self._v2_files[candidate] = _fingerprint_setup_file(candidate, self.target, label=label)

    def _capture_v2_tree(self, path: Path, *, label: str) -> None:
        candidate = _assert_setup_directory_safe(path, self.target, label=label)
        self._v2_trees[candidate] = _fingerprint_regular_tree(candidate, self.target, label=label)

    def capture_v2_publication(self) -> None:
        """Capture CAS fingerprints for v2-owned publication roots before activation."""
        self._capture_v2_file(self.target / "AGENTS.md", label="AGENTS.md authority file")
        for path, label in (
            (self.target / ".kimmizo" / "voice-bootstrap.json", "v2 voice bootstrap"),
            (self.target / ".kimmizo" / "core" / "manifest.json", "v2 manifest"),
            (self.target / ".kimmizo" / "core" / "migration.json", "v2 migration receipt"),
        ):
            self._capture_v2_file(path, label=label)
        for path, label in (
            (self.target / ".agents" / "skills" / "kimweaver", "v2 skill root"),
            (self.target / ".kimmizo" / "core" / "runtime" / "kimmizo_v2", "v2 runtime root"),
            (self.target / ".kimmizo" / "core" / "revisions", "v2 revision root"),
        ):
            self._capture_v2_tree(path, label=label)

    def rollback(self) -> None:
        diverged: list[Path] = []
        for path, expected in self._v2_files.items():
            try:
                if _fingerprint_setup_file(path, self.target, label="v2 rollback verification") != expected:
                    diverged.append(path)
            except Exception:
                diverged.append(path)
        for root, expected in self._v2_trees.items():
            try:
                if _fingerprint_regular_tree(root, self.target, label="v2 rollback verification") != expected:
                    diverged.append(root)
            except Exception:
                diverged.append(root)
        for path, content in reversed(tuple(self._files.items())):
            expected = self._expected_files.get(path)
            if expected is None:
                continue
            try:
                if _fingerprint_setup_file(path, self.target, label="setup rollback file") != expected:
                    diverged.append(path)
                    continue
                if content is None:
                    _remove_unlinked_path(path, self.target)
                else:
                    _atomic_write_bytes(path, content)
            except Exception:
                diverged.append(path)
        for directory in sorted(self._created_directories, key=lambda item: len(item.parts), reverse=True):
            try:
                info = _lstat_or_none(directory)
                if (
                    info is not None
                    and stat.S_ISDIR(info.st_mode)
                    and not _is_linked_or_reparse(directory, info)
                    and self._created_directory_fingerprints.get(directory) == (info.st_dev, info.st_ino)
                ):
                    directory.rmdir()
            except OSError:
                # A non-empty directory may contain a concurrently-created user
                # artifact.  Retaining it is safer than deleting it.
                pass
        if diverged:
            raise _SetupRollbackDiverged(dict.fromkeys(diverged))


def write_if_changed(
    path: Path,
    content: str,
    actions: list[dict[str, Any]] | None = None,
    *,
    dry_run: bool = False,
    reason: str = "managed",
    allowed_root: Path | None = None,
    transaction: _SetupTransaction | None = None,
) -> bool:
    safe_path = (
        _assert_setup_file_safe(path, allowed_root, label=reason)
        if allowed_root is not None
        else path
    )
    current = safe_path.read_text(encoding="utf-8") if safe_path.is_file() else None
    if current == content:
        return False
    if actions is not None:
        actions.append(
            {
                "action": "create" if current is None else "update",
                "path": str(safe_path),
                "reason": reason,
            }
        )
    if not dry_run:
        if transaction is not None:
            transaction.capture_file(safe_path, label=reason)
        # Preserve Path.write_text's platform newline behavior for existing
        # v1 authority bytes; the v2 migration receipt hashes those raw bytes.
        _atomic_write_text(safe_path, content, newline=None)
        if transaction is not None:
            transaction.record_written_file(safe_path, label=reason)
    return True


@contextmanager
def _exclusive_directory_lock(
    root: Path,
    name: str,
    timeout_seconds: float = 15.0,
    *,
    recover_stale: bool = True,
):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / f".{name}.lock"
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()} at={utc_now()}".encode("utf-8"))
        except (FileExistsError, PermissionError) as exc:
            if isinstance(exc, PermissionError) and not lock.exists():
                raise
            try:
                stale = time.time() - lock.stat().st_mtime > 60
            except (FileNotFoundError, PermissionError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for checkpoint lock: {lock}")
                time.sleep(0.05)
                continue
            if stale and recover_stale:
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for checkpoint lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock.unlink(missing_ok=True)


def load_registry(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or CAPABILITY_REGISTRY)


def load_conflict_rules() -> list[dict[str, Any]]:
    return load_json(CONFLICT_REGISTRY)["rules"]


def _install_requires_approval(install: dict[str, Any]) -> bool:
    authority_rule = next(
        (rule for rule in load_conflict_rules() if rule["id"] == "authority-change"),
        {"when": {"any": ["auth", "hook", "mcp", "app", "new_permissions", "external_write"]}},
    )
    authority_fields = authority_rule.get("when", {}).get("any", [])
    return install.get("approval") != "none" or any(install.get(field) for field in authority_fields)


def _template_text(relative_path: str) -> str:
    return (TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")


def _unique_paths(paths: Iterable[Path]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path.absolute()).casefold()
        if key not in seen:
            seen.add(key)
            result.append(str(path))
    return result


def _glob_home(home: Path, patterns: Iterable[str]) -> list[str]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(path for path in home.glob(pattern) if path.is_file())
    return _unique_paths(found)


def _read_toml(path: Path) -> tuple[dict[str, Any], str, str | None]:
    if not path.is_file():
        return {}, "", None
    text = path.read_text(encoding="utf-8-sig")
    try:
        return tomllib.loads(text), text, None
    except tomllib.TOMLDecodeError as error:
        return {}, text, str(error)


def _merge_config_data(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _selector_enabled(data: dict[str, Any], text: str, selector: str) -> bool:
    plugin_table = data.get("plugins", {})
    if isinstance(plugin_table, dict):
        value = plugin_table.get(selector)
        if isinstance(value, dict) and value.get("enabled") is True:
            return True
    pattern = re.compile(
        rf'\[plugins\."{re.escape(selector)}"\][^\[]*?\benabled\s*=\s*true',
        re.IGNORECASE | re.DOTALL,
    )
    return bool(pattern.search(text))


def _command_evidence(commands: Iterable[str]) -> list[str]:
    paths = [Path(found) for command in commands if (found := shutil.which(command))]
    return _unique_paths(paths)


def _system_browser_evidence() -> list[str]:
    candidates: list[Path] = []
    if platform.system().casefold() == "windows":
        for variable, suffixes in {
            "PROGRAMFILES": ["Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"],
            "PROGRAMFILES(X86)": ["Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"],
            "LOCALAPPDATA": ["Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"],
        }.items():
            root = os.environ.get(variable)
            if root:
                candidates.extend(Path(root) / Path(suffix) for suffix in suffixes)
    else:
        candidates.extend(
            Path(found)
            for command in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")
            if (found := shutil.which(command))
        )
    return _unique_paths(path for path in candidates if path.is_file())


def _codex_features() -> dict[str, bool]:
    """Probe host features instead of assuming built-ins are available."""
    global _HOST_FEATURE_CACHE
    cached_at, cached_value = _HOST_FEATURE_CACHE
    if cached_value and time.monotonic() - cached_at < 5.0:
        return {**cached_value}
    executable = shutil.which("codex")
    if not executable:
        return {}
    try:
        completed = subprocess.run(
            [executable, "-c", 'model_reasoning_effort="xhigh"', "features", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    features: dict[str, bool] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1].casefold() in {"true", "false"}:
            features[parts[0]] = parts[-1].casefold() == "true"
    _HOST_FEATURE_CACHE = (time.monotonic(), features)
    return {**features}


def _host_plugin_inventory(cwd: Path | None = None) -> dict[str, dict[str, str]]:
    """Return the host-reported active plugin state, version and package path."""
    global _HOST_PLUGIN_CACHE
    cached_at, cached_value = _HOST_PLUGIN_CACHE
    if cached_value and time.monotonic() - cached_at < 5.0:
        return {key: {**value} for key, value in cached_value.items()}
    executable = shutil.which("codex")
    if not executable:
        return {}
    try:
        completed = subprocess.run(
            [executable, "-c", 'model_reasoning_effort="xhigh"', "plugin", "list"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    inventory: dict[str, dict[str, str]] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if "@" not in line:
            continue
        columns = re.split(r"\s{2,}", line, maxsplit=3)
        if len(columns) < 3 or "@" not in columns[0]:
            continue
        selector, status = columns[0], columns[1].casefold()
        if status.startswith("installed") and len(columns) >= 4:
            state = "enabled" if "enabled" in status else "disabled"
            version, package_path = columns[2], columns[3]
        elif status == "not installed":
            state, version, package_path = "not_installed", "", columns[-1]
        else:
            continue
        inventory[selector] = {
            "selector": selector,
            "state": state,
            "version": version,
            "path": package_path,
        }
        manifest_path = Path(package_path) / ".codex-plugin" / "plugin.json"
        if manifest_path.is_file():
            try:
                manifest_version = load_json(manifest_path).get("version")
            except (OSError, UnicodeError, json.JSONDecodeError):
                manifest_version = None
            if manifest_version:
                inventory[selector]["manifest_version"] = str(manifest_version)
    _HOST_PLUGIN_CACHE = (time.monotonic(), inventory)
    return {key: {**value} for key, value in inventory.items()}


def _kimmizo_auto_host_active() -> bool:
    """Detect the reversible Codex host extension inherited by this process."""
    executable = os.environ.get("CODEX_CLI_PATH", "").strip().strip('"')
    if not executable:
        return False
    path = Path(executable).expanduser()
    return path.name.casefold().startswith("codex-kimmizo-auto") and path.suffix.casefold() == ".exe" and path.is_file()


def _invalidate_host_probe_cache() -> None:
    global _HOST_FEATURE_CACHE, _HOST_PLUGIN_CACHE
    _HOST_FEATURE_CACHE = (0.0, {})
    _HOST_PLUGIN_CACHE = (0.0, {})


def _observed_plugin_versions(home: Path, capability: dict[str, Any]) -> list[str]:
    selector = capability.get("selector") or (capability.get("detect") or {}).get("config_selector")
    if not selector or "@" not in selector:
        return []
    plugin_name, marketplace = selector.split("@", 1)
    marketplace_dirs = {
        "openai-curated": ["openai-curated-remote", "openai-curated"],
        "openai-bundled": ["openai-bundled"],
        "openai-primary-runtime": ["openai-primary-runtime"],
        "awesome-codex-plugins": ["awesome-codex-plugins"],
    }.get(marketplace, [marketplace])
    manifests: list[Path] = []
    for marketplace_dir in marketplace_dirs:
        manifests.extend(
            home.glob(
                f".codex/plugins/cache/{marketplace_dir}/{plugin_name}/*/.codex-plugin/plugin.json"
            )
        )
    manifests.extend(
        home.glob(
            f".cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/{plugin_name}/.codex-plugin/plugin.json"
        )
    )
    versions: list[str] = []
    for manifest in manifests:
        try:
            value = load_json(manifest).get("version")
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if value and value not in versions:
            versions.append(str(value))
    return versions


def _capability_status(
    capability: dict[str, Any],
    *,
    home: Path,
    config_data: dict[str, Any],
    config_text: str,
    host_features: dict[str, bool] | None = None,
    host_plugins: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    detect = capability.get("detect") or {}
    kind = capability.get("kind", "unknown")
    evidence: list[str] = []
    state = "missing"

    skill_evidence = _glob_home(home, detect.get("skill_paths", []))
    cache_evidence = _glob_home(home, detect.get("cache_paths", []))
    command_evidence = _command_evidence(detect.get("commands", []))
    evidence.extend(skill_evidence)
    evidence.extend(cache_evidence)
    evidence.extend(command_evidence)

    selector = detect.get("config_selector") or capability.get("selector")
    host_plugin = host_plugins.get(selector) if selector and host_plugins is not None else None
    if host_plugin and host_plugin.get("state") == "enabled":
        state = "enabled_dependency_missing" if detect.get("commands") and not command_evidence else "enabled"
        package_path = Path(host_plugin.get("path", ""))
        if package_path.exists():
            evidence.append(str(package_path))
    elif host_plugin and host_plugin.get("state") == "disabled":
        state = "installed_disabled"
    elif selector and host_plugins is None and _selector_enabled(config_data, config_text, selector):
        state = "enabled_dependency_missing" if detect.get("commands") and not command_evidence else "enabled"
    elif kind in {"plugin", "bundled_plugin", "connector_plugin"} and cache_evidence:
        state = "cached_only"
    elif kind == "skill" and skill_evidence:
        state = "installed"
    elif kind == "cli" and command_evidence:
        state = "installed"
    elif kind == "skill_cli":
        state = "installed" if skill_evidence and command_evidence else "partial" if skill_evidence or command_evidence else "missing"
    elif kind == "host_feature":
        if capability["id"] == "multi-agent":
            state = "available" if (host_features or {}).get("multi_agent") else "missing"
        elif capability["id"] == "skill-discovery":
            state = "available" if (host_features or {}).get("plugins") else "missing"
        elif capability["id"] == "model-catalog":
            state = "configured" if config_data.get("model") else "host_default"

    runtime_evidence: list[str] = []
    if capability.get("id") == "agent-browser" and state == "installed":
        runtime_evidence = _system_browser_evidence()
        evidence.extend(runtime_evidence)
        if not runtime_evidence:
            state = "runtime_missing"

    active_version = (
        host_plugin.get("manifest_version") or host_plugin.get("version")
        if host_plugin and host_plugin.get("state") in {"enabled", "disabled"}
        else None
    )
    observed_versions = [active_version] if active_version else _observed_plugin_versions(home, capability)

    return {
        "id": capability["id"],
        "tier": capability["tier"],
        "kind": kind,
        "state": state,
        "selector": capability.get("selector"),
        "evidence": _unique_paths(Path(item) for item in evidence),
        "observed_versions": observed_versions,
        "active_version": active_version,
        "host_state": host_plugin.get("state") if host_plugin else None,
        "host_release": host_plugin.get("version") if host_plugin else None,
        "host_path": host_plugin.get("path") if host_plugin else None,
        "runtime_evidence": runtime_evidence,
    }


def _parse_codex_version() -> str | None:
    executable = shutil.which("codex")
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", completed.stdout + completed.stderr)
    return match.group(1) if match else None


def _model_catalog(config_data: dict[str, Any], home: Path) -> dict[str, Any]:
    model = config_data.get("model")
    effort = config_data.get("model_reasoning_effort")
    cli_version = _parse_codex_version()
    cli_supported = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
    warnings: list[str] = []
    # Codex CLI 0.136.x is known to reject ultra even when Desktop accepts it.
    if cli_version:
        parts = tuple(int(part) for part in cli_version.split("."))
        if parts <= (0, 136, 99):
            cli_supported = ["none", "minimal", "low", "medium", "high", "xhigh"]
            if effort not in cli_supported and effort is not None:
                warnings.append(
                    f"Configured reasoning '{effort}' is not accepted by Codex CLI {cli_version}; pass an explicit compatible override."
                )
    catalog_path = home / ".codex" / "models_cache.json"
    models: list[dict[str, Any]] = []
    if catalog_path.is_file():
        try:
            cached = load_json(catalog_path)
            for item in cached.get("models", []):
                slug = item.get("slug")
                if not slug:
                    continue
                models.append(
                    {
                        "slug": slug,
                        "display_name": item.get("display_name", slug),
                        "description": item.get("description", ""),
                        "priority": item.get("priority"),
                        "supported_reasoning": [
                            level["effort"]
                            for level in item.get("supported_reasoning_levels", [])
                            if level.get("effort")
                        ],
                    }
                )
        except (OSError, UnicodeError, json.JSONDecodeError):
            warnings.append(f"Model cache could not be read: {catalog_path}")
    configured_entry = next((item for item in models if item["slug"] == model), None)
    host_supported = (
        configured_entry["supported_reasoning"]
        if configured_entry
        else ["low", "medium", "high", "xhigh", "max", "ultra"]
    )
    return {
        "source": "host_models_cache" if models else "host_config_fallback",
        "catalog_path": str(catalog_path),
        "configured_model": model,
        "configured_reasoning": effort,
        "codex_cli_version": cli_version,
        "supported_reasoning": host_supported,
        "cli_supported_reasoning": cli_supported,
        "compatibility_warnings": warnings,
        "catalog_complete": bool(models),
        "models": models,
        "note": "Profiles are resolved from the current host catalog; CLI compatibility is reported separately from Desktop compatibility.",
    }


def doctor(
    target: str | Path,
    *,
    home: str | Path | None = None,
    codex_config: str | Path | None = None,
    registry: dict[str, Any] | None = None,
    host_plugins: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    target_path = Path(target).expanduser().resolve()
    home_path = Path(home).expanduser().resolve() if home else Path.home()
    config_path = Path(codex_config) if codex_config else home_path / ".codex" / "config.toml"
    registry_data = registry or load_registry()
    config_data, config_text, config_error = _read_toml(config_path)
    config_sources = [str(config_path)]
    project_config = target_path / ".codex" / "config.toml"
    if project_config.is_file() and project_config.resolve() != config_path.resolve():
        project_data, project_text, project_error = _read_toml(project_config)
        config_data = _merge_config_data(config_data, project_data)
        config_text = config_text + "\n" + project_text
        config_sources.append(str(project_config))
        if project_error:
            config_error = "; ".join(filter(None, [config_error, f"{project_config}: {project_error}"]))

    host_features = _codex_features()
    live_plugins = host_plugins
    if live_plugins is None and home_path.resolve() == Path.home().resolve():
        live_plugins = _host_plugin_inventory(target_path if target_path.exists() else None)
    catalog = _model_catalog(config_data, home_path)
    capabilities = [
        _capability_status(
            capability,
            home=home_path,
            config_data=config_data,
            config_text=config_text,
            host_features=host_features,
            host_plugins=live_plugins,
        )
        for capability in registry_data["capabilities"]
    ]
    model_capability = next((item for item in capabilities if item["id"] == "model-catalog"), None)
    if model_capability is not None:
        model_capability["state"] = (
            "configured"
            if catalog.get("catalog_complete") or catalog.get("configured_model")
            else "missing"
        )
    lock_by_id = _install_lock_by_id()
    for item in capabilities:
        expected = (lock_by_id.get(item["id"]) or {}).get("sha256")
        if not expected or not item["evidence"]:
            continue
        hashes = {
            path: sha256_file(Path(path))
            for path in item["evidence"]
            if Path(path).is_file() and Path(path).name.casefold() == "skill.md"
        }
        verified = [path for path, value in hashes.items() if value.casefold() == expected.casefold()]
        item["integrity"] = {
            "expected_sha256": expected,
            "verified_paths": verified,
            "observed_sha256": hashes,
        }
        if hashes and not verified:
            item["state"] = "integrity_drift"
    for item in capabilities:
        lock = lock_by_id.get(item["id"]) or {}
        expected_version = lock.get("version")
        observed_versions = item.get("observed_versions") or []
        if not expected_version or expected_version == "host-managed" or not observed_versions:
            continue
        matches = [
            version
            for version in observed_versions
            if version == expected_version
            or version.startswith(expected_version + "-")
            or version.startswith(expected_version + "+")
        ]
        item["version_lock"] = {
            "expected": expected_version,
            "observed": observed_versions,
            "matched": matches,
        }
        if not matches and item["state"] not in {"missing", "partial"}:
            item["state"] = "version_drift"

    conflict_evidence = _glob_home(
        home_path,
        [".agents/skills/computer-use/SKILL.md", ".codex/skills/computer-use/SKILL.md"],
    )
    rules = load_conflict_rules()
    rule_by_id = {rule["id"]: rule for rule in rules}
    conflicts: list[dict[str, Any]] = []
    if platform.system().casefold() == "windows" and conflict_evidence:
        capabilities.append(
            {
                "id": "community-computer-use",
                "tier": 3,
                "kind": "skill",
                "state": "blocked_conflict",
                "selector": None,
                "evidence": conflict_evidence,
            }
        )
        conflicts.append(
            {
                "id": "windows-community-computer-use",
                "action": "blocked",
                "prefer": "computer-use",
                "reason": rule_by_id["windows-community-computer-use"]["reason"],
            }
        )
    context_overlap = _selector_enabled(
        config_data,
        config_text,
        "context-pack@awesome-codex-plugins",
    ) or bool(_glob_home(home_path, [".agents/skills/Context Manager/SKILL.md", ".codex/skills/Context Manager/SKILL.md"]))
    if context_overlap:
        rule = rule_by_id["duplicate-context-manager"]
        conflicts.append(
            {
                "id": rule["id"],
                "action": rule["action"],
                "prefer": rule["prefer"],
                "reason": rule["reason"],
            }
        )

    missing_tier0 = [
        item["id"]
        for item in capabilities
        if item["tier"] == 0 and item["state"] in {"missing", "partial"}
    ]
    install_plan: list[dict[str, Any]] = []
    by_id = {item["id"]: item for item in registry_data["capabilities"]}
    approved_capabilities = [
        item["id"]
        for item in capabilities
        if item["id"] in by_id
        and _install_requires_approval((by_id[item["id"]].get("install") or {}))
        and _has_valid_capability_approval(
            target_path,
            item["id"],
            host_plugins=live_plugins if live_plugins is not None else {},
        )
    ]
    for item in capabilities:
        registered = by_id.get(item["id"])
        if registered is None:
            continue
        install = registered.get("install") or {}
        installable_tier0 = item["tier"] == 0 and bool(install)
        baseline_tier1 = item["tier"] == 1
        if (
            not (installable_tier0 or baseline_tier1)
            or item["state"]
            not in {
                "missing",
                "partial",
                "cached_only",
                "installed_disabled",
                "integrity_drift",
                "version_drift",
            }
        ):
            continue
        approved = item["id"] in approved_capabilities
        # Kimmizo never mutates an authority-bearing plugin. The boss/Host must
        # install or update it; approval receipts only adopt the resulting state.
        gated = _install_requires_approval(install)
        install_plan.append(
            {
                "id": item["id"],
                "current_state": item["state"],
                "action": "request_system_approval" if gated else "enable_cached" if item["state"] in {"cached_only", "installed_disabled"} else "repair_integrity" if item["state"] in {"integrity_drift", "version_drift"} else "auto_install",
                "restart": bool(install.get("restart")),
            }
        )

    status = "healthy"
    if missing_tier0 or config_error:
        status = "degraded"
    elif install_plan:
        status = "attention"
    core_capsule = _load_v2_package().capsule_status(target_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "setup_version": VERSION,
        "status": status,
        "target": str(target_path),
        "platform": platform.system(),
        "config_path": str(config_path),
        "config_sources": config_sources,
        "config_error": config_error,
        "capabilities": capabilities,
        "missing_tier0": missing_tier0,
        "install_plan": install_plan,
        "approval_required": [item["id"] for item in install_plan if item["action"] == "request_system_approval"],
        "approved_capabilities": approved_capabilities,
        "conflicts": conflicts,
        "policy_guards": [
            {"id": rule["id"], "action": rule["action"], "reason": rule["reason"]}
            for rule in rules
            if rule["id"] in {"implicit-using-superpowers", "duplicate-context-manager", "untrusted-install", "authority-change"}
        ],
        "model_catalog": catalog,
        "host_features": host_features,
        "core_capsule": core_capsule,
    }


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _has_explicit_review_intent(text: str) -> bool:
    """Identify review as the requested action, not merely a downstream quality gate."""
    normalized = text.casefold().strip()
    if re.match(r"^(?:(?:please|kindly)\s+)?(?:review|audit|inspect)\b", normalized):
        return True
    return normalized.startswith(
        ("รีวิว", "ตรวจ", "ตรวจสอบ", "ช่วยรีวิว", "ช่วย review", "กรุณาตรวจ")
    )


def route_task(
    task: str,
    registry: dict[str, Any] | None = None,
    model_catalog: dict[str, Any] | None = None,
    *,
    execution_mode: str = "auto",
    assurance_level: str = "standard",
    authority_sources: list[str] | None = None,
    in_scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    constraints: list[str] | None = None,
    acceptance: list[str] | None = None,
    privacy_class: str = "internal",
    approval_boundary: str = "not_authorized",
) -> dict[str, Any]:
    # Loading the registry here validates that routing targets remain known without loading skill bodies.
    registry_data = registry or load_registry()
    known = {item["id"] for item in registry_data["capabilities"]}
    text = task.casefold().strip()
    capabilities: list[str] = []
    workflow: list[str] = []
    reasons: list[str] = []
    classification = "general"
    risk = "low"
    agent_role = "explorer"

    def add(capability: str, reason: str) -> None:
        if capability in known and capability not in capabilities:
            capabilities.append(capability)
            reasons.append(reason)

    web_terms = ["เว็บ", "website", "browser", "localhost", "http://", "https://", "หน้าเว็บ"]
    cli_web_terms = ["headless", "cdp", "electron", "repeatable", "playwright", "browser cli", "ด้วย cli"]
    chrome_state_terms = ["ล็อกอิน", "logged-in", "cookie", "session เดิม", "existing session", "แท็บ", "tab"]
    desktop_terms = ["โปรแกรม windows", "windows app", "desktop app", "ไม่มี api", "native app", "กดเมนู"]

    if _has_any(text, cli_web_terms) and _has_any(text, web_terms + ["qa"]):
        add("agent-browser", "Repeatable CLI/CDP/headless browser work uses agent-browser.")
        classification = "web_automation"
    elif (
        ("chrome" in text and _has_any(text, chrome_state_terms))
        or (_has_any(text, chrome_state_terms) and _has_any(text, web_terms + ["บัญชี"]))
    ):
        add("chrome", "The task needs the boss's existing Chrome state.")
        classification = "logged_in_web"
    elif _has_any(text, web_terms):
        add("browser", "Local or in-app web work uses the structured browser first.")
        classification = "web"
    elif _has_any(text, desktop_terms):
        add("computer-use", "A native Windows application has no more structured interface.")
        classification = "desktop"

    if _has_any(text, ["pull request", " pull ", " pr ", "github", "issue", " ci", "workflow run"]):
        add("github", "Repository collaboration and CI are handled through GitHub.")
        classification = "repository"

    if _has_any(text, ["auth", "secret", "credential", "token", "network", "dependency", "deploy", "security", "สิทธิ์", "ความปลอดภัย"]):
        add("codex-security", "Security-sensitive work requires the canonical security workflow.")
        risk = "high"

    if _has_any(text, [".xlsx", "excel", "spreadsheet", "csv", "สเปรดชีต"]):
        add("spreadsheets", "The primary artifact is tabular.")
        classification = "spreadsheet"
    if _has_any(text, ["kpi", "metric", "dataset", "analytics", "business question", "วิเคราะห์ข้อมูล"]):
        add("data-analytics", "The task is a business or dataset analysis.")
        classification = "data_analysis"
    if _has_any(text, ["diagram", "visualize", "แผนภาพ", "กราฟความสัมพันธ์"]):
        add("visualize", "A visual materially clarifies complex relationships.")
    if _has_any(text, [".docx", "word document", "เอกสาร word"]):
        add("documents", "The requested output is a document.")
    if _has_any(text, [".pdf", "ไฟล์ pdf"]):
        add("pdf", "The requested output is a PDF.")
    if _has_any(text, [".pptx", "presentation", "slides", "สไลด์"]):
        add("presentations", "The requested output is a presentation.")

    if _has_any(text, ["supabase"]):
        add("supabase", "The project explicitly uses Supabase.")
    elif _has_any(text, ["neon", "postgres", "postgresql", "migration", "schema"]):
        add("neon-postgres", "The task is about PostgreSQL schema or migration work.")
    if _has_any(text, ["vercel"]):
        add("vercel", "The deployment provider is Vercel.")
    if _has_any(text, ["cloudflare", "wrangler", "workers", "pages deploy"]):
        add("cloudflare", "The deployment provider is Cloudflare.")
    if _has_any(text, ["sentry", "error monitoring"]):
        add("sentry", "The task uses Sentry observability.")
    if _has_any(text, ["datadog", "log dashboard", "observability"]):
        add("datadog", "The task needs logs, metrics, or observability.")
    if _has_any(text, ["figma"]):
        add("figma", "The design source is Figma.")
    if _has_any(text, ["canva"]):
        add("canva", "The design output belongs in Canva.")
    if _has_any(text, ["remotion", "programmatic video"]):
        add("remotion", "The video is generated programmatically.")
    if _has_any(text, ["heygen", "avatar video"]):
        add("heygen", "The requested media uses HeyGen.")
    if _has_any(text, ["สร้างภาพ", "generate image", "image generation"]):
        add("imagegen", "The requested output is a generated image.")
    if _has_any(text, ["google drive", "ไฟล์ใน drive"]):
        add("google-drive", "The knowledge source is Google Drive.")
    if _has_any(text, ["notion"]):
        add("notion", "The knowledge source or destination is Notion.")
    if _has_any(text, ["gmail", "ส่งอีเมล", "อ่านอีเมล"]):
        add("gmail", "The communication channel is Gmail.")
    if _has_any(text, ["slack"]):
        add("slack", "The communication channel is Slack.")
    if _has_any(text, ["openai api", "openai sdk", "responses api", "agents sdk"]):
        add("openai-developers", "The project uses OpenAI developer APIs.")
        add("openai-docs", "Version-specific OpenAI behavior must be checked in official docs.")
    if _has_any(text, ["mql5", "mt5", "trading", "เทรด"]):
        add("domain-trading", "Trading work needs a project-specific risk and domain specialist selection.")
        risk = "high"
    if _has_any(text, ["newsroom", "ข่าว", "content pipeline", "publishing"]):
        add("domain-content", "The project needs content-domain routing.")
    if _has_any(text, ["finance", "portfolio", "market data", "การเงิน"]):
        add("domain-finance", "Finance work needs project-specific data and risk controls.")
        risk = "high"

    ambiguous = _has_any(text, ["ยังไม่รู้", "ไม่ชัด", "คลุมเครือ", "กำกวม", "requirement", "conflict", "ทางเลือก"])
    high_impact_open = _has_any(text, ["architecture", "สถาปัตยกรรม", "api", "naming", "ตั้งชื่อ", "fuzzy"])
    explicit_adhd = _has_any(text, ["/adhd", "adhd mode", "โหมด adhd"])
    if ambiguous:
        add("grill-me", "Important requirements are unresolved or conflicting.")
    if explicit_adhd:
        add("adhd", "The boss explicitly requested divergent multi-agent ideation.")
    if ambiguous and high_impact_open:
        risk = "high"

    is_feature = _has_any(text, ["feature", "ฟีเจอร์", "เพิ่มระบบ", "สร้างระบบ", "implement"])
    is_bug = _has_any(text, ["bug", "บั๊ก", "แก้ปัญหา", "error", "ผิดพลาด", "ไม่ทำงาน"])
    is_simple = _has_any(text, ["แก้คำสะกด", "typo", "rename one", "เปลี่ยนคำเดียว"])
    explicit_review_intent = _has_explicit_review_intent(text)
    if is_feature and not is_simple:
        add("superpowers", "A new feature benefits from staged planning, TDD and verification.")
        workflow = [
            "superpowers:brainstorming",
            "superpowers:writing-plans",
            "superpowers:test-driven-development",
            "implementer",
            "reviewer",
            "superpowers:verification-before-completion",
        ]
        classification = "feature"
        risk = "medium" if risk == "low" else risk
        agent_role = "implementer"
    elif is_bug and not is_simple:
        add("superpowers", "A bug needs systematic debugging and independent verification.")
        workflow = [
            "superpowers:systematic-debugging",
            "implementer",
            "reviewer",
            "superpowers:verification-before-completion",
        ]
        classification = "bug"
        risk = "medium" if risk == "low" else risk
        agent_role = "implementer"
    elif risk == "high":
        agent_role = "reviewer"
    if explicit_review_intent:
        agent_role = "reviewer"
        workflow = ["reviewer", "superpowers:verification-before-completion"]

    critical_task = _has_any(
        text,
        [
            "critical",
            "mission critical",
            "production",
            "deploy",
            "security",
            "vulnerability",
            "authentication",
            "authorization",
            "secret",
            "credential",
            "token",
            "payment",
            "database migration",
            "schema migration",
            "incident",
            "release",
            "compliance",
            "audit",
            "real money",
            "customer data",
            "trading",
            "finance",
            "ระบบจริง",
            "โปรดักชัน",
            "ดีพลอย",
            "ความปลอดภัย",
            "ช่องโหว่",
            "ยืนยันตัวตน",
            "กำหนดสิทธิ์",
            "ชำระเงิน",
            "ไมเกรตฐานข้อมูล",
            "ย้ายฐานข้อมูล",
            "เหตุขัดข้อง",
            "รีลีส",
            "กำกับดูแล",
            "เงินจริง",
            "ข้อมูลลูกค้า",
            "เทรด",
            "การเงิน",
        ],
    )
    important_task = critical_task or risk == "high" or _has_any(
        text,
        [
            "สำคัญ",
            "งานใหญ่",
            "critical",
            "high impact",
            "high-impact",
            "production",
            "breaking change",
            "architecture",
            "security",
            "เงินจริง",
            "ข้อมูลลูกค้า",
        ],
    )
    model_tier = (
        "critical"
        if critical_task
        else "deep"
        if important_task
        else "balanced"
        if classification in {"feature", "bug", "data_analysis", "repository", "web_automation"}
        else "fast"
    )
    model_recommendation: dict[str, Any] = {
        "tier": model_tier,
        "reasoning": {
            "fast": "low",
            "balanced": "medium",
            "deep": "high",
            "critical": "high",
        }[model_tier],
    }
    if model_catalog:
        model_recommendation.update(_resolve_model_policy(model_catalog)[model_tier])
    secretary_tier = model_tier
    secretary_recommendation: dict[str, Any] = {
        "tier": secretary_tier,
        "reasoning": {
            "fast": "low",
            "balanced": "medium",
            "deep": "high",
            "critical": "high",
        }[secretary_tier],
    }
    observed_host_default = {"model": None, "reasoning": None}
    if model_catalog:
        secretary_recommendation.update(_resolve_model_policy(model_catalog)[secretary_tier])
        observed_host_default = {
            "model": model_catalog.get("configured_model"),
            "reasoning": model_catalog.get("configured_reasoning"),
        }
    recommended_model = secretary_recommendation.get("model") or f"tier {secretary_tier}"
    auto_host_extension = _kimmizo_auto_host_active()
    use_auto_main_model = auto_host_extension or not important_task
    if important_task and auto_host_extension:
        secretary_message = (
            f"Kimmizo Auto จะเลือก {recommended_model} และ Reasoning "
            f"{secretary_recommendation['reasoning']} ให้งานสำคัญนี้อัตโนมัติค่ะ"
        )
    elif important_task:
        secretary_message = (
            f"งานนี้สำคัญ คิมแนะนำให้บอสเปลี่ยน Model ของคิมเป็น {recommended_model} "
            f"และ Reasoning เป็น {secretary_recommendation['reasoning']} เองก่อนเริ่มงานค่ะ"
        )
    else:
        secretary_message = (
            "งานทั่วไปนี้คิมแนะนำ Model = Auto เพื่อให้ Codex เลือกโมเดลใหม่ให้เหมาะกับแต่ละข้อความ "
            f"และใช้ Reasoning ระดับ {secretary_recommendation['reasoning']} ค่ะ"
        )
    secretary_model_advice = {
        "selection_mode": (
            "automatic_by_kimmizo_auto"
            if auto_host_extension
            else "boss_changes_manually"
        ),
        "ui_model_mode": "auto" if use_auto_main_model else "specific",
        "recommended_ui_model": "Auto" if use_auto_main_model else recommended_model,
        "auto_select_each_message": use_auto_main_model,
        "host_auto_extension_active": auto_host_extension,
        "notify_before_start": important_task and not auto_host_extension,
        "must_not_auto_change_main_model": not auto_host_extension,
        "recommendation": secretary_recommendation,
        "observed_host_default": observed_host_default,
        "message_th": secretary_message,
    }
    worker_model_selection = {
        "selection_mode": "automatic_by_kimmizo",
        "agent_role": agent_role,
        "effective_on": "selected_worker_spawn",
        "recommendation": model_recommendation,
    }
    legacy_result = {
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "classification": classification,
        "risk": risk,
        "importance": "important" if important_task else "routine",
        "capabilities": capabilities,
        "workflow": workflow,
        "agent_role": agent_role,
        "secretary_model_advice": secretary_model_advice,
        "worker_model_selection": worker_model_selection,
        "model_recommendation": model_recommendation,
        "reasons": reasons,
        "routing_guards": [
            rule["id"]
            for rule in load_conflict_rules()
            if rule["action"] in {"disable_implicit_routing", "disable_unless_benchmarked", "require_boss_approval"}
        ],
        "context_policy": {
            "metadata_only_in_main": True,
            "max_sources": 6,
            "max_lines": 300,
            "worker_return_max_bullets": 10,
        },
    }
    legacy_result["v2"] = _load_v2_package().build_route_plan(
        task=task,
        legacy_route=legacy_result,
        model_catalog=model_catalog,
        execution_mode=execution_mode,
        assurance_level=assurance_level,
        authority_sources=authority_sources,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        constraints=constraints,
        acceptance=acceptance,
        privacy_class=privacy_class,
        approval_boundary=approval_boundary,
    )
    return legacy_result


def strip_managed_block(text: str, *, style: str) -> str:
    prefix = "<!--" if style == "html" else "#"
    suffix = "-->" if style == "html" else ""
    if style == "html":
        pattern = re.compile(
            r"\n?<!-- BEGIN KIMMIZO MANAGED BLOCK.*?<!-- END KIMMIZO MANAGED BLOCK -->\n?",
            re.DOTALL,
        )
    else:
        pattern = re.compile(
            r"\n?# BEGIN KIMMIZO MANAGED BLOCK.*?# END KIMMIZO MANAGED BLOCK\n?",
            re.DOTALL,
        )
    del prefix, suffix
    return pattern.sub("\n", text).rstrip() + ("\n" if text else "")


def managed_merge(text: str, content: str, *, style: str) -> str:
    content = content.strip() + "\n"
    checksum = sha256_text(content)
    if style == "html":
        begin = f"<!-- {AGENT_BLOCK_BEGIN} v{VERSION} checksum:{checksum} -->"
        end = f"<!-- {AGENT_BLOCK_END} -->"
    else:
        begin = f"# {AGENT_BLOCK_BEGIN} v{VERSION} checksum:{checksum}"
        end = f"# {AGENT_BLOCK_END}"
    base = strip_managed_block(text, style=style).rstrip()
    block = f"{begin}\n{content}{end}\n"
    return (base + "\n\n" + block) if base else block


def _agents_managed_merge_preserving_v2(text: str, content: str) -> str:
    """Refresh the v1 block without reordering or rewriting the independent v2 block."""
    matches = list(KIMWEAVER_V2_BLOCK_PATTERN.finditer(text))
    if len(matches) != 1:
        return managed_merge(text, content, style="html")
    v2_block = matches[0].group(0)
    without_v2 = KIMWEAVER_V2_BLOCK_PATTERN.sub("", text)
    merged_v1 = managed_merge(without_v2, content, style="html").rstrip()
    return merged_v1 + "\n\n" + v2_block + "\n"


def managed_block_integrity(text: str, *, style: str) -> dict[str, Any] | None:
    if style == "html":
        pattern = re.compile(
            r"<!-- BEGIN KIMMIZO MANAGED BLOCK v(?P<version>[^ ]+) checksum:(?P<checksum>[0-9a-f]{64}) -->\n(?P<content>.*?)<!-- END KIMMIZO MANAGED BLOCK -->",
            re.DOTALL,
        )
    else:
        pattern = re.compile(
            r"# BEGIN KIMMIZO MANAGED BLOCK v(?P<version>[^ ]+) checksum:(?P<checksum>[0-9a-f]{64})\n(?P<content>.*?)# END KIMMIZO MANAGED BLOCK",
            re.DOTALL,
        )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    if len(matches) != 1:
        return {"valid": False, "reason": "multiple_managed_blocks", "count": len(matches)}
    match = matches[0]
    observed = sha256_text(match.group("content"))
    expected = match.group("checksum")
    return {
        "valid": observed == expected,
        "reason": "ok" if observed == expected else "checksum_mismatch",
        "version": match.group("version"),
        "expected_checksum": expected,
        "observed_checksum": observed,
    }


def _backup_managed_drift(
    target: Path,
    logical_name: str,
    original: str,
    integrity: dict[str, Any] | None,
    actions: list[dict[str, Any]],
    *,
    dry_run: bool,
    transaction: _SetupTransaction | None = None,
) -> dict[str, Any] | None:
    if not integrity or integrity.get("valid") is not False:
        return None
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", logical_name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    backup = target / ".kimmizo" / "runtime" / "managed-backups" / safe_name / f"{stamp}.bak"
    actions.append(
        {
            "action": "backup_managed_block_drift",
            "path": str(backup),
            "reason": integrity["reason"],
        }
    )
    if not dry_run:
        if transaction is not None:
            transaction.capture_file(backup, label="managed drift backup")
        else:
            _assert_setup_file_safe(backup, target, label="managed drift backup")
        _atomic_write_text(backup, original, newline=None)
        if transaction is not None:
            transaction.record_written_file(backup, label="managed drift backup")
    return {"file": logical_name, "backup": str(backup), **integrity}


def _detect_project(target: Path) -> dict[str, Any]:
    extension_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript-react",
        ".js": "javascript",
        ".jsx": "javascript-react",
        ".go": "go",
        ".rs": "rust",
        ".cs": "dotnet",
        ".java": "java",
        ".mq5": "mql5",
    }
    counts: dict[str, int] = {}
    if target.exists():
        for path in target.rglob("*"):
            if not path.is_file() or any(part in {".git", ".kimmizo", "node_modules", ".venv"} for part in path.parts):
                continue
            language = extension_map.get(path.suffix.casefold())
            if language:
                counts[language] = counts.get(language, 0) + 1
    files = {path.name.casefold() for path in target.iterdir()} if target.is_dir() else set()
    manifest_text = ""
    for name in ("package.json", "pyproject.toml", "requirements.txt", "docker-compose.yml", "README.md"):
        path = target / name
        if path.is_file() and path.stat().st_size <= 500_000:
            try:
                manifest_text += "\n" + path.read_text(encoding="utf-8", errors="ignore").casefold()
            except OSError:
                pass
    domains: list[str] = []
    if {"package.json", "vite.config.ts", "next.config.js", "next.config.mjs"} & files:
        domains.append("web_application")
    if {"supabase", "prisma", "migrations"} & files:
        domains.append("database")
    if any(language == "mql5" for language in counts):
        domains.append("trading")
    if "openai" in manifest_text:
        domains.append("openai")
    if any(term in manifest_text for term in ("newsroom", "content pipeline", "publishing")):
        domains.append("content")
    if any(term in manifest_text for term in ("portfolio", "market data", "finance")):
        domains.append("finance")
    git_commits = _git_commit_count(target) if (target / ".git").exists() else 0
    return {
        "schema_version": SCHEMA_VERSION,
        "name": target.name,
        "git_repository": (target / ".git").exists(),
        "git_commit_count": git_commits,
        "languages": sorted(counts, key=lambda key: (-counts[key], key)),
        "language_file_counts": counts,
        "domains": domains,
        "tier2_recommendations": _tier2_recommendations(files, counts, domains, git_commits),
    }


def _git_commit_count(target: Path) -> int:
    executable = shutil.which("git")
    if not executable:
        return 0
    try:
        completed = subprocess.run(
            [executable, "-C", str(target), "rev-list", "--count", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        return int(completed.stdout.strip()) if completed.returncode == 0 else 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def _tier2_recommendations(files: set[str], counts: dict[str, int], domains: list[str], git_commits: int = 0) -> list[str]:
    result: list[str] = []
    if "web_application" in domains or any(lang in counts for lang in ("typescript", "typescript-react", "javascript-react")):
        result.extend(["sites", "build-web-apps", "agent-browser"])
    if "database" in domains or "supabase" in " ".join(files):
        result.append("supabase")
    if any(name in files for name in ("drizzle.config.ts", "prisma", "migrations")):
        result.append("neon-postgres")
    if any(name.startswith("vercel") for name in files):
        result.append("vercel")
    if any(name.startswith("wrangler") for name in files):
        result.append("cloudflare")
    if any("sentry" in name for name in files):
        result.append("sentry")
    if any("datadog" in name for name in files):
        result.append("datadog")
    if "openai" in domains:
        result.append("openai-developers")
    if ".github" in files:
        result.append("codex-reviewer")
    if git_commits >= 5:
        result.append("codebase-recon")
    if "trading" in domains:
        result.append("domain-trading")
    if "content" in domains:
        result.append("domain-content")
    if "finance" in domains:
        result.append("domain-finance")
    return list(dict.fromkeys(result))


DEFAULT_TEAM = [
    {
        "name": "mira",
        "role": "explorer",
        "nickname_candidates": ["Mira", "Scout"],
        "personality": "curious, concise and evidence-first",
        "sandbox_mode": "read-only",
        "reasoning": "low",
        "allowed_skills": ["kimmizo-capability-router"],
    },
    {
        "name": "arin",
        "role": "implementer",
        "nickname_candidates": ["Arin", "Maker"],
        "personality": "practical, focused and test-driven",
        "sandbox_mode": "workspace-write",
        "reasoning": "medium",
        "allowed_skills": ["kimmizo-capability-router", "superpowers:test-driven-development"],
    },
    {
        "name": "vera",
        "role": "reviewer",
        "nickname_candidates": ["Vera", "Audit"],
        "personality": "skeptical, precise and independent",
        "sandbox_mode": "read-only",
        "reasoning": "high",
        "allowed_skills": ["kimmizo-capability-router", "codex-security"],
    },
    {
        "name": "nami",
        "role": "context_keeper",
        "nickname_candidates": ["Nami", "Keeper"],
        "personality": "structured, quiet and loss-averse",
        "sandbox_mode": "workspace-write",
        "reasoning": "medium",
        "allowed_skills": ["kimmizo-memory"],
    },
]

SPECIALIST_TEAM = {
    "web_application": {
        "name": "elio",
        "role": "web_specialist",
        "nickname_candidates": ["Elio", "Web"],
        "personality": "systematic, browser-aware and integration-focused",
        "sandbox_mode": "read-only",
        "reasoning": "high",
        "model_tier": "deep",
        "allowed_skills": ["kimmizo-capability-router", "browser", "agent-browser", "codex-security"],
    },
    "trading": {
        "name": "taro",
        "role": "trading_specialist",
        "nickname_candidates": ["Taro", "Risk"],
        "personality": "risk-first, evidence-driven and conservative",
        "sandbox_mode": "read-only",
        "reasoning": "high",
        "model_tier": "critical",
        "allowed_skills": ["kimmizo-capability-router", "domain-trading", "codex-security", "data-analytics"],
    },
    "content": {
        "name": "lina",
        "role": "content_specialist",
        "nickname_candidates": ["Lina", "Desk"],
        "personality": "source-conscious, clear and audience-aware",
        "sandbox_mode": "read-only",
        "reasoning": "medium",
        "model_tier": "balanced",
        "allowed_skills": ["kimmizo-capability-router", "domain-content", "documents"],
    },
    "finance": {
        "name": "finn",
        "role": "finance_specialist",
        "nickname_candidates": ["Finn", "Ledger"],
        "personality": "quantitative, cautious and audit-friendly",
        "sandbox_mode": "read-only",
        "reasoning": "high",
        "model_tier": "critical",
        "allowed_skills": ["kimmizo-capability-router", "domain-finance", "data-analytics", "spreadsheets"],
    },
    "openai": {
        "name": "nova",
        "role": "openai_specialist",
        "nickname_candidates": ["Nova", "Docs"],
        "personality": "documentation-first, precise and version-aware",
        "sandbox_mode": "read-only",
        "reasoning": "high",
        "model_tier": "deep",
        "allowed_skills": ["kimmizo-capability-router", "openai-developers", "openai-docs"],
    },
}


def _members_for_project(project_profile: dict[str, Any]) -> list[dict[str, Any]]:
    members = [dict(item) for item in DEFAULT_TEAM]
    for domain in project_profile.get("domains", []):
        if domain in SPECIALIST_TEAM:
            members.append(dict(SPECIALIST_TEAM[domain]))
    return members


def _resolve_model_policy(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policy = load_json(MODEL_POLICY)
    routes = policy["model_selection"]
    usage_policy = policy["usage_policy"]
    manual_only = set(usage_policy["manual_only_models"])
    configured = catalog.get("configured_model")
    models = {item["slug"]: item for item in catalog.get("models", [])}

    def choose_model(tier: str) -> str | None:
        preferences = routes[tier]["models"]
        for preferred in preferences:
            if preferred in models and preferred not in manual_only:
                return preferred
        if configured and configured in models and configured not in manual_only:
            return configured
        return next((model for model in models if model not in manual_only), None)

    def effort(model: str | None, preferred: str) -> str:
        if model is None:
            return preferred
        supported = set(
            (models.get(model) or {}).get("supported_reasoning")
            or catalog.get("supported_reasoning")
            or ["low", "medium", "high"]
        )
        if preferred in supported:
            return preferred
        for fallback in ("high", "medium", "low", "minimal", "none"):
            if fallback in supported:
                return fallback
        return "medium"

    result: dict[str, dict[str, Any]] = {}
    for tier in ("fast", "balanced", "deep", "critical"):
        model = choose_model(tier)
        preferred_effort = routes[tier]["effort"]
        result[tier] = {
            "model": model,
            "reasoning": effort(model, preferred_effort),
        }
    return result


def _project_model_catalog(target: Path, home: Path | None = None) -> dict[str, Any]:
    home_path = (home or Path.home()).resolve()
    global_data, _, _ = _read_toml(home_path / ".codex" / "config.toml")
    project_data, _, _ = _read_toml(target / ".codex" / "config.toml")
    return _model_catalog(_merge_config_data(global_data, project_data), home_path)


def _validate_model_reasoning(model: Any, reasoning: Any, catalog: dict[str, Any]) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Agent model must be a non-empty host model id")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("Agent reasoning must be a non-empty host reasoning level")
    entries = {
        item.get("slug"): item
        for item in catalog.get("models", [])
        if isinstance(item, dict) and item.get("slug")
    }
    if entries:
        if model not in entries:
            raise ValueError(f"Agent model {model!r} is not in the live host model catalog")
        supported = entries[model].get("supported_reasoning") or []
    else:
        configured = catalog.get("configured_model")
        if not configured or model != configured:
            raise ValueError(
                "The live model catalog is unavailable; only the configured host model may be used"
            )
        supported = catalog.get("supported_reasoning") or []
    if reasoning not in supported:
        raise ValueError(
            f"Agent reasoning {reasoning!r} is not supported by model {model!r}; supported={supported}"
        )


def _standard_profile_evaluation(
    profile: dict[str, Any],
    identity: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    immutable_ok = all(profile.get(key) == identity[key] for key in ("name", "agent_id", "role"))
    checks.append({"check": "immutable_identity", "passed": immutable_ok})
    if not immutable_ok:
        raise ValueError("Candidate profile identity was altered")
    _validate_model_reasoning(profile.get("model"), profile.get("reasoning"), catalog)
    checks.append({"check": "model_reasoning_compatibility", "passed": True})
    _validate_allowed_skills(profile.get("allowed_skills", []))
    checks.append({"check": "skill_allowlist", "passed": True})
    authority = profile.get("authority")
    authority_ok = isinstance(authority, dict) and all(value is False for value in authority.values())
    checks.append({"check": "authority_unchanged", "passed": authority_ok})
    if not authority_ok:
        raise PermissionError("Candidate profile attempts to expand authority")
    parsed = tomllib.loads(_agent_toml(profile))
    toml_ok = (
        parsed.get("name") == identity["name"]
        and parsed.get("model") == profile["model"]
        and parsed.get("model_reasoning_effort") == profile["reasoning"]
    )
    checks.append({"check": "custom_agent_toml", "passed": toml_ok})
    if not toml_ok:
        raise ValueError("Candidate did not pass the standard custom-agent TOML evaluation")
    return {"suite": "kimmizo-profile-standard-v1", "passed": True, "checks": checks}


def _team_identities(project_id: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    namespace = uuid.UUID(project_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "identity_policy": "name_and_agent_id_are_immutable",
        "agents": [
            {
                "name": member["name"],
                "agent_id": str(uuid.uuid5(namespace, member["role"])),
                "role": member["role"],
            }
            for member in members
        ],
    }


def _instructions_for_role(role: str) -> str:
    shared = (
        "Work only on the bounded task from Kim. Inspect real evidence before concluding. "
        "Load only allowlisted skills relevant to this assignment. Return at most 10 bullets and point to files, tests, or receipts instead of pasting raw logs. "
        "Do not expand authority, authentication, MCP access, plugins, sandbox, or external writes."
    )
    role_text = {
        "explorer": "Map the project and execution path. Stay read-only. Do not implement fixes.",
        "implementer": "Implement the smallest scoped change with tests. Preserve unrelated user work.",
        "reviewer": "Review independently for correctness, security, regressions, and missing tests. Stay read-only.",
        "context_keeper": "Maintain Kimmizo checkpoints and compact project memory. Do not modify product code.",
    }.get(role, f"Act as the project's {role.replace('_', ' ')} specialist and stay within that domain.")
    return f"{role_text} {shared}"


def _profile_for_member(
    member: dict[str, Any],
    identity: dict[str, Any],
    policy: dict[str, dict[str, str]],
    revision: int = 1,
) -> dict[str, Any]:
    tier = member.get(
        "model_tier",
        "fast" if member["role"] == "explorer" else "deep" if member["role"] == "reviewer" else "balanced",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "name": identity["name"],
        "agent_id": identity["agent_id"],
        "role": identity["role"],
        "model_tier": tier,
        "model": policy[tier]["model"],
        "reasoning": policy[tier]["reasoning"],
        "personality": member["personality"],
        "sandbox_mode": member["sandbox_mode"],
        "nickname_candidates": member["nickname_candidates"],
        "allowed_skills": member["allowed_skills"],
        "authority": {
            "auth": False,
            "new_mcp": False,
            "new_plugins": False,
            "external_write": False,
            "scope_expansion": False,
        },
        "authority_enforcement": {
            "sandbox": "host_enforced",
            "skill_allowlist": "instruction_policy",
            "tool_and_mcp_allowlist": "parent_must_withhold_unapproved_tools",
        },
        "developer_instructions": _instructions_for_role(identity["role"]),
        "promotion_state": "active",
    }


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _agent_toml(profile: dict[str, Any]) -> str:
    nicknames = ", ".join(_toml_string(item) for item in profile["nickname_candidates"])
    allowed = ", ".join(profile["allowed_skills"]) or "none"
    authority = "; ".join(
        f"{key}={str(value).lower()}" for key, value in sorted(profile["authority"].items())
    )
    effective_instructions = (
        f"{profile['developer_instructions']} Allowed skills only: {allowed}. "
        f"Authority (must not expand): {authority}. The host enforces sandbox_mode; "
        "skill/tool/MCP allowlists are parent-controlled policy, so do not use capabilities the parent did not expose."
    )
    return "\n".join(
        [
            f"name = {_toml_string(profile['name'])}",
            f"description = {_toml_string('Kimmizo ' + profile['role'] + ' agent for bounded project work.')}",
            f"model = {_toml_string(profile['model'])}",
            f"model_reasoning_effort = {_toml_string(profile['reasoning'])}",
            f"sandbox_mode = {_toml_string(profile['sandbox_mode'])}",
            f"nickname_candidates = [{nicknames}]",
            f"developer_instructions = {_toml_string(effective_instructions)}",
            "",
        ]
    )


def _secretary_skill() -> str:
    return _template_text("skills/kimmizo-secretary/SKILL.md")


def _router_skill() -> str:
    return _template_text("skills/kimmizo-capability-router/SKILL.md")


def _memory_skill() -> str:
    return _template_text("skills/kimmizo-memory/SKILL.md")


def _agents_block() -> str:
    return _template_text("AGENTS.block.md")


def _config_block(user_text: str) -> str:
    if re.search(r"(?m)^\s*\[agents\]\s*$|^\s*agents\.", user_text):
        return "# Existing [agents] settings are owned by the project. Kimmizo leaves them unchanged.\n# Project-scoped profiles are loaded from .codex/agents/*.toml."
    return _template_text("config.block.toml").strip()


def _gitignore_block() -> str:
    return """# Kimmizo runtime and private project memory
.kimmizo/memory/
.kimmizo/runtime/
.kimmizo/capabilities/receipts/
.kimmizo/knowledge/lessons.jsonl
"""


def _boot_text() -> str:
    return _template_text("BOOT.md")


def _sanitize_capability_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "setup_version": VERSION,
        "status": report["status"],
        "capabilities": [
            {
                key: item.get(key)
                for key in (
                    "id",
                    "tier",
                    "kind",
                    "state",
                    "selector",
                    "observed_versions",
                    "integrity",
                    "version_lock",
                )
                if item.get(key) is not None
            }
            for item in report["capabilities"]
        ],
        "install_plan": report["install_plan"],
        "approval_required": report["approval_required"],
        "approved_capabilities": report.get("approved_capabilities", []),
        "conflicts": report["conflicts"],
        "policy_guards": report["policy_guards"],
    }


def _extend_project_install_plan(report: dict[str, Any], project_profile: dict[str, Any]) -> None:
    """Add only project-relevant Tier 2 capabilities to the install plan."""
    registry = _registry_by_id()
    states = {item["id"]: item["state"] for item in report["capabilities"]}
    planned = {item["id"] for item in report["install_plan"]}
    for capability_id in project_profile["tier2_recommendations"]:
        capability = registry.get(capability_id)
        if not capability or capability_id in planned or capability.get("kind") == "domain_policy":
            continue
        state = states.get(capability_id, "missing")
        if state in {"enabled", "installed", "available", "configured"}:
            continue
        install = capability.get("install") or {}
        gated = _install_requires_approval(install)
        if state == "enabled_dependency_missing":
            action = "dependency_missing"
        elif state == "runtime_missing":
            action = "system_browser_required"
        elif gated:
            action = "request_system_approval"
        elif state == "cached_only":
            action = "enable_cached"
        else:
            action = "auto_install"
        report["install_plan"].append(
            {
                "id": capability_id,
                "current_state": state,
                "action": action,
                "restart": bool(install.get("restart")),
                "project_reason": True,
            }
        )
        planned.add(capability_id)
        if gated or action in {"dependency_missing", "system_browser_required"}:
            if capability_id not in report["approval_required"]:
                report["approval_required"].append(capability_id)
    if report["install_plan"] and report["status"] == "healthy":
        report["status"] = "attention"


def _active_capabilities(report: dict[str, Any], project_profile: dict[str, Any]) -> dict[str, Any]:
    active_states = {"available", "configured", "installed", "enabled"}
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline": [item["id"] for item in report["capabilities"] if item["tier"] <= 1 and item["state"] in active_states],
        "project_recommended": project_profile["tier2_recommendations"],
        "routing_policy": "load_metadata_then_only_selected_capability",
    }


def _validated_slug(value: str, label: str) -> str:
    if not isinstance(value, str) or not SAFE_SLUG.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _validated_uuid(value: str, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error
    if str(parsed) != str(value).casefold():
        raise ValueError(f"Non-canonical {label}: {value!r}")
    return str(parsed)


def _validate_allowed_skills(skills: list[str]) -> list[str]:
    if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
        raise ValueError("allowed_skills must be a list of skill identifiers")
    known = set(_registry_by_id()) | {
        "kimmizo-secretary",
        "kimmizo-capability-router",
        "kimmizo-memory",
    } | ALLOWED_SUPERPOWER_SKILLS
    unknown = sorted(set(skills) - known)
    if unknown:
        raise ValueError(f"Skills are not in the Kimmizo allowlist: {unknown}")
    return list(dict.fromkeys(skills))


def _safe_profile_path(target: Path, name: str, revision: int, relative: str) -> Path:
    _validated_slug(name, "agent name")
    if revision < 1:
        raise ValueError("Profile revision must be positive")
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ValueError(f"Agent profile path must be project-relative: {relative}")
    expected_relative = Path(".kimmizo") / "team" / "profiles" / name / f"v{revision:03d}.json"
    if relative_path != expected_relative:
        raise ValueError(
            f"Agent profile path does not match immutable identity/revision: {relative}"
        )
    path = target / relative_path
    expected_root = target / ".kimmizo" / "team" / "profiles" / name
    if not _is_within(path, expected_root):
        raise ValueError(f"Agent profile path escapes its profile root: {relative}")
    return path


def _validate_identities(identities: dict[str, Any], project_id: str) -> None:
    namespace = uuid.UUID(project_id)
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    for identity in identities.get("agents", []):
        name = _validated_slug(identity.get("name"), "agent name")
        role = _validated_slug(identity.get("role"), "agent role")
        agent_id = _validated_uuid(identity.get("agent_id"), "agent_id")
        expected = str(uuid.uuid5(namespace, role))
        if agent_id != expected:
            raise ValueError(f"Agent identity was altered for {name}")
        if name in seen_names or agent_id in seen_ids:
            raise ValueError("Agent names and agent_ids must be unique")
        seen_names.add(name)
        seen_ids.add(agent_id)


def _ensure_initial_team(
    target: Path,
    project_id: str,
    project_profile: dict[str, Any],
    model_catalog: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    dry_run: bool,
    transaction: _SetupTransaction | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identities_path = target / ".kimmizo" / "team" / "identities.json"
    _assert_setup_file_safe(identities_path, target, label="immutable team identity")
    members = _members_for_project(project_profile)
    desired = _team_identities(project_id, members)
    identities = load_json(identities_path) if identities_path.is_file() else desired
    _validate_identities(identities, project_id)
    existing_names = {item["name"] for item in identities["agents"]}
    existing_roles = {item["role"] for item in identities["agents"]}
    for identity in desired["agents"]:
        if identity["name"] not in existing_names:
            if identity["role"] in existing_roles:
                raise ValueError(f"Specialist role already has a different immutable identity: {identity['role']}")
            identities["agents"].append(identity)
            existing_names.add(identity["name"])
            existing_roles.add(identity["role"])
    _validate_identities(identities, project_id)
    write_if_changed(
        identities_path,
        json_text(identities),
        actions,
        dry_run=dry_run,
        reason="immutable team identity",
        allowed_root=target,
        transaction=transaction,
    )

    active_path = target / ".kimmizo" / "team" / "active.json"
    _assert_setup_file_safe(active_path, target, label="active team revisions")
    active = load_json(active_path) if active_path.is_file() else {"schema_version": SCHEMA_VERSION, "profiles": {}}
    policy = _resolve_model_policy(model_catalog)
    identity_by_name = {item["name"]: item for item in identities["agents"]}
    member_by_name = {
        item["name"]: item
        for item in [*DEFAULT_TEAM, *SPECIALIST_TEAM.values()]
    }
    extra_profiles = set(active.get("profiles", {})) - set(identity_by_name)
    if extra_profiles:
        raise ValueError(f"Active team contains unknown identities: {sorted(extra_profiles)}")

    for name, identity in identity_by_name.items():
        entry = active["profiles"].get(name)
        if entry:
            revision = int(entry["revision"])
            profile_path = _safe_profile_path(target, name, revision, entry["path"])
            _assert_setup_file_safe(profile_path, target, label="agent profile")
            if profile_path.is_file():
                profile = load_json(profile_path)
            else:
                profile = _profile_for_member(member_by_name[name], identity, policy, revision)
        else:
            profile = _profile_for_member(member_by_name[name], identity, policy, 1)
            entry = {
                "revision": 1,
                "path": f".kimmizo/team/profiles/{name}/v001.json",
                "previous_revisions": [],
            }
            active["profiles"][name] = entry
            profile_path = _safe_profile_path(target, name, 1, entry["path"])
            _assert_setup_file_safe(profile_path, target, label="agent profile")
        if (
            profile.get("name") != identity["name"]
            or profile.get("agent_id") != identity["agent_id"]
            or profile.get("role") != identity["role"]
            or int(profile.get("revision", 0)) != int(entry["revision"])
        ):
            raise ValueError(f"Agent profile identity or revision was altered for {name}")
        _validate_allowed_skills(profile.get("allowed_skills", []))
        write_if_changed(
            profile_path,
            json_text(profile),
            actions,
            dry_run=dry_run,
            reason="agent profile",
            allowed_root=target,
            transaction=transaction,
        )
        write_if_changed(
            target / ".codex" / "agents" / f"{name}.toml",
            _agent_toml(profile),
            actions,
            dry_run=dry_run,
            reason="Codex custom agent",
            allowed_root=target,
            transaction=transaction,
        )

    write_if_changed(
        active_path,
        json_text(active),
        actions,
        dry_run=dry_run,
        reason="active team revisions",
        allowed_root=target,
        transaction=transaction,
    )
    return identities, active


def _install_lock_by_id() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in load_json(BASELINE_LOCK)["entries"]}


def _registry_by_id() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in load_registry()["capabilities"]}


def _tree_fingerprint(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Plugin package directory not found: {root}")
    entries: list[dict[str, Any]] = []
    total_size = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ValueError(f"Plugin package contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total_size += size
        if len(entries) >= 20_000 or total_size > 512 * 1024 * 1024:
            raise ValueError("Plugin package exceeds the fingerprint safety limits")
        entries.append({"path": relative, "size": size, "sha256": sha256_file(path)})
    if not entries:
        raise ValueError(f"Plugin package is empty: {root}")
    digest = sha256_text(json.dumps(entries, sort_keys=True, separators=(",", ":")))
    return {"sha256": digest, "file_count": len(entries), "total_size": total_size}


def _version_matches(expected: str | None, observed: str) -> bool:
    return bool(expected) and (
        expected == "host-managed"
        or observed == expected
        or observed.startswith(expected + "-")
        or observed.startswith(expected + "+")
    )


def _manifest_authority(manifest: dict[str, Any]) -> dict[str, Any]:
    interface = manifest.get("interface") if isinstance(manifest.get("interface"), dict) else {}
    capabilities = sorted(
        str(item) for item in interface.get("capabilities", []) if isinstance(item, str)
    )
    has_write = any(item.casefold() == "write" for item in capabilities)
    return {
        "hook": bool(manifest.get("hooks")),
        "mcp": bool(manifest.get("mcpServers")),
        "app": bool(manifest.get("apps")),
        "new_permissions": bool(manifest.get("permissions")),
        "interface_capabilities": capabilities,
        "interface_write": has_write,
        "external_write": has_write
        and bool(manifest.get("mcpServers") or manifest.get("apps") or manifest.get("hooks")),
    }


def _verify_host_plugin_package(
    capability: dict[str, Any],
    lock: dict[str, Any],
    host_plugin: dict[str, str],
) -> dict[str, Any]:
    selector = capability.get("selector")
    if not selector or host_plugin.get("selector") != selector:
        raise ValueError("Host plugin selector does not match the capability registry")
    if host_plugin.get("state") != "enabled":
        raise PermissionError(f"{selector} is not installed and enabled by the host")
    package_root = Path(host_plugin.get("path", "")).expanduser().resolve()
    manifest_path = package_root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Host plugin manifest not found: {manifest_path}")
    manifest = load_json(manifest_path)
    plugin_name = selector.split("@", 1)[0]
    if manifest.get("name") != plugin_name:
        raise ValueError("Host plugin manifest name does not match the selector")
    manifest_version = str(manifest.get("version", ""))
    host_version = str(host_plugin.get("version", ""))
    reported_manifest_version = host_plugin.get("manifest_version")
    if reported_manifest_version and manifest_version != str(reported_manifest_version):
        raise ValueError(
            f"Host plugin manifest version {reported_manifest_version!r} differs from package {manifest_version!r}"
        )
    if not reported_manifest_version and manifest_version != host_version:
        raise ValueError(f"Host plugin version {host_version!r} differs from manifest {manifest_version!r}")
    if not _version_matches(lock.get("version"), manifest_version):
        raise ValueError(
            f"Host plugin version {manifest_version!r} does not match lock {lock.get('version')!r}"
        )
    observed_authority = _manifest_authority(manifest)
    install = capability.get("install") or {}
    undeclared = sorted(
        key
        for key in ("hook", "mcp", "app", "new_permissions", "external_write")
        if observed_authority[key] and not install.get(key)
    )
    if undeclared:
        raise PermissionError(f"Host manifest adds undeclared authority: {undeclared}")
    package = _tree_fingerprint(package_root)
    return {
        "selector": selector,
        "state": "enabled",
        "version": manifest_version,
        "host_release": host_version,
        "path": str(package_root),
        "manifest_sha256": sha256_file(manifest_path),
        "package_sha256": package["sha256"],
        "package_file_count": package["file_count"],
        "package_total_size": package["total_size"],
        "observed_authority": observed_authority,
    }


def _approval_fingerprint(capability_id: str, package_sha256: str) -> str:
    capability = _registry_by_id()[capability_id]
    lock = _install_lock_by_id().get(capability_id)
    return sha256_text(
        json.dumps(
            {
                "id": capability_id,
                "install": capability.get("install"),
                "lock": lock,
                "package_sha256": package_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _approval_path(target: Path, capability_id: str) -> Path:
    capability_id = _validated_slug(capability_id, "capability id")
    target_root = target.expanduser().resolve()
    path = (
        target_root
        / ".kimmizo"
        / "capabilities"
        / "receipts"
        / f"approval-{capability_id}.json"
    )
    try:
        path.resolve().relative_to(target_root)
    except ValueError as error:
        raise PermissionError("Capability approval receipt path escapes the project") from error
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise PermissionError("Capability approval receipt is a linked path")
        info = path.lstat()
        reparse = bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
        if reparse or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
            raise PermissionError("Capability approval receipt is linked or not a singly-owned regular file")
    return path


def _has_valid_capability_approval(
    target: Path,
    capability_id: str,
    *,
    host_plugins: dict[str, dict[str, str]] | None = None,
) -> bool:
    path = _approval_path(target, capability_id)
    if not path.is_file():
        return False
    try:
        receipt = load_json(path)
        capability = _registry_by_id()[capability_id]
        selector = capability.get("selector")
        inventory = host_plugins if host_plugins is not None else _host_plugin_inventory()
        host_plugin = inventory.get(selector) if selector else None
        if not host_plugin:
            return False
        verified = _verify_host_plugin_package(
            capability,
            _install_lock_by_id()[capability_id],
            host_plugin,
        )
        return (
            receipt.get("id") == capability_id
            and receipt.get("approval_source") == "host_enabled_package"
            and receipt.get("host_evidence", {}).get("package_sha256")
            == verified["package_sha256"]
            and receipt.get("fingerprint")
            == _approval_fingerprint(capability_id, verified["package_sha256"])
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError, PermissionError):
        return False


def grant_capability_approval(
    capability_id: str,
    *,
    target: str | Path | None = None,
    home: str | Path | None = None,
    host_plugins: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    capability_id = _validated_slug(capability_id, "capability id")
    registry = _registry_by_id()
    if capability_id not in registry:
        raise ValueError(f"Unknown capability: {capability_id}")
    install = registry[capability_id].get("install") or {}
    if not _install_requires_approval(install):
        raise ValueError(f"Capability {capability_id} does not require a system approval")
    if target is not None and home is not None:
        raise ValueError("Specify target or legacy home, not both")
    approval_root_value = target if target is not None else home
    if approval_root_value is None:
        raise ValueError("A project target is required for a project-local approval receipt")
    approval_root = Path(approval_root_value).expanduser().resolve()
    selector = registry[capability_id].get("selector")
    if not selector:
        raise PermissionError("Only a host-managed plugin can provide system approval evidence")
    inventory = host_plugins if host_plugins is not None else _host_plugin_inventory()
    host_plugin = inventory.get(selector)
    if not host_plugin:
        raise PermissionError(
            f"Install and approve {selector} in the Codex host first; Kimmizo cannot grant this authority"
        )
    verified = _verify_host_plugin_package(
        registry[capability_id],
        _install_lock_by_id()[capability_id],
        host_plugin,
    )
    path = _approval_path(approval_root, capability_id)
    if path.is_file():
        try:
            existing_receipt = load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PermissionError("Refusing to replace an unowned receipt path") from error
        if (
            existing_receipt.get("id") != capability_id
            or existing_receipt.get("approval_source") != "host_enabled_package"
        ):
            raise PermissionError("Refusing to replace an unowned receipt path")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "id": capability_id,
        "approval_source": "host_enabled_package",
        "fingerprint": _approval_fingerprint(capability_id, verified["package_sha256"]),
        "host_evidence": verified,
        "authority": {
            key: value
            for key, value in install.items()
            if key in {"approval", "auth", "hook", "mcp", "app", "new_permissions", "external_write"}
        },
        "granted_at": utc_now(),
        "scope": "this_machine_until_registry_lock_or_package_changes",
    }
    _atomic_write_text(path, json_text(receipt))
    return {"status": "host_approval_adopted", "id": capability_id, "path": str(path)}


def _safe_command(command: list[str]) -> bool:
    return bool(command) and command[0].casefold().removesuffix(".exe").removesuffix(".cmd") in {
        "codex",
        "npx",
        "npm",
        "agent-browser",
        "winget",
        "git",
        "python",
        "py",
    }


def _source_plugin_manifests(home: Path, selector: str) -> list[Path]:
    plugin_name, marketplace = selector.split("@", 1)
    candidates: list[Path] = []
    if marketplace == "openai-curated":
        candidates.append(home / ".codex" / ".tmp" / "plugins" / "plugins" / plugin_name / ".codex-plugin" / "plugin.json")
    elif marketplace == "openai-bundled":
        candidates.append(
            home
            / ".codex"
            / ".tmp"
            / "bundled-marketplaces"
            / "openai-bundled"
            / "plugins"
            / plugin_name
            / ".codex-plugin"
            / "plugin.json"
        )
    elif marketplace == "openai-primary-runtime":
        candidates.append(
            home
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "plugins"
            / "openai-primary-runtime"
            / "plugins"
            / plugin_name
            / ".codex-plugin"
            / "plugin.json"
        )
    elif marketplace == "awesome-codex-plugins":
        candidates.extend(
            home.glob(
                ".codex/.tmp/marketplaces/awesome-codex-plugins/plugins/**/.codex-plugin/plugin.json"
            )
        )
    return [path for path in candidates if path.is_file()]


def _cached_plugin_manifests(home: Path, selector: str) -> list[Path]:
    plugin_name, marketplace = selector.split("@", 1)
    marketplace_dirs = {
        "openai-curated": ["openai-curated-remote", "openai-curated"],
        "openai-bundled": ["openai-bundled"],
        "openai-primary-runtime": ["openai-primary-runtime"],
        "awesome-codex-plugins": ["awesome-codex-plugins"],
    }.get(marketplace, [marketplace])
    manifests: list[Path] = []
    for directory in marketplace_dirs:
        manifests.extend(
            home.glob(
                f".codex/plugins/cache/{directory}/{plugin_name}/*/.codex-plugin/plugin.json"
            )
        )
    return [path for path in manifests if path.is_file()]


def _preflight_plugin_install(
    capability: dict[str, Any],
    lock: dict[str, Any],
    *,
    home: Path | None = None,
    allow_cached: bool = False,
) -> dict[str, Any]:
    selector = capability.get("selector")
    if not selector or "@" not in selector:
        return {"ok": False, "status": "blocked_manifest_unverified", "reason": "missing selector"}
    home_path = (home or Path.home()).resolve()
    codex = shutil.which("codex")
    if codex:
        subprocess.run(
            [codex, "-c", 'model_reasoning_effort="xhigh"', "plugin", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    manifests: list[tuple[Path, dict[str, Any]]] = []
    manifest_paths = _source_plugin_manifests(home_path, selector)
    if allow_cached:
        manifest_paths.extend(_cached_plugin_manifests(home_path, selector))
    for path in _unique_paths(manifest_paths):
        path = Path(path)
        try:
            manifest = load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if manifest.get("name") == selector.split("@", 1)[0]:
            manifests.append((path, manifest))
    if not manifests:
        return {
            "ok": False,
            "status": "blocked_manifest_unverified",
            "reason": f"source manifest not found for {selector}",
        }
    expected_version = lock.get("version")
    matching = [
        item
        for item in manifests
        if _version_matches(expected_version, str(item[1].get("version", "")))
    ]
    if not matching:
        return {
            "ok": False,
            "status": "blocked_version_mismatch",
            "reason": f"expected {expected_version}, source offers {[item[1].get('version') for item in manifests]}",
            "manifest": str(manifests[0][0]),
        }
    path, manifest = matching[0]
    observed_version = str(manifest.get("version", ""))
    install = capability.get("install") or {}
    observed_authority = _manifest_authority(manifest)
    undeclared = sorted(
        key
        for key in ("hook", "mcp", "app", "new_permissions", "external_write")
        if observed_authority[key] and not install.get(key)
    )
    if undeclared:
        return {
            "ok": False,
            "status": "blocked_authority_change",
            "reason": f"manifest adds undeclared authority: {undeclared}",
            "manifest": str(path),
        }
    package = _tree_fingerprint(path.parent.parent)
    return {
        "ok": True,
        "status": "verified",
        "selector": selector,
        "version": observed_version,
        "manifest": str(path),
        "manifest_sha256": sha256_file(path),
        "package_sha256": package["sha256"],
        "package_file_count": package["file_count"],
        "observed_authority": observed_authority,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _remove_path_safely(path: Path, allowed_root: Path) -> None:
    if not _is_within(path, allowed_root) or path == allowed_root:
        raise ValueError(f"Refusing to remove path outside allowed root: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def enforce_implicit_superpowers_guard(
    *,
    home: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Disable only the always-on Superpowers skill while retaining named subskills."""
    home_path = Path(home).resolve() if home else Path.home().resolve()
    cache_roots = [
        home_path / ".codex" / "plugins" / "cache" / directory / "superpowers"
        for directory in ("openai-curated-remote", "openai-curated")
    ]
    source_root = home_path / ".codex" / ".tmp" / "plugins" / "plugins" / "superpowers"
    allowed_roots = [*cache_roots, source_root]
    active_paths = [
        *[path for root in cache_roots for path in root.glob("*/skills/using-superpowers/SKILL.md")],
        source_root / "skills" / "using-superpowers" / "SKILL.md",
    ]
    active_paths = [path for path in active_paths if path.is_file()]
    disabled_paths = [
        *[
            path
            for root in cache_roots
            for path in root.glob("*/skills/using-superpowers/SKILL.md.kimmizo-disabled")
        ],
        source_root / "skills" / "using-superpowers" / "SKILL.md.kimmizo-disabled",
    ]
    disabled_paths = [path for path in disabled_paths if path.is_file()]
    if not active_paths:
        return {
            "status": "already_disabled" if disabled_paths else "not_installed",
            "active": [],
            "disabled": [str(path) for path in disabled_paths],
            "restart_required": False,
        }
    actions: list[dict[str, Any]] = []
    for active in active_paths:
        if not any(_is_within(active, root) for root in allowed_roots):
            raise ValueError(f"Superpowers guard path escapes the cache root: {active}")
        disabled = active.with_name("SKILL.md.kimmizo-disabled")
        observed_hash = sha256_file(active)
        if disabled.exists() and sha256_file(disabled) != observed_hash:
            raise ValueError(f"Refusing to replace a different disabled Superpowers skill: {disabled}")
        actions.append(
            {
                "active": str(active),
                "disabled": str(disabled),
                "sha256": observed_hash,
            }
        )
        if not dry_run:
            if disabled.exists():
                active.unlink()
            else:
                os.replace(active, disabled)
    receipt_path = home_path / ".codex" / "kimmizo" / "conflicts" / "implicit-using-superpowers.json"
    if not dry_run:
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "id": "implicit-using-superpowers",
            "status": "disabled",
            "reason": "Kimmizo routes only named Superpowers subskills.",
            "actions": actions,
            "recorded_at": utc_now(),
        }
        _atomic_write_text(receipt_path, json_text(receipt))
    return {
        "status": "planned" if dry_run else "disabled",
        "actions": actions,
        "receipt": str(receipt_path),
        "restart_required": not dry_run,
    }


def _download_pinned_archive(url: str, expected_sha256: str) -> bytes:
    if not url.startswith("https://codeload.github.com/"):
        raise ValueError("Pinned skill archives must use codeload.github.com over HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": f"kimmizo-setup/{VERSION}"})
    with urllib.request.urlopen(request, timeout=90) as response:
        if not response.geturl().startswith("https://codeload.github.com/"):
            raise ValueError(f"Pinned archive redirected to an untrusted host: {response.geturl()}")
        length = response.headers.get("Content-Length")
        if length and int(length) > 25 * 1024 * 1024:
            raise ValueError("Pinned skill archive exceeds 25 MB")
        data = response.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Pinned skill archive exceeds 25 MB")
    observed = hashlib.sha256(data).hexdigest()
    if observed.casefold() != expected_sha256.casefold():
        raise ValueError(f"Archive SHA256 mismatch: expected {expected_sha256}, observed {observed}")
    return data


def _extract_skill_from_zip(data: bytes, skill_subpath: str, destination: Path) -> list[str]:
    wanted = tuple(PurePosixPath(skill_subpath).parts)
    if not wanted or any(part in {"", ".", ".."} for part in wanted):
        raise ValueError("Invalid skill_subpath")
    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 5_000:
            raise ValueError("Pinned skill archive contains too many entries")
        if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
            raise ValueError("Pinned skill archive expands beyond 50 MB")
        for info in archive.infolist():
            parts = PurePosixPath(info.filename).parts
            if len(parts) <= len(wanted) or tuple(parts[1 : 1 + len(wanted)]) != wanted:
                continue
            relative = parts[1 + len(wanted) :]
            if not relative or any(part in {"", ".", ".."} for part in relative):
                continue
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError(f"Symlink entries are not allowed in pinned skill archives: {info.filename}")
            output = destination.joinpath(*relative)
            if not _is_within(output, destination):
                raise ValueError(f"Archive path escapes destination: {info.filename}")
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.read(info))
                extracted.append(str(output.relative_to(destination)))
    if "SKILL.md" not in {Path(item).as_posix() for item in extracted}:
        raise ValueError("Pinned archive did not contain the expected SKILL.md")
    return extracted


def _install_pinned_skill(
    capability_id: str,
    install: dict[str, Any],
    lock: dict[str, Any],
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    home_path = (home or Path.home()).resolve()
    archive = _download_pinned_archive(install["archive_url"], install["archive_sha256"])
    canonical_root = home_path / ".agents" / "skills"
    legacy_root = home_path / ".codex" / "skills"
    canonical_root.mkdir(parents=True, exist_ok=True)
    targets = [canonical_root / capability_id]
    legacy_target = legacy_root / capability_id
    if legacy_target.exists() or legacy_target.is_symlink():
        legacy_root.mkdir(parents=True, exist_ok=True)
        targets.append(legacy_target)

    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    backup_root = canonical_root / ".kimmizo-backups" / capability_id / backup_stamp
    installed_targets: list[str] = []
    backups: list[str] = []
    rollback_entries: list[dict[str, Any]] = []
    expected_skill_hash = lock["sha256"]
    plans: list[dict[str, Any]] = []
    committed: list[dict[str, Any]] = []

    try:
        # Prepare and verify every target before mutating the first one.
        for index, target in enumerate(targets):
            allowed_root = canonical_root if target.parent == canonical_root else legacy_root
            stage = allowed_root / f".kimmizo-stage-{capability_id}-{uuid.uuid4().hex}"
            stage.mkdir(parents=True, exist_ok=False)
            plan = {
                "target": target,
                "allowed_root": allowed_root,
                "stage": stage,
                "rollback": None,
            }
            plans.append(plan)
            _extract_skill_from_zip(archive, install["skill_subpath"], stage)
            observed = sha256_file(stage / "SKILL.md")
            if observed.casefold() != expected_skill_hash.casefold():
                raise ValueError(
                    f"Skill SHA256 mismatch: expected {expected_skill_hash}, observed {observed}"
                )
            backup = backup_root / f"target-{index}"
            rollback_entry: dict[str, Any] = {"target": str(target), "backup": None, "backup_type": None}
            if target.exists() or target.is_symlink():
                backup.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink():
                    backup.with_suffix(".link.txt").write_text(str(target.readlink()), encoding="utf-8")
                    backups.append(str(backup.with_suffix(".link.txt")))
                    rollback_entry.update(
                        {
                            "backup": str(backup.with_suffix(".link.txt")),
                            "backup_type": "symlink",
                        }
                    )
                elif target.is_dir():
                    shutil.copytree(target, backup, symlinks=True)
                    backups.append(str(backup))
                    rollback_entry.update({"backup": str(backup), "backup_type": "directory"})
                else:
                    shutil.copy2(target, backup)
                    backups.append(str(backup))
                    rollback_entry.update({"backup": str(backup), "backup_type": "file"})
            rollback_entries.append(rollback_entry)
            plan["rollback"] = rollback_entry

        # Commit only after all archives, hashes, paths, and backups are valid.
        for plan in plans:
            committed.append(plan)
            target = plan["target"]
            if target.exists() or target.is_symlink():
                _remove_path_safely(target, plan["allowed_root"])
            os.replace(plan["stage"], target)
            installed_targets.append(str(target))
    except Exception:
        restoration_errors: list[str] = []
        for plan in reversed(committed):
            target = plan["target"]
            try:
                if target.exists() or target.is_symlink():
                    _remove_path_safely(target, plan["allowed_root"])
                entry = plan["rollback"]
                backup_value = entry.get("backup")
                if backup_value:
                    backup = Path(backup_value)
                    if entry["backup_type"] == "directory":
                        shutil.copytree(backup, target, symlinks=True)
                    elif entry["backup_type"] == "file":
                        shutil.copy2(backup, target)
                    elif entry["backup_type"] == "symlink":
                        target.symlink_to(
                            backup.read_text(encoding="utf-8"),
                            target_is_directory=True,
                        )
            except Exception as restore_error:  # keep the original error, but expose restoration failure
                restoration_errors.append(f"{target}: {restore_error}")
        if restoration_errors:
            raise RuntimeError(
                "Pinned skill install failed and transaction restoration also failed: "
                + "; ".join(restoration_errors)
            )
        raise
    finally:
        for plan in plans:
            stage = plan["stage"]
            if stage.exists() or stage.is_symlink():
                _remove_path_safely(stage, plan["allowed_root"])

    history_root = canonical_root / ".kimmizo-backups" / capability_id
    if history_root.is_dir():
        generations = sorted(path for path in history_root.iterdir() if path.is_dir())
        for old in generations[:-2]:
            _remove_path_safely(old, history_root)

    return {
        "archive_url": install["archive_url"],
        "archive_sha256": install["archive_sha256"],
        "skill_sha256": expected_skill_hash,
        "installed_targets": installed_targets,
        "backups": backups,
        "rollback_entries": rollback_entries,
    }


def _plugin_cache_roots(home: Path, selector: str) -> list[Path]:
    plugin_name, marketplace = selector.split("@", 1)
    marketplace_dirs = {
        "openai-curated": ["openai-curated-remote", "openai-curated"],
        "openai-bundled": ["openai-bundled"],
        "openai-primary-runtime": ["openai-primary-runtime"],
        "awesome-codex-plugins": ["awesome-codex-plugins"],
    }.get(marketplace, [marketplace])
    return [
        home / ".codex" / "plugins" / "cache" / directory / plugin_name
        for directory in marketplace_dirs
    ]


def _capture_plugin_snapshot(
    target: str | Path,
    capability_id: str,
    capability: dict[str, Any],
    *,
    home: str | Path | None = None,
) -> dict[str, Any]:
    target_path = Path(target).resolve()
    home_path = Path(home).resolve() if home else Path.home().resolve()
    capability_id = _validated_slug(capability_id, "capability id")
    selector = capability.get("selector")
    if not selector or "@" not in selector:
        raise ValueError("Plugin snapshot requires a registered selector")
    snapshot_root = (
        target_path
        / ".kimmizo"
        / "capabilities"
        / "receipts"
        / "backups"
        / f"{capability_id}-{uuid.uuid4().hex}"
    )
    snapshot_root.mkdir(parents=True, exist_ok=False)
    config = home_path / ".codex" / "config.toml"
    config_backup = snapshot_root / "config.toml"
    config_existed = config.is_file()
    if config_existed:
        shutil.copy2(config, config_backup)
    cache_snapshots: list[dict[str, Any]] = []
    for index, root in enumerate(_plugin_cache_roots(home_path, selector)):
        existed = root.is_dir()
        backup = snapshot_root / f"cache-{index}"
        fingerprint = None
        if existed:
            shutil.copytree(root, backup, symlinks=False)
            fingerprint = _tree_fingerprint(backup)["sha256"]
        cache_snapshots.append(
            {
                "original": str(root),
                "existed": existed,
                "backup": str(backup) if existed else None,
                "sha256": fingerprint,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "selector": selector,
        "home": str(home_path),
        "snapshot_root": str(snapshot_root),
        "captured_at": utc_now(),
        "config": {
            "original": str(config),
            "existed": config_existed,
            "backup": str(config_backup) if config_existed else None,
            "sha256": sha256_file(config_backup) if config_existed else None,
        },
        "cache_roots": cache_snapshots,
    }


def _restore_plugin_snapshot(
    target: Path,
    capability_id: str,
    snapshot: dict[str, Any],
    *,
    home: Path,
    require_post_config_match: bool,
) -> dict[str, Any]:
    selector = _registry_by_id()[capability_id].get("selector")
    if snapshot.get("selector") != selector or snapshot.get("home") != str(home):
        raise ValueError("Plugin rollback snapshot does not match the registry or current home")
    approved_backup_root = (
        target / ".kimmizo" / "capabilities" / "receipts" / "backups"
    ).resolve()
    snapshot_root = Path(snapshot.get("snapshot_root", "")).resolve()
    if not _is_within(snapshot_root, approved_backup_root) or not snapshot_root.is_dir():
        raise ValueError("Plugin rollback snapshot is outside the project receipt backup root")
    config_meta = snapshot.get("config") or {}
    config = home / ".codex" / "config.toml"
    if Path(config_meta.get("original", "")).resolve() != config.resolve():
        raise ValueError("Plugin rollback config path does not match the active Codex config")
    if require_post_config_match:
        current_hash = sha256_file(config) if config.is_file() else None
        if current_hash != snapshot.get("post_config_sha256"):
            raise RuntimeError(
                "Codex config changed after installation; refusing to overwrite newer user changes"
            )
    config_backup = Path(config_meta["backup"]) if config_meta.get("backup") else None
    if config_meta.get("existed"):
        if (
            config_backup is None
            or not _is_within(config_backup, snapshot_root)
            or not config_backup.is_file()
            or sha256_file(config_backup) != config_meta.get("sha256")
        ):
            raise ValueError("Plugin rollback config backup failed integrity validation")

    allowed_cache_roots = {
        str(path.resolve()): path for path in _plugin_cache_roots(home, selector)
    }
    prepared: list[dict[str, Any]] = []
    config_stage: Path | None = None
    try:
        for meta in snapshot.get("cache_roots", []):
            original = Path(meta.get("original", "")).resolve()
            if str(original) not in allowed_cache_roots:
                raise ValueError(f"Plugin rollback cache root is not allowlisted: {original}")
            original.parent.mkdir(parents=True, exist_ok=True)
            stage = original.parent / f".{original.name}.kimmizo-restore-{uuid.uuid4().hex}"
            if meta.get("existed"):
                backup = Path(meta.get("backup", "")).resolve()
                if not _is_within(backup, snapshot_root) or not backup.is_dir():
                    raise ValueError("Plugin rollback cache backup is missing or outside the snapshot")
                shutil.copytree(backup, stage, symlinks=False)
                if _tree_fingerprint(stage)["sha256"] != meta.get("sha256"):
                    raise ValueError("Plugin rollback cache backup failed integrity validation")
            prepared.append({"original": original, "stage": stage if meta.get("existed") else None})
        if config_meta.get("existed"):
            config.parent.mkdir(parents=True, exist_ok=True)
            config_stage = config.parent / f".{config.name}.kimmizo-restore-{uuid.uuid4().hex}"
            shutil.copy2(config_backup, config_stage)
            if sha256_file(config_stage) != config_meta.get("sha256"):
                raise ValueError("Plugin rollback staged config failed integrity validation")
    except Exception:
        for item in prepared:
            stage = item.get("stage")
            if stage and (stage.exists() or stage.is_symlink()):
                _remove_path_safely(stage, stage.parent)
        if config_stage:
            config_stage.unlink(missing_ok=True)
        raise

    committed: list[dict[str, Any]] = []
    config_quarantine: Path | None = None
    try:
        for item in prepared:
            original = item["original"]
            quarantine = original.parent / f".{original.name}.kimmizo-current-{uuid.uuid4().hex}"
            if original.exists() or original.is_symlink():
                os.replace(original, quarantine)
            else:
                quarantine = None
            if item["stage"] is not None:
                os.replace(item["stage"], original)
            committed.append({"original": original, "quarantine": quarantine})
        config.parent.mkdir(parents=True, exist_ok=True)
        if config.exists():
            config_quarantine = config.parent / f".{config.name}.kimmizo-current-{uuid.uuid4().hex}"
            os.replace(config, config_quarantine)
        if config_stage is not None:
            os.replace(config_stage, config)
    except Exception:
        if config.exists():
            config.unlink(missing_ok=True)
        if config_quarantine and config_quarantine.exists():
            os.replace(config_quarantine, config)
        for item in reversed(committed):
            original, quarantine = item["original"], item["quarantine"]
            if original.exists() or original.is_symlink():
                _remove_path_safely(original, original.parent)
            if quarantine and quarantine.exists():
                os.replace(quarantine, original)
        for item in prepared:
            stage = item.get("stage")
            if stage and (stage.exists() or stage.is_symlink()):
                _remove_path_safely(stage, stage.parent)
        if config_stage:
            config_stage.unlink(missing_ok=True)
        raise

    for item in committed:
        quarantine = item["quarantine"]
        if quarantine and (quarantine.exists() or quarantine.is_symlink()):
            _remove_path_safely(quarantine, quarantine.parent)
    if config_quarantine:
        config_quarantine.unlink(missing_ok=True)
    return {
        "config_restored": bool(config_meta.get("existed")),
        "cache_roots_restored": [str(item["original"]) for item in committed],
    }


def install_missing(
    target: str | Path,
    report: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    target_path = Path(target).resolve()
    registry = _registry_by_id()
    locked = _install_lock_by_id()
    results: list[dict[str, Any]] = []
    restart_required = False

    for planned in report["install_plan"]:
        capability_id = planned["id"]
        capability = registry[capability_id]
        install = capability.get("install") or {}
        if planned.get("action") == "system_browser_required":
            results.append({"id": capability_id, "status": "system_browser_required"})
            continue
        if planned.get("action") == "dependency_missing":
            results.append({"id": capability_id, "status": "dependency_missing"})
            continue
        if capability_id not in locked:
            results.append({"id": capability_id, "status": "blocked_unpinned"})
            continue
        gated = _install_requires_approval(install)
        if gated:
            results.append({"id": capability_id, "status": "approval_required"})
            continue
        if install.get("method") == "pinned_github_zip":
            if dry_run:
                results.append(
                    {
                        "id": capability_id,
                        "status": "planned",
                        "method": "pinned_github_zip",
                        "archive_url": install["archive_url"],
                    }
                )
                continue
            if install.get("restart"):
                write_checkpoint(
                    target_path,
                    {
                        "goal": f"Install baseline capability {capability_id}",
                        "status": "before_restart_capability_install",
                        "decisions": ["Use the pinned archive and verify both archive and skill SHA256."],
                        "files": [],
                        "tests": [],
                        "evidence": [],
                        "blockers": [],
                        "next_actions": ["Resume setup after skill installation and host restart."],
                    },
                )
            try:
                installation = _install_pinned_skill(capability_id, install, locked[capability_id])
                status = "installed"
                error = None
            except Exception as caught:  # receipt must preserve the failure without hiding it
                installation = None
                status = "failed"
                error = f"{type(caught).__name__}: {caught}"
            receipt_data = {
                "id": capability_id,
                "status": status,
                "method": "pinned_github_zip",
                "installation": installation,
                "error": error,
                "lock": locked[capability_id],
                "recorded_at": utc_now(),
            }
            receipt = target_path / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json_text(receipt_data), encoding="utf-8")
            results.append({"id": capability_id, "status": status, "receipt": str(receipt)})
            restart_required = restart_required or (status == "installed" and bool(install.get("restart")))
            continue
        preflight: dict[str, Any] | None = None
        plugin_snapshot: dict[str, Any] | None = None
        if (
            not dry_run
            and capability.get("kind") in {"plugin", "bundled_plugin", "connector_plugin"}
        ):
            preflight = _preflight_plugin_install(
                capability,
                locked[capability_id],
                allow_cached=planned.get("current_state") == "cached_only",
            )
            if not preflight["ok"]:
                receipt_data = {
                    "id": capability_id,
                    "status": preflight["status"],
                    "preflight": preflight,
                    "lock": locked[capability_id],
                    "recorded_at": utc_now(),
                }
                receipt = target_path / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
                receipt.parent.mkdir(parents=True, exist_ok=True)
                receipt.write_text(json_text(receipt_data), encoding="utf-8")
                results.append(
                    {"id": capability_id, "status": preflight["status"], "receipt": str(receipt)}
                )
                continue
            plugin_snapshot = _capture_plugin_snapshot(
                target_path,
                capability_id,
                capability,
            )
        commands = install.get("commands") or ([install["command"]] if install.get("command") else [])
        if not commands or not all(_safe_command(command) for command in commands):
            results.append({"id": capability_id, "status": "blocked_invalid_installer"})
            continue
        if dry_run:
            results.append({"id": capability_id, "status": "planned", "commands": commands})
            continue

        if install.get("restart"):
            write_checkpoint(
                target_path,
                {
                    "goal": f"Install baseline capability {capability_id}",
                    "status": "before_restart_capability_install",
                    "decisions": ["Use only the pinned baseline installer."],
                    "files": [],
                    "tests": [],
                    "evidence": [],
                    "blockers": [],
                    "next_actions": ["Resume setup after capability installation and host restart."],
                },
            )

        command_results: list[dict[str, Any]] = []
        success = True
        for raw_command in commands:
            command = list(raw_command)
            if command[0].casefold().startswith("codex") and "plugin" in command:
                command = [command[0], "-c", 'model_reasoning_effort="xhigh"', *command[1:]]
            executable = shutil.which(command[0])
            if not executable:
                success = False
                command_results.append({"command": command, "returncode": 127, "output": "executable not found"})
                break
            completed = subprocess.run(
                [executable, *command[1:]],
                cwd=target_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
            output = redact_secrets((completed.stdout + "\n" + completed.stderr).strip()[-2000:])
            command_results.append({"command": command, "returncode": completed.returncode, "output": output})
            if completed.returncode != 0:
                success = False
                break
        version_command = install.get("version_command")
        if success and version_command:
            if not _safe_command(version_command) or not shutil.which(version_command[0]):
                success = False
                command_results.append(
                    {"command": version_command, "returncode": 127, "output": "version command unavailable"}
                )
            else:
                version_check = subprocess.run(
                    [shutil.which(version_command[0]), *version_command[1:]],
                    cwd=target_path,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                version_output = redact_secrets((version_check.stdout + version_check.stderr).strip())
                version_ok = version_check.returncode == 0 and bool(
                    re.fullmatch(install["version_regex"], version_output)
                )
                command_results.append(
                    {
                        "command": version_command,
                        "returncode": 0 if version_ok else 1,
                        "output": version_output[-500:],
                    }
                )
                success = success and version_ok
        if success and capability.get("kind") in {"plugin", "bundled_plugin", "connector_plugin"}:
            _invalidate_host_probe_cache()
            post_report = doctor(target_path)
            post_item = next(
                (item for item in post_report["capabilities"] if item["id"] == capability_id),
                None,
            )
            if not post_item or post_item["state"] != "enabled":
                success = False
                command_results.append(
                    {
                        "command": ["post_install_verification"],
                        "returncode": 1,
                        "output": f"Expected enabled, observed {post_item['state'] if post_item else 'missing'}",
                    }
                )
        integrity: dict[str, Any] | None = None
        expected_sha256 = locked[capability_id].get("sha256")
        if success and expected_sha256:
            paths = _glob_home(Path.home(), (capability.get("detect") or {}).get("skill_paths", []))
            observed = {path: sha256_file(Path(path)) for path in paths if Path(path).is_file()}
            verified_paths = [
                path for path, value in observed.items() if value.casefold() == expected_sha256.casefold()
            ]
            integrity = {
                "expected_sha256": expected_sha256,
                "observed_sha256": observed,
                "verified_paths": verified_paths,
            }
            if not verified_paths:
                success = False
        result = {
            "id": capability_id,
            "status": "installed" if success else "integrity_failed" if integrity and not integrity["verified_paths"] else "failed",
            "commands": command_results,
            "lock": locked[capability_id],
            "preflight": preflight,
            "integrity": integrity,
            "recorded_at": utc_now(),
        }
        if success and capability.get("kind") in {"plugin", "bundled_plugin", "connector_plugin"}:
            if plugin_snapshot is None:
                raise RuntimeError("Plugin installation completed without a rollback snapshot")
            config_path = Path.home() / ".codex" / "config.toml"
            plugin_snapshot["post_config_sha256"] = (
                sha256_file(config_path) if config_path.is_file() else None
            )
            result["rollback"] = {
                "method": "restore_plugin_snapshot",
                "selector": capability["selector"],
                "previous_state": planned.get("current_state"),
                "snapshot": plugin_snapshot,
            }
        elif (
            not success
            and plugin_snapshot is not None
            and capability.get("kind") in {"plugin", "bundled_plugin", "connector_plugin"}
        ):
            result["failed_install_restore"] = _restore_plugin_snapshot(
                target_path,
                capability_id,
                plugin_snapshot,
                home=Path.home().resolve(),
                require_post_config_match=False,
            )
        elif success and capability_id == "agent-browser":
            result["rollback"] = {
                "method": "commands",
                "commands": [["npm", "uninstall", "-g", "agent-browser"]],
                "note": "The pinned CLI is removed; browser runtime cleanup remains provider-managed.",
            }
        receipt = target_path / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json_text(result), encoding="utf-8")
        results.append({"id": capability_id, "status": result["status"], "receipt": str(receipt)})
        restart_required = restart_required or (success and bool(install.get("restart")))

    return {"results": results, "restart_required": restart_required}


def rollback_capability(
    target: str | Path,
    capability_id: str,
    *,
    home: str | Path | None = None,
) -> dict[str, Any]:
    target_path = Path(target).expanduser().resolve()
    home_path = Path(home).expanduser().resolve() if home else Path.home().resolve()
    capability_id = _validated_slug(capability_id, "capability id")
    if capability_id not in _registry_by_id():
        raise ValueError(f"Unknown capability: {capability_id}")
    receipt_path = target_path / ".kimmizo" / "capabilities" / "receipts" / f"{capability_id}.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(f"Capability receipt not found: {receipt_path}")
    receipt = load_json(receipt_path)
    if receipt.get("id") != capability_id:
        raise ValueError("Capability receipt id does not match the requested rollback")
    installation = receipt.get("installation") or {}
    entries = installation.get("rollback_entries") or []
    if not entries:
        rollback = receipt.get("rollback") or {}
        method = rollback.get("method")
        if method == "restore_plugin_snapshot":
            expected_selector = _registry_by_id()[capability_id].get("selector")
            if rollback.get("selector") != expected_selector or not expected_selector:
                raise ValueError("Plugin rollback selector does not match the registry")
            restored = _restore_plugin_snapshot(
                target_path,
                capability_id,
                rollback.get("snapshot") or {},
                home=home_path,
                require_post_config_match=True,
            )
            receipt["status"] = "rolled_back"
            receipt["rolled_back_at"] = utc_now()
            receipt["rollback_result"] = restored
            _atomic_write_text(receipt_path, json_text(receipt))
            return {
                "status": "rolled_back",
                "id": capability_id,
                **restored,
                "receipt": str(receipt_path),
                "restart_required": True,
            }
        commands: list[list[str]] = []
        if method == "codex_plugin_remove":
            expected_selector = _registry_by_id()[capability_id].get("selector")
            if rollback.get("selector") != expected_selector or not expected_selector:
                raise ValueError("Plugin rollback selector does not match the registry")
            commands = [["codex", "plugin", "remove", expected_selector]]
        elif method == "commands" and capability_id == "agent-browser":
            expected = [["npm", "uninstall", "-g", "agent-browser"]]
            if rollback.get("commands") != expected:
                raise ValueError("CLI rollback command does not match the allowlist")
            commands = expected
        else:
            raise ValueError("This capability receipt has no automatic rollback data")
        command_results: list[dict[str, Any]] = []
        for raw in commands:
            executable = shutil.which(raw[0])
            if not executable:
                raise FileNotFoundError(f"Rollback executable not found: {raw[0]}")
            command = [executable, *raw[1:]]
            if raw[0] == "codex":
                command = [executable, "-c", 'model_reasoning_effort="xhigh"', *raw[1:]]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = redact_secrets((completed.stdout + "\n" + completed.stderr).strip()[-2000:])
            command_results.append(
                {"command": raw, "returncode": completed.returncode, "output": output}
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Capability rollback failed for {capability_id}: {output}")
        receipt["status"] = "rolled_back"
        receipt["rolled_back_at"] = utc_now()
        receipt["rollback_result"] = {"commands": command_results}
        receipt_path.write_text(json_text(receipt), encoding="utf-8")
        return {
            "status": "rolled_back",
            "id": capability_id,
            "commands": command_results,
            "receipt": str(receipt_path),
            "restart_required": True,
        }

    allowed_roots = [home_path / ".agents" / "skills", home_path / ".codex" / "skills"]
    backup_root = home_path / ".agents" / "skills" / ".kimmizo-backups"
    operations: list[tuple[dict[str, Any], Path, Path, Path | None]] = []
    capability_backup_root = backup_root / capability_id
    for entry in entries:
        current = Path(entry["target"])
        allowed_root = next(
            (
                root
                for root in allowed_roots
                if current.parent.resolve(strict=False) == root.resolve(strict=False)
                and current.name == capability_id
            ),
            None,
        )
        if allowed_root is None:
            raise ValueError(f"Rollback target is outside approved skill roots: {current}")
        backup_value = entry.get("backup")
        backup = Path(backup_value) if backup_value else None
        if backup is not None and (
            not _is_within(backup, capability_backup_root) or not backup.exists()
        ):
            raise ValueError(f"Rollback backup is missing or outside the capability backup root: {backup}")
        if backup is not None and entry.get("backup_type") not in {"directory", "file", "symlink"}:
            raise ValueError(f"Unsupported rollback backup type: {entry.get('backup_type')}")
        operations.append((entry, current, allowed_root, backup))

    prepared: list[dict[str, Any]] = []
    try:
        for entry, current, allowed_root, backup in reversed(operations):
            current.parent.mkdir(parents=True, exist_ok=True)
            stage = allowed_root / f".kimmizo-rollback-{capability_id}-{uuid.uuid4().hex}"
            backup_type = entry.get("backup_type")
            if backup_type == "directory":
                shutil.copytree(backup, stage, symlinks=True)
            elif backup_type == "file":
                shutil.copy2(backup, stage)
            elif backup_type == "symlink":
                stage.symlink_to(backup.read_text(encoding="utf-8"), target_is_directory=True)
            else:
                stage = None
            prepared.append(
                {
                    "current": current,
                    "allowed_root": allowed_root,
                    "stage": stage,
                    "restore": backup is not None,
                }
            )
    except Exception:
        for item in prepared:
            stage = item.get("stage")
            if stage and (stage.exists() or stage.is_symlink()):
                _remove_path_safely(stage, item["allowed_root"])
        raise

    restored: list[str] = []
    removed: list[str] = []
    committed: list[dict[str, Any]] = []
    try:
        for item in prepared:
            current = item["current"]
            quarantine = item["allowed_root"] / f".kimmizo-current-{capability_id}-{uuid.uuid4().hex}"
            existed = current.exists() or current.is_symlink()
            if existed:
                os.replace(current, quarantine)
                removed.append(str(current))
            else:
                quarantine = None
            if item["stage"] is not None:
                os.replace(item["stage"], current)
                restored.append(str(current))
            committed.append({**item, "quarantine": quarantine})
    except Exception:
        for item in reversed(committed):
            current, quarantine = item["current"], item["quarantine"]
            if current.exists() or current.is_symlink():
                _remove_path_safely(current, item["allowed_root"])
            if quarantine and quarantine.exists():
                os.replace(quarantine, current)
        for item in prepared:
            stage = item.get("stage")
            if stage and (stage.exists() or stage.is_symlink()):
                _remove_path_safely(stage, item["allowed_root"])
        raise

    for item in committed:
        quarantine = item["quarantine"]
        if quarantine and (quarantine.exists() or quarantine.is_symlink()):
            _remove_path_safely(quarantine, item["allowed_root"])

    receipt["status"] = "rolled_back"
    receipt["rolled_back_at"] = utc_now()
    receipt["rollback_result"] = {"restored": restored, "removed": removed}
    receipt_path.write_text(json_text(receipt), encoding="utf-8")
    return {
        "status": "rolled_back",
        "id": capability_id,
        "restored": restored,
        "removed": removed,
        "receipt": str(receipt_path),
        "restart_required": True,
    }


def _installable_tier0_requirements(capability_ids: Iterable[str]) -> list[str]:
    registry = _registry_by_id()
    return [
        capability_id
        for capability_id in capability_ids
        if bool((registry.get(capability_id) or {}).get("install"))
    ]


def setup_project(
    target: str | Path,
    *,
    dry_run: bool = False,
    skip_install: bool = False,
    repair_capsule: bool = False,
) -> dict[str, Any]:
    requested_target = _assert_setup_target_safe(Path(target).expanduser())
    # Keep this lexical path after the first guard.  Resolving it here would
    # conceal a target junction swapped in between validation and publication;
    # every later authority-file guard rechecks this same lexical root.
    target_path = requested_target
    actions: list[dict[str, Any]] = []
    managed_drifts: list[dict[str, Any]] = []

    # These three files carry project authority.  Validate all of them before
    # reading the manifest, running detection, or creating any setup artifact.
    agents_path = target_path / "AGENTS.md"
    config_path = target_path / ".codex" / "config.toml"
    gitignore_path = target_path / ".gitignore"
    for path, label in (
        (agents_path, "AGENTS.md authority file"),
        (config_path, ".codex/config.toml authority file"),
        (gitignore_path, ".gitignore authority file"),
    ):
        _assert_setup_file_safe(path, target_path, label=label)

    manifest_path = target_path / ".kimmizo" / "manifest.json"
    _assert_setup_file_safe(manifest_path, target_path, label="capsule manifest")
    existing_manifest = load_json(manifest_path) if manifest_path.is_file() else None
    initial_checkpoint_path = target_path / ".kimmizo" / "runtime" / "checkpoints" / "latest.json"
    initial_checkpoint_lock = initial_checkpoint_path.parent / ".checkpoint.lock"
    _assert_setup_file_safe(initial_checkpoint_path, target_path, label="checkpoint latest mirror")
    _assert_setup_file_safe(initial_checkpoint_lock, target_path, label="checkpoint lock")
    if (
        not dry_run
        and not initial_checkpoint_path.is_file()
        and _lstat_or_none(initial_checkpoint_lock) is not None
    ):
        raise TimeoutError(
            f"Setup refuses to steal an existing initial checkpoint lock: {initial_checkpoint_lock}"
        )
    project_id = (
        existing_manifest["project_id"]
        if existing_manifest
        else str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{target_path}"))
    )
    created_at = existing_manifest.get("created_at", utc_now()) if existing_manifest else utc_now()

    report = doctor(target_path)
    project_profile = _detect_project(target_path)
    _extend_project_install_plan(report, project_profile)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "setup_version": VERSION,
        "project_id": project_id,
        "created_at": created_at,
        "source": "tongkungtk/kimmizo_setup",
        "state": "prepared",
        "identity_policy": "agent name and agent_id are immutable",
        "model_policy": {
            "secretary": "native_or_kimmizo_auto_each_message_with_manual_fallback",
            "workers": "kimmizo_selects_automatically_from_live_host_catalog_per_task",
        },
        "memory_policy": "project-local, git-ignored, no telemetry, no vector DB, no cross-project memory",
        "managed_files": [
            "AGENTS.md",
            ".codex/config.toml",
            ".codex/agents/*.toml",
            ".agents/skills/kimmizo-*/SKILL.md",
            ".kimmizo/BOOT.md",
        ],
    }

    v2 = _load_v2_package()
    if not dry_run:
        # Discover v2 ownership conflicts before publishing a single v1 file.
        # The real call below runs again under v2's lock immediately before its
        # activation, so this preflight is not relied on for race protection.
        v2.materialize_capsule(
            target_path,
            project_id=project_id,
            dry_run=True,
            repair=repair_capsule,
            plugin_root=PLUGIN_ROOT,
        )

    transaction = _SetupTransaction(target_path) if not dry_run else None
    try:
        core_capsule = _setup_project_publish_v1_and_v2(
            target_path=target_path,
            project_id=project_id,
            manifest=manifest,
            report=report,
            project_profile=project_profile,
            agents_path=agents_path,
            config_path=config_path,
            gitignore_path=gitignore_path,
            actions=actions,
            managed_drifts=managed_drifts,
            dry_run=dry_run,
            repair_capsule=repair_capsule,
            v2=v2,
            transaction=transaction,
        )
    except Exception:
        if transaction is not None:
            transaction.rollback()
        raise

    install_result = {"results": [], "restart_required": False}
    if not skip_install:
        install_result = install_missing(target_path, report, dry_run=dry_run)
    guard_result: dict[str, Any] = {"status": "skipped"}
    if not skip_install:
        guard_result = enforce_implicit_superpowers_guard(dry_run=dry_run)
        install_result["restart_required"] = install_result["restart_required"] or bool(
            guard_result.get("restart_required")
        )

    failed_statuses = {
        "failed",
        "integrity_failed",
        "blocked_unpinned",
        "blocked_invalid_installer",
        "blocked_manifest_unverified",
        "blocked_version_mismatch",
        "blocked_authority_change",
    }
    observed_install_statuses = {item.get("status") for item in install_result["results"]}
    blocking_missing_tier0 = (
        report["missing_tier0"]
        if not skip_install
        else _installable_tier0_requirements(report["missing_tier0"])
    )
    if install_result["restart_required"]:
        final_status = "restart_required"
    elif observed_install_statuses & failed_statuses:
        final_status = "install_failed"
    elif blocking_missing_tier0:
        final_status = "blocked_missing_prerequisites"
    elif not skip_install and report["approval_required"]:
        final_status = "approval_required"
    else:
        final_status = "ready"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": final_status,
        "target": str(target_path),
        "project_id": project_id,
        "actions": actions,
        "managed_block_drifts": managed_drifts,
        "doctor_status": report["status"],
        "missing_tier0": report["missing_tier0"],
        "approval_required": report["approval_required"],
        "install": install_result,
        "policy_guard": guard_result,
        "core_capsule": core_capsule,
    }


def _setup_project_publish_v1_and_v2(
    *,
    target_path: Path,
    project_id: str,
    manifest: dict[str, Any],
    report: dict[str, Any],
    project_profile: dict[str, Any],
    agents_path: Path,
    config_path: Path,
    gitignore_path: Path,
    actions: list[dict[str, Any]],
    managed_drifts: list[dict[str, Any]],
    dry_run: bool,
    repair_capsule: bool,
    v2: Any,
    transaction: _SetupTransaction | None,
) -> dict[str, Any]:
    """Publish v1 and v2 while the caller owns the in-memory compensation log."""
    manifest_path = target_path / ".kimmizo" / "manifest.json"
    for path, label in (
        (agents_path, "AGENTS.md authority file"),
        (config_path, ".codex/config.toml authority file"),
        (gitignore_path, ".gitignore authority file"),
        (manifest_path, "capsule manifest"),
    ):
        _assert_setup_file_safe(path, target_path, label=label)
    agents_existing = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""
    if drift := _backup_managed_drift(
        target_path,
        "AGENTS.md",
        agents_existing,
        managed_block_integrity(agents_existing, style="html"),
        actions,
        dry_run=dry_run,
        transaction=transaction,
    ):
        managed_drifts.append(drift)
    write_if_changed(
        agents_path,
        _agents_managed_merge_preserving_v2(agents_existing, _agents_block()),
        actions,
        dry_run=dry_run,
        reason="managed secretary instructions",
        allowed_root=target_path,
        transaction=transaction,
    )

    config_existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    if drift := _backup_managed_drift(
        target_path,
        ".codex/config.toml",
        config_existing,
        managed_block_integrity(config_existing, style="comment"),
        actions,
        dry_run=dry_run,
        transaction=transaction,
    ):
        managed_drifts.append(drift)
    config_user = strip_managed_block(config_existing, style="comment")
    write_if_changed(
        config_path,
        managed_merge(config_existing, _config_block(config_user), style="comment"),
        actions,
        dry_run=dry_run,
        reason="managed subagent settings",
        allowed_root=target_path,
        transaction=transaction,
    )

    gitignore_existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.is_file() else ""
    if drift := _backup_managed_drift(
        target_path,
        ".gitignore",
        gitignore_existing,
        managed_block_integrity(gitignore_existing, style="comment"),
        actions,
        dry_run=dry_run,
        transaction=transaction,
    ):
        managed_drifts.append(drift)
    write_if_changed(
        gitignore_path,
        managed_merge(gitignore_existing, _gitignore_block(), style="comment"),
        actions,
        dry_run=dry_run,
        reason="private runtime ignore rules",
        allowed_root=target_path,
        transaction=transaction,
    )

    generated_files = {
        target_path / ".kimmizo" / "BOOT.md": _boot_text(),
        target_path / ".kimmizo" / "project-profile.json": json_text(project_profile),
        target_path / ".kimmizo" / "capabilities" / "available.json": json_text(_sanitize_capability_report(report)),
        target_path / ".kimmizo" / "capabilities" / "active.json": json_text(_active_capabilities(report, project_profile)),
        target_path / ".kimmizo" / "capabilities" / "receipts" / "README.md": "Install receipts are generated here and ignored by Git.\n",
        target_path / ".kimmizo" / "knowledge" / "README.md": "Verified project lessons promoted from evidence-backed candidates live here.\n",
        target_path / ".agents" / "skills" / "kimmizo-secretary" / "SKILL.md": _secretary_skill(),
        target_path / ".agents" / "skills" / "kimmizo-capability-router" / "SKILL.md": _router_skill(),
        target_path / ".agents" / "skills" / "kimmizo-memory" / "SKILL.md": _memory_skill(),
    }
    for path, content in generated_files.items():
        write_if_changed(
            path,
            content,
            actions,
            dry_run=dry_run,
            reason="project capsule",
            allowed_root=target_path,
            transaction=transaction,
        )

    _ensure_initial_team(
        target_path,
        project_id,
        project_profile,
        report["model_catalog"],
        actions,
        dry_run=dry_run,
        transaction=transaction,
    )
    write_if_changed(
        manifest_path,
        json_text(manifest),
        actions,
        dry_run=dry_run,
        reason="capsule manifest",
        allowed_root=target_path,
        transaction=transaction,
    )

    checkpoint_path = target_path / ".kimmizo" / "runtime" / "checkpoints" / "latest.json"
    _assert_setup_file_safe(checkpoint_path, target_path, label="checkpoint latest mirror")
    if not checkpoint_path.is_file() and not dry_run:
        write_checkpoint(
            target_path,
            {
                "goal": "Kimmizo project bootstrap",
                "status": "bootstrap_prepared",
                "boss_constraints": ["Preserve project-owned files and authority boundaries."],
                "decisions": ["Use project-local team, routing, checkpoint and memory."],
                "files": ["AGENTS.md", ".codex/config.toml", ".kimmizo/manifest.json"],
                "tests": [],
                "evidence": [".kimmizo/capabilities/available.json"],
                "blockers": report["approval_required"],
                "next_actions": ["Route the boss's first project task."],
            },
            transaction=transaction,
        )
        actions.append({"action": "create", "path": str(checkpoint_path), "reason": "initial checkpoint"})
    elif dry_run and not checkpoint_path.is_file():
        actions.append({"action": "create", "path": str(checkpoint_path), "reason": "initial checkpoint"})

    if transaction is not None:
        transaction.capture_v2_publication()
    return v2.materialize_capsule(
        target_path,
        project_id=project_id,
        dry_run=dry_run,
        repair=repair_capsule,
        plugin_root=PLUGIN_ROOT,
    )


CHECKPOINT_KEYS = [
    "goal",
    "status",
    "boss_constraints",
    "decisions",
    "files",
    "tests",
    "evidence",
    "blockers",
    "next_actions",
]


def _checkpoint_markdown(checkpoint: dict[str, Any]) -> str:
    lines = ["# Kimmizo Current Context", "", f"Goal: {checkpoint['goal']}", f"Status: {checkpoint['status']}"]
    labels = {
        "boss_constraints": "Boss constraints",
        "decisions": "Decisions",
        "files": "Files",
        "tests": "Tests",
        "evidence": "Evidence",
        "blockers": "Blockers",
        "next_actions": "Next actions",
    }
    for key, label in labels.items():
        lines.extend(["", f"## {label}"])
        values = checkpoint.get(key) or []
        lines.extend([f"- {value}" for value in values] or ["- None"])
    if len(lines) > 150:
        raise ValueError("Checkpoint mirror exceeds the 150-line boot budget")
    return "\n".join(lines) + "\n"


def write_checkpoint(
    target: str | Path,
    payload: dict[str, Any],
    *,
    transaction: _SetupTransaction | None = None,
) -> dict[str, Any]:
    target_path = Path(target).expanduser().resolve()
    root = target_path / ".kimmizo" / "runtime" / "checkpoints"
    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpointed_at": utc_now(),
        "goal": payload.get("goal", ""),
        "status": payload.get("status", "in_progress"),
    }
    for key in CHECKPOINT_KEYS[2:]:
        value = payload.get(key, [])
        normalized[key] = value if isinstance(value, list) else [value]
    if not normalized["goal"]:
        raise ValueError("Checkpoint goal is required")

    content = json_text(normalized)
    memory_path = target_path / ".kimmizo" / "memory" / "current.md"
    latest_path = root / "latest.json"
    if transaction is not None:
        transaction.capture_file(latest_path, label="checkpoint latest mirror")
        transaction.capture_file(memory_path, label="checkpoint memory mirror")
    root.mkdir(parents=True, exist_ok=True)
    with _exclusive_directory_lock(root, "checkpoint", recover_stale=transaction is None):
        sequences = [
            int(path.stem)
            for path in root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")
            if path.stem.isdigit()
        ]
        sequence = max(sequences, default=0) + 1
        while True:
            archive = root / f"{sequence:06d}.json"
            try:
                if transaction is not None:
                    transaction.capture_file(archive, label="checkpoint archive")
                with archive.open("x", encoding="utf-8", newline="") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                if transaction is not None:
                    transaction.record_written_file(archive, label="checkpoint archive")
                break
            except FileExistsError:
                sequence += 1
        _atomic_write_text(latest_path, content)
        _atomic_write_text(memory_path, _checkpoint_markdown(normalized))
        if transaction is not None:
            transaction.record_written_file(latest_path, label="checkpoint latest mirror")
            transaction.record_written_file(memory_path, label="checkpoint memory mirror")
    return {
        "status": "checkpointed",
        "checkpoint": str(archive),
        "latest": str(root / "latest.json"),
        "memory": str(memory_path),
    }


def build_context_packet(sources: list[dict[str, str]]) -> dict[str, Any]:
    if len(sources) > 6:
        raise ValueError("Context packet may contain at most 6 sources")
    total_lines = sum(len(item.get("content", "").splitlines()) for item in sources)
    if total_lines > 300:
        raise ValueError("Context packet may contain at most 300 lines")
    redacted_sources = redact_value(sources)
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": redacted_sources,
        "source_count": len(sources),
        "line_count": total_lines,
        "redaction": "applied",
    }


def _v2_project_id(target_path: Path) -> str:
    manifest_path = target_path / ".kimmizo" / "manifest.json"
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        project_id = manifest.get("project_id")
        if project_id:
            return str(project_id)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{target_path}"))


def task_start(
    target: str | Path,
    task: str,
    *,
    model_catalog: dict[str, Any] | None = None,
    execution_mode: str = "auto",
    assurance_level: str = "standard",
    authority_sources: list[str] | None = None,
    in_scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    constraints: list[str] | None = None,
    acceptance: list[str] | None = None,
    privacy_class: str = "internal",
    approval_boundary: str = "not_authorized",
    task_id: str | None = None,
    legacy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create canonical v2 state without changing v1 route or checkpoint files."""
    target_path = Path(target).expanduser().resolve()
    routed = route_task(
        task,
        model_catalog=model_catalog,
        execution_mode=execution_mode,
        assurance_level=assurance_level,
        authority_sources=authority_sources,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        constraints=constraints,
        acceptance=acceptance,
        privacy_class=privacy_class,
        approval_boundary=approval_boundary,
    )
    v2 = _load_v2_package()
    canonical = v2.new_task_from_plan(
        routed["v2"],
        task_id=task_id or str(uuid.uuid4()),
        project_id=_v2_project_id(target_path),
    )
    v2.validate_legacy_compatibility(canonical, legacy)
    stored = v2.create_task(target_path, canonical)
    return {"status": "blocked" if stored["execution"]["state"] == "blocked" else "started", "task": stored}


def task_status(target: str | Path, task_id: str) -> dict[str, Any]:
    return _load_v2_package().read_task(Path(target).expanduser().resolve(), task_id)


def task_transition(
    target: str | Path,
    task_id: str,
    state: str,
    *,
    evidence: list[str] | None = None,
    review_accepted: bool = False,
    review_outcome: str | None = None,
    review_attempt_id: str | None = None,
    review_evidence: list[str] | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    return _load_v2_package().transition_task(
        Path(target).expanduser().resolve(),
        task_id,
        state,
        evidence=evidence,
        review_accepted=review_accepted,
        review_outcome=review_outcome,
        review_attempt_id=review_attempt_id,
        review_evidence=review_evidence,
        expected_revision=expected_revision,
    )


def task_validate(target: str | Path, task_id: str) -> dict[str, Any]:
    task = _load_v2_package().validate_persisted_task(Path(target).expanduser().resolve(), task_id)
    return {"valid": True, "task": task}


# Verb aliases keep the Python facade easy to discover without changing CLI names.
start_task = task_start
transition_task = task_transition


def update_team_profile(target: str | Path, name: str, changes: dict[str, Any]) -> dict[str, Any]:
    target_path = Path(target).expanduser().resolve()
    name = _validated_slug(name, "agent name")
    manifest = load_json(target_path / ".kimmizo" / "manifest.json")
    identities = load_json(target_path / ".kimmizo" / "team" / "identities.json")
    _validate_identities(identities, manifest["project_id"])
    identity = next((item for item in identities["agents"] if item["name"] == name), None)
    if not identity:
        raise KeyError(f"Unknown agent: {name}")
    forbidden = {"name", "agent_id", "role"} & set(changes)
    if forbidden:
        raise ValueError(f"Immutable identity fields cannot change: {sorted(forbidden)}")
    allowed = {"model", "reasoning", "personality", "developer_instructions", "allowed_skills"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Profile update needs boss approval or is unsupported: {sorted(unknown)}")
    if "allowed_skills" in changes:
        changes = {**changes, "allowed_skills": _validate_allowed_skills(changes["allowed_skills"])}

    active_path = target_path / ".kimmizo" / "team" / "active.json"
    active = load_json(active_path)
    entry = active["profiles"][name]
    current_revision = int(entry["revision"])
    current_path = _safe_profile_path(target_path, name, current_revision, entry["path"])
    current = load_json(current_path)
    proposed = dict(current)
    proposed.update(changes)
    comparable = {key: value for key, value in proposed.items() if key not in {"revision", "promotion_state", "evaluation"}}
    current_comparable = {
        key: value for key, value in current.items() if key not in {"revision", "promotion_state", "evaluation"}
    }
    if comparable == current_comparable:
        return {"status": "unchanged", "name": name, "revision": current["revision"]}
    profile_root = target_path / ".kimmizo" / "team" / "profiles" / name
    existing_revisions = [
        int(match.group(1))
        for path in profile_root.glob("v*.json")
        if (match := re.fullmatch(r"v(\d{3,})\.json", path.name))
    ]
    revision = max(existing_revisions or [current_revision]) + 1
    proposed["revision"] = revision
    proposed["name"] = identity["name"]
    proposed["agent_id"] = identity["agent_id"]
    proposed["role"] = identity["role"]
    proposed["promotion_state"] = "candidate"
    proposed["evaluation"] = {"status": "pending", "evidence": []}
    catalog = _project_model_catalog(target_path)
    _standard_profile_evaluation(proposed, identity, catalog)
    new_rel = f".kimmizo/team/profiles/{name}/v{revision:03d}.json"
    new_path = _safe_profile_path(target_path, name, revision, new_rel)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(json_text(proposed), encoding="utf-8")
    return {
        "status": "candidate_pending_evaluation",
        "name": name,
        "agent_id": identity["agent_id"],
        "revision": revision,
        "active_revision": current_revision,
        "next_action": "Run the standard evaluation, then promote or reject this revision.",
    }


def evaluate_team_profile(
    target: str | Path,
    name: str,
    revision: int,
    *,
    passed: bool,
    evidence: list[str],
) -> dict[str, Any]:
    target_path = Path(target).expanduser().resolve()
    name = _validated_slug(name, "agent name")
    if passed and not evidence:
        raise ValueError("A passing profile evaluation requires evidence")
    manifest = load_json(target_path / ".kimmizo" / "manifest.json")
    identities = load_json(target_path / ".kimmizo" / "team" / "identities.json")
    _validate_identities(identities, manifest["project_id"])
    identity = next((item for item in identities["agents"] if item["name"] == name), None)
    if not identity:
        raise KeyError(f"Unknown agent: {name}")
    candidate_rel = f".kimmizo/team/profiles/{name}/v{int(revision):03d}.json"
    candidate_path = _safe_profile_path(target_path, name, int(revision), candidate_rel)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"Candidate profile not found: {candidate_path}")
    candidate = load_json(candidate_path)
    if candidate.get("promotion_state") != "candidate":
        raise ValueError("Only a pending candidate profile can be evaluated")
    standard_evaluation = _standard_profile_evaluation(
        candidate,
        identity,
        _project_model_catalog(target_path),
    )
    candidate["evaluation"] = {
        "status": "passed" if passed else "failed",
        "evaluated_at": utc_now(),
        "evidence": evidence,
        "standard_evaluation": standard_evaluation,
    }
    if not passed:
        candidate["promotion_state"] = "rejected"
        candidate_path.write_text(json_text(candidate), encoding="utf-8")
        return {"status": "rejected", "name": name, "revision": int(revision), "evidence": evidence}

    active_path = target_path / ".kimmizo" / "team" / "active.json"
    active = load_json(active_path)
    entry = active["profiles"][name]
    current_revision = int(entry["revision"])
    _safe_profile_path(target_path, name, current_revision, entry["path"])
    if int(revision) <= current_revision:
        raise ValueError("Candidate revision must be newer than the active revision")
    candidate["promotion_state"] = "active"
    candidate_path.write_text(json_text(candidate), encoding="utf-8")
    previous = [int(item) for item in entry.get("previous_revisions", [])]
    previous.append(current_revision)
    entry.update(
        {
            "revision": int(revision),
            "path": candidate_rel,
            "previous_revisions": previous[-2:],
        }
    )
    active_path.write_text(json_text(active), encoding="utf-8")
    agent_path = target_path / ".codex" / "agents" / f"{name}.toml"
    agent_path.write_text(_agent_toml(candidate), encoding="utf-8")
    keep = {int(revision), *entry["previous_revisions"]}
    for path in candidate_path.parent.glob("v*.json"):
        match = re.fullmatch(r"v(\d{3,})\.json", path.name)
        if match and int(match.group(1)) not in keep:
            path.unlink()
    return {
        "status": "promoted",
        "name": name,
        "agent_id": identity["agent_id"],
        "revision": int(revision),
        "previous_revisions": entry["previous_revisions"],
        "effective_on": "next_spawn",
        "evidence": evidence,
    }


def record_agent_outcome(
    target: str | Path,
    name: str,
    *,
    verification_passed: bool,
    scope_or_security_failure: bool = False,
) -> dict[str, Any]:
    target_path = Path(target).resolve()
    name = _validated_slug(name, "agent name")
    manifest = load_json(target_path / ".kimmizo" / "manifest.json")
    identities = load_json(target_path / ".kimmizo" / "team" / "identities.json")
    _validate_identities(identities, manifest["project_id"])
    if not any(item["name"] == name for item in identities["agents"]):
        raise ValueError(f"Unknown agent: {name}")
    outcome_path = target_path / ".kimmizo" / "team" / "outcomes" / f"{name}.json"
    if not _is_within(outcome_path, target_path / ".kimmizo" / "team" / "outcomes"):
        raise ValueError("Agent outcome path escapes the project")
    data = load_json(outcome_path) if outcome_path.is_file() else {"consecutive_verification_failures": 0, "history": []}
    data["consecutive_verification_failures"] = 0 if verification_passed else data["consecutive_verification_failures"] + 1
    data["history"].append(
        {"at": utc_now(), "verification_passed": verification_passed, "scope_or_security_failure": scope_or_security_failure}
    )
    data["history"] = data["history"][-20:]
    rollback = scope_or_security_failure or data["consecutive_verification_failures"] >= 2
    if rollback:
        rollback_team_profile(target_path, name)
        data["consecutive_verification_failures"] = 0
    learning_candidate_id = None
    if not verification_passed or scope_or_security_failure:
        learning = record_learning_candidate(
            target_path,
            {
                "title": f"{name} verification or scope failure",
                "category": "agent_failure",
                "root_cause": "",
                "evidence": [],
                "prevention_test": "",
                "agent": name,
            },
        )
        learning_candidate_id = learning["candidate_id"]
    outcome_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_path.write_text(json_text(data), encoding="utf-8")
    return {"name": name, "rollback": rollback, "learning_candidate_id": learning_candidate_id, **data}


def rollback_team_profile(target: str | Path, name: str) -> dict[str, Any]:
    target_path = Path(target).resolve()
    name = _validated_slug(name, "agent name")
    manifest = load_json(target_path / ".kimmizo" / "manifest.json")
    identities = load_json(target_path / ".kimmizo" / "team" / "identities.json")
    _validate_identities(identities, manifest["project_id"])
    identity = next((item for item in identities["agents"] if item["name"] == name), None)
    if not identity:
        raise ValueError(f"Unknown agent: {name}")
    active_path = target_path / ".kimmizo" / "team" / "active.json"
    active = load_json(active_path)
    entry = active["profiles"][name]
    previous = entry.get("previous_revisions", [])
    if not previous:
        return {"status": "no_previous_revision", "name": name}
    revision = int(previous[-1])
    relative = f".kimmizo/team/profiles/{name}/v{revision:03d}.json"
    path = _safe_profile_path(target_path, name, revision, relative)
    if not path.is_file():
        raise FileNotFoundError(f"Rollback profile is unavailable: {path}")
    profile = load_json(path)
    if any(profile.get(key) != identity[key] for key in ("name", "agent_id", "role")):
        raise ValueError("Rollback profile identity was altered")
    entry.update(
        {
            "revision": revision,
            "path": relative,
            "previous_revisions": previous[:-1],
        }
    )
    active_path.write_text(json_text(active), encoding="utf-8")
    (target_path / ".codex" / "agents" / f"{name}.toml").write_text(_agent_toml(profile), encoding="utf-8")
    return {"status": "rolled_back", "name": name, "revision": revision}


def record_learning_candidate(target: str | Path, payload: dict[str, Any], *, allow_personal: bool = False) -> dict[str, Any]:
    if payload.get("category") == "personal_preference" and not allow_personal:
        raise PermissionError("Boss approval is required before storing a personal preference")
    target_path = Path(target).resolve()
    candidate_id = str(uuid.uuid4())
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "created_at": utc_now(),
        "status": "candidate",
        **payload,
    }
    path = target_path / ".kimmizo" / "memory" / "candidates" / f"{candidate_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text(candidate), encoding="utf-8")
    return candidate


def promote_learning(target: str | Path, candidate_id: str) -> dict[str, Any]:
    target_path = Path(target).resolve()
    candidate_id = _validated_uuid(candidate_id, "candidate_id")
    candidate_path = target_path / ".kimmizo" / "memory" / "candidates" / f"{candidate_id}.json"
    if not _is_within(candidate_path, target_path / ".kimmizo" / "memory" / "candidates"):
        raise ValueError("Learning candidate path escapes the project")
    candidate = load_json(candidate_path)
    required = ["evidence", "root_cause", "prevention_test"]
    missing = [key for key in required if not candidate.get(key)]
    if missing:
        raise ValueError(f"Learning candidate is not promotable; missing {missing}")
    lesson = redact_value({**candidate, "status": "promoted", "promoted_at": utc_now()})
    knowledge_path = target_path / ".kimmizo" / "knowledge" / "lessons.jsonl"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    with knowledge_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(lesson, ensure_ascii=False, sort_keys=True) + "\n")
    candidate_path.write_text(json_text(lesson), encoding="utf-8")
    return {"status": "promoted", "candidate_id": candidate_id, "knowledge": str(knowledge_path)}


def capsule_status(target: str | Path) -> dict[str, Any]:
    """Return the local Kimweaver v2 capsule health without consulting a Home Base."""
    return _load_v2_package().capsule_status(Path(target).expanduser().resolve())


def rollback_core_capsule(target: str | Path) -> dict[str, Any]:
    """Roll back only the project-local v2 capsule; v1/user artifacts are untouched."""
    return _load_v2_package().rollback_capsule(Path(target).expanduser().resolve())


def repair_project(target: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    result = setup_project(target, dry_run=dry_run, skip_install=True, repair_capsule=True)
    return {**result, "status": "repaired", "repaired_actions": len(result["actions"])}


def team_report(target: str | Path) -> dict[str, Any]:
    target_path = Path(target).resolve()
    manifest = load_json(target_path / ".kimmizo" / "manifest.json")
    identities = load_json(target_path / ".kimmizo" / "team" / "identities.json")
    _validate_identities(identities, manifest["project_id"])
    active = load_json(target_path / ".kimmizo" / "team" / "active.json")
    agents: list[dict[str, Any]] = []
    for identity in identities["agents"]:
        entry = active["profiles"][identity["name"]]
        profile_path = _safe_profile_path(
            target_path,
            identity["name"],
            int(entry["revision"]),
            entry["path"],
        )
        profile = load_json(profile_path)
        agents.append(
            {
                **identity,
                "revision": entry["revision"],
                "model": profile["model"],
                "reasoning": profile["reasoning"],
                "personality": profile["personality"],
                "sandbox_mode": profile["sandbox_mode"],
            }
        )
    return {"schema_version": SCHEMA_VERSION, "agents": agents}


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Kimmizo: {result.get('status', 'ok')}")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _add_task_envelope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority-source", action="append", default=[])
    parser.add_argument("--in-scope", action="append", default=[])
    parser.add_argument("--out-of-scope", action="append", default=[])
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument(
        "--privacy-class", choices=("public", "internal", "private", "sensitive"), default="internal"
    )
    parser.add_argument("--approval-boundary", default="not_authorized")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kimmizo Setup v1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("doctor", "repair", "team-report", "update"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--target", required=True)
        sub.add_argument("--json", action="store_true")
        if name in {"repair", "update"}:
            sub.add_argument("--dry-run", action="store_true")

    setup = subparsers.add_parser("setup")
    setup.add_argument("--target", required=True)
    setup.add_argument("--dry-run", action="store_true")
    setup.add_argument("--skip-install", action="store_true")
    setup.add_argument("--json", action="store_true")

    route = subparsers.add_parser("route")
    route.add_argument("--target", required=True)
    route.add_argument("--task", required=True)
    route.add_argument("--execution-mode", choices=("auto", "solo", "solo-reviewed", "team"), default="auto")
    route.add_argument(
        "--assurance-level", choices=("standard", "reviewed", "protected"), default="standard"
    )
    _add_task_envelope_arguments(route)
    route.add_argument("--json", action="store_true")

    task_start_parser = subparsers.add_parser("task-start")
    task_start_parser.add_argument("--target", required=True)
    task_start_parser.add_argument("--task", required=True)
    task_start_parser.add_argument(
        "--execution-mode", choices=("auto", "solo", "solo-reviewed", "team"), default="auto"
    )
    task_start_parser.add_argument(
        "--assurance-level", choices=("standard", "reviewed", "protected"), default="standard"
    )
    _add_task_envelope_arguments(task_start_parser)
    task_start_parser.add_argument("--task-id")
    task_start_parser.add_argument("--legacy-json")
    task_start_parser.add_argument("--json", action="store_true")

    task_status_parser = subparsers.add_parser("task-status")
    task_status_parser.add_argument("--target", required=True)
    task_status_parser.add_argument("--task-id", required=True)
    task_status_parser.add_argument("--json", action="store_true")

    task_transition_parser = subparsers.add_parser("task-transition")
    task_transition_parser.add_argument("--target", required=True)
    task_transition_parser.add_argument("--task-id", required=True)
    task_transition_parser.add_argument("--state", required=True)
    task_transition_parser.add_argument("--evidence", action="append", default=[])
    task_transition_parser.add_argument("--review-accepted", action="store_true")
    task_transition_parser.add_argument(
        "--review-outcome", choices=("fix-first", "rethink", "unusable")
    )
    task_transition_parser.add_argument("--review-attempt-id")
    task_transition_parser.add_argument("--review-evidence", action="append", default=[])
    task_transition_parser.add_argument("--expected-revision", type=int)
    task_transition_parser.add_argument("--json", action="store_true")

    task_validate_parser = subparsers.add_parser("task-validate")
    task_validate_parser.add_argument("--target", required=True)
    task_validate_parser.add_argument("--task-id", required=True)
    task_validate_parser.add_argument("--json", action="store_true")

    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("--target", required=True)
    checkpoint.add_argument("--goal", required=True)
    checkpoint.add_argument("--status", required=True)
    checkpoint.add_argument("--boss-constraint", action="append", default=[])
    checkpoint.add_argument("--decision", action="append", default=[])
    checkpoint.add_argument("--file", action="append", default=[])
    checkpoint.add_argument("--test", action="append", default=[])
    checkpoint.add_argument("--evidence", action="append", default=[])
    checkpoint.add_argument("--blocker", action="append", default=[])
    checkpoint.add_argument("--next", action="append", default=[])
    checkpoint.add_argument("--json", action="store_true")

    team_update = subparsers.add_parser("team-update")
    team_update.add_argument("--target", required=True)
    team_update.add_argument("--name", required=True)
    team_update.add_argument("--model")
    team_update.add_argument("--reasoning")
    team_update.add_argument("--personality")
    team_update.add_argument("--instructions")
    team_update.add_argument("--skill", action="append")
    team_update.add_argument("--json", action="store_true")

    team_outcome = subparsers.add_parser("team-outcome")
    team_outcome.add_argument("--target", required=True)
    team_outcome.add_argument("--name", required=True)
    team_outcome.add_argument("--verification", choices=("passed", "failed"), required=True)
    team_outcome.add_argument("--scope-security-failure", action="store_true")
    team_outcome.add_argument("--json", action="store_true")

    team_evaluate = subparsers.add_parser("team-evaluate")
    team_evaluate.add_argument("--target", required=True)
    team_evaluate.add_argument("--name", required=True)
    team_evaluate.add_argument("--revision", required=True, type=int)
    team_evaluate.add_argument("--result", choices=("passed", "failed"), required=True)
    team_evaluate.add_argument("--evidence", action="append", default=[])
    team_evaluate.add_argument("--json", action="store_true")

    learn_candidate = subparsers.add_parser("learn-candidate")
    learn_candidate.add_argument("--target", required=True)
    learn_candidate.add_argument("--title", required=True)
    learn_candidate.add_argument("--root-cause")
    learn_candidate.add_argument("--evidence", action="append", default=[])
    learn_candidate.add_argument("--prevention-test")
    learn_candidate.add_argument("--category", default="project_lesson")
    learn_candidate.add_argument("--allow-personal", action="store_true")
    learn_candidate.add_argument("--json", action="store_true")

    learn_promote = subparsers.add_parser("learn-promote")
    learn_promote.add_argument("--target", required=True)
    learn_promote.add_argument("--candidate-id", required=True)
    learn_promote.add_argument("--json", action="store_true")

    capability_rollback = subparsers.add_parser("capability-rollback")
    capability_rollback.add_argument("--target", required=True)
    capability_rollback.add_argument("--id", required=True)
    capability_rollback.add_argument("--json", action="store_true")

    capability_approve = subparsers.add_parser("capability-approve")
    capability_approve.add_argument("--target", required=True)
    capability_approve.add_argument("--id", required=True)
    capability_approve.add_argument("--json", action="store_true")

    capsule_status_parser = subparsers.add_parser("capsule-status")
    capsule_status_parser.add_argument("--target", required=True)
    capsule_status_parser.add_argument("--json", action="store_true")

    capsule_rollback_parser = subparsers.add_parser("capsule-rollback")
    capsule_rollback_parser.add_argument("--target", required=True)
    capsule_rollback_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        result = doctor(args.target)
    elif args.command == "setup":
        result = setup_project(args.target, dry_run=args.dry_run, skip_install=args.skip_install)
    elif args.command == "capsule-status":
        result = capsule_status(args.target)
    elif args.command == "capsule-rollback":
        result = rollback_core_capsule(args.target)
    elif args.command == "route":
        host_report = doctor(args.target)
        result = route_task(
            args.task,
            model_catalog=host_report["model_catalog"],
            execution_mode=args.execution_mode,
            assurance_level=args.assurance_level,
            authority_sources=args.authority_source,
            in_scope=args.in_scope,
            out_of_scope=args.out_of_scope,
            constraints=args.constraint,
            acceptance=args.acceptance,
            privacy_class=args.privacy_class,
            approval_boundary=args.approval_boundary,
        )
        result["target"] = str(Path(args.target).resolve())
    elif args.command == "task-start":
        legacy = json.loads(args.legacy_json) if args.legacy_json else None
        if legacy is not None and not isinstance(legacy, dict):
            raise ValueError("schema_conflict: --legacy-json must contain an object")
        host_report = doctor(args.target)
        result = task_start(
            args.target,
            args.task,
            model_catalog=host_report["model_catalog"],
            execution_mode=args.execution_mode,
            assurance_level=args.assurance_level,
            authority_sources=args.authority_source,
            in_scope=args.in_scope,
            out_of_scope=args.out_of_scope,
            constraints=args.constraint,
            acceptance=args.acceptance,
            privacy_class=args.privacy_class,
            approval_boundary=args.approval_boundary,
            task_id=args.task_id,
            legacy=legacy,
        )
    elif args.command == "task-status":
        result = task_status(args.target, args.task_id)
    elif args.command == "task-transition":
        result = task_transition(
            args.target,
            args.task_id,
            args.state,
            evidence=args.evidence,
            review_accepted=args.review_accepted,
            review_outcome=args.review_outcome,
            review_attempt_id=args.review_attempt_id,
            review_evidence=args.review_evidence,
            expected_revision=args.expected_revision,
        )
    elif args.command == "task-validate":
        result = task_validate(args.target, args.task_id)
    elif args.command == "checkpoint":
        result = write_checkpoint(
            args.target,
            {
                "goal": args.goal,
                "status": args.status,
                "boss_constraints": args.boss_constraint,
                "decisions": args.decision,
                "files": args.file,
                "tests": args.test,
                "evidence": args.evidence,
                "blockers": args.blocker,
                "next_actions": args.next,
            },
        )
    elif args.command == "repair":
        result = repair_project(args.target, dry_run=args.dry_run)
    elif args.command == "update":
        result = setup_project(args.target, dry_run=args.dry_run, skip_install=False)
        result["operation"] = "update"
        if result["status"] == "ready":
            result["status"] = "updated"
    elif args.command == "team-report":
        result = team_report(args.target)
    elif args.command == "team-update":
        changes = {
            key: value
            for key, value in {
                "model": args.model,
                "reasoning": args.reasoning,
                "personality": args.personality,
                "developer_instructions": args.instructions,
                "allowed_skills": args.skill,
            }.items()
            if value is not None
        }
        if not changes:
            raise ValueError("team-update requires at least one profile change")
        result = update_team_profile(args.target, args.name, changes)
    elif args.command == "team-outcome":
        result = record_agent_outcome(
            args.target,
            args.name,
            verification_passed=args.verification == "passed",
            scope_or_security_failure=args.scope_security_failure,
        )
    elif args.command == "team-evaluate":
        result = evaluate_team_profile(
            args.target,
            args.name,
            args.revision,
            passed=args.result == "passed",
            evidence=args.evidence,
        )
    elif args.command == "learn-candidate":
        result = record_learning_candidate(
            args.target,
            {
                "title": args.title,
                "root_cause": args.root_cause,
                "evidence": args.evidence,
                "prevention_test": args.prevention_test,
                "category": args.category,
            },
            allow_personal=args.allow_personal,
        )
    elif args.command == "learn-promote":
        result = promote_learning(args.target, args.candidate_id)
    elif args.command == "capability-rollback":
        result = rollback_capability(args.target, args.id)
    elif args.command == "capability-approve":
        target_path = Path(args.target).expanduser().resolve()
        result = grant_capability_approval(
            args.id,
            target=target_path,
            host_plugins=_host_plugin_inventory(target_path),
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Atomic, project-local persistence for canonical Kimweaver v2 task state."""

from __future__ import annotations

import copy
import json
import os
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from .contracts import transition_allowed, utc_now, validate_new_task, validate_task


def _canonical_task_id(value: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"schema_invalid: task_id must be a UUID: {value!r}") from error
    if str(parsed) != str(value).casefold():
        raise ValueError(f"schema_invalid: task_id must be canonical: {value!r}")
    return str(parsed)


def _canonical_project_id(value: Any) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("schema_invalid: project manifest project_id must be a UUID") from error
    if str(parsed) != str(value).casefold():
        raise ValueError("schema_invalid: project manifest project_id must be canonical")
    return str(parsed)


def task_paths(target: str | Path, task_id: str) -> dict[str, Path]:
    canonical_id = _canonical_task_id(task_id)
    target_root = Path(target).expanduser().resolve()
    root = target_root / ".kimmizo" / "runtime" / "tasks" / canonical_id
    try:
        root.resolve().relative_to(target_root)
    except ValueError as error:
        raise ValueError("path_escape: task runtime root resolves outside the project") from error
    _assert_no_path_aliases(root, target_root)
    return {
        "project": target_root,
        "root": root,
        "current": root / "current.json",
        "history": root / "history.jsonl",
        "lock": root / ".state.lock",
    }


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    return bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _assert_no_path_aliases(path: Path, project_root: Path) -> None:
    """Reject existing symlink/junction ancestors, including aliases that stay in-project."""
    canonical_project = project_root.resolve()
    try:
        relative = path.relative_to(canonical_project)
    except ValueError as error:
        raise ValueError("path_escape: task runtime path is outside the project") from error
    current = canonical_project
    for part in relative.parts:
        current = current / part
        if not current.exists() and not current.is_symlink():
            continue
        if current.is_symlink() or _is_reparse_point(current):
            raise ValueError(f"path_alias: task runtime path contains a symlink or junction: {current}")


def _assert_safe_leaf(path: Path, project_root: Path, *, allow_missing: bool = False) -> None:
    _assert_no_path_aliases(path.parent, project_root)
    if not path.exists() and not path.is_symlink():
        if allow_missing:
            return
        raise FileNotFoundError(f"Task state not found: {path}")
    if path.is_symlink():
        raise ValueError(f"unsafe_link: task state leaf is a symlink: {path}")
    try:
        path.resolve().relative_to(project_root.resolve())
    except ValueError as error:
        raise ValueError("path_escape: task state leaf resolves outside the project") from error
    info = path.lstat()
    reparse = _is_reparse_point(path)
    if reparse or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"unsafe_link: task state leaf is not a singly-owned regular file: {path}")


def _expected_project_id(project_root: Path) -> str:
    """Resolve the task's project identity from local authority, never from task state."""
    manifest = project_root / ".kimmizo" / "manifest.json"
    if not manifest.exists() and not manifest.is_symlink():
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimmizo-v2:{project_root.resolve()}"))
    _assert_safe_leaf(manifest, project_root)
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("schema_invalid: project manifest cannot be read") from error
    if not isinstance(raw, Mapping):
        raise ValueError("schema_invalid: project manifest must be an object")
    return _canonical_project_id(raw.get("project_id"))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.kimmizo-v2-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive_task_lock(root: Path, *, timeout_seconds: float = 15.0) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".state.lock"
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()} at={utc_now()}".encode("utf-8"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for v2 task lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock.unlink(missing_ok=True)


def _load_current(path: Path, project_root: Path, expected_task_id: str) -> dict[str, Any]:
    _assert_safe_leaf(path, project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"schema_invalid: task state cannot be read: {path}") from error
    validated = validate_task(raw)
    if validated["identity"]["task_id"] != expected_task_id:
        raise ValueError(
            "identity_mismatch: persisted task identity does not match its task directory"
        )
    if validated["identity"]["project_id"] != _expected_project_id(project_root):
        raise ValueError(
            "project_identity_mismatch: persisted task does not belong to the target project"
        )
    return validated


def _history_line(*, event: str, task: Mapping[str, Any], previous_state: str | None = None) -> str:
    execution = task["execution"]
    record: dict[str, Any] = {
        "at": execution["updated_at"],
        "event": event,
        "revision": execution["revision"],
        "state": execution["state"],
    }
    if previous_state is not None:
        record["previous_state"] = previous_state
    return json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"


def _write_current_and_history(
    paths: Mapping[str, Path],
    *,
    current: Mapping[str, Any],
    history: str,
    old_current: str | None,
    old_history: str | None,
) -> None:
    """Publish two files under one lock and restore both on a write failure."""
    current_content = _json_text(current)
    try:
        _atomic_write_text(paths["history"], history)
        _atomic_write_text(paths["current"], current_content)
    except Exception:
        if old_history is None:
            paths["history"].unlink(missing_ok=True)
        else:
            _atomic_write_text(paths["history"], old_history)
        if old_current is None:
            paths["current"].unlink(missing_ok=True)
        else:
            _atomic_write_text(paths["current"], old_current)
        raise


def create_task(target: str | Path, task: Mapping[str, Any]) -> dict[str, Any]:
    """Persist a validated new task at the only v2 state location."""
    normalized = validate_new_task(task)
    paths = task_paths(target, normalized["identity"]["task_id"])
    if normalized["identity"]["project_id"] != _expected_project_id(paths["project"]):
        raise ValueError(
            "project_identity_mismatch: new task does not belong to the target project"
        )
    with _exclusive_task_lock(paths["root"]):
        if paths["current"].exists():
            raise FileExistsError(f"Task state already exists: {paths['current']}")
        _assert_safe_leaf(paths["current"], paths["project"], allow_missing=True)
        _assert_safe_leaf(paths["history"], paths["project"], allow_missing=True)
        _write_current_and_history(
            paths,
            current=normalized,
            history=_history_line(event="started", task=normalized),
            old_current=None,
            old_history=None,
        )
    return copy.deepcopy(normalized)


def read_task(target: str | Path, task_id: str) -> dict[str, Any]:
    paths = task_paths(target, task_id)
    canonical_id = _canonical_task_id(task_id)
    return _load_current(paths["current"], paths["project"], canonical_id)


def transition_task(
    target: str | Path,
    task_id: str,
    target_state: str,
    *,
    evidence: list[str] | None = None,
    review_accepted: bool = False,
    review_outcome: str | None = None,
    review_attempt_id: str | None = None,
    review_evidence: list[str] | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Apply one validated lifecycle transition without persisting legacy projections."""
    paths = task_paths(target, task_id)
    parent_evidence = list(evidence or [])
    accepted_evidence = list(review_evidence or [])
    if not all(isinstance(item, str) and item.strip() for item in parent_evidence + accepted_evidence):
        raise ValueError("schema_invalid: evidence values must be non-empty strings")
    if review_attempt_id is not None and (
        not isinstance(review_attempt_id, str) or not review_attempt_id.strip()
    ):
        raise ValueError("schema_invalid: review_attempt_id must be a non-empty string")
    with _exclusive_task_lock(paths["root"]):
        current = _load_current(paths["current"], paths["project"], _canonical_task_id(task_id))
        _assert_safe_leaf(paths["history"], paths["project"])
        current_revision = current["execution"]["revision"]
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError(
                f"revision_conflict: expected {expected_revision}, observed {current_revision}"
            )
        if not transition_allowed(current, target_state):
            raise ValueError(
                f"invalid_transition: {current['execution']['state']} -> {target_state}"
            )

        assurance = current["assurance"]
        if target_state == "parent_verified" and not parent_evidence:
            raise ValueError("evidence_required: parent_verified requires evidence")
        if target_state == "review_ready" and (
            review_outcome is not None or review_accepted or accepted_evidence
        ):
            raise ValueError(
                "review_reservation_invalid: reserve the attempt before dispatching a verdict"
            )
        if target_state == "review_ready" and not assurance["review"]["reviewer_available"]:
            # This is an honest non-transition: protected work remains parent-verified
            # until an independent, read-only review backend is available.
            result = copy.deepcopy(current)
            result["assurance"]["review_ready"] = False
            return result
        if target_state == "review_ready" and (
            assurance["review_exhausted"]
            or assurance["review_budget"]["used"] >= assurance["review_budget"]["max"]
        ):
            raise ValueError("review_budget_exhausted: no review attempts remain")
        if target_state == "review_ready" and assurance["active_review_attempt"] is not None:
            raise ValueError("review_attempt_active: a review attempt is already reserved")
        rejected_review = current["execution"]["state"] == "review_ready" and target_state in {
            "in_progress",
            "rethink",
        }
        if rejected_review:
            if (
                review_accepted
                or review_outcome not in {"fix-first", "rethink", "unusable"}
                or not accepted_evidence
            ):
                raise ValueError(
                    "review_outcome_required: review_ready exit requires fix-first/rethink/unusable evidence"
                )
            if review_attempt_id != assurance["active_review_attempt"]:
                raise ValueError("review_attempt_mismatch: verdict does not match active reservation")
        if target_state == "complete" and assurance["review_required"]:
            if review_outcome is not None or not review_accepted or not accepted_evidence:
                raise ValueError("review_evidence_required: reviewed completion requires accepted review evidence")
            if review_attempt_id != assurance["active_review_attempt"]:
                raise ValueError("review_attempt_mismatch: verdict does not match active reservation")

        proposed = copy.deepcopy(current)
        previous_state = proposed["execution"]["state"]
        timestamp = utc_now()
        proposed["execution"].update(
            {
                "state": target_state,
                "revision": current_revision + 1,
                "updated_at": timestamp,
            }
        )
        if target_state == "parent_verified":
            proposed["evidence"]["parent"].extend(parent_evidence)
            proposed["parent_proof"] = {"status": "verified", "evidence": list(parent_evidence)}
        if target_state == "review_ready":
            reserved_id = review_attempt_id or str(uuid.uuid4())
            if any(
                item["attempt_id"] == reserved_id
                for item in proposed["assurance"]["review_attempts"]
            ):
                raise ValueError("review_attempt_conflict: review attempt ID was already used")
            proposed["assurance"]["review_ready"] = True
            proposed["assurance"]["active_review_attempt"] = reserved_id
            proposed["assurance"]["review_budget"]["used"] += 1
            proposed["assurance"]["review_attempts"].append(
                {
                    "attempt_id": reserved_id,
                    "state": "reserved",
                    "outcome": None,
                    "evidence": [],
                }
            )
        if rejected_review:
            proposed["assurance"]["review_ready"] = False
            proposed["assurance"]["active_review_attempt"] = None
            proposed["assurance"]["review"]["accepted"] = False
            proposed["assurance"]["review"]["evidence"].extend(accepted_evidence)
            proposed["evidence"]["review"].extend(accepted_evidence)
            active_attempt = proposed["assurance"]["review_attempts"][-1]
            active_attempt.update(
                {"state": "closed", "outcome": review_outcome, "evidence": accepted_evidence}
            )
            if (
                proposed["assurance"]["review_budget"]["used"]
                >= proposed["assurance"]["review_budget"]["max"]
            ):
                proposed["execution"]["state"] = "blocked"
                proposed["assurance"]["review_exhausted"] = True
        if target_state == "complete" and proposed["assurance"]["review_required"]:
            proposed["assurance"]["review_ready"] = False
            proposed["assurance"]["active_review_attempt"] = None
            proposed["assurance"]["review"]["accepted"] = True
            proposed["assurance"]["review"]["evidence"].extend(accepted_evidence)
            proposed["evidence"]["review"].extend(accepted_evidence)
            active_attempt = proposed["assurance"]["review_attempts"][-1]
            active_attempt.update(
                {"state": "closed", "outcome": "accept", "evidence": accepted_evidence}
            )
        normalized = validate_task(proposed)
        old_current = paths["current"].read_text(encoding="utf-8")
        old_history = paths["history"].read_text(encoding="utf-8") if paths["history"].is_file() else ""
        _write_current_and_history(
            paths,
            current=normalized,
            history=old_history + _history_line(
                event="transition", task=normalized, previous_state=previous_state
            ),
            old_current=old_current,
            old_history=old_history,
        )
    return normalized


def validate_persisted_task(target: str | Path, task_id: str) -> dict[str, Any]:
    return read_task(target, task_id)

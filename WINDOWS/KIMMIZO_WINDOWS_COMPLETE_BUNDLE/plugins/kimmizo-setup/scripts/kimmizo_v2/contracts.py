"""Dependency-free Kimweaver v2 task contracts.

The v2 contract is deliberately JSON-shaped so a project-local runtime can use
it without importing the v1 setup entrypoint or a Home Base package.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping


SCHEMA = {"name": "kimweaver.task", "version": 2}
RUNTIME_EVIDENCE_LABELS = {"observed", "configured", "unverified"}
EXECUTION_MODES = {"auto", "solo", "solo-reviewed", "team"}
ASSURANCE_LEVELS = {"standard", "reviewed", "protected"}
PRIVACY_CLASSES = {"public", "internal", "private", "sensitive"}
FUNCTIONAL_ROLES = {"explore", "produce", "review", "compact"}
DOMAIN_ADAPTERS = {"software", "research", "document-data", "secretary-coordination"}
ROLE_OWNERS = {
    "explore": "mira",
    "produce": "arin",
    "review": "vera",
    "compact": "nami",
}
TASK_STATES = {
    "scoped",
    "in_progress",
    "checkpoint_ready",
    "parent_verified",
    "review_ready",
    "complete",
    "needs_approval",
    "partial",
    "blocked",
    "rethink",
}
_FORBIDDEN_PERSONAL_KEYS = {"personal_memory", "personal_profile", "personal_preference"}
_ROUTE_PLAN_KEYS = {
    "schema",
    "task",
    "decision",
    "assurance",
    "assignments",
    "evidence_profile",
    "parent_proof",
}
_PERSISTED_TASK_KEYS = _ROUTE_PLAN_KEYS | {"identity", "execution", "evidence"}
_TASK_ENVELOPE_KEYS = {
    "goal",
    "authority_sources",
    "in_scope",
    "out_of_scope",
    "constraints",
    "acceptance",
    "privacy_class",
    "approval_boundary",
    "intent",
    "routing",
}
_REVIEW_BUDGETS = {
    "standard": {"target": 0, "max": 0},
    "reviewed": {"target": 1, "max": 2},
    "protected": {"target": 1, "max": 3},
}
_REVIEW_OUTCOMES = {"accept", "fix-first", "rethink", "unusable"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"schema_invalid: {label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"schema_invalid: {label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"schema_invalid: {label} must be a list of non-empty strings")
    return list(value)


def _optional_string_list(value: list[str] | None, label: str) -> list[str]:
    return [] if value is None else _string_list(value, label)


def _validate_uuid(value: Any, label: str) -> str:
    raw = _string(value, label)
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"schema_invalid: {label} must be a UUID") from error
    if str(parsed) != raw.casefold():
        raise ValueError(f"schema_invalid: {label} must be canonical")
    return str(parsed)


def _reject_personal_memory(value: Any) -> None:
    if isinstance(value, Mapping):
        forbidden = _FORBIDDEN_PERSONAL_KEYS & {str(key).casefold() for key in value}
        if forbidden:
            raise ValueError(f"schema_invalid: personal memory is forbidden ({sorted(forbidden)})")
        for item in value.values():
            _reject_personal_memory(item)


def _reject_extra_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    extra = {str(key) for key in value} - allowed
    if extra:
        raise ValueError(f"schema_conflict: {label} contains non-canonical keys {sorted(extra)}")
    elif isinstance(value, list):
        for item in value:
            _reject_personal_memory(item)


def normalize_execution_mode(value: str) -> str:
    if value not in EXECUTION_MODES:
        raise ValueError(f"schema_invalid: execution_mode must be one of {sorted(EXECUTION_MODES)}")
    return value


def normalize_assurance_level(value: str) -> str:
    if value not in ASSURANCE_LEVELS:
        raise ValueError(f"schema_invalid: assurance_level must be one of {sorted(ASSURANCE_LEVELS)}")
    return value


def new_assurance(level: str, *, reviewer_available: bool) -> dict[str, Any]:
    normalized = normalize_assurance_level(level)
    review_required = normalized in {"reviewed", "protected"}
    budget = _REVIEW_BUDGETS[normalized]
    return {
        "level": normalized,
        "review_required": review_required,
        "review_ready": False,
        "reviewer_available": bool(reviewer_available),
        "review_budget": {**budget, "used": 0},
        "review_exhausted": False,
        "active_review_attempt": None,
        "review_attempts": [],
        "review": {
            "reviewer_available": bool(reviewer_available),
            "accepted": False,
            "evidence": [],
        },
    }


def new_route_plan(
    *,
    goal: str,
    routing: Mapping[str, Any],
    decision: Mapping[str, Any],
    assurance: Mapping[str, Any],
    assignments: list[Mapping[str, Any]],
    authority_sources: list[str] | None = None,
    in_scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    constraints: list[str] | None = None,
    acceptance: list[str] | None = None,
    privacy_class: str = "internal",
    approval_boundary: str = "not_authorized",
) -> dict[str, Any]:
    """Build a canonical, non-persisted v2 routing plan."""
    _string(goal, "task.intent.goal")
    route = _mapping(routing, "task.routing")
    route_data = {
        "classification": _string(route.get("classification"), "task.routing.classification"),
        "risk": _string(route.get("risk"), "task.routing.risk"),
        "capabilities": _string_list(route.get("capabilities", []), "task.routing.capabilities"),
        "workflow": _string_list(route.get("workflow", []), "task.routing.workflow"),
        "agent_role": _string(route.get("agent_role"), "task.routing.agent_role"),
    }
    envelope_constraints = _optional_string_list(constraints, "task.constraints")
    envelope = {
        "goal": goal,
        "authority_sources": _optional_string_list(authority_sources, "task.authority_sources"),
        "in_scope": _optional_string_list(in_scope, "task.in_scope"),
        "out_of_scope": _optional_string_list(out_of_scope, "task.out_of_scope"),
        "constraints": envelope_constraints,
        "acceptance": _optional_string_list(acceptance, "task.acceptance"),
        "privacy_class": privacy_class,
        "approval_boundary": approval_boundary,
        # `intent` remains for the first v2 slice's route projection compatibility.
        "intent": {"goal": goal, "constraints": envelope_constraints},
        "routing": route_data,
    }
    plan = {
        "schema": copy.deepcopy(SCHEMA),
        "task": envelope,
        "decision": copy.deepcopy(dict(_mapping(decision, "decision"))),
        "assurance": copy.deepcopy(dict(_mapping(assurance, "assurance"))),
        "assignments": [copy.deepcopy(dict(_mapping(item, "assignment"))) for item in assignments],
        "evidence_profile": {
            "configuration": "configured",
            "runtime": "unverified",
        },
        "parent_proof": {"status": "unverified", "evidence": []},
    }
    validate_route_plan(plan)
    return plan


def validate_route_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    _reject_personal_memory(value)
    _reject_extra_keys(value, _PERSISTED_TASK_KEYS, "task record")
    if dict(value.get("schema") or {}) != SCHEMA:
        raise ValueError("schema_invalid: expected kimweaver.task v2")
    task = _mapping(value.get("task"), "task")
    _reject_extra_keys(task, _TASK_ENVELOPE_KEYS, "task envelope")
    goal = _string(task.get("goal"), "task.goal")
    for key in ("authority_sources", "in_scope", "out_of_scope", "constraints", "acceptance"):
        _string_list(task.get(key, []), f"task.{key}")
    if task.get("privacy_class") not in PRIVACY_CLASSES:
        raise ValueError("schema_invalid: task.privacy_class is invalid")
    _string(task.get("approval_boundary"), "task.approval_boundary")
    intent = _mapping(task.get("intent"), "task.intent")
    if _string(intent.get("goal"), "task.intent.goal") != goal:
        raise ValueError("schema_invalid: task goal and intent goal must match")
    constraints = intent.get("constraints", [])
    if _string_list(constraints, "task.intent.constraints") != task["constraints"]:
        raise ValueError("schema_invalid: task constraints and intent constraints must match")
    routing = _mapping(task.get("routing"), "task.routing")
    _string(routing.get("classification"), "task.routing.classification")
    _string(routing.get("risk"), "task.routing.risk")
    _string_list(routing.get("capabilities", []), "task.routing.capabilities")
    _string_list(routing.get("workflow", []), "task.routing.workflow")
    _string(routing.get("agent_role"), "task.routing.agent_role")
    decision = _mapping(value.get("decision"), "decision")
    _reject_extra_keys(
        decision,
        {"status", "execution_mode", "reason", "assurance_level", "adapter", "reason_codes", "context_budget", "fallback"},
        "routing decision",
    )
    if decision.get("status") not in {"scoped", "blocked"}:
        raise ValueError("schema_invalid: decision.status must be scoped or blocked")
    normalize_execution_mode(_string(decision.get("execution_mode"), "decision.execution_mode"))
    _string(decision.get("reason"), "decision.reason")
    if decision.get("assurance_level") not in ASSURANCE_LEVELS:
        raise ValueError("schema_invalid: decision.assurance_level is invalid")
    if decision.get("adapter") not in DOMAIN_ADAPTERS:
        raise ValueError("schema_invalid: decision.adapter is invalid")
    _string_list(decision.get("reason_codes", []), "decision.reason_codes")
    context_budget = _mapping(decision.get("context_budget"), "decision.context_budget")
    if context_budget != {"max_sources": 6, "max_lines": 300, "return_max_bullets": 10}:
        raise ValueError("schema_invalid: decision.context_budget is invalid")
    fallback = decision.get("fallback")
    if fallback is not None and not isinstance(fallback, Mapping):
        raise ValueError("schema_invalid: decision.fallback must be an object or null")
    assurance = _mapping(value.get("assurance"), "assurance")
    _reject_extra_keys(
        assurance,
        {
            "level",
            "review_required",
            "review_ready",
            "reviewer_available",
            "review_budget",
            "review_exhausted",
            "active_review_attempt",
            "review_attempts",
            "review",
        },
        "assurance",
    )
    level = normalize_assurance_level(_string(assurance.get("level"), "assurance.level"))
    if decision["assurance_level"] != level:
        raise ValueError("schema_invalid: decision assurance does not match assurance object")
    if not isinstance(assurance.get("review_required"), bool) or not isinstance(assurance.get("review_ready"), bool):
        raise ValueError("schema_invalid: assurance review flags must be booleans")
    if assurance["review_required"] != (level in {"reviewed", "protected"}):
        raise ValueError("schema_invalid: assurance review_required does not match level")
    if not isinstance(assurance.get("reviewer_available"), bool):
        raise ValueError("schema_invalid: assurance.reviewer_available must be a boolean")
    if not isinstance(assurance.get("review_exhausted"), bool):
        raise ValueError("schema_invalid: assurance.review_exhausted must be a boolean")
    review_budget = _mapping(assurance.get("review_budget"), "assurance.review_budget")
    expected_budget = _REVIEW_BUDGETS[level]
    if (
        review_budget.get("target") != expected_budget["target"]
        or review_budget.get("max") != expected_budget["max"]
        or not isinstance(review_budget.get("used"), int)
        or review_budget["used"] < 0
        or review_budget["used"] > review_budget["max"]
    ):
        raise ValueError("schema_invalid: assurance.review_budget is invalid")
    active_attempt = assurance.get("active_review_attempt")
    if active_attempt is not None and (
        not isinstance(active_attempt, str) or not active_attempt.strip()
    ):
        raise ValueError("schema_invalid: assurance.active_review_attempt is invalid")
    attempts = assurance.get("review_attempts")
    if not isinstance(attempts, list):
        raise ValueError("schema_invalid: assurance.review_attempts must be a list")
    attempt_ids: set[str] = set()
    reserved_ids: list[str] = []
    accepted_attempts: list[str] = []
    closed_evidence: list[str] = []
    for attempt in attempts:
        item = _mapping(attempt, "assurance.review_attempt")
        _reject_extra_keys(
            item,
            {"attempt_id", "state", "outcome", "evidence"},
            "assurance.review_attempt",
        )
        attempt_id = _string(item.get("attempt_id"), "assurance.review_attempt.attempt_id")
        if attempt_id in attempt_ids:
            raise ValueError("schema_invalid: review attempt IDs must be unique")
        attempt_ids.add(attempt_id)
        state = item.get("state")
        outcome = item.get("outcome")
        attempt_evidence = _string_list(
            item.get("evidence", []), "assurance.review_attempt.evidence"
        )
        if state == "reserved":
            if outcome is not None or attempt_evidence:
                raise ValueError("schema_invalid: reserved review attempt cannot have an outcome")
            reserved_ids.append(attempt_id)
        elif state == "closed":
            if outcome not in _REVIEW_OUTCOMES or not attempt_evidence:
                raise ValueError("schema_invalid: closed review attempt requires outcome evidence")
            closed_evidence.extend(attempt_evidence)
            if outcome == "accept":
                accepted_attempts.append(attempt_id)
        else:
            raise ValueError("schema_invalid: review attempt state is invalid")
    if review_budget["used"] != len(attempts):
        raise ValueError("schema_invalid: every review attempt must consume budget when reserved")
    if active_attempt is None:
        if reserved_ids:
            raise ValueError("schema_invalid: reserved review attempt must be active")
    elif reserved_ids != [active_attempt]:
        raise ValueError("schema_invalid: active review attempt must be the only reservation")
    review = _mapping(assurance.get("review"), "assurance.review")
    _reject_extra_keys(review, {"reviewer_available", "accepted", "evidence"}, "assurance.review")
    if not isinstance(review.get("reviewer_available"), bool) or not isinstance(review.get("accepted"), bool):
        raise ValueError("schema_invalid: assurance.review flags must be booleans")
    if review["reviewer_available"] != assurance["reviewer_available"]:
        raise ValueError("schema_invalid: reviewer availability must match")
    review_evidence = _string_list(review.get("evidence", []), "assurance.review.evidence")
    if review_evidence != closed_evidence:
        raise ValueError("schema_invalid: review evidence must be bound to closed attempts")
    if review["accepted"] != (len(accepted_attempts) == 1) or len(accepted_attempts) > 1:
        raise ValueError("schema_invalid: accepted review must identify exactly one attempt")
    assignments = value.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("schema_invalid: assignments must be a list")
    for assignment in assignments:
        item = _mapping(assignment, "assignment")
        _reject_extra_keys(
            item,
            {"functional_role", "owner", "backend", "sandbox_mode", "runtime_evidence", "ownership", "focused_verification"},
            "assignment",
        )
        role = _string(item.get("functional_role"), "assignment.functional_role")
        if role not in FUNCTIONAL_ROLES:
            raise ValueError("schema_invalid: unknown functional role")
        if item.get("owner") != ROLE_OWNERS[role]:
            raise ValueError("schema_invalid: assignment owner does not match functional role")
        if not isinstance(item.get("backend"), str) or not item["backend"]:
            raise ValueError("schema_invalid: assignment backend must be a non-empty string")
        sandbox = _string(item.get("sandbox_mode"), "assignment.sandbox_mode")
        if role == "review" and sandbox != "read-only":
            raise ValueError("schema_invalid: reviewers must be read-only")
        if item.get("runtime_evidence") not in RUNTIME_EVIDENCE_LABELS:
            raise ValueError("schema_invalid: assignment.runtime_evidence is invalid")
        ownership = _mapping(item.get("ownership"), "assignment.ownership")
        if ownership.get("mode") != "bounded":
            raise ValueError("schema_invalid: assignment ownership must be bounded")
        _string_list(ownership.get("paths", []), "assignment.ownership.paths")
        _string_list(item.get("focused_verification", []), "assignment.focused_verification")
    evidence_profile = _mapping(value.get("evidence_profile"), "evidence_profile")
    for key in ("configuration", "runtime"):
        if evidence_profile.get(key) not in RUNTIME_EVIDENCE_LABELS:
            raise ValueError(f"schema_invalid: evidence_profile.{key} is invalid")
    parent_proof = _mapping(value.get("parent_proof"), "parent_proof")
    if parent_proof.get("status") not in {"unverified", "verified"}:
        raise ValueError("schema_invalid: parent_proof.status is invalid")
    _string_list(parent_proof.get("evidence", []), "parent_proof.evidence")
    return copy.deepcopy(dict(value))


def new_task_from_plan(
    plan: Mapping[str, Any],
    *,
    task_id: str,
    project_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Turn a validated route plan into persisted canonical task state."""
    validated = validate_route_plan(plan)
    canonical_task_id = _validate_uuid(task_id, "identity.task_id")
    canonical_project_id = _validate_uuid(project_id, "identity.project_id")
    timestamp = created_at or utc_now()
    initial_state = "blocked" if validated["decision"]["status"] == "blocked" else "scoped"
    result = {
        **validated,
        "identity": {"task_id": canonical_task_id, "project_id": canonical_project_id},
        "execution": {
            "mode": validated["decision"]["execution_mode"],
            "state": initial_state,
            "revision": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "evidence": {"parent": [], "review": []},
    }
    validate_task(result)
    return result


def validate_task(value: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_route_plan(value)
    identity = _mapping(value.get("identity"), "identity")
    _reject_extra_keys(identity, {"task_id", "project_id"}, "identity")
    _validate_uuid(identity.get("task_id"), "identity.task_id")
    _validate_uuid(identity.get("project_id"), "identity.project_id")
    execution = _mapping(value.get("execution"), "execution")
    _reject_extra_keys(
        execution,
        {"mode", "state", "revision", "created_at", "updated_at"},
        "execution",
    )
    if normalize_execution_mode(_string(execution.get("mode"), "execution.mode")) != value["decision"]["execution_mode"]:
        raise ValueError("schema_invalid: execution mode does not match decision")
    if execution.get("state") not in TASK_STATES:
        raise ValueError("schema_invalid: unknown execution state")
    if not isinstance(execution.get("revision"), int) or execution["revision"] < 1:
        raise ValueError("schema_invalid: execution.revision must be positive")
    _string(execution.get("created_at"), "execution.created_at")
    _string(execution.get("updated_at"), "execution.updated_at")
    evidence = _mapping(value.get("evidence"), "evidence")
    _reject_extra_keys(evidence, {"parent", "review"}, "evidence")
    _string_list(evidence.get("parent", []), "evidence.parent")
    _string_list(evidence.get("review", []), "evidence.review")
    state = execution["state"]
    parent_proof = value["parent_proof"]
    assurance = value["assurance"]
    if evidence["review"] != assurance["review"]["evidence"]:
        raise ValueError("state_invariant: task review evidence must match closed attempts")
    parent_required = state in {"parent_verified", "review_ready", "complete"}
    if parent_required and (
        parent_proof["status"] != "verified"
        or not parent_proof["evidence"]
        or not evidence["parent"]
    ):
        raise ValueError("state_invariant: verified task state requires parent evidence")
    if parent_proof["status"] == "verified" and not parent_proof["evidence"]:
        raise ValueError("state_invariant: verified parent proof requires evidence")
    if state == "review_ready" and (
        not assurance["review_required"]
        or not assurance["reviewer_available"]
        or not assurance["review_ready"]
        or assurance["review_exhausted"]
        or assurance["active_review_attempt"] is None
    ):
        raise ValueError(
            "state_invariant: review_ready requires an available reviewer and a reserved attempt"
        )
    if state != "review_ready" and assurance["active_review_attempt"] is not None:
        raise ValueError("state_invariant: active review attempt requires review_ready state")
    if assurance["review_ready"] != (state == "review_ready"):
        raise ValueError("state_invariant: assurance.review_ready must match task state")
    if assurance["review_exhausted"] and assurance["review_budget"]["used"] < assurance["review_budget"]["max"]:
        raise ValueError("state_invariant: review exhaustion requires the full budget")
    if assurance["review_exhausted"] and assurance["active_review_attempt"] is not None:
        raise ValueError("state_invariant: exhausted review cannot keep an active attempt")
    if assurance["review_exhausted"] and state != "blocked":
        raise ValueError("state_invariant: exhausted review must block the task")
    accepted_attempts = [
        attempt
        for attempt in assurance["review_attempts"]
        if attempt["outcome"] == "accept"
    ]
    if accepted_attempts and state != "complete":
        raise ValueError("state_invariant: accepted review is valid only at complete")
    if assurance["review"]["accepted"] != bool(accepted_attempts):
        raise ValueError("state_invariant: accepted review flag must match attempt outcome")
    if state == "complete" and assurance["review_required"]:
        if (
            not assurance["review"]["accepted"]
            or not assurance["review"]["evidence"]
            or not evidence["review"]
            or assurance["review_budget"]["used"] < 1
            or not assurance["review_attempts"]
            or assurance["review_attempts"][-1]["outcome"] != "accept"
        ):
            raise ValueError("state_invariant: reviewed completion requires accepted review evidence")
    return copy.deepcopy(dict(value))


def validate_new_task(value: Mapping[str, Any]) -> dict[str, Any]:
    """Require a pristine revision-one state before opening a task path."""
    task = validate_task(value)
    state = task["execution"]["state"]
    if state not in {"scoped", "blocked"} or task["execution"]["revision"] != 1:
        raise ValueError("state_invariant: new task must start scoped or blocked at revision 1")
    if (
        task["parent_proof"] != {"status": "unverified", "evidence": []}
        or task["evidence"] != {"parent": [], "review": []}
        or task["assurance"]["review_ready"]
        or task["assurance"]["review_exhausted"]
        or task["assurance"]["active_review_attempt"] is not None
        or task["assurance"]["review_attempts"]
        or task["assurance"]["review"]["accepted"]
        or task["assurance"]["review_budget"]["used"] != 0
    ):
        raise ValueError("state_invariant: new task contains pre-existing proof or review state")
    return task


def transition_allowed(task: Mapping[str, Any], target_state: str) -> bool:
    """Return whether the contract permits a lifecycle edge before evidence gates."""
    if target_state not in TASK_STATES:
        return False
    execution = _mapping(task.get("execution"), "execution")
    current = execution.get("state")
    assurance = _mapping(task.get("assurance"), "assurance")
    level = assurance.get("level")
    if current == "scoped":
        return target_state == "in_progress"
    if current == "in_progress":
        return target_state in {"checkpoint_ready", "needs_approval", "partial", "blocked", "rethink"}
    if current == "checkpoint_ready":
        return target_state in {"in_progress", "parent_verified"}
    if current == "parent_verified":
        return target_state == ("complete" if level == "standard" else "review_ready")
    if current == "review_ready":
        return target_state in {"complete", "in_progress", "rethink"}
    return False

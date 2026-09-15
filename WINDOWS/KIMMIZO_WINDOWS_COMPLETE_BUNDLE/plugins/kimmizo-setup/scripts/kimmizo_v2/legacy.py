"""Compatibility projection and deterministic role/backend resolution for v2."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    ROLE_OWNERS,
    new_assurance,
    new_route_plan,
    normalize_assurance_level,
    normalize_execution_mode,
)


_NARROW_TERMS = (
    "narrow",
    "mechanical",
    "simple",
    "small",
    "typo",
    "สั้น",
    "เล็ก",
    "เชิงกล",
)
_COUPLED_TERMS = (
    "coupled",
    "architecture",
    "complex",
    "multiple module",
    "หลายโมดูล",
    "เชื่อมหลาย",
    "สำคัญ",
    "critical",
    "judgment",
)
_COMPACT_TERMS = ("compact", "checkpoint", "summar", "สรุป", "ย่อ")
_REVIEW_TERMS = ("review", "audit", "ตรวจ", "security", "ความปลอดภัย")
_RESEARCH_TERMS = ("research", "paper", "citation", "source", "งานวิจัย", "อ้างอิง", "แหล่งข้อมูล")
_DOCUMENT_DATA_TERMS = (
    "spreadsheet",
    "excel",
    "csv",
    "document",
    "pdf",
    "slides",
    "formula",
    "เอกสาร",
    "สูตร",
    "ตาราง",
)
_SECRETARY_TERMS = ("meeting", "schedule", "next action", "ประชุม", "นัด", "ติดตาม", "เจ้าของงาน")


def _available_backends(model_catalog: Mapping[str, Any] | None) -> list[str]:
    if not model_catalog:
        return []
    result: list[str] = []
    for item in model_catalog.get("models", []):
        if isinstance(item, Mapping) and isinstance(item.get("slug"), str) and item["slug"]:
            result.append(item["slug"])
    configured = model_catalog.get("configured_model")
    if isinstance(configured, str) and configured and configured not in result:
        result.append(configured)
    return result


def _functional_role(task: str, route: Mapping[str, Any]) -> str:
    text = task.casefold()
    if route.get("agent_role") == "reviewer":
        return "review"
    if any(term in text for term in _COMPACT_TERMS):
        return "compact"
    if route.get("agent_role") == "implementer":
        return "produce"
    if any(term in text for term in _REVIEW_TERMS):
        return "review"
    if route.get("classification") in {"feature", "bug", "repository", "data_analysis", "web_automation"}:
        return "produce"
    return "explore"


def _preferred_backends(role: str, task: str) -> list[str]:
    text = task.casefold()
    narrow = any(term in text for term in _NARROW_TERMS)
    coupled = any(term in text for term in _COUPLED_TERMS)
    if role == "review":
        return ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
    if role == "compact" or narrow:
        return ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
    if role == "produce" or coupled:
        return ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"]
    return ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]


def _select_backend(role: str, task: str, available: list[str]) -> str | None:
    if not available:
        return None
    available_set = set(available)
    for preferred in _preferred_backends(role, task):
        if preferred in available_set:
            return preferred
    return available[0]


def _assignment(role: str, backend: str) -> dict[str, Any]:
    sandbox = "read-only" if role in {"explore", "review"} else "workspace-write"
    return {
        "functional_role": role,
        "owner": ROLE_OWNERS[role],
        "backend": backend,
        "sandbox_mode": sandbox,
        "runtime_evidence": "configured",
        "ownership": {"mode": "bounded", "paths": []},
        "focused_verification": [],
    }


def _adapter(task: str, route: Mapping[str, Any]) -> str:
    text = task.casefold()
    classification = route.get("classification")
    if classification in {"feature", "bug", "repository", "web", "web_automation"}:
        return "software"
    if classification in {"spreadsheet", "data_analysis"} or any(
        term in text for term in _DOCUMENT_DATA_TERMS
    ):
        return "document-data"
    if any(term in text for term in _RESEARCH_TERMS):
        return "research"
    if any(term in text for term in _SECRETARY_TERMS):
        return "secretary-coordination"
    return "secretary-coordination"


def _needs_team(task: str, route: Mapping[str, Any]) -> bool:
    if route.get("classification") in {"feature", "bug", "data_analysis", "repository", "web_automation"}:
        return True
    return any(term in task.casefold() for term in _COUPLED_TERMS)


def resolve_role_first(
    *,
    task: str,
    route: Mapping[str, Any],
    model_catalog: Mapping[str, Any] | None,
    execution_mode: str,
    assurance_level: str,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    """Resolve task roles before backend selection, with deterministic safe fallback."""
    requested_mode = normalize_execution_mode(execution_mode)
    level = normalize_assurance_level(assurance_level)
    available = _available_backends(model_catalog)
    primary_role = _functional_role(task, route)
    review_required = level in {"reviewed", "protected"}
    assignments: list[dict[str, Any]] = []

    def add_reviewer() -> None:
        reviewer_backend = _select_backend("review", task, available)
        if reviewer_backend:
            assignments.append(_assignment("review", reviewer_backend))

    def add_team_assignments() -> None:
        primary_backend = _select_backend(primary_role, task, available)
        if primary_backend is None:  # defensive; available is truthy above
            raise AssertionError("available backend selection unexpectedly failed")
        assignments.append(_assignment(primary_role, primary_backend))
        if review_required and primary_role != "review":
            add_reviewer()

    if requested_mode == "solo":
        decision = (
            {"status": "blocked", "execution_mode": "solo", "reason": "review_requires_solo_reviewed"}
            if review_required
            else {"status": "scoped", "execution_mode": "solo", "reason": "explicit_solo"}
        )
    elif requested_mode == "team":
        if not available:
            decision = {"status": "blocked", "execution_mode": "team", "reason": "backend_unavailable"}
        else:
            add_team_assignments()
            decision = {"status": "scoped", "execution_mode": "team", "reason": "role_first_assignment"}
    elif requested_mode == "solo-reviewed":
        if available:
            add_reviewer()
            decision = {
                "status": "scoped",
                "execution_mode": "solo-reviewed",
                "reason": "explicit_solo_reviewed",
            }
        else:
            decision = {
                "status": "blocked",
                "execution_mode": "solo-reviewed",
                "reason": "reviewer_unavailable",
            }
    elif review_required:
        if available:
            add_reviewer()
        decision = {
            "status": "scoped",
            "execution_mode": "solo-reviewed",
            "reason": "auto_selected_solo_reviewed",
        }
    else:
        decision = {
            "status": "scoped",
            "execution_mode": "solo",
            "reason": "auto_selected_solo" if available else "backend_unavailable_auto_fallback",
        }

    reviewer_available = any(
        assignment["functional_role"] == "review" and assignment["sandbox_mode"] == "read-only"
        for assignment in assignments
    )
    adapter = _adapter(task, route)
    reason = decision["reason"]
    fallback: dict[str, str] | None = None
    if reason == "backend_unavailable_auto_fallback":
        fallback = {"kind": "parent_solo", "reason": "backend_unavailable"}
    elif decision["status"] == "blocked":
        fallback = {"kind": "blocked", "reason": reason}
    decision.update(
        {
            "assurance_level": level,
            "adapter": adapter,
            "reason_codes": [reason, f"adapter:{adapter}"],
            "context_budget": {
                "max_sources": 6,
                "max_lines": 300,
                "return_max_bullets": 10,
            },
            "fallback": fallback,
        }
    )
    return decision, new_assurance(level, reviewer_available=reviewer_available), assignments


def build_route_plan(
    *,
    task: str,
    legacy_route: Mapping[str, Any],
    model_catalog: Mapping[str, Any] | None,
    execution_mode: str,
    assurance_level: str,
    authority_sources: list[str] | None = None,
    in_scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    constraints: list[str] | None = None,
    acceptance: list[str] | None = None,
    privacy_class: str = "internal",
    approval_boundary: str = "not_authorized",
) -> dict[str, Any]:
    decision, assurance, assignments = resolve_role_first(
        task=task,
        route=legacy_route,
        model_catalog=model_catalog,
        execution_mode=execution_mode,
        assurance_level=assurance_level,
    )
    return new_route_plan(
        goal=task,
        routing={
            "classification": legacy_route["classification"],
            "risk": legacy_route["risk"],
            "capabilities": list(legacy_route["capabilities"]),
            "workflow": list(legacy_route["workflow"]),
            "agent_role": legacy_route["agent_role"],
        },
        decision=decision,
        assurance=assurance,
        assignments=assignments,
        authority_sources=authority_sources,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        constraints=constraints,
        acceptance=acceptance,
        privacy_class=privacy_class,
        approval_boundary=approval_boundary,
    )


def project_task_to_legacy(task: Mapping[str, Any]) -> dict[str, Any]:
    """Generate the legacy fields that can be compared without persisting them."""
    task_body = task.get("task")
    if not isinstance(task_body, Mapping):
        raise ValueError("schema_conflict: canonical task body is missing")
    intent = task_body.get("intent")
    routing = task_body.get("routing")
    if not isinstance(intent, Mapping) or not isinstance(routing, Mapping):
        raise ValueError("schema_conflict: canonical task routing is missing")
    return {
        "task": intent.get("goal"),
        "classification": routing.get("classification"),
        "risk": routing.get("risk"),
        "capabilities": routing.get("capabilities"),
        "workflow": routing.get("workflow"),
        "agent_role": routing.get("agent_role"),
    }


def validate_legacy_compatibility(task: Mapping[str, Any], legacy: Mapping[str, Any] | None) -> None:
    """Reject a supplied v1 projection conflict before the state layer opens a path."""
    if legacy is None:
        return
    if not isinstance(legacy, Mapping):
        raise ValueError("schema_conflict: legacy projection must be an object")
    expected = project_task_to_legacy(task)
    for key, observed in legacy.items():
        if key in expected and observed != expected[key]:
            raise ValueError(f"schema_conflict: legacy {key} does not match canonical task")

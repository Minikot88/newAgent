from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "kimmizo-setup" / "scripts" / "kimmizo.py"


def load_kimmizo():
    spec = importlib.util.spec_from_file_location("kimmizo_v2_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def kimmizo():
    return load_kimmizo()


def model_catalog() -> dict:
    return {
        "models": [
            {"slug": "gpt-5.6-luna", "supported_reasoning": ["low", "medium"]},
            {"slug": "gpt-5.6-terra", "supported_reasoning": ["medium", "high"]},
            {"slug": "gpt-5.6-sol", "supported_reasoning": ["high"]},
        ],
        "configured_model": "gpt-5.6-terra",
        "supported_reasoning": ["low", "medium", "high"],
    }


def empty_catalog() -> dict:
    return {
        "models": [],
        "configured_model": None,
        "supported_reasoning": [],
    }


def test_route_keeps_v1_fields_and_adds_role_first_v2_assignments(kimmizo):
    """Catches a route refactor that drops legacy fields or assigns the wrong owner/backend."""
    task = "เพิ่ม feature ที่เชื่อมหลายโมดูลและต้อง review"

    routed = kimmizo.route_task(
        task,
        model_catalog=model_catalog(),
        execution_mode="team",
        assurance_level="reviewed",
    )

    assert routed["task"] == task
    assert routed["classification"] == "feature"
    assert routed["workflow"][2] == "superpowers:test-driven-development"
    v2 = routed["v2"]
    assert v2["schema"] == {"name": "kimweaver.task", "version": 2}
    assert v2["task"]["intent"]["goal"] == task
    assert v2["decision"]["execution_mode"] == "team"
    assert v2["assurance"]["level"] == "reviewed"
    assert v2["assignments"][0] == {
        "functional_role": "produce",
        "owner": "arin",
        "backend": "gpt-5.6-terra",
        "sandbox_mode": "workspace-write",
        "runtime_evidence": "configured",
        "ownership": {"mode": "bounded", "paths": []},
        "focused_verification": [],
    }
    assert v2["assignments"][1] == {
        "functional_role": "review",
        "owner": "vera",
        "backend": "gpt-5.6-sol",
        "sandbox_mode": "read-only",
        "runtime_evidence": "configured",
        "ownership": {"mode": "bounded", "paths": []},
        "focused_verification": [],
    }
    assert v2["evidence_profile"]["runtime"] == "unverified"


def test_repository_security_review_routes_only_to_read_only_vera(kimmizo):
    """Catches repository classification overriding an explicit review boundary with a writer."""
    routed = kimmizo.route_task(
        "review GitHub security",
        model_catalog=model_catalog(),
        execution_mode="team",
        assurance_level="reviewed",
    )

    assert routed["classification"] == "repository"
    assert routed["agent_role"] == "reviewer"
    assert routed["v2"]["assignments"] == [
        {
            "functional_role": "review",
            "owner": "vera",
            "backend": "gpt-5.6-sol",
            "sandbox_mode": "read-only",
            "runtime_evidence": "configured",
            "ownership": {"mode": "bounded", "paths": []},
            "focused_verification": [],
        }
    ]


def test_explicit_review_intent_outranks_feature_classification(kimmizo):
    """Catches the word feature turning an explicit review request into a write-capable lane."""
    routed = kimmizo.route_task(
        "review GitHub security feature",
        model_catalog=model_catalog(),
        execution_mode="team",
        assurance_level="reviewed",
    )

    assert routed["classification"] == "feature"
    assert routed["agent_role"] == "reviewer"
    assert [item["functional_role"] for item in routed["v2"]["assignments"]] == ["review"]
    assert routed["v2"]["assignments"][0]["owner"] == "vera"
    assert routed["v2"]["assignments"][0]["sandbox_mode"] == "read-only"


@pytest.mark.parametrize(
    ("task", "adapter"),
    [
        ("เพิ่ม feature พร้อม regression tests", "software"),
        ("วิเคราะห์งานวิจัยล่าสุดพร้อมแหล่งอ้างอิง", "research"),
        ("ตรวจไฟล์ spreadsheet และสูตรคำนวณ", "document-data"),
        ("เตรียมประชุม เจ้าของงาน และ next action", "secretary-coordination"),
    ],
)
def test_route_selects_v2_domain_adapter_and_complete_decision_contract(kimmizo, task, adapter):
    """Catches a route that ships adapter files but never selects one in its canonical decision."""
    routed = kimmizo.route_task(task, model_catalog=model_catalog())
    decision = routed["v2"]["decision"]

    assert decision["adapter"] == adapter
    assert decision["assurance_level"] == routed["v2"]["assurance"]["level"]
    assert decision["reason_codes"]
    assert decision["context_budget"] == {
        "max_sources": 6,
        "max_lines": 300,
        "return_max_bullets": 10,
    }
    assert "fallback" in decision


def test_auto_routine_with_catalog_uses_solo_and_round_trips_complete_envelope(kimmizo):
    """Catches auto delegation of routine work and envelope fields being lost or treated as raw sensitive data."""
    routed = kimmizo.route_task(
        "สรุปสถานะงานประจำวัน",
        model_catalog=model_catalog(),
        authority_sources=["AGENTS.md", "ticket-42"],
        in_scope=["reports"],
        out_of_scope=["production"],
        constraints=["read-only"],
        acceptance=["concise summary"],
        privacy_class="sensitive",
        approval_boundary="boss_approval_required",
    )

    v2 = routed["v2"]
    assert v2["decision"]["execution_mode"] == "solo"
    assert v2["assignments"] == []
    envelope = v2["task"]
    assert {key: envelope[key] for key in ("goal", "authority_sources", "in_scope", "out_of_scope", "constraints", "acceptance", "privacy_class", "approval_boundary")} == {
        "goal": "สรุปสถานะงานประจำวัน",
        "authority_sources": ["AGENTS.md", "ticket-42"],
        "in_scope": ["reports"],
        "out_of_scope": ["production"],
        "constraints": ["read-only"],
        "acceptance": ["concise summary"],
        "privacy_class": "sensitive",
        "approval_boundary": "boss_approval_required",
    }
    assert envelope["intent"] == {"goal": "สรุปสถานะงานประจำวัน", "constraints": ["read-only"]}
    assert envelope["routing"]["classification"] == "general"


def test_limit_first_auto_keeps_large_feature_serial_until_team_is_explicit(kimmizo):
    routed = kimmizo.route_task(
        "เพิ่ม feature ขนาดใหญ่ที่เชื่อมหลายโมดูล",
        model_catalog=model_catalog(),
        execution_mode="auto",
    )

    assert routed["v2"]["decision"]["execution_mode"] == "solo"
    assert routed["v2"]["decision"]["reason"] == "auto_selected_solo"
    assert routed["v2"]["assignments"] == []


def test_auto_reviewed_routine_uses_solo_reviewed_with_budgeted_reviewer(kimmizo):
    """Catches a reviewed routine silently becoming an ordinary solo task or lacking a reviewer budget."""
    routed = kimmizo.route_task(
        "สรุปสถานะงานประจำวัน",
        model_catalog=model_catalog(),
        execution_mode="auto",
        assurance_level="reviewed",
    )

    assert {key: routed["v2"]["decision"][key] for key in ("status", "execution_mode", "reason")} == {
        "status": "scoped",
        "execution_mode": "solo-reviewed",
        "reason": "auto_selected_solo_reviewed",
    }
    assert routed["v2"]["assignments"] == [
        {
            "functional_role": "review",
            "owner": "vera",
            "backend": "gpt-5.6-sol",
            "sandbox_mode": "read-only",
            "runtime_evidence": "configured",
            "ownership": {"mode": "bounded", "paths": []},
            "focused_verification": [],
        }
    ]
    assert routed["v2"]["assurance"]["review_budget"] == {"target": 1, "max": 2, "used": 0}
    assert routed["v2"]["assurance"]["reviewer_available"] is True


def test_explicit_solo_reviewed_or_protected_work_is_blocked(kimmizo):
    """Catches explicit solo review work being silently downgraded instead of requiring solo-reviewed mode."""
    routed = kimmizo.route_task(
        "สรุปสถานะงานประจำวัน",
        model_catalog=model_catalog(),
        execution_mode="solo",
        assurance_level="protected",
    )

    assert {key: routed["v2"]["decision"][key] for key in ("status", "execution_mode", "reason")} == {
        "status": "blocked",
        "execution_mode": "solo",
        "reason": "review_requires_solo_reviewed",
    }


def test_explicit_solo_reviewed_without_reviewer_is_blocked(kimmizo):
    """Catches an explicit independent-review mode being declared runnable without a reviewer."""
    routed = kimmizo.route_task(
        "สรุปสถานะงานประจำวัน",
        model_catalog=empty_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )

    assert {key: routed["v2"]["decision"][key] for key in ("status", "execution_mode", "reason")} == {
        "status": "blocked",
        "execution_mode": "solo-reviewed",
        "reason": "reviewer_unavailable",
    }
    assert routed["v2"]["assignments"] == []


def test_parent_verification_records_parent_proof_without_observing_runtime(kimmizo, tmp_path):
    """Catches parent evidence being misrepresented as observed model or runtime evidence."""
    started = kimmizo.task_start(tmp_path, "สรุปสถานะงาน", model_catalog=model_catalog())
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")

    verified = kimmizo.task_transition(
        tmp_path, task_id, "parent_verified", evidence=["tests/parent-proof.json"]
    )

    assert verified["parent_proof"] == {
        "status": "verified",
        "evidence": ["tests/parent-proof.json"],
    }
    assert verified["evidence_profile"]["runtime"] == "unverified"
    assert verified["evidence_profile"]["configuration"] == "configured"


def test_parent_verification_cannot_bypass_checkpoint_ready(kimmizo, tmp_path):
    """Catches a task reaching parent proof/review without publishing a checkpoint-ready state."""
    started = kimmizo.task_start(tmp_path, "งานตาม state machine", model_catalog=model_catalog())
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    task_root = tmp_path / ".kimmizo" / "runtime" / "tasks" / task_id
    before_current = task_root.joinpath("current.json").read_bytes()
    before_history = task_root.joinpath("history.jsonl").read_bytes()

    with pytest.raises(ValueError, match="invalid_transition"):
        kimmizo.task_transition(
            tmp_path, task_id, "parent_verified", evidence=["parent-proof"]
        )

    assert task_root.joinpath("current.json").read_bytes() == before_current
    assert task_root.joinpath("history.jsonl").read_bytes() == before_history
    checkpoint = kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    assert checkpoint["execution"]["state"] == "checkpoint_ready"
    verified = kimmizo.task_transition(
        tmp_path, task_id, "parent_verified", evidence=["parent-proof"]
    )
    assert verified["execution"]["state"] == "parent_verified"


def test_context_packet_redacts_common_secret_patterns_without_mutating_sources(kimmizo):
    """Catches the bounded context bridge forwarding raw credentials into worker context."""
    sources = [
        {
            "path": "notes.txt",
            "content": "Bearer abc.def token=secret123 api_key:xyz",
        }
    ]

    packet = kimmizo.build_context_packet(sources)

    content = packet["sources"][0]["content"]
    assert packet["redaction"] == "applied"
    assert "abc.def" not in content
    assert "secret123" not in content
    assert "xyz" not in content
    assert sources[0]["content"] == "Bearer abc.def token=secret123 api_key:xyz"


def test_route_auto_without_backend_falls_back_to_solo(kimmizo):
    """Catches auto routing that attempts an unavailable worker backend instead of solo fallback."""
    routed = kimmizo.route_task(
        "สรุปงานสั้น ๆ",
        model_catalog=empty_catalog(),
        execution_mode="auto",
    )

    assert {key: routed["v2"]["decision"][key] for key in ("status", "execution_mode", "reason")} == {
        "status": "scoped",
        "execution_mode": "solo",
        "reason": "backend_unavailable_auto_fallback",
    }
    assert routed["v2"]["assignments"] == []


def test_route_explicit_team_without_backend_is_blocked(kimmizo):
    """Catches explicit team work being silently downgraded when no backend exists."""
    routed = kimmizo.route_task(
        "เพิ่ม feature",
        model_catalog=empty_catalog(),
        execution_mode="team",
    )

    assert {key: routed["v2"]["decision"][key] for key in ("status", "execution_mode", "reason")} == {
        "status": "blocked",
        "execution_mode": "team",
        "reason": "backend_unavailable",
    }


def test_task_start_keeps_explicit_backend_unavailability_blocked(kimmizo, tmp_path):
    """Catches task-start persisting a runnable scoped state after an explicit team backend block."""
    started = kimmizo.task_start(
        tmp_path,
        "เพิ่ม feature",
        model_catalog=empty_catalog(),
        execution_mode="team",
    )

    assert started["status"] == "blocked"
    assert started["task"]["decision"]["reason"] == "backend_unavailable"
    assert started["task"]["execution"]["state"] == "blocked"


def test_task_parent_verification_and_review_completion_require_evidence(kimmizo, tmp_path):
    """Catches state changes to parent_verified or reviewed completion without the required evidence."""
    started = kimmizo.task_start(
        tmp_path,
        "เพิ่ม feature ที่เชื่อมหลายโมดูล",
        model_catalog=model_catalog(),
        execution_mode="team",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")

    with pytest.raises(ValueError, match="evidence_required"):
        kimmizo.task_transition(tmp_path, task_id, "parent_verified")

    verified = kimmizo.task_transition(
        tmp_path, task_id, "parent_verified", evidence=["tests/feature.json"]
    )
    assert verified["execution"]["state"] == "parent_verified"
    ready = kimmizo.task_transition(tmp_path, task_id, "review_ready")
    assert ready["execution"]["state"] == "review_ready"
    assert ready["assurance"]["review_ready"] is True
    attempt_id = ready["assurance"]["active_review_attempt"]
    assert attempt_id
    assert ready["assurance"]["review_budget"]["used"] == 1

    with pytest.raises(ValueError, match="review_evidence_required"):
        kimmizo.task_transition(tmp_path, task_id, "complete")

    completed = kimmizo.task_transition(
        tmp_path,
        task_id,
        "complete",
        review_accepted=True,
        review_attempt_id=attempt_id,
        review_evidence=["reviews/accepted.json"],
    )
    assert completed["execution"]["state"] == "complete"
    assert completed["assurance"]["review"]["accepted"] is True
    assert (tmp_path / ".kimmizo" / "runtime" / "tasks" / task_id / "history.jsonl").is_file()


def test_reviewed_task_without_reviewer_keeps_review_ready_false(kimmizo, tmp_path):
    """Catches a reviewed task claiming review readiness when no read-only reviewer backend exists."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture",
        model_catalog=empty_catalog(),
        execution_mode="auto",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["tests/parent.json"])

    waiting = kimmizo.task_transition(tmp_path, task_id, "review_ready")

    assert waiting["execution"]["state"] == "parent_verified"
    assert waiting["assurance"]["review_ready"] is False


def test_task_start_rejects_legacy_conflict_before_writing_state(kimmizo, tmp_path):
    """Catches a migration bridge that persists canonical state after a conflicting legacy projection."""
    with pytest.raises(ValueError, match="schema_conflict"):
        kimmizo.task_start(
            tmp_path,
            "งานจริง",
            model_catalog=model_catalog(),
            legacy={"task": "งานคนละเรื่อง"},
        )

    assert not (tmp_path / ".kimmizo" / "runtime" / "tasks").exists()


def test_task_transition_rejects_stale_revision_without_appending_history(kimmizo, tmp_path):
    """Catches a non-atomic transition that accepts stale writers or appends history before rejection."""
    started = kimmizo.task_start(tmp_path, "งานสถานะ", model_catalog=model_catalog())
    task_id = started["task"]["identity"]["task_id"]
    progressed = kimmizo.task_transition(tmp_path, task_id, "in_progress", expected_revision=1)
    task_root = tmp_path / ".kimmizo" / "runtime" / "tasks" / task_id
    before_current = (task_root / "current.json").read_text(encoding="utf-8")
    before_history = (task_root / "history.jsonl").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="revision_conflict"):
        kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready", expected_revision=1)

    assert progressed["execution"]["revision"] == 2
    assert (task_root / "current.json").read_text(encoding="utf-8") == before_current
    assert (task_root / "history.jsonl").read_text(encoding="utf-8") == before_history


def test_task_cli_facade_emits_json_for_start_status_transition_and_validate(kimmizo, tmp_path, capsys):
    """Catches new task CLI commands that do not preserve machine-readable JSON behavior."""
    assert (
        kimmizo.main(
            [
                "task-start",
                "--target",
                str(tmp_path),
                "--task",
                "ทำงานสั้น",
                "--authority-source",
                "AGENTS.md",
                "--authority-source",
                "ticket-42",
                "--in-scope",
                "reports",
                "--out-of-scope",
                "production",
                "--constraint",
                "read-only",
                "--acceptance",
                "summary",
                "--privacy-class",
                "private",
                "--approval-boundary",
                "boss_approval_required",
                "--json",
            ]
        )
        == 0
    )
    started = json.loads(capsys.readouterr().out)
    task_id = started["task"]["identity"]["task_id"]
    assert started["task"]["task"]["authority_sources"] == ["AGENTS.md", "ticket-42"]
    assert started["task"]["task"]["privacy_class"] == "private"

    assert (
        kimmizo.main(
            ["task-transition", "--target", str(tmp_path), "--task-id", task_id, "--state", "in_progress", "--json"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["execution"]["state"] == "in_progress"

    assert kimmizo.main(["task-status", "--target", str(tmp_path), "--task-id", task_id, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["identity"]["task_id"] == task_id

    assert kimmizo.main(["task-validate", "--target", str(tmp_path), "--task-id", task_id, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_direct_task_state_rejects_terminal_or_legacy_inconsistent_creation(kimmizo, tmp_path):
    """Catches callers bypassing lifecycle/review gates through the public state API."""
    routed = kimmizo.route_task(
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="protected",
    )
    v2 = kimmizo._load_v2_package()
    task = v2.new_task_from_plan(
        routed["v2"],
        task_id="00000000-0000-4000-8000-000000000001",
        project_id="00000000-0000-4000-8000-000000000002",
    )
    task["execution"]["state"] = "complete"
    task["legacy_task"] = "conflicting second authority"

    with pytest.raises(ValueError, match="state_invariant|schema_conflict"):
        v2.create_task(tmp_path, task)

    assert not (tmp_path / ".kimmizo" / "runtime" / "tasks").exists()


def test_direct_task_creation_rejects_project_identity_before_writing(kimmizo, tmp_path):
    """Catches a caller persisting a task that is already foreign to the target project."""
    manifest = tmp_path / ".kimmizo" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"project_id": "00000000-0000-4000-8000-0000000000b2"}),
        encoding="utf-8",
    )
    routed = kimmizo.route_task("งาน foreign", model_catalog=model_catalog())
    v2 = kimmizo._load_v2_package()
    task = v2.new_task_from_plan(
        routed["v2"],
        task_id="00000000-0000-4000-8000-0000000000b1",
        project_id="00000000-0000-4000-8000-0000000000a1",
    )

    with pytest.raises(ValueError, match="project_identity_mismatch"):
        v2.create_task(tmp_path, task)

    assert not (tmp_path / ".kimmizo" / "runtime" / "tasks").exists()


def test_rejected_reviews_consume_budget_and_final_rejection_blocks(kimmizo, tmp_path):
    """Catches unlimited fix-first/rethink review loops that never consume the declared budget."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])
    first_ready = kimmizo.task_transition(tmp_path, task_id, "review_ready")
    first_attempt = first_ready["assurance"]["active_review_attempt"]
    assert first_ready["assurance"]["review_budget"]["used"] == 1

    first = kimmizo.task_transition(
        tmp_path,
        task_id,
        "in_progress",
        review_outcome="fix-first",
        review_attempt_id=first_attempt,
        review_evidence=["review-1"],
    )
    assert first["assurance"]["review_budget"]["used"] == 1
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-2"])
    second_ready = kimmizo.task_transition(tmp_path, task_id, "review_ready")
    second_attempt = second_ready["assurance"]["active_review_attempt"]
    assert second_ready["assurance"]["review_budget"]["used"] == 2
    exhausted = kimmizo.task_transition(
        tmp_path,
        task_id,
        "in_progress",
        review_outcome="rethink",
        review_attempt_id=second_attempt,
        review_evidence=["review-2"],
    )
    assert exhausted["execution"]["state"] == "blocked"
    assert exhausted["assurance"]["review_budget"] == {"target": 1, "max": 2, "used": 2}
    assert exhausted["assurance"]["review_exhausted"] is True


def test_review_attempt_is_atomically_reserved_before_dispatch_and_unusable_consumes_it(
    kimmizo, tmp_path
):
    """Catches crashed or unparsable reviewers receiving unlimited unrecorded retries."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])

    ready = kimmizo.task_transition(
        tmp_path,
        task_id,
        "review_ready",
        review_attempt_id="review-attempt-1",
    )

    assert ready["assurance"]["active_review_attempt"] == "review-attempt-1"
    assert ready["assurance"]["review_budget"]["used"] == 1
    assert ready["assurance"]["review_attempts"] == [
        {
            "attempt_id": "review-attempt-1",
            "state": "reserved",
            "outcome": None,
            "evidence": [],
        }
    ]
    persisted = kimmizo.task_status(tmp_path, task_id)
    assert persisted["assurance"]["active_review_attempt"] == "review-attempt-1"
    assert persisted["assurance"]["review_budget"]["used"] == 1

    with pytest.raises(ValueError, match="invalid_transition|review_attempt_active"):
        kimmizo.task_transition(
            tmp_path,
            task_id,
            "review_ready",
            review_attempt_id="review-attempt-2",
        )

    resumed = kimmizo.task_transition(
        tmp_path,
        task_id,
        "in_progress",
        review_outcome="unusable",
        review_attempt_id="review-attempt-1",
        review_evidence=["reviewer process exited without a verdict"],
    )
    assert resumed["assurance"]["review_budget"]["used"] == 1
    assert resumed["assurance"]["active_review_attempt"] is None
    assert resumed["assurance"]["review_attempts"][0]["state"] == "closed"
    assert resumed["assurance"]["review_attempts"][0]["outcome"] == "unusable"


def test_review_outcome_must_match_the_active_reserved_attempt(kimmizo, tmp_path):
    """Catches a stale reviewer response being applied to a newer frozen candidate call."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])
    kimmizo.task_transition(
        tmp_path,
        task_id,
        "review_ready",
        review_attempt_id="current-attempt",
    )

    task_root = tmp_path / ".kimmizo" / "runtime" / "tasks" / task_id
    before_current = (task_root / "current.json").read_bytes()
    before_history = (task_root / "history.jsonl").read_bytes()
    with pytest.raises(ValueError, match="review_attempt_mismatch"):
        kimmizo.task_transition(
            tmp_path,
            task_id,
            "in_progress",
            review_outcome="fix-first",
            review_attempt_id="stale-attempt",
            review_evidence=["stale verdict"],
        )
    assert (task_root / "current.json").read_bytes() == before_current
    assert (task_root / "history.jsonl").read_bytes() == before_history


def test_task_transition_cli_reserves_and_closes_named_review_attempt(
    kimmizo, tmp_path, capsys
):
    """Catches a state-layer reservation that cannot be used safely through the public CLI."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])

    assert kimmizo.main(
        [
            "task-transition",
            "--target",
            str(tmp_path),
            "--task-id",
            task_id,
            "--state",
            "review_ready",
            "--review-attempt-id",
            "cli-attempt-1",
            "--json",
        ]
    ) == 0
    reserved = json.loads(capsys.readouterr().out)
    assert reserved["assurance"]["active_review_attempt"] == "cli-attempt-1"
    assert reserved["assurance"]["review_budget"]["used"] == 1

    assert kimmizo.main(
        [
            "task-transition",
            "--target",
            str(tmp_path),
            "--task-id",
            task_id,
            "--state",
            "in_progress",
            "--review-outcome",
            "unusable",
            "--review-attempt-id",
            "cli-attempt-1",
            "--review-evidence",
            "reviewer returned no verdict",
            "--json",
        ]
    ) == 0
    closed = json.loads(capsys.readouterr().out)
    assert closed["assurance"]["active_review_attempt"] is None
    assert closed["assurance"]["review_budget"]["used"] == 1


def test_review_reservation_rejects_a_premature_verdict_without_writing(kimmizo, tmp_path):
    """Catches review evidence being supplied before the attempt is durably reserved."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])
    task_root = tmp_path / ".kimmizo" / "runtime" / "tasks" / task_id
    before_current = (task_root / "current.json").read_bytes()
    before_history = (task_root / "history.jsonl").read_bytes()

    with pytest.raises(ValueError, match="review_reservation_invalid"):
        kimmizo.task_transition(
            tmp_path,
            task_id,
            "review_ready",
            review_attempt_id="attempt-with-verdict",
            review_outcome="fix-first",
            review_evidence=["premature verdict"],
        )

    assert (task_root / "current.json").read_bytes() == before_current
    assert (task_root / "history.jsonl").read_bytes() == before_history


def test_validator_rejects_accepted_review_outside_complete_state(kimmizo, tmp_path):
    """Catches hand-edited state replaying an accepted attempt before completion."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    verified = kimmizo.task_transition(
        tmp_path, task_id, "parent_verified", evidence=["parent-1"]
    )
    verified["assurance"]["review_budget"]["used"] = 1
    verified["assurance"]["review_attempts"] = [
        {
            "attempt_id": "forged-accept",
            "state": "closed",
            "outcome": "accept",
            "evidence": ["forged evidence"],
        }
    ]
    verified["assurance"]["review"]["accepted"] = True
    verified["assurance"]["review"]["evidence"] = ["forged evidence"]
    verified["evidence"]["review"] = ["forged evidence"]

    with pytest.raises(ValueError, match="state_invariant"):
        kimmizo._load_v2_package().validate_task(verified)


def test_final_reserved_review_can_accept_at_the_hard_budget_limit(kimmizo, tmp_path):
    """Catches reserve-before-dispatch accidentally rejecting a valid final-budget acceptance."""
    started = kimmizo.task_start(
        tmp_path,
        "ตรวจ architecture สำคัญ",
        model_catalog=model_catalog(),
        execution_mode="solo-reviewed",
        assurance_level="reviewed",
    )
    task_id = started["task"]["identity"]["task_id"]
    kimmizo.task_transition(tmp_path, task_id, "in_progress")
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-1"])
    first = kimmizo.task_transition(
        tmp_path, task_id, "review_ready", review_attempt_id="attempt-1"
    )
    assert first["assurance"]["review_budget"]["used"] == 1
    kimmizo.task_transition(
        tmp_path,
        task_id,
        "in_progress",
        review_outcome="unusable",
        review_attempt_id="attempt-1",
        review_evidence=["no verdict"],
    )
    kimmizo.task_transition(tmp_path, task_id, "checkpoint_ready")
    kimmizo.task_transition(tmp_path, task_id, "parent_verified", evidence=["parent-2"])
    final = kimmizo.task_transition(
        tmp_path, task_id, "review_ready", review_attempt_id="attempt-2"
    )
    assert final["assurance"]["review_budget"]["used"] == 2

    complete = kimmizo.task_transition(
        tmp_path,
        task_id,
        "complete",
        review_accepted=True,
        review_attempt_id="attempt-2",
        review_evidence=["accepted final candidate"],
    )
    assert complete["execution"]["state"] == "complete"
    assert complete["assurance"]["review_exhausted"] is False
    assert complete["assurance"]["review_attempts"][-1]["outcome"] == "accept"


def test_task_lock_never_steals_an_old_live_lock(kimmizo, tmp_path):
    """Catches mtime-only stale-lock deletion admitting two state writers."""
    v2 = kimmizo._load_v2_package()
    root = tmp_path / "task"
    root.mkdir()
    lock = root / ".state.lock"
    lock.write_text("pid=live", encoding="utf-8")
    old = lock.stat().st_mtime - 3600
    import os

    os.utime(lock, (old, old))

    with pytest.raises(TimeoutError):
        with v2.task_state._exclusive_task_lock(root, timeout_seconds=0.05):
            pass
    assert lock.read_text(encoding="utf-8") == "pid=live"


def test_task_state_rejects_symlinked_project_runtime_root(kimmizo, tmp_path):
    """Catches canonical task writes escaping through a project-local symlink/junction parent."""
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    try:
        (project / ".kimmizo").symlink_to(outside, target_is_directory=True)
    except OSError:
        import os
        import subprocess

        if os.name != "nt":
            pytest.skip("directory symlinks are unavailable")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(project / ".kimmizo"), str(outside)],
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip("directory junctions are unavailable")
    try:
        with pytest.raises(ValueError, match="path_escape"):
            kimmizo.task_start(project, "งานสถานะ", model_catalog=model_catalog())
        assert not (outside / "runtime" / "tasks").exists()
    finally:
        import os

        link = project / ".kimmizo"
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            os.rmdir(link)


def test_task_state_rejects_linked_current_and_history_leaf_files(kimmizo, tmp_path):
    """Catches cross-project task reads or history copying through linked leaf files."""
    import os

    started = kimmizo.task_start(tmp_path / "project", "งานสถานะ", model_catalog=model_catalog())
    task_id = started["task"]["identity"]["task_id"]
    task_root = tmp_path / "project" / ".kimmizo" / "runtime" / "tasks" / task_id
    current = task_root / "current.json"
    history = task_root / "history.jsonl"

    outside_current = tmp_path / "outside-current.json"
    outside_current.write_bytes(current.read_bytes())
    current.unlink()
    os.link(outside_current, current)
    with pytest.raises(ValueError, match="unsafe_link"):
        kimmizo.task_status(tmp_path / "project", task_id)
    assert outside_current.read_bytes() == current.read_bytes()

    current.unlink()
    current.write_text(json.dumps(started["task"], ensure_ascii=False), encoding="utf-8")
    outside_history = tmp_path / "outside-history.txt"
    outside_history.write_text("PRIVATE EXTERNAL CONTENT\n", encoding="utf-8")
    history.unlink()
    os.link(outside_history, history)
    with pytest.raises(ValueError, match="unsafe_link"):
        kimmizo.task_transition(tmp_path / "project", task_id, "in_progress")
    assert outside_history.read_text(encoding="utf-8") == "PRIVATE EXTERNAL CONTENT\n"
    assert "PRIVATE EXTERNAL CONTENT" not in current.read_text(encoding="utf-8")


def test_task_state_rejects_state_copied_under_a_different_task_id(kimmizo, tmp_path):
    """Catches valid task-B state being read or mutated through task-A's directory."""
    project = tmp_path / "project"
    first = kimmizo.task_start(project, "งาน A", model_catalog=model_catalog())
    second = kimmizo.task_start(project, "งาน B", model_catalog=model_catalog())
    first_id = first["task"]["identity"]["task_id"]
    second_id = second["task"]["identity"]["task_id"]
    tasks = project / ".kimmizo" / "runtime" / "tasks"
    first_root = tasks / first_id
    second_root = tasks / second_id
    (first_root / "current.json").write_bytes((second_root / "current.json").read_bytes())
    (first_root / "history.jsonl").write_bytes((second_root / "history.jsonl").read_bytes())

    with pytest.raises(ValueError, match="identity_mismatch"):
        kimmizo.task_status(project, first_id)
    with pytest.raises(ValueError, match="identity_mismatch"):
        kimmizo.task_transition(project, first_id, "in_progress")

    assert kimmizo.task_status(project, second_id)["identity"]["task_id"] == second_id


def test_task_state_rejects_same_task_id_copied_from_another_project(kimmizo, tmp_path):
    """Catches project-A state being accepted by project B when the task UUID is reused."""
    task_id = "00000000-0000-4000-8000-0000000000b1"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    for project, project_id in (
        (project_a, "00000000-0000-4000-8000-0000000000a1"),
        (project_b, "00000000-0000-4000-8000-0000000000b2"),
    ):
        manifest = project / ".kimmizo" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
        kimmizo.task_start(
            project,
            "งานที่ใช้ UUID เดียวกัน",
            task_id=task_id,
            model_catalog=model_catalog(),
        )

    tasks_a = project_a / ".kimmizo" / "runtime" / "tasks" / task_id
    tasks_b = project_b / ".kimmizo" / "runtime" / "tasks" / task_id
    tasks_b.joinpath("current.json").write_bytes(tasks_a.joinpath("current.json").read_bytes())
    tasks_b.joinpath("history.jsonl").write_bytes(tasks_a.joinpath("history.jsonl").read_bytes())

    with pytest.raises(ValueError, match="project_identity_mismatch"):
        kimmizo.task_status(project_b, task_id)
    with pytest.raises(ValueError, match="project_identity_mismatch"):
        kimmizo.task_transition(project_b, task_id, "in_progress")


def test_task_state_rejects_in_project_task_directory_alias(kimmizo, tmp_path):
    """Catches task-A resolving to task-B through an in-project junction or symlink."""
    import os
    import subprocess

    project = tmp_path / "project"
    second = kimmizo.task_start(project, "งาน B", model_catalog=model_catalog())
    second_id = second["task"]["identity"]["task_id"]
    first_id = "00000000-0000-4000-8000-0000000000a1"
    tasks = project / ".kimmizo" / "runtime" / "tasks"
    alias = tasks / first_id
    target = tasks / second_id
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("directory symlinks are unavailable")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip("directory junctions are unavailable")
    try:
        with pytest.raises(ValueError, match="path_alias"):
            kimmizo.task_status(project, first_id)
    finally:
        if alias.is_symlink():
            alias.unlink()
        elif alias.exists():
            os.rmdir(alias)

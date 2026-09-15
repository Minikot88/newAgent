"""Kimweaver v2, shipped as a local stdlib-only package beside Kimmizo v1."""

from . import capsule
from .capsule import capsule_status, materialize_capsule, rollback_capsule
from .contracts import SCHEMA, new_task_from_plan, validate_new_task, validate_task
from .legacy import build_route_plan, validate_legacy_compatibility
from .task_state import create_task, read_task, transition_task, validate_persisted_task

__all__ = [
    "SCHEMA",
    "build_route_plan",
    "capsule",
    "capsule_status",
    "create_task",
    "materialize_capsule",
    "new_task_from_plan",
    "read_task",
    "rollback_capsule",
    "transition_task",
    "validate_legacy_compatibility",
    "validate_new_task",
    "validate_persisted_task",
    "validate_task",
]

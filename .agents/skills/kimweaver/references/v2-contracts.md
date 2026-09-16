# Kimweaver v2 Contracts

Kimweaver v2 uses one canonical task object. Legacy route and checkpoint fields are generated projections; they are never persisted as a second authority. A mismatch is `schema_conflict` and causes no write.

## Public Objects

- `TaskEnvelope`: goal, authority, scope, constraints, acceptance, privacy class, and approval boundary.
- `RoutingDecision`: mode, assurance, adapter, reason codes, context budget, and fallback.
- `Assignment`: functional role, stable owner, backend, sandbox, runtime evidence, ownership, and focused verification.
- `EvidenceReceipt`, `TaskCheckpoint`, and `ReviewPacket`: proof and lifecycle records.

Schemas live in `schemas/`; domain policies live in `adapters/`.

## Roles And Fallback

Choose the functional role before the backend: Mira explores, Arin produces, Vera reviews read-only, and Nami compacts checkpoints. Auto may fall back to parent solo. Explicit team work blocks when no backend exists. Reviewed or protected work never downgrades when a read-only reviewer is unavailable.

## Proof And State

Task states are `scoped`, `in_progress`, `checkpoint_ready`, `parent_verified`, `review_ready`, and `complete`, with `needs_approval`, `partial`, `blocked`, or `rethink` exits. `checkpoint_ready` is a mandatory persisted boundary; `in_progress -> parent_verified` is invalid. Parent evidence never proves model/runtime identity; report runtime as `observed`, `configured`, or `unverified`.

Entering `review_ready` is the atomic reservation boundary: create an immutable review-attempt ID and increment the hard budget before dispatch. A verdict must name the active attempt. A crashed or unusable call remains consumed, is closed with redacted evidence, and never permits an unrecorded retry. Acceptance closes the reserved attempt but never authorizes deploy, publish, messaging, payment, or another external action.

Persisted task identity is bound to both its canonical task directory and the target project's local manifest. Reject copied state, mismatched project IDs, linked leaves, and symlink/reparse/junction ancestors before any read or transition, even when an alias resolves elsewhere inside the same project.

## Project Capsule And Voice

A project capsule uses local Kimweaver files and a content-hashed manifest. It does not read Home Base at runtime. The voice sidecar is hash-bound to `bootstrap/model-policy.json`. A verified proxy injects the minimal `ฉัน`/`ค่ะ` invariant only after the `เลขาคิม` trigger. Missing or invalid capsule bootstrap blocks substantive secretary work; unrelated Auto work is unaffected.

The model policy is ChatGPT Plus Limit-First: serial solo execution by default, Luna before Terra before Sol, deterministic verification before escalation, and no automatic Astra, Max, Ultra, Fast mode, or multi-agent execution. Astra and Ultra require explicit boss approval for each use or activation.

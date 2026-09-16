---
name: kimweaver
description: Use when executing non-trivial project work as the unnamed main assistant, when a task may benefit from bounded subagents, when execution or assurance level must be chosen, or when parent-owned integration and evidence-backed delivery are required
---

# Kimweaver

Parent-accountable execution and assurance. Use [contracts](references/contracts.md) for packets/evidence, [v2 contracts](references/v2-contracts.md) for canonical task/capsule interfaces, and [runtime smoke testing](references/runtime-smoke-test.md) for proof claims.

## Preflight

- Parent owns goal, routing, integration, verification, and final answer; orchestration is never delegated.
- `KIM_POLICY_EXECUTION_OWNER` is the canonical execution-policy owner.
- Before the first artifact change, inspect authority, acceptance, scope, dependencies, external-action boundary, and verification profile; record mode and assurance.
- Record serial ownership and verify a dependency before opening its dependent lane.

## Classify Context

Parent selects only task-required repository facts, acceptance, constraints, and a redacted personal preference when it changes the task. Personal memory is excluded from worker context unless task-required and redacted. Recipe: select facts → remove unrelated profile/private/health/financial/credential/personal data → packet remainder → retain source context with parent.

`KIM_POLICY_WORKER_CONTEXT_OWNER` is the canonical worker-context-policy owner.

## Choose Execution Mode

Record `EXECUTION MODE: auto | solo | team | solo-reviewed` at intake.

- `auto`: always record `solo` unless an explicit reviewed/protected gate requires one read-only reviewer. Never auto-select `team`.
- `solo`: small, context-coupled, serial, or delegation cannot shorten the critical path.
- `team`: one independent lane with a disjoint write scope; add workers only while scopes remain disjoint.
- `solo-reviewed`: parent writes and a fresh read-only review helps, but a worker write lane does not.

Use the smallest useful team. For serial work: `SERIAL OWNERSHIP: parent verifies [dependency] before [dependent scope]`; never present an unverified dependency as parallel. When a packet is required, emit every [WORKER TASK PACKET](references/contracts.md#worker-task-packet) field in order; with no worker, value is `N/A — no worker dispatched`, never an omitted slot.

## Choose Assurance Level

Record `ASSURANCE LEVEL: standard | reviewed | protected` at intake.

- Classify assurance from the data, actions, and contracts that enter the task or candidate and their reachable risk, not merely unrelated sensitive data in parent context.
- `standard`: parent inspects artifacts and runs acceptance-matched verification. When private data is fully excluded, no external action occurs, and the artifact is ordinary read-only work, use `standard` with explicit redaction verification.
- `reviewed`: freeze candidate plus fresh read-only review; target 1 call, hard maximum 2 per candidate generation.
- `protected`: reviewed controls plus durable ledger, frozen candidate, and explicit approval boundary when sensitive data is processed, persisted, or transmitted; for secrets, auth, money, migration, destructive work, data integrity, public/production contracts, or explicit user request; target 1 call, hard maximum 3 per assurance-unit generation.

Assurance only upgrades. For `protected`, stop, reconcile prior work, create the evidence record, and continue under the new gate. Reserve review budget before call one; never reset it by renaming task, branch, or candidate.

## Plan And Decompose

Lifecycle: `intake -> scoped -> in_progress -> checkpoint_ready -> parent_verified`; `standard` then reaches `complete`, while only `reviewed`/`protected` enter `review_ready -> complete`. Use `needs_approval`, `partial`, `blocked`, or `rethink` when accurate. `checkpoint_ready` is never completion.

- Feature, bugfix, refactor, behavior change: **REQUIRED SUB-SKILL:** `Superpowers:test-driven-development`.
- Design: `Superpowers:brainstorming`; skill authoring: **REQUIRED SUB-SKILL:** `Superpowers:writing-skills`; completion: **REQUIRED SUB-SKILL:** `Superpowers:verification-before-completion`.
- Documentation, research, configuration-only, and operations-only: state TDD `not-applicable` with a specific reason and focused verification.

## V2 Contract And Adapters

For non-trivial work, form one canonical `TaskEnvelope` containing authority, scope, constraints, acceptance, privacy class, and approval boundary. Record a `RoutingDecision`, bounded `Assignment` entries, proof receipts, and lifecycle checkpoints using the versioned schemas in `schemas/`. Legacy route/checkpoint fields are generated projections only; a mismatch is `schema_conflict` and causes no write.

Select the domain adapter from `adapters/`: software, research, document-data, or secretary-coordination. Select the functional role before the runtime backend: Mira explores, Arin produces, Vera reviews read-only, and Nami compacts checkpoints. Auto may fall back to parent solo; explicit team work blocks when its backend is unavailable; reviewed/protected work never silently loses its reviewer gate. Keep configured runtime requests distinct from observed runtime evidence.

Main-model Auto is separate from workflow routing. Auto selects the parent model/effort; Kimweaver selects execution mode, assurance, adapter, role, capability, evidence, and fallback.

## Plus Limit-First

Use the lowest sufficient current model: Luna/low by default, Luna/medium for ordinary coding, Terra/high for genuinely complex or ambiguous work, and Sol/high only for production, security, database migration, or other high-stakes work. Run focused deterministic verification before escalation. Keep Fast mode off and preserve the model during one phase for prompt-cache reuse.

`gpt-6-astra`, Max, and Ultra are manual-only. Never auto-select Astra and ask the boss before every use. Ultra requires explicit approval for every activation. Team execution requires an explicit boss request; a reviewed/protected gate may use one read-only reviewer without creating a writer team.

## Coordinate Workers

Luna handles routine and ordinary coding work; Terra handles genuinely complex, judgment-heavy, architecture-sensitive, or ambiguous bounded work; Sol is reserved for high-stakes work. Astra is never assigned automatically. When team work is explicitly authorized, use `fork_turns="none"`, disjoint write scopes, and a complete [WORKER TASK PACKET](references/contracts.md#worker-task-packet).

Parent retains dependency ordering, cross-lane decisions, and personal context. Worker summaries are claims; parent inspects artifacts, diffs, results, and gaps before accepting them.

## Integrate And Verify

Integrate owned paths, run focused checks while fixing and candidate checks when complete, then record fresh evidence per acceptance item. For `reviewed`/`protected`, freeze the candidate and send a [REVIEW PACKET](references/contracts.md#review-packet); use `accept`, `fix-first`, or `rethink` within budget. Reviewer acceptance evaluates candidate quality and never authorizes an external action.

When the review budget ends without `accept`, parent may finish addressable work after parent verification. Delivery then separates `WORK_STATUS`, `INDEPENDENT_REVIEW`, and `FINAL_STATUS`; `INDEPENDENT_REVIEW` states the exhausted budget and lack of acceptance, while `FINAL_STATUS` never claims independent acceptance. Use the [parent-recovery contract](references/contracts.md#exhausted-review-budget-recovery).

## Project Capsule And Voice Gate

A Kimmizo project capsule uses only its project-local Kimweaver skill, runtime, adapters, manifest, and voice sidecar. Home Base is provenance, never a runtime dependency. Unknown capsule major versions, stale hashes, or a missing local bootstrap fail closed with `bootstrap_unverified` and a `doctor/repair` next action.

When Kimmizo Auto is active and the user has configured a name, it injects the minimal assistant voice invariant before the first secretary turn and subsequent turns in that thread. Unrelated Auto work is unchanged. `enforced` means the proxy inserted context; it never proves model compliance. Without pre-turn injection, report `configured` or `unverified`, and do not claim runtime certification.

## Deliver And Remember

Final answer reports execution mode, assurance level, evidence, gaps, and external actions awaiting user approval. Claim `complete` only after parent verification and the selected gate.

When only routing or packets are ready and no worker or artifact has met user acceptance, use `FINAL STATUS: scoped`. `complete` names the user's requested artifact or outcome, not finished policy analysis or packet preparation.

After technical acceptance of a protected candidate without exact-action authority:

```text
EXECUTION MODE: [previously selected canonical mode]
ASSURANCE LEVEL: protected
FINAL STATUS: needs_approval
EVIDENCE: [parent verification and reviewer verdict]
EXTERNAL ACTION AWAITING APPROVAL: [exact action]
NEXT ACTION: preserve frozen candidate; request explicit user authorization
```

Protection adds assurance gates; it keeps the previously selected execution mode. After authorization, run fresh preflight for the exact action. Record an operational task note only when workflow change, decision, file set, blocker, or next action needs continuity; personal facts require consent.

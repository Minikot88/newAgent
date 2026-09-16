# Kimweaver Contracts

## Contents

- Packet completion rule
- WORKER TASK PACKET
- REVIEW PACKET
- Protected assurance ledger
- REPOSITORY VERIFICATION PROFILE
- Kimweaver v2 object authority

## Packet Completion Rule

Templates use bracketed instructions so the parent can adapt them. An instantiated packet is valid only when every required label has a concrete value for the task. Instantiated packets reject full-line bracket instructions and unresolved `{{...}}`, `TBD`, `TODO`, and `FIXME` markers.

## WORKER TASK PACKET

```text
WORKER TASK PACKET
ROLE
[Terra or Luna role and task-specific responsibility]

EXECUTION MODE
[team]

ASSURANCE LEVEL
[standard, reviewed, or protected]

OBJECTIVE
[bounded, observable result]

OWNERSHIP
[paths, modules, or read-only evidence the worker owns]

DO NOT TOUCH
[paths, systems, decisions, and external actions outside scope]

CONTRACTS
[interfaces, source-of-truth documents, inputs, outputs, and dependencies]

CONSTRAINTS
[time, privacy, no-external-action, compatibility, and scope constraints]

ACCEPTANCE
[observable completion conditions]

SKILLS / TDD APPLICABILITY
[required skill, or not-applicable with a task-specific reason]

FOCUSED VERIFICATION
[exact commands, inspection, or evidence to run before return]

RETURN FORMAT
[Return exactly the schema below.]

STATUS
[complete | partial | blocked | rethink]

CHANGES / FINDINGS
[changed paths and concise findings; state read-only when no files changed]

VERIFIED
[commands/inspections run and their outcomes]

JUDGMENT CALLS
[decisions, assumptions, or escalations that need parent attention]

GAPS
[remaining acceptance, unknowns, risks, or none]
```

The parent completes every label before dispatch. For read-only work, `CHANGES / FINDINGS` reports findings and explicitly says that no files were changed.

## REVIEW PACKET

```text
REVIEW PACKET
ATTEMPT RESERVATION
[immutable attempt ID and durable reserved state created before dispatch]

CANDIDATE IDENTITY
[immutable candidate ID, base, complete changed-path list, content hashes, and freeze state]

ACCEPTANCE
[candidate acceptance criteria being assessed]

PARENT EVIDENCE
[fresh focused/candidate checks, artifact/diff inspection, and evidence locations]

REVIEW BUDGET / CALL
[assurance-unit or candidate generation, reserved call number, hard cap, and calls remaining]

GAPS
[known gaps, deviations, unproved runtime behavior, and review focus]

USER-AUTHORIZATION STATE
[not required | exact external action awaiting approval | exact action explicitly authorized]

VERDICT
[choose exactly: accept | fix-first | rethink]
```

The candidate identity and attempt ID remain immutable while review is open. A verdict must name the active attempt. A reviewer evaluates the frozen candidate and returns the verdict; it does not implement changes or authorize any external action.

## Protected Assurance Ledger

For `protected` work, select an existing repository phase or evidence log first. If none exists, use `docs/kimweaver/assurance/เลขาคิม-home-base-kimweaver-phase-a/` as the repository ledger location.

Before every reviewer call, create a durable reviewer-attempt reservation in that ledger containing the assurance-unit identity, immutable candidate identity, call number, budget cap, reservation state, and redacted evidence reference. A reservation is consumed by the call and remains part of the record; renaming a task, branch, or candidate does not create a new budget.

The ledger stores only hashes, decisions, redacted evidence, and an authorized private-location pointer when sensitive evidence is necessary. It never stores raw secrets, credentials, financial data, or personal data. Freeze the candidate before parent verification and review; content or behavior changes invalidate that candidate and require a new freeze, parent verification, and a review call within the remaining budget.

## Exhausted Review Budget Recovery

When the reviewer budget ends without `accept`, the parent may finish addressable work after parent verification. The final delivery must separate the work result from independent review and must not claim independent acceptance:

```text
WORK_STATUS
[addressable work completed, partial, blocked, or rethink; parent evidence]

INDEPENDENT_REVIEW
[budget exhausted without accept; calls used, final verdicts, and remaining review gap]

FINAL_STATUS
[complete, partial, blocked, rethink, or needs_approval without claiming independent acceptance]
```

## REPOSITORY VERIFICATION PROFILE

```text
REPOSITORY VERIFICATION PROFILE
AUTHORITY INSPECTED
[AGENTS.md, acceptance source, CI/workflow, package/task scripts, and runtime entrypoints used]

FOCUSED_CHECKS
[checks run during implementation and fix loops]

CANDIDATE_CHECKS
[checks run for the complete candidate, including scoped untracked files]

RUNTIME_CHECKS
[runtime behavior needed to meet acceptance, or not-applicable with reason]

EXTERNAL_CHECKS
[external checks and their explicit approval requirement]

CANDIDATE BOUNDARY
[changed paths, generated artifacts, untracked scope, and frozen identity]

PROFILE INVALIDATION
[authority, acceptance, CI/workflow, scripts, Compose/runtime entrypoint, or command changes that require rebuilding this profile]
```

Use focused checks while changing work, candidate checks only when the integrated candidate is ready, and external checks only after the corresponding authorization exists.

## Kimweaver v2 Object Authority

The schemas in `../schemas/` define `TaskEnvelope`, `RoutingDecision`, `Assignment`, `EvidenceReceipt`, `TaskCheckpoint`, and `ReviewPacket`. The domain adapters in `../adapters/` supply acceptance and verification defaults without changing project authority.

Canonical v2 state is the only writable task authority. Legacy fields are derived when serializing compatibility output. If supplied legacy and v2 values disagree, return `schema_conflict` before opening a task path or appending history.

Proof labels are `implemented`, `statically_verified`, `runtime_observed`, and `not_yet_proved`. Parent verification is evidence about the artifact; it does not promote a configured model, effort, sandbox, or worker identity to observed runtime evidence.

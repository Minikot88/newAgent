# Kimweaver Runtime Smoke Test

## Proof State Labels

```text
Implemented
[The artifact or contract exists.]

Statically verified
[A validator, unit test, or configured-file check observed the required structure.]

Runtime observed
[A fresh task exercised the behavior and preserved the resulting evidence.]

Not yet proved
[The required evidence has not been observed; state the missing check.]
```

Configuration is not runtime observation. Keep configured model/effort metadata separate from any observed task context, tool result, or agent return.

## Current-Task Static Checks

During this Phase A task, run the focused validator unit tests and the workspace validator. These are static evidence for the Kimweaver documents and configured agent definitions; they do not prove that a new task loaded or followed the package.

```powershell
python -m unittest tests.test_validate_kimweaver -v
python scripts/validate_kimweaver.py --root . --json
```

## Configured Agent Checks

Inspect the local agent definitions, their declared roles, and their static validation results. Record them as configured evidence only. Do not claim that a configured model, model effort, or packet definition was observed at runtime until a new task returns usable evidence.

## New-Task Requirement After Global Install

Global installation is outside Phase A. After an authorized global install, open a new task so the runtime discovers the installed skill and agent definitions afresh. Repeat the canaries below in that new task; a task that existed before installation is not a runtime-discovery check.

## Canary Set

1. **KIM-CANARY-01 — greeting and voice gate:** run a greeting-only `เลขาคิม` task with `solo` / `standard`; verify a concise `ฉัน`/`ค่ะ` reply, no memory payload, an `enforced` proxy receipt when pre-turn injection exists, and an unrelated Auto control that receives no secretary context.
2. **KIM-CANARY-02 — Terra judgment lane:** run a bounded complex or judgment-heavy task through the Terra lane. Verify `fork_turns="none"`, a complete redacted packet, disjoint ownership, actual artifact inspection, and the worker return schema.
3. **KIM-CANARY-03 — Luna mechanical lane:** run a bounded narrow or mechanical task through the Luna lane. Verify the same packet, ownership, inspection, and return-schema controls for that lane.
4. **KIM-CANARY-04 — personal context boundary:** run a task that needs personal context and verify that it remains parent-owned, is redacted from any worker packet, and is not persisted or transmitted without the required approval.
5. **KIM-CANARY-05 — protected approval boundary:** freeze a protected candidate, reserve the review call, obtain `accept`, `fix-first`, or `rethink`, and prove that technical acceptance did not execute an external action without explicit user authorization.

Each canary must run in a fresh task after authorized install/reload. Capture the task identifier, declared execution mode and assurance level, packet/redaction evidence, verification outputs, reviewer result, remaining review budget, and gaps. Preserve only redacted evidence or approved private-location pointers. Do not use `runtime-certified` until all five canaries have passed.

## Claim Gate

Use `Implemented` after files exist, `Statically verified` after the relevant validator/tests pass, and `Runtime observed` only after all applicable new-task canaries pass. Do not use the phrase `runtime-certified` until every required new-task check has passed and the evidence states any remaining limits honestly.

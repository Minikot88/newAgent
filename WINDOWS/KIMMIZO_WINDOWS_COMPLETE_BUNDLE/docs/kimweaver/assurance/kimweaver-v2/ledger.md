# Kimweaver v2 Assurance Ledger

- Assurance unit: `kimmizo-setup/kimweaver-v2/unified-core`
- Reopen generation: `0`
- Execution mode: `team`
- Assurance level: `protected`
- Unit status: `parent_verified; rollout_needs_approval`
- Review budget: target `1`, hard maximum `3`, used `3`
- Kimmizo base: `bfd43f818ec809ca0e1ec74c7c36c4c4f2d4f7de`
- Home Base base: `662d8fa618aeaf669d1b102cb5345d20d8377a84`
- Candidate status: frozen after exhausted-budget parent recovery; no independent accept
- Frozen candidate ID: `sha256:d8a9afb20f7f0b34105ea6ccf911afd023976c42609f5c14f38e19200f8be973`
- Candidate manifest: `docs/kimweaver/assurance/kimweaver-v2/candidate-manifest.json`
- Candidate manifest SHA-256: `75702107780f2b35ba9e8430265f31c1ea006ac894e7a11f2df4f652e31954dd`
- Parent adversarial ready: `yes`
- Review ready: `no` (hard budget exhausted)

## Objective

Evolve the existing Kimweaver package into the canonical v2 workflow core and make Kimmizo Setup its standalone, project-local distribution and migration adapter.

## Scope

- Kimmizo v2 contracts, task state, routing, capsule, compatibility CLI, templates, Auto voice gate, tests, and validation.
- Canonical Home Base Kimweaver skill/contracts/package validation under an explicit path allowlist.
- Temporary target-project installation, migration, rollback, and portability rehearsal.

## Protected Boundaries

- Preserve project-owned managed content, agent identities, profiles, receipts, memory, knowledge, checkpoints, and unrelated dirty work.
- Store no raw secrets, credentials, financial data, health data, or personal profile data in task packets or assurance artifacts.
- Do not update the globally installed Kimweaver copy, create a real Codex task, migrate another real project, commit, push, or publish without separate exact authorization.

## Verification Profile

- Focused: behavior-specific pytest/unittest targets and Kimmizo repository validator.
- Candidate: complete Kimmizo pytest suite, repository validator, Home Base unittest suite, Home Base validator, frozen snapshot parity, and temporary migration/rollback rehearsal.
- Runtime: five post-install canaries remain `not_yet_proved` until an authorized installed-copy upgrade and fresh tasks.
- External: Home Base writes require filesystem approval; global installed-copy upgrade and real-project migration are not authorized by this implementation request.

## Evidence Log

- 2026-08-27 intake: Kimmizo worktree clean; validator passed; base recorded.
- 2026-08-27 intake: scoped Home Base Kimweaver paths clean; unrelated Home Base dirty/untracked paths excluded.
- 2026-08-27 RED evidence: the prior task produced a male Thai first response before Persona loading, demonstrating the voice-bootstrap failure.
- 2026-08-27 baseline: Home Base `unittest discover` passed `111/111`.
- 2026-08-27 baseline: Kimmizo pytest passed `55/58`; the three expected failures are setup/CLI readiness assertions coupled to unavailable ambient host-feature probes.
- 2026-08-27 GREEN: the three SkipInstall/setup/CLI regressions passed after missing Tier-0 prerequisites were scoped to real install attempts.
- 2026-08-27 RED side effect: the capability CLI test exposed that `--target` was ignored and created a fake global approval receipt. Parent verified it was newly created at the test timestamp, bound deletion to its exact path/length/SHA-256, removed it, and confirmed the path no longer exists. The CLI test was then isolated so future RED runs cannot write global state.
- 2026-08-27 GREEN: capability approval receipts are project-local, CLI forwards the target, doctor reports valid adopted receipts, and focused approval tests passed `3/3`.
- 2026-08-27 Home Base RED: v2 schema/adapter/bootstrap validator APIs were absent and failed `3/3` focused tests for the expected reason.
- 2026-08-27 Home Base GREEN: six schemas, four adapters, hash-bound model/voice bootstrap, v2 reference, skill/contracts/runtime guidance, validator integration, and fixture support passed the complete Home Base suite `114/114`; workspace validator reported zero findings.
- 2026-08-27 Auto GREEN: parent reran `10/10` focused tests, compiled production C# plus the checked-in scope harness with .NET Framework csc, and observed `AUTO_SCOPE_HARNESS_PASS` in an isolated temporary directory.
- 2026-08-28 writing-skills pressure evidence: no-bootstrap control produced male `ผม/ครับ` in `5/5` samples (four fresh Luna samples plus the original live failure). With the project-local v2 bootstrap invariant, `5/5` fresh Luna samples used `ฉัน/ค่ะ` before any Persona read or tool call.
- 2026-08-28 capsule parent evidence: integrated v2/Auto/capsule/approval focused suite passed `34/34`; complete Kimmizo suite passed `89/89` before the final unowned-path regression; validator passed with `18` JSON files and `5` skills; isolated copied-runtime rehearsal returned capsule status `healthy` without importing the source package.
- 2026-08-28 capsule hardening RED/GREEN: first install previously overwrote a pre-existing unowned `.agents/skills/kimweaver`; the new guard failed the regression as expected, then passed while preserving exact user bytes and creating no active v2 manifest/voice sidecar.
- 2026-08-28 root-cause correction: the unowned-path helper was initially inserted inside `_active_manifest_if_parseable`, making its manifest return unreachable. The idempotence and rollback regressions exposed this; the function boundary was restored, the three focused regressions passed, and the complete Kimmizo suite passed `90/90`.
- 2026-08-28 installed-copy preflight: read-only validator reports the expected `16` v2 upgrade findings (three changed core documents and thirteen new adapter/bootstrap/reference/schema files). Global v1 remains active; no global write or runtime-certification claim was made.
- 2026-08-28 temporary Home Base package rehearsal: dry-run `planned`, isolated install `complete`, installed-copy validation `valid` with `0` findings; the GUID temp root was verified and removed afterward.
- 2026-08-28 post-adversarial GREEN: complete Kimmizo suite passed `115/115`; complete Home Base suite passed `115/115`; both repository validators reported zero findings; Auto C#/policy tests passed `14/14`. The capsule focused run passed `20` with one unavailable symlink sample, then the replacement Windows-junction check passed and was included in the complete suite.
- 2026-08-28 final portability rehearsal: setup `ready`, capsule `active`, copied stdlib runtime reported `healthy` in isolated Python mode, first-install rollback returned `removed`, and the v1 manifest remained present.
- 2026-08-28 final parity: Home Base Kimweaver source and Kimmizo vendor matched raw SHA-256 for `16/16` files with no extras; final temporary Home Base install was `complete` and installed-copy validation was `valid` with zero findings.
- 2026-08-28 review call 2 verdict: `fix-first` with six blockers covering target-authoritative capsule identity, linked/partial setup, mixed review routing, reserve-before-dispatch review calls, and task directory/project identity.
- 2026-08-28 review-call-2 closure: complete capsules copied into another authoritative project fail status/update; missing or malformed v1 authority fails for setup-installed capsules, while direct standalone capsules bind identity to their deterministic target path.
- 2026-08-28 setup closure: authority leaves/parents fail closed; v2 conflicts preflight before v1 publication; caught activation failures compensate v1+v2 publication; rollback uses CAS fingerprints and preserves divergent concurrent edits; setup never steals an existing initial checkpoint lock. Focused setup suite passed `12` with `3` unavailable file-symlink fixtures; hard-link and junction cases passed.
- 2026-08-28 routing/state closure: repository security review maps only to read-only Vera; review attempts reserve an immutable ID and consume budget before dispatch; unusable calls remain consumed; stale verdict IDs fail before write; copied task/project identities and in-project aliases fail closed. Focused task/state suite passed `34/34`.
- 2026-08-28 repair ownership hardening: an extra project file hidden behind an earlier core hash mismatch is detected before repair and preserved; complete capsule suite passed `27/27`.
- 2026-08-28 integrated candidate gates: Kimmizo full suite passed `146` with `3` Windows file-symlink privilege skips; Auto/C# policy suite passed `14/14`; Kimmizo validator passed `19` JSON files and `5` skills; Home Base suite passed `116/116`; Home Base validator reported zero errors; Home/vendor raw parity remained `16/16`.
- 2026-08-28 isolated portability rehearsal: first setup `ready`, capsule `active/healthy`, repeat setup `unchanged`, project-local stdlib runtime `healthy` under `-I -S`, rollback `removed`, v1 manifest preserved, and no Home Base path reference was present.
- 2026-08-28 temporary Home package rehearsal: dry-run `planned`, install `complete`, installed-copy validation `valid` with zero findings. Read-only global validator reports the expected `19` v2 upgrade deltas; no global write occurred.
- 2026-08-28 residual boundary: in-process caught-exception compensation is verified; process-crash atomicity and a malicious ancestor-swap micro-race are not claimed. Lexical target rechecks close the concrete resolve-after-guard junction bypass, and CAS prevents silent concurrent-data loss.

## Review Attempt Reservations

- Attempt ID: `kimweaver-v2-review-1-f3955816`
- Call: `1` of hard maximum `3`
- State: `completed`
- Verdict: `fix-first`
- Blocking findings: Ultra denial intent/re-arm; task-state leaf links; approval receipt leaf links; migration receipt project provenance.

- Attempt ID: `kimweaver-v2-review-2-ff1e8720`
- Call: `2` of hard maximum `3`
- State: `completed`
- Verdict: `fix-first`
- Candidate: `sha256:ff1e8720a9658aa2241adfd879ba32c9d2761fba950b45755b47b9a371150055`
- Blocking findings: target-authoritative capsule identity; linked setup authority files; all-or-nothing setup activation; reviewer-first mixed-intent routing; reserve-before-dispatch review attempts; task-directory identity and in-project alias rejection.
- Reservation primitive: single-parent serialized ledger update in the active task; calls 1 and 2 are completed and no other reservation is active.

- Attempt ID: `kimweaver-v2-review-3-c00ae54e`
- Call: `3` of hard maximum `3`
- State: `completed`
- Verdict: `fix-first`
- Candidate: `sha256:c00ae54e415a768ff61a1fc1f617bd119e716b20831494983531f1314907f9da`
- Reservation primitive: durable single-parent ledger update completed before reviewer dispatch; this call is consumed even if no verdict is returned.
- Blocking findings: foreign explicit standalone capsule identity; mandatory checkpoint bypass; Auto manifest/bootstrap binding; mixed approval/substantive voice bypass; feature/bug text overriding explicit review intent.

## Re-review Closure Matrix

- Ultra denial/re-arm: explicit English/Thai denial precedence, anchored approval intent, forced non-pending downgrade; Auto suite `14/14` and executable harness passed.
- Task-state leaf links: linked/reparse/hard-linked current/history leaves rejected before reads/writes; hard-link and Windows-junction regressions passed.
- Approval receipt leaf links: linked/non-owned receipt leaves rejected and normal receipts atomically replaced; in-project AGENTS hard-link and outside-directory junction regressions passed.
- Migration provenance: receipt includes canonical project ID, first-install preseed is an unowned conflict, and every stage/status/update/archive/rollback validates receipt ID against manifest; cross-project preseed and rehashed mismatch regressions passed.
- Fresh candidate gates after all fixes: Kimmizo `119/119`, Home Base `115/115`, Auto `14/14`, capsule `23/23`, task/approval `27/27`, both validators green, and isolated capsule rehearsal healthy.
- Superseded candidate after call 1 fixes: `sha256:ff1e8720a9658aa2241adfd879ba32c9d2761fba950b45755b47b9a371150055`.
- Reservation primitive: single-parent serialized ledger update in the active task; no reviewer attempt is currently active.

## Review Call 2 Closure Matrix

- Target identity: active/staged/archive/rollback capsule identities bind to the target v1 manifest, or to a deterministic target identity for direct standalone capsules; copied complete capsule regressions pass.
- Setup safety: linked authority files and linked parents reject before writes; v2 preflight precedes v1 publication; caught failures compensate exact setup-owned state, while CAS preserves divergent user edits and reports conflict.
- Role mapping: explicit reviewer intent outranks repository/data production; `review GitHub security` yields only Vera with `read-only` sandbox.
- Review accounting: `review_ready` atomically reserves an immutable attempt and increments `used`; outcome/acceptance must name that attempt; `unusable` closes without refund.
- Task identity: task ID must match its directory and project ID must match target authority; linked/reparse/junction ancestors reject even when resolving inside the project.
- Extra hardening: ownership conflicts outrank repairable hash drift so repair never deletes an unmanifested user file.
- Candidate gates: Kimmizo `146 passed, 3 skipped`, Home Base `116/116`, Auto `14/14`, capsule `27/27`, task/state `34/34`, both validators green, Home/vendor `16/16`, isolated capsule rehearsal healthy, and temporary Home install parity zero findings.
- Call-3 reviewed candidate (superseded by parent recovery): `sha256:c00ae54e415a768ff61a1fc1f617bd119e716b20831494983531f1314907f9da` (`55` files); manifest SHA-256 `be8d90d4ff148cfe01d87c67822ef6845f67fec7581c116ce796d41881df9b84`.

## Exhausted Review Budget Recovery

- Independent review final state: budget `3/3` exhausted; call 3 verdict `fix-first`; no independent `accept` is claimed.
- Standalone identity: foreign explicit project IDs and malformed v1 authority reject before dry-run/target writes; new setup and direct standalone use the same deterministic target UUID while existing v1 IDs remain unchanged.
- Mandatory lifecycle: `in_progress -> parent_verified` is invalid; callers and CLI examples traverse `checkpoint_ready`; focused task/state suite passed `37/37`.
- Auto manifest/voice gate: project voice injection requires a valid active `kimmizo-capsule-v2` manifest, recomputed integrity fields, policy binding, and exact sidecar byte hash. Invalid schema/major/lifecycle/shape/hash blocks; English/Thai mixed approval-plus-work remains substantive; Auto/C# suite passed `16/16`.
- Review intent: explicit review/audit intent outranks feature/bug classification and yields only Vera in a read-only sandbox; feature implementation with a downstream review gate still yields Arin plus Vera.
- Context hardening: the bounded context bridge now returns a deep redacted copy and marks redaction applied; caller-owned input remains unchanged.
- Fresh parent candidate gates: complete Kimmizo suite `154 passed, 3 skipped` (only unavailable Windows file-symlink privilege fixtures; hard-link/junction cases executed), capsule tests included `30/30`, setup transaction `12 passed, 3 skipped`, both repository validators green, Home Base `116/116`, Home/vendor `16/16`, and `diff --check` clean.
- Fresh portability/install gates: Kimmizo setup `ready`, capsule `active`, repeat `unchanged`, isolated stdlib runtime `healthy`, rollback `removed`, v1 manifest preserved, zero Home Base references; Home installer `planned -> complete -> valid` with zero findings.
- Final parent-recovery candidate: `sha256:d8a9afb20f7f0b34105ea6ccf911afd023976c42609f5c14f38e19200f8be973` (`55` files); manifest SHA-256 `75702107780f2b35ba9e8430265f31c1ea006ac894e7a11f2df4f652e31954dd`.
- Rollout boundary: actual global installed copy remains v1 with `19` expected v2 deltas; global upgrade and five fresh-task runtime canaries remain `not_yet_proved` and require separate authorization.
- Residual engineering risk: process-crash atomicity, malicious filesystem ancestor-swap micro-races, and privileged Windows file-symlink execution are not claimed; caught failures, CAS divergence preservation, static link guards, hard links, and junctions are verified.

## Authorized Global Rollout

- Operation ID: `kimweaver-v2-global-rollout-20260828`
- State: `preflight_ready`
- Execution mode: `team`
- Assurance level: `protected`
- Authorization: user explicitly approved the previously enumerated global upgrade, backup, validation, restart/reload, and five fresh-task canaries by replying `ทำเลย`.
- Authorized write targets: `C:/Users/VivoBook/.agents/skills/kimweaver`, Kimmizo Auto under `C:/Users/VivoBook/AppData/Local/Kimmizo/CodexAuto`, and the user-level `CODEX_CLI_PATH` needed to activate the proxy.
- Not authorized: commit, push, publish, deployment, payment, message sending, or migration of any real project.
- Source preflight: Home validator zero findings; Kimmizo validator passed `19` JSON files and `5` skills; frozen `55`-file candidate `d8a9afb20f7f0b34105ea6ccf911afd023976c42609f5c14f38e19200f8be973` has zero hash/size mismatches.
- Installed-copy preflight: read-only validator reports `16` expected v1-to-v2 deltas. Dry-run with `--upgrade` plans one tree upgrade with a timestamped sibling backup and reuses the three already-matching agent TOMLs.
- Existing authority: global `AGENTS.md` already contains the Kimweaver trigger/core pointers and global `config.toml` already contains the enabled agent settings; no manual overwrite or merge is planned.
- Auto preflight: current global Auto is enabled but `degraded`, stores no prompts, and requires a fresh proxy/policy install followed by restart/reload.
- Skill-tree execution receipt: global Kimweaver upgrade completed; `C:/Users/VivoBook/.agents/skills/kimweaver.backup-20260828T032410Z/payload` retains the verified v1 tree, backup matches preflight, destination matches source, and no staging root remains.
- Installed-copy verification: post-upgrade validator status `valid`, finding count `0`; all three agent TOMLs were reused unchanged.
- Auto execution receipt: installed timestamped proxy `codex-kimmizo-auto.20260828032610.exe`; runtime bundle `4/4` current from signed Codex MSIX `26.818.5229.0`; self-test `passed`; policy/voice `2.0.0` hash `1037f00d42e1e379919520b92a5fbdbbe679cb593ba9cdec5309e824f7b7860b`; prompt storage `false`; post-install status `ready/configured`.
- Reload boundary: installer changed the user proxy after self-test and requires a fresh Codex task/reload before runtime-discovery claims. Static receipts do not yet prove the five canaries.
- Pre-reload diagnostic: an unrelated Auto control reported secretary context absent, while a later trigger produced correct `ฉัน/ค่ะ` text but reported `VOICE_BOOTSTRAP_CONTEXT=absent` and `POLICY_VERSION=unknown`. This is not an enforced receipt and proves the running desktop host has not reloaded the new proxy. Diagnostic tasks were archived.
- Current rollout state: `needs_reload`; all five runtime canaries remain `not_yet_proved` until Codex is fully closed and reopened.

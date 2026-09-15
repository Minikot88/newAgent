---
name: kimmizo-setup
description: Bootstrap, diagnose, update, or repair a project-local เลขาคิม secretary, custom-agent team, capability routing, checkpoints, and memory. Use before starting a new project, when the user asks to set up เลขาคิม, or when an existing Kimmizo capsule needs doctor, update, repair, or team changes.
---

# Kimmizo Setup

Kimmizo Setup is a temporary bootstrap layer. It prepares a project-local secretary and team, then steps out of daily work. Return to this skill only for `doctor`, `update`, `repair`, capability changes, or team profile changes.

## Workflow

1. Resolve the target project from the current workspace or the path the boss named.
2. Run Doctor before mutating anything.
3. Use native Codex UI `Model = Auto` when the Host exposes it. On Windows setup/update, the boss-approved Kimmizo Auto host extension may add `✦ Auto` through the Codex app-server protocol and synchronize the complete signed runtime bundle from the latest Codex Desktop MSIX. It must stay reversible, never create a separate launcher, never patch the signed Desktop renderer, never write the virtual model to `config.toml`, and never retain prompt or token content.
4. Enforce ChatGPT Plus Limit-First: Luna/low by default, Luna/medium for general coding, Terra/high only for genuinely complex or ambiguous work, and Sol/high only for production/security/database migration/high-stakes work. Run focused deterministic verification before escalation and keep Fast mode off.
5. Treat Astra, Max, Ultra, and multi-agent execution as manual-only. Ask the boss before every Astra use and every Ultra activation. Work serially and solo unless the boss explicitly requests a team; an explicitly selected reviewed/protected gate may use one read-only reviewer.
6. Resolve each explicitly authorized worker's Model/Reasoning and compatible profile from the live Host catalog using the Luna → Terra → Sol ladder. Never assign Astra automatically.
7. Before each non-trivial work section, report the executor, Model, Reasoning, and selection reason. For Auto, report the concrete route only when the Host exposes it; never guess. Report each authorized worker's agent/model/reasoning before spawn.
8. Explain any authority gate. Auth, hooks, MCP, new permissions, sandbox expansion, or external writes require the boss's system approval.
9. Run Setup. Existing `AGENTS.md`, `.codex/config.toml`, and `.gitignore` content stays outside versioned, checksummed managed blocks.
10. Verify the capsule, team identities, custom agent TOML, routing, and latest checkpoint.
11. If an install requires a restart, ensure a checkpoint exists before the install and report the resume action.
12. Stage team profile edits as candidates. Run a bounded standard evaluation and attach evidence before promotion.

## Commands

From the setup repository:

```powershell
.\install.ps1 -Target D:\path\to\project
.\install.ps1 -Mode doctor -Target D:\path\to\project
.\install.ps1 -Mode repair -Target D:\path\to\project
```

Direct Python entry point:

```powershell
python plugins\kimmizo-setup\scripts\kimmizo.py setup --target D:\path\to\project --json
python plugins\kimmizo-setup\scripts\kimmizo.py route --target D:\path\to\project --task "the boss's task" --json
```

Use `--skip-install` to create only the project capsule. Use `--dry-run` to report intended writes without changing files.

After the boss installs and approves a gated plugin through the Codex host, use `capability-approve` to adopt that already-enabled host state. Kimmizo cannot mint approval: the receipt binds the Registry, Lock, host selector, manifest, and full package fingerprint, and invalidates when any of them changes. Use `capability-rollback` to restore a staged pinned-skill or plugin snapshot.

## Non-negotiable policies

- Call the user `บอส`; Kimmizo refers to herself as `คิม`. Use `คะ` for questions and `ค่ะ` for statements.
- Never depend on or modify another secretary project. The target `.kimmizo/` directory is the project source of truth.
- Never rename an existing agent or reuse its `agent_id`. Model, reasoning, personality, instructions, and allowlisted skills can change through a new revision for future spawns.
- Keep model authority split: native Auto or the installed Kimmizo Auto host extension applies only to Kim's main Codex task. Kimmizo Auto resolves a concrete model for every message from the live Host catalog. Kim separately selects each worker's Model/Reasoning for the actual task.
- Keep Plus Limit-First immutable unless the boss explicitly changes it: serial solo by default, deterministic checks before escalation, no Fast mode, no automatic Astra/Max/Ultra/team.
- Load capability metadata in the main context. Load a skill body, MCP tools, or large logs only in the bounded worker context that needs them.
- Select a structured API/file/repository path before Browser, logged-in Chrome, or official Computer Use. Block the Linux/Xvfb community `computer-use` skill on Windows.
- Do not route `using-superpowers` implicitly. Setup physically disables its always-on `SKILL.md` in the active marketplace/cache while retaining named Superpowers subskills; `update` and `repair` must re-enforce this guard after marketplace refreshes.
- Use `grill-me` for important ambiguity; add `adhd` only when the ambiguity is open-ended and high-impact.
- Promote a lesson only with evidence, root cause, and a prevention test. Ask before recording a personal preference.

Read [security-policy.md](references/security-policy.md) before changing install or authority behavior. Read [registry-schema.md](references/registry-schema.md) before adding or updating a capability.

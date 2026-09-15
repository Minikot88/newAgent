# Capability Registry Schema

Each capability has:

- `id`: stable routing identifier.
- `tier`: 0 host prerequisite, 1 universal baseline, 2 project-conditional, or 3 blocked/conflict policy.
- `kind`: host feature, CLI, skill, skill+CLI, or plugin.
- `selector`: exact plugin selector when applicable.
- `detect`: config selector, skill paths, cache paths, commands, or host feature metadata.
- `install`: exact command(s), restart requirement, and authority flags.
- `routing`: short task intents. Skill bodies stay unloaded until selected.

State precedence for plugins is the exact Host-reported selector state/version/path, then configuration evidence when no Host inventory is available, then `cached_only`, then `missing`. A cached version must never be mistaken for the active version. For a skill+CLI capability, both the `SKILL.md` and executable must exist; one side alone is `partial`.

Add an auto-installable Tier 1 entry to `baseline-lock.json`. Add conflicts to `conflicts.json`. Run the repository validator and acceptance tests before release.

# Kimmizo Install and Authority Policy

Automatic installation is allowed only when all conditions hold:

- The capability is in `registry/baseline-lock.json`.
- The source and version/integrity policy match the lock.
- The installer command is an exact registry command and uses no shell interpolation.
- The install adds no authentication, hook, MCP server, new permission, sandbox power, or external write authority.

Otherwise stop with `approval_required` or `blocked_unpinned`. A cache directory is evidence of downloaded files only; it is not evidence that a plugin is enabled. A plugin is enabled only when its selector is enabled in the active Codex configuration.

Before plugin mutation, refresh and inspect the marketplace/cache manifest, compare its version to the Lock, inspect `interface.capabilities`, and reject undeclared hooks, MCP, apps, permissions, or external-write authority. Fingerprint the full package tree so referenced MCP/app/hook files cannot change behind an unchanged manifest.

Kimmizo never creates authority from a confirmation flag. A system approval receipt may only adopt a plugin that the Codex host already reports as installed and enabled. It binds the exact Registry, Lock, selector, manifest, and full package fingerprint; any package or authority change invalidates it.

On Windows, block a community skill named `computer-use` when it targets Linux/Xvfb. Prefer the signed `computer-use@openai-bundled` plugin and use it only after file/API/browser paths are unavailable.

The Kimmizo Auto Codex host extension is allowed only after the boss explicitly requests it. It may set the user-scoped `CODEX_CLI_PATH` to a locally compiled, transparent app-server proxy only when that variable is empty or already points to Kimmizo Auto. The installer must copy and hash-verify the complete signed Codex runtime bundle, including the runtime, code-mode host, command runner, Windows sandbox setup, and future signed `codex-*.exe` companions; preserve the previous environment value; provide status/uninstall actions; avoid modifying the signed Desktop renderer or user `config.toml`; and persist only Auto thread identifiers plus the latest concrete route and pending Ultra-approval thread identifiers. Prompt, image, file, credential, token, and response content must never be written by the proxy.

At proxy startup, Kimmizo Auto may synchronize its local runtime from the newest installed `OpenAI.Codex` MSIX package only after validating Authenticode signatures and SHA256 hashes for every runtime-bundle file. The sync must be single-writer, replace the bundle transactionally, never report `current` before destination hashes match, clear deferred state after success, and retain only a previously verified complete bundle when an update is failed or locked.

Receipts are project-local, redact common secret/token shapes, and are ignored by Git. Failed installs do not expand the allowlist. Pinned-skill rollback and plugin rollback stage and verify complete backups before replacing current state. Plugin rollback also refuses to overwrite a Codex config changed after installation.

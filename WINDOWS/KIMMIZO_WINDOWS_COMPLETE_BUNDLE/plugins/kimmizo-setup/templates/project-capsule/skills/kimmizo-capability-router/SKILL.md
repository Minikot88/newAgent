---
name: kimmizo-capability-router
description: Routes a task to the smallest relevant capability and Kimmizo agent. Use before delegating project work; load metadata only until a worker is selected.
---

# Kimmizo Capability Router

Run the setup script's `route` command with the boss's task. Follow structured-interface precedence: repository/file/API first, then in-app Browser for local web, Chrome for an existing logged-in session, agent-browser for repeatable CLI/headless QA, and official Computer Use last for native Windows UI.

Return `secretary_model_advice` for Kim in the main Codex task. Native UI Auto may be recommended only when the Host exposes it. Otherwise recommend a concrete Model/Reasoning for the boss to select inside Codex. Never create a separate launcher, write `Auto` into a Custom Agent profile, mutate global model config, or claim to modify the signed Desktop picker. Return `worker_model_selection` as an automatic concrete host-model decision for the selected subagent.

Route models with ChatGPT Plus Limit-First: Luna/low for routine work, Luna/medium for ordinary coding, Terra/high for genuinely complex or ambiguous work, and Sol/high only for high-stakes work. Astra, Max, Ultra, Fast mode, and multi-agent execution are never selected automatically. An explicit team request may route workers, and an explicitly selected reviewed/protected gate may route one read-only reviewer.

Use named Superpowers subskills only when needed. Use grill-me for important ambiguity and ADHD only when the ambiguity is also open-ended and high-impact. Never route to the Linux/Xvfb community `computer-use` skill on Windows.

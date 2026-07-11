---
title: "/scaffold-ecosystem — Slash Command for AI Coding Agents"
description: "Scaffold a four-pillar agentic config ecosystem (context/, skills/, agents/, workflows/). Usage: /scaffold-ecosystem <stack-name> [--output DIR]. Slash command for Claude Code, Codex CLI, Gemini CLI."
---

# /scaffold-ecosystem

<div class="page-meta" markdown>
<span class="meta-badge">:material-console: Slash Command</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/commands\scaffold-ecosystem.md">Source</a></span>
</div>


Scaffold the directory structure for a new four-pillar agentic configuration stack, seeded with hardened template examples. Target: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the user what name to give the new configuration stack (e.g. `my-agent-stack`).

## Usage

```bash
/scaffold-ecosystem my-agent-stack
/scaffold-ecosystem my-agent-stack --output ./workspace
```

## Step 1: Execute Scaffolder

Run the scaffolding tool using:

```bash
python skills/agentic-system-architect/scripts/ecosystem_scaffolder.py {stack_name} --output {output_dir}
```

Add `--force` if you need to overwrite an existing directory, or `--dry-run` to print the file tree without writing anything to disk.

## Step 2: Output and Next Steps

The tool will create:
* `context/README.md` and basic boundary specifications.
* `skills/sample-skill/SKILL.md` (and scripts/references/assets subdirectories).
* `agents/cs-sample-agent.md` (audited template).
* `workflows/sample-workflow.md` (validated gated workflow).
* `README.md` explaining the stack structure.

Verify that the scaffolding executed correctly and report the created file tree to the user.

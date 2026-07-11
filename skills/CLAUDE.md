# Skill Creation Guide

This guide covers creating and maintaining skill packages in `skills/`. Skills are the
expertise layer of **agentic-config-hub**: self-contained packages that agents in
`agents/` orchestrate via `../skills/<name>/` paths.

## Package Pattern

Every skill is one folder with this layout:

```
skills/<skill-name>/
├── SKILL.md          # Master documentation: purpose, workflows, tool usage
├── scripts/          # Python CLI tools (deterministic, stdlib-only)
├── references/       # Expert knowledge bases (markdown)
└── assets/           # User-facing templates and sample inputs
```

Knowledge flows from `references/` -> into `SKILL.md` workflows -> executed via
`scripts/` -> applied using `assets/` templates. A skill without scripts or assets is
valid (some are pure knowledge packages), but `SKILL.md` is always mandatory.

## SKILL.md Frontmatter Rules

```yaml
---
name: "agentic-system-architect"
description: "Use when designing agentic ecosystems, hardening agents with exit conditions, or adding HITL gates to workflows."
---
```

- `name` — **quoted**, kebab-case, matches the folder name exactly.
- `description` — **quoted**, and **starts with "Use when"** so triggering is
  unambiguous for both humans and agent routers. State the concrete situations, not
  the topic ("Use when auditing agent loops for runaway risk", not "Loop safety").

## Atomicity

- **One capability per skill.** If a skill does two unrelated things, split it.
- **Zero cross-skill dependencies.** A skill must never import, execute, or reference
  files from another skill folder. Anyone must be able to copy one skill folder out
  of the repo and use it immediately.
- Shared logic is not shared — duplicate small helpers into each skill rather than
  creating a common library. Portability beats DRY here.
- Composition happens one level up: agents and workflows combine skills; skills never
  combine each other.

## Python Script Rules

Every script in `scripts/` must satisfy all of the following (these are CI gates):

- **Python 3.8+ standard library only** — no third-party imports, no pip installs.
- **argparse CLI** — `--help` must work and document every flag.
- **`--json` flag** — machine-readable output for CI and agent consumption, alongside
  the default human-readable report.
- **ASCII-safe output** — no emoji or non-ASCII glyphs in printed output (Windows
  consoles and CI logs must render it verbatim).
- **Meaningful exit codes** — 0 on success/PASS; non-zero on failure or when a
  quality gate is not met (e.g. `loop_auditor.py --min-score 90` exits 1 below 90).
- **No LLM calls, no network calls** — deterministic, algorithmic analysis only.
  Same input, same output, every run, offline.

## How to Test a Skill

```bash
# 1. Syntax check every script
python -m py_compile skills/<name>/scripts/*.py

# 2. Every script answers --help with exit code 0
python skills/<name>/scripts/<tool>.py --help

# 3. Run the full 8-phase audit pipeline on the skill folder
/plugin-audit skills/<name>
```

Also verify by hand: frontmatter parses and follows the rules above, all paths
mentioned in `SKILL.md` exist, and `--json` output is valid JSON (pipe it through
`python -m json.tool`). Record eval iterations in `evals/` (see
[../evals/README.md](../evals/README.md)).

## Catalog: The 19 Current Skills

### Core agentic design

| Skill | Capability |
|-------|-----------|
| [agentic-system-architect](agentic-system-architect/SKILL.md) | **Flagship.** Four-pillar ecosystem design, loop auditing, ReAct trace analysis, HITL gate validation |
| [agent-designer](agent-designer/SKILL.md) | Designing individual agent definitions and role prompts |
| [agent-workflow-designer](agent-workflow-designer/SKILL.md) | Multi-agent workflow orchestration and step design |
| [spec-driven-workflow](spec-driven-workflow/SKILL.md) | Spec-first development flow: spec -> plan -> implement -> verify |
| [agenthub](agenthub/SKILL.md) | Agent registry and discovery patterns for multi-agent systems |

### Prompts & quality

| Skill | Capability |
|-------|-----------|
| [prompt-governance](prompt-governance/SKILL.md) | Prompt versioning, review, and change-control policies |
| [senior-prompt-engineer](senior-prompt-engineer/SKILL.md) | Advanced prompt design, evaluation, and refinement |
| [self-eval](self-eval/SKILL.md) | Honest work-quality scoring with inflation detection |
| [skill-tester](skill-tester/SKILL.md) | Testing skill packages for correctness and triggering accuracy |
| [focused-fix](focused-fix/SKILL.md) | Scoped 5-phase repair protocol for a single feature/module |

### Autonomy & security

| Skill | Capability |
|-------|-----------|
| [self-improving-agent](self-improving-agent/SKILL.md) | Bounded self-improvement loops with guardrails |
| [ai-security](ai-security/SKILL.md) | LLM threat modeling: prompt injection, data exfiltration, misuse |
| [adversarial-reviewer](adversarial-reviewer/SKILL.md) | Red-team style review of configs and outputs |
| [skill-security-auditor](skill-security-auditor/SKILL.md) | Auditing skill packages for malicious or unsafe patterns |
| [autoresearch-agent](autoresearch-agent/SKILL.md) | Governed autonomous research with verification loops |

### Infrastructure

| Skill | Capability |
|-------|-----------|
| [mcp-server-builder](mcp-server-builder/SKILL.md) | Building MCP servers: tools, resources, transports |
| [rag-architect](rag-architect/SKILL.md) | Retrieval-augmented generation pipeline design |
| [llm-cost-optimizer](llm-cost-optimizer/SKILL.md) | Token, caching, and model-routing cost analysis |
| [browser-automation](browser-automation/SKILL.md) | Agent-driven browser automation patterns |

## Adding a New Skill

1. Confirm the capability is atomic and not covered by an existing skill above.
2. Create `skills/<name>/` with the package pattern; write `SKILL.md` first.
3. Add scripts/references/assets following the rules in this guide.
4. Test: `py_compile`, `--help`, `/plugin-audit skills/<name>`.
5. Add the skill to the catalog table above and to the repo root `CLAUDE.md` count.
6. Branch `feature/skills-<name>` -> conventional commit
   (`feat(skills): add <name>`) -> PR to `dev`.

## References

- Repo guide: [../CLAUDE.md](../CLAUDE.md)
- Agent development guide: [../agents/CLAUDE.md](../agents/CLAUDE.md)
- Eval workspace: [../evals/README.md](../evals/README.md)
- Quality standards: [../standards/](../standards/)

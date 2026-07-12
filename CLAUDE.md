# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**agentic-config-hub** is a curated library of **production-ready AI configurations for agents and agentic systems** - skills, agents, workflows, and context packages that teams extract and deploy directly into their own Claude Code (or Codex / Gemini CLI / OpenClaw) setups.

**Key Distinction**: This is NOT an application. There is nothing to build, deploy, or serve. It is a configuration library: every skill is an extractable, self-contained product, and every agent and workflow is a ready-to-run configuration file hardened with loop controls and human approval gates.

## Current Scope

- **29 atomic skill packages** in `skills/` (agent design, framework integration - LangGraph/CrewAI/MS Agent Framework, RAG & memory, MCP, prompt engineering, evals, guardrails, observability, cost control, autonomous loops)
- **1 flagship skill**: `skills/agentic-system-architect/` - four-pillar ecosystem design plus 4 Python quality-gate tools
- **1 flagship agent**: `agents/cs-agentic-system-architect.md` plus reviewer personas in `agents/personas/`
- **4 pillars** at repo root: `context/`, `skills/`, `agents/`, `workflows/`
- **Quality tooling**: `loop_auditor.py` (100-point rubric), `hitl_gate_validator.py` (R1-R6), `react_trace_analyzer.py` (D1-D7), `ecosystem_scaffolder.py`
- Meta-infrastructure: `commands/`, `templates/`, `standards/`, `evals/`, `scripts/`, `docs/`, `documentation/`

## Navigation Map

| Area | Location | Focus |
|------|----------|-------|
| **Context** | [context/](context/) | Project ground truth; read-only for agents |
| **Skills** | [skills/](skills/) + [skills/CLAUDE.md](skills/CLAUDE.md) | 29 atomic, self-contained skill packages |
| **Agents** | [agents/](agents/) + [agents/CLAUDE.md](agents/CLAUDE.md) | cs-* role agents and reviewer personas |
| **Workflows** | [workflows/](workflows/) | Gated multi-agent orchestrations with HITL blocks |
| **Commands** | [commands/](commands/) | Slash commands (focused-fix, plugin-audit) |
| **Templates** | [templates/](templates/) | Reusable agent and skill templates |
| **Standards** | [standards/](standards/) | Git, quality, security, communication, documentation |
| **Evals** | [evals/](evals/) | Skill and agent evaluation results |
| **Scripts** | [scripts/](scripts/) | Multi-platform install + docs generation |
| **Workflow Guide** | [documentation/WORKFLOW.md](documentation/WORKFLOW.md) | Complete git workflow reference |

## The Four-Pillar Architecture

Knowledge flows **one way** through four pillars:

```
context/  ->  skills/  ->  agents/  ->  workflows/
(ground       (atomic       (roles that    (gated multi-agent
 truth)        expertise)    load skills)   orchestrations)
```

1. **context/** - Ground truth about the project. Agents read it; nothing writes to it during a run.
2. **skills/** - Atomic capability packages. Each skill stands alone and never imports from another skill.
3. **agents/** - Role definitions that compose skills. Agent files reference skills as `../skills/<skill-name>/` (one level up).
4. **workflows/** - Multi-agent orchestrations. Every workflow embeds explicit human approval gates.

**Atomicity rule**: dependencies only point left in the diagram. A skill never depends on an agent, an agent never depends on a workflow, and no skill depends on another skill.

## Skill Package Pattern

Each skill follows this structure:

```
skills/skill-name/
|-- SKILL.md              # Master documentation (YAML frontmatter: name + description)
|-- scripts/              # Python CLI tools (stdlib-only, no LLM/network calls)
|-- references/           # Expert knowledge bases
|-- assets/               # User-facing templates
```

**Design Philosophy**: Skills are self-contained products. Knowledge flows from `references/` into `SKILL.md` workflows, executed via `scripts/`, applied using `assets/` templates. A team can copy one skill folder and use it immediately - no cross-skill wiring, no setup.

## Quality Gates

Every configuration in this repo must pass deterministic gates before merge:

1. **Agents**: every agent `.md` scores **>= 90 (HARDENED)** on the loop-engineering rubric:

   ```bash
   python skills/agentic-system-architect/scripts/loop_auditor.py agents/cs-agentic-system-architect.md --min-score 90
   ```

   Rubric: 100 points. Grades: >= 90 HARDENED / 75-89 PRODUCTION-READY / 50-74 NEEDS-CONTROLS / < 50 UNSAFE-FOR-AUTONOMY. The `--min-score N` gate exits 1 below N, so it wires directly into CI.

2. **Workflows**: every workflow `.md` embeds a fenced `json` block that **PASSES** the HITL gate validator (rules R1-R6; PASS = zero CRITICAL/HIGH findings):

   ```bash
   python skills/agentic-system-architect/scripts/hitl_gate_validator.py workflows/<workflow>.md
   ```

3. **Python scripts**: Python 3.8+ **standard library only**, argparse with `--help`, a `--json` output flag, ASCII-safe output, and **no LLM or network calls**.

4. **Skills**: self-contained - zero cross-skill dependencies.

Supporting tools in `skills/agentic-system-architect/scripts/`:

- `ecosystem_scaffolder.py` - scaffold a complete four-pillar ecosystem
- `react_trace_analyzer.py` - detect reasoning-loop pathologies D1-D7 in agent traces
- `loop_auditor.py` / `hitl_gate_validator.py` - the two merge gates above

## Git Workflow

**Branch Strategy:** feature -> dev -> main (PR only)

```bash
# 1. Always start from dev
git checkout dev
git pull origin dev

# 2. Create feature branch
git checkout -b feature/skills-{name}

# 3. Work and commit (conventional commits)
#    feat(skills): add exit-condition reference to rag-architect
#    fix(scripts): correct rubric weighting in loop_auditor
#    docs(workflows): document HITL gate placement

# 4. Run the quality gates locally (see Quality Gates above)

# 5. Push and create PR to dev
git push origin feature/skills-{name}
gh pr create --base dev --head feature/skills-{name}

# 6. Periodically, dev merges to main via PR
```

**Rules:**

- Main requires PR approval; direct pushes blocked
- Dev is unprotected, but PRs are recommended
- Conventional commits enforced everywhere

See [documentation/WORKFLOW.md](documentation/WORKFLOW.md) for the complete workflow guide and [standards/git/](standards/git/) for commit standards.

## Development Environment

**No build system or test frameworks** - an intentional design choice for portability. Configurations must work by copying files, nothing else.

**Python Scripts:**

- Python 3.8+ standard library only (no third-party dependencies)
- CLI-first design: argparse, `--help`, and a `--json` flag on every tool
- ASCII-safe output (no emojis, no non-ASCII glyphs in stdout)
- No ML/LLM calls and no network calls - deterministic, fast, offline

**If a dependency ever seems necessary:** prefer a standard-library implementation. If truly unavoidable, it must be a single `pip install`, documented in the skill's SKILL.md - but the default answer is no.

## Key Principles

1. **Skills are products** - Each skill is deployable as a standalone package
2. **Algorithm over AI** - Deterministic analysis (code) beats LLM calls in tooling
3. **Template-heavy** - Ship ready-to-use templates that users customize
4. **Defensive autonomy** - Every agent carries loop controls (exit conditions, iteration counters, self-reflection checkpoints) and follows the 5-Phase Protocol; autonomy without brakes never merges
5. **Gates before execution** - Human approval happens before irreversible work, never after

## The 5-Phase Protocol

Canonical execution protocol for every agent and workflow in this repo:

1. **Phase 1 DISCOVERY** (read-only) - explore and gather facts, no writes
2. **Phase 2 MANIFEST** - produce an explicit plan of intended changes
3. **Phase 3 HUMAN GATE** (hard stop) - human approves/edits/rejects the manifest
4. **Phase 4 IMPLEMENTATION** - execute strictly against the approved manifest
5. **Phase 5 SELF-REVIEW & HANDOFF** - audit own output, report deviations, hand off

### Exit-Condition Taxonomy (6 types)

Every autonomous loop declares its exit conditions from this taxonomy:

| Type | Fires when |
|------|-----------|
| `max_iterations` | Hard cap on loop count reached |
| `no_progress` | N consecutive iterations without measurable improvement |
| `oscillation` | The loop revisits previously seen states |
| `budget` | Token/time/cost ceiling exhausted |
| `success_predicate` | The goal condition is verifiably met |
| `escalation_trigger` | A condition requiring human judgment appears |

Full definitions, patterns, and scoring live in the flagship skill: [skills/agentic-system-architect/](skills/agentic-system-architect/).

## Anti-Patterns to Avoid

- **Cross-skill dependencies** - keep every skill self-contained
- **LLM or network calls in scripts** - defeats portability, speed, and determinism
- **Unbounded loops** - any loop without declared exit conditions from the 6-type taxonomy is UNSAFE-FOR-AUTONOMY
- **Gates after execution** - approval must precede irreversible actions; a gate placed after the work it guards is a validator failure
- **Renaming folders to match registry slugs** - the repo is the source of truth
- **Complex build systems or test frameworks** - maintain copy-and-run simplicity

## Working with This Repository

**Creating new skills:** follow the Skill Package Pattern above and the guidance in [skills/CLAUDE.md](skills/CLAUDE.md). Run new Python tools through the script rules before committing.

**Creating or editing agents:** use [templates/agent-template.md](templates/agent-template.md), reference skills as `../skills/<skill-name>/`, and audit with `loop_auditor.py --min-score 90` until HARDENED.

**Creating workflows:** embed the fenced `json` HITL block and validate with `hitl_gate_validator.py` until PASS.

**Quality standard:** each configuration should save users 40%+ time while measurably improving safety and consistency.

## Additional Resources

- **Standards Library:** [standards/](standards/) - git, quality, security, communication, documentation
- **Install scripts:** [scripts/](scripts/) - `install.sh`, `codex-install.sh`, `gemini-install.sh`, `openclaw-install.sh`
- **Docs site:** [docs/](docs/) - MkDocs Material, generated via `scripts/generate-docs.py`
- **Workflow guide:** [documentation/WORKFLOW.md](documentation/WORKFLOW.md)

---

**Last Updated:** 2026-07-10
**Version:** v0.1.0
**Status:** Initial release - 29 skills, 4 hardened agents, four-pillar architecture, quality gates active

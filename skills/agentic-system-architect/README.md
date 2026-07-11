# Agentic System Architect

POWERFUL-tier engineering skill for designing complete agentic configuration ecosystems and hardening autonomous agents with loop-engineering controls, ReAct reasoning patterns, and defensive Human-in-the-Loop (HITL) flow control built around the 5-Phase Protocol (Discovery, Manifest, Human Gate, Implementation, Self-Review & Handoff).

## What It Does

Most agent failures are architecture failures: loops without exit conditions, irreversible actions without approval gates, components designed in isolation. This skill provides a repeatable architecture method plus four deterministic Python tools that scaffold ecosystems, audit agent configs against a 100-point loop-safety rubric, analyze ReAct traces for runaway patterns (action loops, oscillation, error cascades, budget overruns), and validate workflows for HITL gate coverage. All tools are standard-library Python with no LLM or network calls.

## The Four Pillars

Every ecosystem is organized into four directories with single responsibilities, and knowledge flows in one direction between them: `context/` holds what the system knows (boundaries, vocabulary, constraints), `skills/` holds what it can do (atomic, reusable procedures), `agents/` holds who does the work (role-bound executors with loop-safety controls and tool allowlists), and `workflows/` holds how work is sequenced and gated (orchestration with human gates, rollback plans, and escalation paths in front of every irreversible action).

## When to Use

- Design a multi-agent ecosystem for a project or team from scratch
- Harden an existing agent against runaway loops, infinite retries, or unbounded tool usage
- Add human approval gates and the 5-Phase Protocol to workflows with irreversible actions
- Diagnose why an agent looped, oscillated, or failed to converge from its ReAct trace

## Quickstart

```bash
# 1. Scaffold a new four-pillar ecosystem (preview first)
python scripts/ecosystem_scaffolder.py my-project --output ./ --dry-run

# 2. Audit an agent config against the 100-point loop-safety rubric
python scripts/loop_auditor.py path/to/agent.md --json

# 3. Analyze a ReAct trace for runaway patterns
python scripts/react_trace_analyzer.py assets/sample_react_trace.json

# 4. Validate a workflow for HITL gate coverage
python scripts/hitl_gate_validator.py assets/workflow-template.md
```

All tools support `--help` and `--json`, exit 0 on success and 1 on error, and produce ASCII-safe console output.

## Quality Bar

- Every generated agent must score >= 90 (HARDENED) on `loop_auditor.py`
- Every generated workflow must PASS `hitl_gate_validator.py` (no CRITICAL or HIGH violations)

## Contents

| Path | Description |
|------|-------------|
| [SKILL.md](SKILL.md) | Full skill documentation: architecture, disciplines, tools, end-to-end workflow |
| [references/loop_engineering_patterns.md](references/loop_engineering_patterns.md) | Loop archetypes, the 6-type exit-condition taxonomy, counter design |
| [references/react_reasoning_patterns.md](references/react_reasoning_patterns.md) | ReAct, Reflexion, and Plan-and-Execute patterns and anti-patterns |
| [references/hitl_defensive_architectures.md](references/hitl_defensive_architectures.md) | Gate placement, irreversibility classification, rollback and escalation design |
| [references/four_pillar_ecosystem.md](references/four_pillar_ecosystem.md) | The context/skills/agents/workflows architecture in depth |
| [scripts/](scripts/) | The four Python tools (3.8+, standard library only) |
| [assets/](assets/) | Templates for agents, workflows, context packs, atomic skills, plus a sample ReAct trace |

## Related Skills

- **agent-designer** - single-agent persona and prompt design
- **agent-workflow-designer** - plain workflow scaffolding without defensive gates
- **prompt-governance** - prompt quality and versioning
- **spec-driven-workflow** - spec-first implementation flow

---

**Tier:** POWERFUL | **Category:** Engineering | **Python:** 3.8+ (standard library only)

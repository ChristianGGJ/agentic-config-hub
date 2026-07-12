---
name: "crewai-role-engineering"
description: "Use when building CrewAI multi-agent teams: authoring role/goal/backstory personas, scoping tasks with structured outputs and guardrails, wiring custom tools, choosing sequential vs hierarchical crews vs Flows, or bounding a crew against runaway execution with max_iter, max_rpm, max_execution_time, and human_input gates."
---

# CrewAI Role Engineering

Design CrewAI agent teams whose behavior is shaped by engineered personas, whose
tasks hand off validated structured outputs, and whose execution is bounded by
explicit runaway-prevention controls mapped to this hub's exit-condition canon.

**Version assumption:** API surface as written here targets **CrewAI 0.100+
(2025/2026)**. CrewAI releases frequently; when a member is version-sensitive it
is marked "verify against current docs". Anything not marked is a stable,
long-lived part of the public API (`Agent`, `Task`, `Crew`, `Process`, `LLM`,
`crewai.tools`, `kickoff`).

## Overview

CrewAI's core bet is that **persona is configuration**: an agent's `role`,
`goal`, and `backstory` are injected into its system prompt, so the words you
put there directly change tool selection, delegation behavior, output format,
and stopping behavior. Most CrewAI failures trace back to one of three design
errors: overlapping personas (two agents believe the same work is theirs),
unbounded execution (framework defaults treated as guards), and untyped
handoffs (downstream tasks parsing prose instead of consuming validated
objects). This skill fixes all three.

## Core Capabilities

1. **Persona engineering** — backstory patterns that measurably change agent
   behavior (constraint clauses, method anchoring, escalation instructions),
   goal scoping, and an anti-overlap rubric for team design.
2. **Task allocation** — atomic task design with `expected_output` contracts,
   `context` chaining, `async_execution` fan-out, and `human_input` gates.
3. **Structured handoffs** — `output_pydantic` / `output_json` / `output_file`
   plus task guardrails that validate outputs before the next agent sees them.
4. **Custom tools** — `@tool` decorator and `BaseTool` subclasses with typed
   `args_schema` so agents stop hallucinating tool arguments.
5. **Orchestration selection** — sequential vs hierarchical crews vs Flows
   (`@start`/`@listen`/`@router`), manager configuration, YAML `@CrewBase`
   project structure.
6. **Runaway prevention** — `max_iter`, `max_rpm`, `max_execution_time`,
   guardrail retry caps, and callback-based ledgers, mapped to the hub's
   six exit-condition types.

## Decision Frameworks

### Orchestration topology

| Situation | Choose | Trade-off |
|---|---|---|
| Linear pipeline, known task order, one deliverable | `Crew` + `Process.sequential` | Simplest, cheapest; no dynamic routing |
| Task order unknown, intermediate QA review needed, dynamic assignment | `Crew` + `Process.hierarchical` | Manager LLM adds cost, latency, and a single point of failure |
| Conditional branching, typed state, mixing crews with plain Python steps | **Flow** (`@start`/`@listen`/`@router`) with crews inside | More code; deterministic control flow you own |
| Cyclic graphs, checkpoint/resume, per-node state reducers, time travel | Not CrewAI — see the `langgraph-state-design` sibling skill | — |

Calibrated default: start sequential. Move to hierarchical only when you can
name the routing decision the manager must make. Wrap in a Flow when any
branch, loop, or non-LLM step appears.

### Delegation policy

| Agent kind | `allow_delegation` | Rationale |
|---|---|---|
| Worker (writer, coder, analyst) | `False` (explicit) | Prevents delegation ping-pong; keeps the agent on its own task |
| Supervisor / QA reviewer | `True` | Gains the "Delegate work to coworker" and "Ask question to coworker" tools |
| Manager (`manager_agent` in hierarchical) | `True` | Delegation is its whole job; give it no other tools |

Default is `False` in current releases (early releases defaulted to `True` —
set it explicitly on every agent so behavior survives version bumps).

### Manager configuration (hierarchical only)

| Option | When | Cost |
|---|---|---|
| `manager_llm=LLM(model=...)` | Standard routing/review; you trust the stock manager prompt | Cheapest to set up; opaque behavior |
| `manager_agent=Agent(...)` | You need custom manager rules ("never execute work yourself", domain review criteria) | You own the persona; more tuning |
| `planning=True` (+ optional `planning_llm`) | Sequential crew that benefits from an upfront plan injected into each task | One extra planning call per kickoff; works with sequential — not a manager replacement |

Rule: the manager agent must NOT appear in the `agents=[...]` list — pass it
only via `manager_agent`. Use a capable/frontier-tier model for the manager;
routing quality degrades sharply on utility-tier models.

### Per-agent model tiering

Bind models per agent via `llm=` (see `references/crewai_tools_tasks_outputs.md`
section 1). Assign by role demands, not uniformly:

| Role demands | Tier | Examples of fit |
|---|---|---|
| Multi-step reasoning, review, routing | Frontier/reasoning tier | Manager, QA reviewer, architect |
| Format transformation, extraction, summarization | Utility/fast tier | Formatter, data extractor, collector tasks |
| Tool-heavy research with judgment | Mid/balanced tier | Researcher, analyst |

Cross-provider routing strategy (which tier is cheapest per capability today)
is owned by the `multi-llm-routing` sibling skill; this skill owns the CrewAI
binding syntax.

### Output typing

| Handoff consumer | Use | Why |
|---|---|---|
| Human reading the final report | default `.raw` markdown | No schema overhead |
| Downstream task needs specific fields | `output_pydantic=Model` | Typed, validated, attribute access |
| External system needs JSON | `output_json=Model` | Dict access, schema-shaped |
| Artifact on disk (report, code file) | `output_file="path.md"` | Keeps large outputs out of context |

Rule of thumb: any task whose output another *task* consumes should be typed
(`output_pydantic`) and guarded (`guardrail=`). Prose handoffs are where
hallucinations compound.

### Project structure

| Situation | Use |
|---|---|
| Prototype, single file, < 3 agents | Inline Python `Agent(...)`/`Task(...)` |
| Team-maintained, prompts iterated by non-engineers, CI-deployed | YAML `agents.yaml`/`tasks.yaml` + `@CrewBase` (the documented recommended structure) |

## Runaway Prevention

CrewAI agents run an internal think-act loop per task. The framework default
iteration cap (20-25 depending on version) is calibrated for hard research
tasks, not cheap workers — **never rely on defaults**. Set bounds explicitly:

```python
from crewai import Agent

analyst = Agent(
    role="Data Analyst",
    goal="Produce the requested metrics table from the provided CSV extracts.",
    backstory="You compute metrics only from data you were given. "
              "If a required column is missing, you report that instead of estimating.",
    max_iter=8,               # hard cap on think-act cycles for this agent per task
    max_rpm=20,               # LLM requests per minute (rate budget)
    max_execution_time=300,   # wall-clock seconds per task execution
    allow_delegation=False,
)
```

Semantics worth knowing: when `max_iter` is reached the agent is forced to
produce its best final answer — it does not raise. That means `max_iter` alone
is a soft landing, not a quality gate; pair it with a task `guardrail` so a
forced answer that misses the contract gets caught. Crew-level `max_rpm`
overrides agent-level values.

### Mapping to the hub's six exit-condition types

| Hub exit condition | CrewAI mechanism | Calibrated default |
|---|---|---|
| `max_iterations` | `Agent(max_iter=...)` | 5-10 workers, 10-15 researchers, 15-20 manager |
| `budget` (rate) | `Agent(max_rpm=...)` / `Crew(max_rpm=...)` | 10-30 rpm |
| `budget` (time) | `Agent(max_execution_time=...)` seconds | 300 s worker task, 900 s research task |
| `budget` (calls/tokens) | Not native per-run — `step_callback` ledger + post-hoc `crew.usage_metrics` | 40 tool calls per kickoff |
| `success_predicate` | `Task(guardrail=...)` returning `(True, output)` with a machine check + precise `expected_output` | Guardrail on every typed handoff task |
| `no_progress` | Not native — `step_callback` state-hash window | Window 2 (hub canon) |
| `oscillation` | Not native — `step_callback` A-B-A-B signature window | Window 4 (hub canon) |
| `escalation_trigger` | `Task(human_input=True)`; guardrail `max_retries` exhausted ends the run with the failure | `human_input=True` on every irreversible task |

CrewAI natively covers `max_iterations` and two `budget` denominations. The
detector-style conditions (`no_progress`, `oscillation`) require the
callback ledger shown in `references/role_engineering_patterns.md` section 6.
A crew relying only on `max_iter` is the hub's "guard subset" anti-pattern.

### The HITL gate: `human_input=True`

```python
release_notes = Task(
    description="Draft the public release notes for version {version}.",
    expected_output="Markdown release notes ready to publish.",
    agent=writer,
    human_input=True,   # pause for human review before this output is finalized
)
```

`human_input=True` pauses after the agent produces its output, collects human
feedback, and has the agent incorporate it before the task result is finalized
— CrewAI's native equivalent of the hub 5-Phase Protocol Phase 3 HUMAN GATE,
at task granularity. Caveat: the default runtime collects this input on the
console (blocking). For server/headless deployments you must front the crew
with your own approval UI (e.g., run the gated task in a Flow step that waits
on your queue) — do not ship `human_input` console gates to production
services and call them HITL.

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Trace shows repeated "Delegate work to coworker" / "Ask question to coworker" bouncing between two agents | Delegation loop: multiple workers with `allow_delegation=True` and overlapping personas | `allow_delegation=False` on all workers; add mutual-exclusion clauses to backstories ("You never X"); cap `max_iter` |
| Tool raises validation/type errors repeatedly, agent retries with different malformed args | Hallucinated tool args: tool lacks typed `args_schema` or has a vague description | `BaseTool` subclass with Pydantic `args_schema`, per-field descriptions, one usage example in the tool description |
| Hierarchical crew is slow; manager answers tasks itself or re-does worker output | Manager bottleneck: weak `manager_llm`, or manager included in `agents` list, or too many tasks through one manager | Frontier-tier manager model; custom `manager_agent` with "you never execute work yourself" backstory; keep manager out of `agents=[...]`; split the crew |
| `KeyError` at kickoff | `{placeholder}` in a description/goal has no matching key in `kickoff(inputs={...})` | Audit every `{...}` token; pass all keys; use `kickoff_for_each` for batches |
| Final answers degrade late in the run; context-window errors | Context bloat: every task lists all prior tasks in `context` | Pass only the tasks actually needed; move large artifacts to `output_file` |
| Agent confidently repeats a stale/wrong fact across runs | Long-term memory pollution (`memory=True` persists across kickoffs) | `crewai reset-memories --all` (see reference section 4); scope what memory stores |
| Task loops N times then fails with guardrail error | Guardrail retry storm: guardrail always returns `False` with unactionable message | Return specific, fixable feedback in the `(False, "...")` message; keep `max_retries` at 2-3 |
| Agent rambles, output shape differs every run | Vague `expected_output` ("a good analysis") | Write measurable contracts: "A markdown table with exactly these 4 columns: ..." |

## Hub Canon Integration

- **5-Phase Protocol:** a well-run crew maps cleanly — DISCOVERY = read-only
  research tasks at the head of the task list; MANIFEST = a typed plan output
  (`output_pydantic`) from a planning task (or `planning=True`); HUMAN GATE =
  `human_input=True` on the task that approves the plan and on every
  irreversible task; IMPLEMENTATION = worker tasks consuming the approved
  plan via `context=[...]`; SELF-REVIEW & HANDOFF = a final QA task with a
  guardrail, reviewing all prior outputs.
- **Exit conditions:** declare the full mapping table above in the agent spec
  *before* the crew runs. Native controls (`max_iter`, `max_rpm`,
  `max_execution_time`) plus ledger-based `no_progress`/`oscillation`
  detection satisfy the six-type taxonomy; `max_iter`-only is the canonical
  guard-subset anti-pattern.
- **HARDENED gate (>= 90):** when a crew is wrapped as a hub agent spec, the
  spec must state each agent's bounds, the gated tasks, and the escalation
  path in prose the auditor can see. A spec that says "CrewAI handles limits"
  scores as unbounded. Run `scripts/crewai_runaway_auditor.py` on the crew
  source as the deterministic pre-check.
- **Trace detections:** CrewAI `verbose=True` logs and `step_callback` events
  give you the raw material for D1 (repeated identical tool call), D2
  (oscillation), and D3 (error cascade) style monitoring; the ledger in
  reference section 6 implements D2/D5 equivalents in-process.

## Python Tool

### scripts/crewai_runaway_auditor.py

Statically audits CrewAI Python source (via `ast` — the file is parsed, never
imported or executed) for missing runaway-prevention controls: agents without
`max_iter`, agents with neither `max_execution_time` nor `max_rpm`, tasks
missing `expected_output`, irreversible-verb tasks without `human_input=True`,
and hierarchical crews without a manager. Stdlib-only, `--json`, ASCII output.

```bash
python scripts/crewai_runaway_auditor.py path/to/crew.py
python scripts/crewai_runaway_auditor.py src/ --json      # scans *.py recursively
python scripts/crewai_runaway_auditor.py crew.py --strict # warnings also fail
```

Exit code 0 when no errors (no warnings in `--strict`), 1 otherwise. It is a
lint, not a proof: dynamically-built kwargs (`Agent(**cfg)`) are invisible to
it and reported as "unverifiable".

## When NOT to Use This Skill

- **Framework-agnostic persona and system-prompt design** (no CrewAI) — use
  **agent-designer**. This skill owns the CrewAI parameter surface
  (`role`/`goal`/`backstory` as constructor fields); the general craft of
  role prompts lives there.
- **Cyclic stateful graphs, checkpoint/resume, fine-grained state control** —
  use **langgraph-state-design**. CrewAI Flows branch and route; they are not
  a general cyclic state machine.
- **.NET / C# agent stacks** — use **microsoft-agent-framework**.
- **Ecosystem-level hardening** (gate validators, loop audits, the exit
  condition canon itself) — use **agentic-system-architect**; this skill
  implements that canon with CrewAI mechanisms.
- **Cross-provider model-tier routing strategy** — use **multi-llm-routing**;
  this skill only shows how to bind a chosen model to an agent.
- **Framework-neutral workflow scaffolding** — use **agent-workflow-designer**.

## References

| File | Summary |
|------|---------|
| `references/role_engineering_patterns.md` | Backstory patterns that change behavior, goal scoping, delegation rules, hierarchical/manager configuration, memory depth (embedder, reset-memories), HITL gates, and the runaway-prevention ledger |
| `references/crewai_tools_tasks_outputs.md` | LLM assignment and tiering, custom tools (@tool, BaseTool, args_schema), kickoff inputs and {placeholder} interpolation, kickoff_for_each, structured outputs (output_pydantic/output_json/output_file), task guardrails, async execution, callbacks and usage metrics |
| `references/crewai_flows_and_projects.md` | Crews vs Flows decision, Flow anatomy (@start/@listen/@router, typed state), crews inside flows, and the YAML agents.yaml/tasks.yaml + @CrewBase project pattern |

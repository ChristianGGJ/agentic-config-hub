---
title: "Agentic System Architect - Four-Pillar Ecosystem Design — Core Agentic Design & Loop Safety"
description: "Use when the user asks to design complete agentic configuration ecosystems (context, skills, agents, workflows), harden autonomous agents with. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Agentic System Architect - Four-Pillar Ecosystem Design

<div class="page-meta" markdown>
<span class="meta-badge">:material-robot: Core Agentic Design</span>
<span class="meta-badge">:material-identifier: `agentic-system-architect`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-system-architect/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install core-agentic-design</code>
</div>


**Tier:** POWERFUL
**Category:** Engineering
**Tags:** AI agents, loop engineering, ReAct, human-in-the-loop, prompt engineering, architecture, orchestration

## Overview

Most agent failures are not intelligence failures - they are architecture failures. Agents run away in loops because nobody engineered exit conditions. They take irreversible actions because nobody placed an approval gate in front of them. They drift out of scope because context, skills, agents, and workflows were designed as isolated artifacts instead of one coherent ecosystem.

This skill turns agent design into systems architecture. It provides a repeatable method for designing **complete agentic configuration ecosystems** built on four pillars - `context/`, `skills/`, `agents/`, `workflows/` - and hardens every component with three advanced disciplines:

1. **Loop Engineering** - self-reflection, evaluation, and error-mitigation loops with explicit exit conditions and counters, so no agent can run unbounded.
2. **ReAct Reasoning Patterns** - Thought -> Action -> Observation cycles, Reflexion, and Plan-and-Execute, so agent reasoning is inspectable and auditable.
3. **Defensive Human-in-the-Loop (HITL) Flow Control** - the 5-Phase Protocol with hard human approval gates, so irreversible actions never happen without explicit human consent.

The skill ships four deterministic Python tools that scaffold ecosystems, audit agent configs against a 100-point loop-safety rubric, analyze ReAct execution traces for runaway patterns, and validate workflows for HITL gate coverage. No LLM calls, no network calls - every check is reproducible.

## When to Use This Skill

Use this skill when the user asks to:

- Design a full agent ecosystem for a project or team (multiple agents, shared context, orchestrated workflows)
- Harden an existing agent against runaway loops, infinite retries, or unbounded tool usage
- Add exit conditions, iteration counters, or budget limits to an autonomous agent
- Apply ReAct, Reflexion, or Plan-and-Execute reasoning structure to an agent
- Add human approval gates to a workflow that performs irreversible actions
- Implement the 5-Phase Protocol (Discovery, Manifest, Human Gate, Implementation, Self-Review) for agent-driven changes
- Audit an agent configuration or workflow for autonomy-safety controls
- Analyze a ReAct trace to diagnose why an agent looped, oscillated, or failed to converge

### When NOT to Use This Skill

- **Designing a single agent's persona, tools, and prompt** with no ecosystem, loop, or HITL concerns -> use **agent-designer**. This skill takes over when that agent must live inside a controlled ecosystem or run autonomously.
- **Plain workflow scaffolding** (sequencing steps, wiring handoffs) without defensive gates or loop controls -> use **agent-workflow-designer**. This skill takes over when the workflow contains irreversible actions or autonomous loops.

## The Four-Pillar Architecture

A complete agentic ecosystem is organized as four directories, each with a single responsibility:

```
project/
  context/      # Pillar 1: What the system knows
  skills/       # Pillar 2: What the system can do
  agents/       # Pillar 3: Who does the work
  workflows/    # Pillar 4: How work is sequenced and gated
```

### Pillar 1: context/

**Purpose:** The knowledge substrate. Context packs capture project boundaries, domain vocabulary, architecture constraints, coding standards, and "never do" rules. Context is read-only reference material - it holds no procedures and takes no actions.

**Contents:** One context pack per domain area (e.g., `context/codebase-map.md`, `context/security-boundaries.md`). Use `assets/context-pack-template.md` as the starting point.

### Pillar 2: skills/

**Purpose:** Atomic, reusable capabilities. A skill packages one procedure - the steps, the checks, the output contract - independent of any specific agent. Skills consume context; they never duplicate it.

**Contents:** One directory per skill with a SKILL.md following `assets/atomic-skill-template.md`.

### Pillar 3: agents/

**Purpose:** Role-bound executors. An agent binds a persona to a set of skills, a tool allowlist, explicit boundaries, loop-safety controls, and an output contract. Agents are where autonomy lives - and therefore where loop engineering and boundary control are mandatory.

**Contents:** One .md spec per agent following `assets/agent-spec-template.md`. Every agent spec must score >= 90 (HARDENED) on `loop_auditor.py` before deployment.

### Pillar 4: workflows/

**Purpose:** Orchestration with defense. A workflow sequences agents and skills into a multi-step process, marks irreversible steps, places human gates in front of them, and defines rollback and escalation. Workflows are where HITL flow control is enforced.

**Contents:** One .md per workflow following `assets/workflow-template.md`, each embedding a machine-validatable JSON definition. Every workflow must PASS `hitl_gate_validator.py` before deployment.

### Knowledge Flow

Knowledge flows in one direction: **context -> skills -> agents -> workflows**.

- Context packs feed facts and boundaries into skills.
- Skills feed procedures into agents.
- Agents feed capabilities into workflows.
- Workflows never define knowledge; agents never define orchestration; skills never define personas; context never defines procedures.

### Atomicity Rule

Every component does exactly one thing and declares its inputs and outputs. A skill that does two jobs becomes two skills. An agent that plays two roles becomes two agents. A workflow step that mixes an action with its verification becomes an action step plus a check step. Atomic components are testable, auditable, and swappable; monolithic ones are none of those.

## Advanced Disciplines

### Discipline 1: Loop Engineering

Autonomous agents iterate: retry on failure, reflect on output, re-plan on surprise. Every loop an agent runs must be engineered with an explicit exit condition and a counter - an un-engineered loop is a runaway waiting to happen.

**The four loop patterns:**

| Loop | Purpose | Typical exit |
|------|---------|--------------|
| Self-reflection loop | Critique own output against criteria, revise until acceptable | success_predicate or max_iterations |
| Evaluator-optimizer loop | A separate evaluator scores output against a rubric; the optimizer revises | success_predicate or max_iterations |
| Error-mitigation loop | Classify a failure, retry with an adjusted strategy | max_iterations or escalation_trigger |
| Convergence loop | Iterate toward a machine-checkable goal, guarded by the full taxonomy | success_predicate or budget |

**Exit-Condition Taxonomy (6 canonical types):**

| Exit condition | Definition | Example |
|----------------|------------|---------|
| `max_iterations` | Hard ceiling on loop cycles; the loop terminates when the counter reaches the limit | "Retry the failing test at most 3 times" |
| `no_progress` | Terminate when N consecutive iterations produce no state change | "Stop if two consecutive fix attempts leave the same tests failing" |
| `oscillation` | Terminate when the agent alternates between the same states or actions (A-B-A-B) | "Stop if the agent re-applies and reverts the same edit" |
| `budget` | Terminate on resource exhaustion: tokens, time, tool calls, or cost | "Stop after 50 tool calls or 10 minutes" |
| `success_predicate` | Terminate when a machine-checkable success condition holds | "Stop when all tests pass and lint is clean" |
| `escalation_trigger` | Terminate by handing off to a human when a defined condition fires | "Escalate to the on-call reviewer after the 3rd distinct error class" |

**Rules of loop engineering:**

1. Every loop declares at least one exit condition from the taxonomy - `success_predicate` alone is never enough; pair it with a bounding condition (`max_iterations` or `budget`).
2. Every loop maintains a visible counter (iteration number, error count, budget consumed) that appears in the agent's reasoning trace.
3. Every exit path defines what happens next: return a result, degrade gracefully, or escalate to a human.
4. Nested loops multiply risk - the product of inner and outer bounds must stay within the overall budget.

**Example loop specification (as written into an agent spec):**

```
Loop: fix-and-verify
  Body: apply candidate fix, run test suite
  Counter: attempt (starts at 1, incremented per cycle)
  Exit conditions:
    - success_predicate: all tests pass -> return diff
    - max_iterations: attempt > 3 -> escalation_trigger: hand off
      to human reviewer with failure log
    - no_progress: same tests fail on two consecutive attempts ->
      abort and report
```

See `references/loop_engineering_patterns.md` for the full pattern catalog.

### Discipline 2: ReAct Reasoning Patterns

ReAct (Reasoning + Acting) structures agent execution as an auditable cycle:

```
Thought  -> the agent states what it believes and what it intends to do next
Action   -> the agent invokes exactly one tool with explicit input
Observation -> the agent records what the tool returned
(repeat until an exit condition fires, then emit a final answer)
```

Every step carries all three parts. A step missing its Thought is an unexplained action; a step missing its Observation is an unverified action - both are contract violations that `react_trace_analyzer.py` flags (detection D4).

**Pattern variants:**

- **Plain ReAct** - the base Thought -> Action -> Observation cycle; best for exploratory tasks where each observation informs the next step.
- **Reflexion** - after a failure or at fixed checkpoints, the agent produces a self-critique that is fed back into the next Thought; best for tasks with verifiable feedback (tests, validators).
- **Plan-and-Execute** - the agent first emits a complete plan, then executes steps against it, re-planning only on deviation; best for multi-step tasks with a knowable structure, and the natural fit for the 5-Phase Protocol (the plan is the manifest).

Traces are captured in the canonical JSON schema (see `assets/sample_react_trace.json`) so they can be analyzed deterministically. See `references/react_reasoning_patterns.md` for selection guidance and anti-patterns.

### Discipline 3: Defensive Human-in-the-Loop (HITL) Flow Control

Autonomy is granted per-phase, never globally. The core instrument is the 5-Phase Protocol:

**The 5-Phase Protocol:**

- **Phase 1 - DISCOVERY (read-only):** map scope, constraints and boundaries. No writes allowed.
- **Phase 2 - MANIFEST:** produce an explicit change manifest (files to create/modify, risks, rollback plan).
- **Phase 3 - HUMAN GATE:** hard stop. A human approves, edits, or rejects the manifest. No implementation without approval.
- **Phase 4 - IMPLEMENTATION:** bounded execution strictly against the approved manifest. Any deviation returns to Phase 2.
- **Phase 5 - SELF-REVIEW & HANDOFF:** audit own diff against the manifest, run verification, produce a handoff report.

**Defensive design rules:**

1. Every irreversible action (delete, deploy, publish, send, migrate) either requires explicit approval on the step itself or sits downstream of a gate step in the dependency chain (validator rule R1).
2. Every irreversible action defines a rollback plan, or explicitly justifies why none exists (rule R2).
3. Every workflow defines an escalation path - who gets called, and what triggers the call (rule R3).
4. Failure handling is explicit on every action step: retry (with a bounded count), escalate, or abort (rule R4).
5. The final step of a workflow is a self-review check (rule R6) - the agent audits its own output before handoff.

**Gate placement heuristic:** classify every step as reversible (retry freely), recoverable (rollback exists - gate optional, rollback mandatory), or irreversible (gate mandatory upstream). When in doubt, treat a step as irreversible; a redundant gate costs seconds, a missing one costs incidents.

See `references/hitl_defensive_architectures.md` for gate placement strategies and escalation design.

## Python Tools

All tools are Python 3.8+, standard library only, with `--help`, a `--json` flag for machine-readable output, and human-readable output by default. Exit code 0 on success, 1 on error. Output is ASCII-safe (no emoji, no box-drawing characters). No LLM or network calls.

### 1. ecosystem_scaffolder.py

**Purpose:** Generate the four-pillar directory skeleton for a new agentic ecosystem, pre-populated with the templates from `assets/`.

**Key flags:**
- `name` (positional) - project/ecosystem name (kebab-case)
- `--output` - parent directory for the scaffold (default: current directory)
- `--pillars` - comma-separated subset of pillars to scaffold: `context,skills,agents,workflows` (default: all four; the root README.md is always created)
- `--dry-run` - print the file plan without writing anything
- `--force` - overwrite the target directory if it already exists
- `--json` - machine-readable file plan

**Usage examples:**

```bash
python scripts/ecosystem_scaffolder.py my-project --output ./ --dry-run
python scripts/ecosystem_scaffolder.py my-project --output ./ecosystems --json
```

### 2. loop_auditor.py

**Purpose:** Score an agent configuration .md against the 100-point loop-safety rubric: Loop Safety (30), HITL Gates (25), Phase Protocol (20), Boundary Control (15), Output Contract (10). Checks are deterministic case-insensitive regex matches - no interpretation, fully reproducible.

**Key flags:**
- `file` (positional) - agent config .md file to audit
- `--json` - machine-readable report with per-check results
- `--min-score` - fail (exit 1) if the score is below this threshold; use `--min-score 90` as the CI deployment gate

**Grades:** >= 90 HARDENED, 75-89 PRODUCTION-READY, 50-74 NEEDS-CONTROLS, < 50 UNSAFE-FOR-AUTONOMY. The report includes a per-category breakdown and a remediation hint for every failed check.

**Usage examples:**

```bash
python scripts/loop_auditor.py path/to/agent.md --json
python scripts/loop_auditor.py agents/deploy-agent.md --min-score 90
```

### 3. react_trace_analyzer.py

**Purpose:** Analyze a ReAct execution trace (canonical JSON schema) for runaway patterns. Runs seven detections:

| ID | Detection | Severity |
|----|-----------|----------|
| D1 | Repeated identical action (same tool+input >= 3 times) - "action loop" | CRITICAL |
| D2 | Oscillation: alternating A-B-A-B actions in a window of 4 | HIGH |
| D3 | Consecutive error statuses >= budget.max_errors (default 3) - "error cascade" | HIGH |
| D4 | Step missing thought or observation - "ReAct contract violation" | MEDIUM |
| D5 | len(steps) >= budget.max_steps - "budget overrun" | CRITICAL |
| D6 | final_answer null/absent while last step status is ok - "no convergence" | MEDIUM |
| D7 | Identical thought text >= 3 times - "reasoning loop" | MEDIUM |

**Health score:** starts at 100; subtract 30 per CRITICAL, 15 per HIGH, 5 per MEDIUM (floor 0). Verdicts: >= 90 HEALTHY, 60-89 DEGRADED, < 60 RUNAWAY.

**Key flags:**
- `trace` (positional) - trace JSON file
- `--json` - machine-readable findings and score

**Usage examples:**

```bash
python scripts/react_trace_analyzer.py assets/sample_react_trace.json
python scripts/react_trace_analyzer.py logs/session-42.json --json
```

### 4. hitl_gate_validator.py

**Purpose:** Validate a workflow definition for defensive HITL coverage. Accepts a workflow JSON file directly, or a .md file - in which case it extracts the first fenced json code block. Applies six rules:

| ID | Rule | Severity |
|----|------|----------|
| R1 | Every irreversible step requires approval or an upstream gate (via depends_on chain) | CRITICAL |
| R2 | Every irreversible step defines a non-null rollback (or "none:justified:...") | HIGH |
| R3 | The workflow defines the top-level escalation object | HIGH |
| R4 | Every action step defines on_failure; retry requires max_retries >= 1 | MEDIUM |
| R5 | All depends_on references exist and the dependency graph is acyclic | MEDIUM |
| R6 | The final step should be type=check (self-review) | LOW |

**Result:** PASS if no CRITICAL and no HIGH violations, otherwise FAIL. Every violation is reported with rule id, step id, and a remediation hint.

**Key flags:**
- `workflow` (positional) - workflow .json or .md file
- `--json` - machine-readable violation report

**Usage examples:**

```bash
python scripts/hitl_gate_validator.py assets/workflow-template.md
python scripts/hitl_gate_validator.py workflows/release.json --json
```

## End-to-End Workflow

Ecosystem design itself follows the 5-Phase Protocol. The architect agent practices what it enforces:

### Phase 1 - DISCOVERY (read-only)

Absorb the project's existing documentation: README, architecture docs, CLAUDE.md, coding standards, deployment procedures. Map the domain areas, the roles humans currently play, the actions that are irreversible in this project, and the boundaries no agent may cross. No files are written in this phase.

### Phase 2 - MANIFEST

Produce a component inventory: every context pack, skill, agent, and workflow to be created, with one-line purposes, the exit conditions each agent's loops will use, the gates each workflow will contain, and the risks and rollback plan for introducing the ecosystem.

### Phase 3 - HUMAN GATE

Present the inventory to the human. They approve it, edit it (add/remove components, tighten boundaries), or reject it. Nothing is scaffolded until the inventory is approved. This is a hard stop.

### Phase 4 - IMPLEMENTATION

Run `ecosystem_scaffolder.py` to create the approved structure, then author each component strictly against the approved inventory using the templates in `assets/`: context packs from `context-pack-template.md`, skills from `atomic-skill-template.md`, agents from `agent-spec-template.md`, workflows from `workflow-template.md`. Any component not in the approved inventory triggers a return to Phase 2.

### Phase 5 - SELF-REVIEW & HANDOFF

Run `loop_auditor.py` on every generated agent spec and `hitl_gate_validator.py` on every generated workflow. Fix anything below threshold. Produce a handoff report: components created, audit scores, validator results, open risks, and recommended first pilot workflow.

## Operating Modes

### GENERAL Mode

No project documentation is available or the user wants stack-agnostic output. The skill applies universal best practices: standard exit-condition defaults (max_iterations 3-5 per loop, budget of 20 tool calls per task), generic boundary language, and role archetypes (researcher, implementer, reviewer, orchestrator). Output is a portable ecosystem the user adapts.

### CONTEXTUALIZED Mode

Project documentation exists. Phase 1 absorbs it into context packs, and from that point forward every generated component aligns to those boundaries: agent tool allowlists reflect the project's real toolchain, workflow gates sit in front of the actions that are actually irreversible in this project, skills reference the project's real commands and paths, and forbidden paths come from the project's own rules. Contextualized ecosystems are strictly safer - prefer this mode whenever documentation exists.

**Mode selection:** ask the user for architecture docs, standards, and deployment procedures at the start of Phase 1. If they provide any, run CONTEXTUALIZED; if not, run GENERAL and flag in the handoff report that boundaries were assumed rather than derived, listing each assumption for human confirmation.

## References

| File | Summary |
|------|---------|
| `references/loop_engineering_patterns.md` | Pattern catalog for self-reflection, evaluator-optimizer, error-mitigation, and convergence loops, with the full exit-condition taxonomy and counter design |
| `references/react_reasoning_patterns.md` | ReAct, Reflexion, and Plan-and-Execute in depth: when to use each, trace structure, and anti-patterns |
| `references/hitl_defensive_architectures.md` | Gate placement strategies, irreversibility classification, rollback design, and escalation paths |
| `references/four_pillar_ecosystem.md` | The context/skills/agents/workflows architecture: responsibilities, knowledge flow, atomicity, and directory conventions |

## Assets

| File | Purpose |
|------|---------|
| `assets/agent-spec-template.md` | Template for agent specs with loop-safety, boundary, and output-contract sections pre-structured to score HARDENED |
| `assets/workflow-template.md` | Template for gated workflows with an embedded canonical JSON definition that passes the validator |
| `assets/context-pack-template.md` | Template for context packs: boundaries, vocabulary, constraints, never-do rules |
| `assets/atomic-skill-template.md` | Template for atomic skills: single procedure, inputs, outputs, checks |
| `assets/sample_react_trace.json` | Example ReAct trace in the canonical schema, usable as analyzer input and as a logging format reference |

## Related Skills

- **agent-designer** - designs a single agent's persona, prompt, and tools; this skill designs the ecosystem that agent lives in and hardens it for autonomy.
- **agent-workflow-designer** - scaffolds plain multi-step workflows; this skill adds the defensive layer (gates, rollback, escalation) required when steps are irreversible.
- **prompt-governance** - governs prompt quality and versioning; this skill governs runtime behavior (loops, gates, boundaries) of the agents those prompts drive.
- **spec-driven-workflow** - drives implementation from written specs; this skill's manifest phase is the agentic counterpart, and the two compose naturally.

## Quality Checklist

Before an ecosystem ships, verify:

- [ ] All four pillars exist and each component lives in the correct pillar
- [ ] Knowledge flows one way: context -> skills -> agents -> workflows (no back-references)
- [ ] Every component is atomic: one job, declared inputs, declared outputs
- [ ] Every agent loop declares at least one bounding exit condition (`max_iterations` or `budget`) plus its success path
- [ ] Every generated agent scores >= 90 (HARDENED) on `loop_auditor.py`
- [ ] Every workflow PASSES `hitl_gate_validator.py` (zero CRITICAL, zero HIGH violations)
- [ ] Every irreversible step has an upstream gate or explicit approval, and a rollback plan
- [ ] Every workflow defines an escalation contact and trigger
- [ ] Every workflow ends with a type=check self-review step
- [ ] ReAct traces are logged in the canonical schema so `react_trace_analyzer.py` can audit production runs
- [ ] The handoff report lists all components, audit scores, and validator results

An ecosystem that fails any CRITICAL or HIGH item is not production-ready. Fix, re-audit, and only then hand off.

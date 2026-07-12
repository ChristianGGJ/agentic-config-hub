---
name: "agent-workflow-designer"
description: "Use when designing multi-step agent workflows: selecting a workflow pattern (sequential, parallel, router, orchestrator, evaluator), defining typed handoff contracts between steps, scaffolding validatable workflow configs, or budgeting context and cost across steps."
---

# Agent Workflow Designer

**Tier:** POWERFUL
**Category:** Engineering
**Domain:** Multi-Agent Systems / AI Orchestration

## Overview

A workflow is the unit of orchestration: agents bound to steps, steps wired into a
dependency graph, and data moving between them under an explicit contract. Most
workflow failures are design failures - the wrong pattern for the dependency shape,
handoffs that pass entire transcripts instead of artifacts, or step graphs that no
validator can check.

This skill owns the **step level** of workflow design: choosing the pattern,
defining handoff contracts for every edge, budgeting context and cost per step, and
scaffolding configs in the **hub canonical workflow schema** - the same step shape
(`id` / `type` / `irreversible` / `depends_on` / `on_failure` / `escalation`)
validated by the agentic-system-architect skill's `hitl_gate_validator.py`. Every
config this skill scaffolds passes that validator as generated.

## Core Capabilities

- Pattern selection with explicit trade-offs and calibrated defaults
- Canonical-schema config scaffolding via `scripts/workflow_scaffolder.py`
- Deterministic structural validation (`--validate` mode: required keys, dangling
  references, acyclic dependency graph, retry policy sanity)
- Typed handoff contracts with per-edge validation rules
- Context and cost discipline: per-step token budgets, artifact passing, truncation policy

## Decision Framework: Pattern Selection

Pick the pattern from the dependency shape, not from ambition. Start with the
smallest pattern that satisfies requirements; upgrade only on a named trigger.

| Pattern | Dependency shape | Latency | Token cost | Debuggability | Choose when |
|---|---|---|---|---|---|
| `sequential` | Linear chain, each step needs prior output | Sum of steps | Lowest | Easiest | <= 5 dependent steps, one deliverable |
| `parallel` | Independent subtasks + one fan-in | Max of branches + fan-in | Sum of branches | Medium | >= 3 independent subtasks, results merge |
| `router` | Mutually exclusive branches | Classify + 1 branch | Low (one branch runs) | Medium | Known input categories, <= 8 routes |
| `orchestrator` | Structure unknown at design time | Highest | Highest | Hardest | Dynamic decomposition genuinely required |
| `evaluator` | Generate/score loop | Steps x iterations | x iterations | Medium | Machine- or rubric-checkable quality bar |

**Upgrade triggers** (only reasons to move down the table): a sequential chain
where >= 3 steps have no data dependency -> `parallel`; a step whose prompt
branches on input type -> `router`; requirements that cannot be decomposed into a
fixed step list at design time -> `orchestrator`; a deliverable rejected more than
once by review -> add an `evaluator` loop around the failing step.

**Calibrated defaults** (override with reasons, not habits):

| Parameter | Default | Rationale |
|---|---|---|
| Steps per workflow | <= 12 | Beyond this, split into two workflows with one handoff |
| `max_retries` per action step | 2 | Third identical failure is a signal, not noise |
| Per-step timeout | 300 s | Catches hung tool calls without killing long steps |
| Per-step token budget | 8,000 (16,000 for fan-in/synthesis) | Forces artifact passing over transcript passing |
| Parallel fan-out width | <= 5 | Diminishing returns and fan-in overload beyond 5 |
| Router routes | <= 8 + mandatory `__default__` fallback | Classification accuracy degrades with route count |
| Evaluator `max_iterations` | 3 | Most gains occur in iterations 1-2 |
| Evaluator `pass_threshold` | 0.8, calibrated on golden samples | Uncalibrated thresholds cause loop exhaustion |
| Workflow budget | 50 tool calls / 60k tokens / 30 min | Maps to the `budget` exit condition |

Per-pattern depth (trade-offs, failure modes, when NOT to use, complete worked
configs): `references/workflow-patterns.md`.

## Canonical Workflow Schema

Scaffolded configs use the hub canonical schema so that one artifact serves
design, execution, and validation:

- **Root:** `name`, `version`, `pattern`, `agents` (id -> role map), `budget`,
  `steps`, `escalation` (`contact` + `trigger` - required).
- **Step:** `id`, `type` (`action` | `gate` | `check`), `agent`, `description`,
  `irreversible`, `requires_approval`, `rollback`, `on_failure`
  (`retry` | `escalate` | `abort`), `max_retries`, `depends_on`, `budget`.
- **Pattern metadata rides on extra fields** the validators tolerate: `route`
  on router handlers, `join` (`all` | `any`) on fan-in steps, `loop` on
  evaluator steps, `execution` at the orchestrator root.
- **The `depends_on` graph is always a DAG.** Iteration is declared as a `loop`
  object (`target`, `max_iterations`, `pass_threshold`, `exit_conditions`,
  `on_exhaustion`) - never as a back-edge. A back-edge fails both this skill's
  `--validate` and the flagship's R5 cycle check.
- **The final step is `type: check`** - a self-review that audits the output
  before handoff (flagship rule R6).

Handoff contract fields, edge validation rules, and state management:
`references/handoff-contracts.md`.

## Tools

### workflow_scaffolder.py

Python 3.8+, stdlib only, ASCII-safe output, no LLM/network calls.

```bash
# Scaffold (prints canonical JSON; --output writes a file)
python scripts/workflow_scaffolder.py sequential --name content-pipeline
python scripts/workflow_scaffolder.py orchestrator --name release --output workflows/release.json

# Validate structure (exit 0 = PASS, 1 = ERROR findings or I/O error)
python scripts/workflow_scaffolder.py --validate workflows/release.json
python scripts/workflow_scaffolder.py --validate workflows/release.json --json
```

`--validate` checks: required root keys and escalation object, step types,
unique ids, dangling `depends_on` and agent references, acyclic graph,
`retry` => `max_retries >= 1`, gate steps set `requires_approval`, loop objects
name canonical exit conditions, final step is a check. It does **not** apply
defensive gate rules R1-R6 for irreversible steps - that is
agentic-system-architect territory; the tool emits a routing warning instead.

## Recommended Workflow

1. **Shape the dependency graph first.** List subtasks and true data
   dependencies; the shape names the pattern (table above).
2. **Scaffold** with `workflow_scaffolder.py`; rename agents and steps to the
   real roles.
3. **Write the handoff contract for every edge** using the typed fields in
   `references/handoff-contracts.md` - what the receiving step gets, its budget,
   and what makes the payload invalid.
4. **Assign budgets**: per-step token/timeout, workflow-level totals. Sum of
   step budgets (including loop iterations at `max_iterations`) must not exceed
   the workflow budget.
5. **Validate**: run `--validate`, then run agentic-system-architect's
   `hitl_gate_validator.py` before deployment (mandatory once any step is
   irreversible).
6. **Dry-run at half budgets** on a sample input before scaling; budget
   overruns at half scale predict runaway at full scale.

## Context and Cost Discipline

The claimed discipline, as a procedure:

1. **Budget per step, not per workflow.** Assign each step a `budget.max_tokens`
   sized to its output artifact (default 8k; fan-in 16k), then set the workflow
   budget to `sum(step budgets x expected iterations) x 1.25` headroom.
2. **Pass artifacts, never transcripts.** A handoff carries named artifacts with
   a `summary` and `tokens_estimate` each (see the contract reference). The
   receiving step gets the artifact plus a <= 200-token summary of upstream
   context - not the upstream conversation.
3. **Truncation policy is declared, not improvised.** When an artifact exceeds
   the edge budget: summarize at the producing step (preferred), or truncate
   tail-first with an explicit `truncated: true` marker the consumer can see.
   Silent truncation is the number-one cause of "the synthesizer ignored branch
   C" bugs.
4. **Meter and stop.** The executor increments token/tool-call counters at every
   step boundary; crossing the workflow budget fires the `budget` exit condition
   and routes to `escalation` - it never "finishes the current phase first".

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Fan-in output ignores a branch | Branch artifact exceeded edge budget and was silently truncated | Summarize at source; mark truncation explicitly; raise fan-in budget to 2x branch average |
| Router sends most inputs to fallback | Routes overlap or classify step lacks per-route examples | Rewrite routes as mutually exclusive with 2-3 examples each; keep `__default__` for genuine unknowns |
| Evaluator loop always exits on `max_iterations` | `pass_threshold` never calibrated, or rubric drifts between iterations | Calibrate threshold on golden samples; freeze the rubric text for the whole run |
| Orchestrator re-plans every step | Plan granularity too fine - every observation looks like a deviation | Plan at milestone level; re-plan only when a milestone becomes impossible |
| Cost 3-10x the estimate | Full transcripts passed as context on every edge | Apply the cost discipline procedure above; check `tokens_estimate` on every handoff |
| Workflow never terminates | `depends_on` cycle, or `join: all` waiting on a route that never ran | Run `--validate` (catches cycles); use `join: any` for post-router convergence |
| Same input takes different paths per run | Nondeterministic classification with no tie-break rule | Add explicit tie-break + confidence floor routing to `__default__` |
| Retry storms on a failing step | `on_failure: retry` with no error classification | Retry only transient errors; `escalate` on repeated identical failure (that is `no_progress`, not bad luck) |

## Hub Canon Integration

Workflow mechanics map onto the hub's 6 canonical exit-condition types:

| Exit condition | Where it lives in a workflow config |
|---|---|
| `max_iterations` | `loop.max_iterations` on evaluator steps; `max_retries` on action steps |
| `no_progress` | `loop.no_progress_window`: exit when N consecutive iterations do not improve the score |
| `oscillation` | Executor detects A-B-A-B accept/revert of the same revision across loop iterations |
| `budget` | Root `budget` object (tokens, tool calls, wall clock) + per-step `budget` |
| `success_predicate` | `loop.pass_threshold`; every `type: check` step's pass criterion |
| `escalation_trigger` | Root `escalation` object + `on_failure: escalate` / `loop.on_exhaustion` |

Every loop declares `success_predicate` **plus** a bounding condition
(`max_iterations` or `budget`) - a success predicate alone is an unbounded loop.

The orchestrator template mirrors the 5-Phase Protocol: `plan` = MANIFEST,
`approve-plan` (a `type: gate` step) = HUMAN GATE, the execute steps =
IMPLEMENTATION, `verify` = SELF-REVIEW & HANDOFF.

**Deployment gates** (owned by agentic-system-architect, run by name): workflows
must PASS `hitl_gate_validator.py` (rules R1-R6); every agent bound to a step
should score >= 90 (HARDENED) on `loop_auditor.py` before it runs autonomously.

## When NOT to Use This Skill

- **Designing a single agent's persona, prompt, and tools** -> use
  **agent-designer**. This skill assumes agents exist and wires them into steps.
- **Agent-topology architecture** (supervisor vs swarm vs hierarchical role
  structures, who-talks-to-whom) -> use **agent-designer**; this skill expresses
  the chosen topology as a step graph.
- **Irreversible actions, HITL gate placement, rollback and escalation design,
  ecosystem governance, or gate validation** -> use **agentic-system-architect**.
  The moment any step is `irreversible: true`, that skill's rules and validator
  are mandatory.
- **Dispatching parallel Claude Code sessions / agent registries** -> use
  **agenthub**; its fan-out is session coordination, this skill's fan-out is a
  step-graph shape.
- **Framework-specific implementation** of a designed workflow -> use
  **langgraph-state-design**, **crewai-role-engineering**, or
  **microsoft-agent-framework**. Configs here are framework-neutral.

## References

| File | Summary |
|---|---|
| `references/workflow-patterns.md` | The five patterns in depth: trade-offs, failure modes, when NOT to use, and one complete canonical-schema config each |
| `references/handoff-contracts.md` | Typed handoff contract, full example payloads, edge validation rules, state management, and an end-to-end incident-triage worked example |

## Quality Checklist

- [ ] Pattern chosen from dependency shape via the decision table
- [ ] Config in canonical schema; `--validate` passes with zero ERROR findings
- [ ] `hitl_gate_validator.py` (agentic-system-architect) PASSES before deployment
- [ ] Every edge has a handoff contract with budget and validation rules
- [ ] Every loop declares `success_predicate` plus a bounding exit condition
- [ ] Workflow budget covers step budgets x max iterations with headroom
- [ ] Final step is a `type: check` self-review
- [ ] Escalation contact and trigger are real (a person/role, a condition)

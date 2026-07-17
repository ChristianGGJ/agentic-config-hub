---
title: "Slip-Driven Replanning — Project Planning & Requirements Elicitation"
description: "Use when a confirmed schedule slip must become a replan decision - inject reported delays into a plan for a CPM recompute, diff the baseline schedule. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Slip-Driven Replanning

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `slip-driven-replanning`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/slip-driven-replanning/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


**Tier:** STANDARD
**Category:** Planning / Execution Control
**Dependencies:** None. Python 3.8+ standard library only for both scripts; no network, no LLM calls.

## Description

Slip-driven-replanning turns a confirmed schedule slip into a deterministic, reviewable replan decision. It owns exactly one transformation: (slip event or variance report, current plan, baseline schedule, recomputed schedule) -> replan decision + deadline-impact report + notification draft.

The skill deliberately does NOT compute dates. The critical-path recompute engine is the **critical-path-scheduler** skill, consumed at AGENT level: the hosting agent runs `slip_injector.py` to update the plan, then that skill's CPM tool to produce a recomputed schedule, then `replan_impact.py` to diff the baseline against it and decide. The forward/backward pass is never re-implemented here, and every delta this skill reports is a calendar-day date subtraction - working-day arithmetic stays in the scheduler skill.

The decision layer is a frozen table, not judgment: absorb slips that stay inside float, list compression candidates when the finish delta is tolerable, and escalate with a drafted notification when a milestone breaks or the delta exceeds the declared threshold. Rebaselining is always routed to a human gate - the hub's "gates before execution" rule - because a rebaseline is the irreversible act that erases variance history.

## Features

- **Slip injection** - `slip_injector.py` applies a slip event or a plan-baseline-tracking variance report onto `plan.json`, adjusting `duration_days` and recording per-task `slip_history`, all-or-nothing.
- **Never-resetting replan ledger** - every injection increments a plan-level `replan_ledger`; replans share one attempt budget, defeating the "replan-as-reset" loop pathology.
- **Deterministic impact diff** - `replan_impact.py` reports project finish delta, tasks entering/leaving the critical path, per-task slips, float consumption, and milestone breaches with hardness class.
- **Frozen decision table** - ABSORB / COMPRESS / ESCALATE selected by explicit rules, same inputs -> same decision, every run.
- **Notification drafting, never delivery** - ESCALATE emits ASCII payload text; per-tool formatting belongs to plan-ticket-export and transmission belongs outside scripts entirely.
- **Brooks's-Law guard** - the crash option is never recommended as a default; every compression candidate list carries the warning.
- **CI-wireable exit codes** - 0 = ABSORB, 1 = findings (COMPRESS or ESCALATE), 2 = usage/input error; an agent or workflow can branch on the code alone.

## Interface

### Inputs

**plan.json** (hub canonical shape; extra fields tolerated, mirroring the id/depends_on contract that hitl_gate_validator rule R5 enforces on workflows):

```json
{
  "name": "website-relaunch",
  "version": "0.1.0",
  "tasks": [
    {"id": "frontend", "description": "...", "depends_on": ["design"],
     "duration_days": 8, "owner": "marta",
     "baseline_start": "2026-08-10", "baseline_finish": "2026-08-19",
     "milestone": false}
  ]
}
```

**slip_event.json**: `{"task_id": str, "reported_delay_days": number, "cause": str, "timestamp": str}`. Optional extra field `cause_class` in `estimate | dependency | resource | scope | external` (unknown values warn, never block).

**Variance report** (alternative slip source): the `--json` output of the plan-baseline-tracking skill. Minimal contract read by the injector: an object whose `variances` (or `tasks`) array has entries with `task_id` and `slip_days`; zero-slip entries are skipped.

**Schedule JSON contract** - the expected input of `replan_impact.py`, for both `baseline_schedule.json` and `recomputed_schedule.json`. This is the CPM-style output of the critical-path-scheduler skill:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `tasks[].id` | string | yes | unique per schedule |
| `tasks[].start` | ISO date | yes | alias `early_start` tolerated |
| `tasks[].finish` | ISO date | yes | alias `early_finish` tolerated |
| `tasks[].is_critical` | bool | no (default false) | critical-path membership |
| `tasks[].total_float_days` | number | no | omit = excluded from float analysis |
| `tasks[].milestone` | bool | no (default false) | implicit milestone detection |
| `project_finish` | ISO date | no | alias `project_finish_date` tolerated; defaults to max task finish |

**Milestone registry** (optional, `--milestones`): `{"milestones": [{"task_id": str, "deadline": "YYYY-MM-DD", "hardness": "contractual|internal|aspirational"}]}`. Hardness is mandatory in the registry - unclassified deadlines produce false escalations. When no registry is given, tasks flagged `milestone: true` fall back to their baseline finish as the deadline with hardness `unspecified`.

### Outputs

1. **Updated plan.json** (from `slip_injector.py`): adjusted `duration_days`, per-task `slip_history`, incremented `replan_ledger` - ready for the critical-path-scheduler recompute.
2. **Impact report** (from `replan_impact.py`, ASCII and `--json`): finish delta, critical-path entries/exits, task slips, float consumption, milestone breaches, decision + reason, compression candidates.
3. **Notification draft** (ESCALATE only): ASCII payload text naming the trigger, the delta, each breached milestone with its hardness class, and the gate options. Neutral content only - hand it to plan-ticket-export for Jira/Asana/Trello formatting. Nothing is ever transmitted.
4. **Replan-loop declaration** (`assets/replan-loop-declaration.md`): all six hub exit conditions pre-filled for any agent hosting autonomous replanning.

### Exit codes

| Code | slip_injector.py | replan_impact.py |
|------|------------------|------------------|
| 0 | updated plan written | decision ABSORB (no deadline impact) |
| 1 | validation findings, nothing written | findings: COMPRESS or ESCALATE |
| 2 | usage/input error | usage/input error |

## Usage

### The replan pipeline (agent-level composition)

1. **Detect** - the plan-baseline-tracking skill's variance gate fires (its exit-2 contract) or a human files a slip event.
2. **Inject** - `slip_injector.py` applies the slip onto `plan.json`. The plan is updated; no dates exist yet.
3. **Recompute** - the hosting agent runs the critical-path-scheduler skill's CPM tool on the updated plan. This skill never performs that step itself.
4. **Diff and decide** - `replan_impact.py` compares baseline vs recomputed schedule and emits the decision + report + draft.
5. **Gate** - COMPRESS and ESCALATE outputs become the replan manifest a human approves before anything irreversible (rebaseline, notification send, ticket updates) happens. The gate itself lives in the consuming workflow, not in this skill.

### Commands

```bash
# 1. Apply a slip event onto the plan
python scripts/slip_injector.py --plan assets/sample_plan.json \
    --slip-event assets/sample_slip_event.json --out updated_plan.json

# 1b. Or apply every nonzero slip from a plan-baseline-tracking report
python scripts/slip_injector.py --plan assets/sample_plan.json \
    --variance-report assets/sample_variance_report.json --out updated_plan.json --json

# 2. (outside this skill) recompute updated_plan.json with the
#    critical-path-scheduler skill's CPM tool -> recomputed_schedule.json

# 3. Diff baseline vs recomputed and decide
python scripts/replan_impact.py --baseline assets/sample_baseline_schedule.json \
    --recomputed assets/sample_recomputed_schedule.json \
    --milestones assets/sample_milestones.json \
    --slip-event assets/sample_slip_event.json --json
```

### Decision table

Evaluated top-down; first match wins. Deltas are calendar days between project finish dates; `--threshold-days` defaults to 5.

| Rule | Condition | Decision | Effect |
|------|-----------|----------|--------|
| 1 | any milestone breach (registry or implicit) | ESCALATE | notification draft emitted, exit 1 |
| 2 | finish delta > threshold | ESCALATE | notification draft emitted, exit 1 |
| 3 | 0 < finish delta <= threshold | COMPRESS | candidates on the new critical path listed with Brooks's-Law warning, exit 1 |
| 4 | finish delta <= 0 and no breach | ABSORB | slip absorbed in float, no replan, exit 0 |

## Examples

### Example 1 - ESCALATE: contractual milestone breach

The shipped samples model a frontend task slipping 4 days, pushing the project finish from 2026-08-28 to 2026-09-01 past a contractual launch deadline:

```bash
python scripts/replan_impact.py --baseline assets/sample_baseline_schedule.json \
    --recomputed assets/sample_recomputed_schedule.json \
    --milestones assets/sample_milestones.json --slip-event assets/sample_slip_event.json
```

Output (excerpt; full expected `--json` output ships as `assets/expected_impact_report.json`):

```
Project finish : baseline 2026-08-28 -> recomputed 2026-09-01 (delta +4 calendar days, threshold 5)
Decision       : ESCALATE (1 milestone breach(es), worst +4 days)
Critical-path changes:
  entered : frontend
  left    : cms-setup, content
Milestone breaches:
  launch (contractual): deadline 2026-08-28, forecast 2026-09-01 (+4 days)
```

Exit code 1 fires the consuming workflow's `escalation_trigger`; the notification draft rides along as the gate manifest.

### Example 2 - COMPRESS: delta within threshold, no breach

Same schedule pair, but the milestone registry grants the launch an aspirational deadline of 2026-09-02:

```bash
python scripts/replan_impact.py --baseline assets/sample_baseline_schedule.json \
    --recomputed assets/sample_recomputed_schedule.json \
    --milestones assets/sample_milestones_relaxed.json
```

The +4-day delta is under the 5-day threshold and no deadline breaks, so the decision is COMPRESS: the report lists `frontend`, `qa`, and `design` as candidates (longest calendar span first) with the mandatory Brooks's-Law warning, and exits 1 so the compression choice still passes through review. Running the baseline against itself yields ABSORB and exit 0.

## Replan Loop Declaration

Any agent hosting autonomous replanning must declare its exits from the hub six-type taxonomy, duplicated verbatim here per the portability rule (canonical definitions live in the agentic-system-architect flagship skill):

| Type | Fires when |
|------|-----------|
| `max_iterations` | Hard cap on loop count reached |
| `no_progress` | N consecutive iterations without measurable improvement |
| `oscillation` | The loop revisits previously seen states |
| `budget` | Token/time/cost ceiling exhausted |
| `success_predicate` | The goal condition is verifiably met |
| `escalation_trigger` | A condition requiring human judgment appears |

A pre-filled declaration for replan loops (3-cycle cap, replan-revert-replan oscillation window of 4 ledger entries, `replan_impact.py` exit 0 as the success predicate, exit 1 + ESCALATE as the escalation trigger) ships as `assets/replan-loop-declaration.md`. The `replan_ledger` written by `slip_injector.py` is the loop's shared attempt counter and never resets across replans. Decision scores and impact reports are readings presented at the gate, never a loop's exit condition (the self-eval constraint, inherited by citation).

## Anti-Patterns

Mined from the named sources in References; each row is checkable against this skill's outputs.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Crash-by-default | Every slip is answered with "add another person"; the late task gets later | Brooks's Law (The Mythical Man-Month, 1975/1995 ed.): ramp-up and communication overhead grow faster than capacity on late sequential work | The decision table never recommends crashing as a default; every candidate list carries the Brooks's-Law warning and names fast-tracking first |
| Replan-on-every-slip (schedule nervousness) | The plan changes weekly; owners stop trusting any date | Goldratt, Critical Chain (1997): slips inside float or buffer do not need a new plan; constant recuts destroy buffer management | ABSORB branch: finish delta <= 0 means no replan; plan and replan at milestone granularity (agent-workflow-designer heuristic, cited) |
| Optimistic re-forecast | The replanned date slips again next cycle by roughly the same amount | Planning fallacy (Kahneman and Tversky 1979; Kahneman 2011 ch. 23): the re-estimate repeats the inside-view error that caused the slip | Classify `cause_class` before selecting a strategy; anchor re-forecasts on the observed slip rate and reference-class data (Flyvbjerg), not fresh optimism |
| Rebaseline-to-hide-variance (rubber baseline) | Variance keeps resetting to zero while the finish date quietly walks right | GAO-16-89G: rebaselining used as a cosmetic reset instead of change control | Rebaseline is ALWAYS human-gated; the old baseline stays committed in git and variance history spans baselines |
| Replan-as-reset | An autonomous loop never hits `max_iterations` because each accepted replan zeroes its counter | The "counters that reset" loop pathology (hub loop-engineering canon) transposed to planning | `slip_injector.py` increments a plan-level `replan_ledger` that never resets; replans count against one shared attempt budget |
| Silent float erosion | Non-critical tasks go critical "overnight" with no warning | DCMA 14-Point checks plus Goldratt's student syndrome / Parkinson's Law: float treated as private padding, consumed invisibly | `replan_impact.py` reports per-task float consumption and critical-path entrants on every run, not only at breach time |
| Milestone-hardness blindness | An aspirational internal date triggers a contractual-level escalation, or a contract date is waved through as soft | The deadline registry lacks a hardness class, so all breaches look alike | The registry requires `contractual / internal / aspirational`; notifications name the class; implicit milestones are flagged `unspecified` |

## When NOT to Use

| You need to... | Use instead (skill name) |
|----------------|--------------------------|
| Compute dates, the critical path, or any forward/backward pass | critical-path-scheduler |
| Detect the slip in the first place (baseline vs status diff) | plan-baseline-tracking |
| Decompose a macro objective into tasks | wbs-decomposition |
| Model or validate the precedence graph | critical-path-scheduler |
| Critique a preliminary plan before execution | plan-critique |
| Format Jira/Asana/Trello payloads from the neutral notification | plan-ticket-export |
| Design loop machinery and exit-condition wiring | loop-engineering-mechanisms, agentic-system-architect |
| Persist plan state and slip history across sessions | hybrid-rag-memory |
| Export an approved replan as an executable workflow | agent-workflow-designer |
| Host the replan loop in a framework runtime | langgraph-state-design, crewai-role-engineering, microsoft-agent-framework |

## Dual-Track Note

**FRAMEWORK TRACK** (delegated to framework skills; verify against current docs): an autonomous replanning loop runs as a LangGraph bounded cycle - conditional edges with cycle guards and checkpoint forking to trial a replan, then commit or discard (see langgraph-state-design); as a CrewAI Flow router with step-callback ledgers (see crewai-role-engineering); or as a Microsoft Agent Framework custom executor graph with a ledger guard (see microsoft-agent-framework). Runtime constructs are never duplicated in this skill.

**STATIC TRACK** (how this hub uses it, offline and git-versioned): replanning is a gated workflow - variance breach (plan-baseline-tracking exit 2) -> slip injection -> CPM recompute (critical-path-scheduler) -> impact diff -> replan manifest at the human gate -> apply -> verify against the new baseline. The plan, both schedules, and every impact report are committed artifacts; a rebaseline is a new gated commit, so git history is the revision store. Consuming workflows validate against hitl_gate_validator rules R1-R6, and any replanning agent must score >= 90 (HARDENED) on the hub loop auditor.

## References

- PMBOK Guide, 7th ed. (PMI, 2021) - schedule-compression definitions (crashing, fast-tracking); PMBOK Guide, 6th ed. (2017), process 6.6 Control Schedule. External standard - verify against current PMI editions.
- Goldratt, Critical Chain (North River Press, 1997) - buffer management, student syndrome, Parkinson's Law.
- Brooks, The Mythical Man-Month (Addison-Wesley, 1975; Anniversary ed. 1995) - Brooks's Law.
- Kahneman and Tversky, "Intuitive Prediction: Biases and Corrective Procedures" (1979); Kahneman, Thinking, Fast and Slow (2011), ch. 23 - planning fallacy, inside vs outside view.
- Flyvbjerg, "Underestimating Costs in Public Works Projects: Error or Lie?" (Journal of the American Planning Association 68:3, 2002); Flyvbjerg and Gardner, How Big Things Get Done (2023) - reference-class forecasting.
- GAO Schedule Assessment Guide, GAO-16-89G (Dec 2015) - rebaselining criteria and abuse. External standard - verify against current GAO revision.
- DCMA 14-Point Schedule Assessment - negative float and remaining-duration concentration checks. External standard - verify against current DCMA guidance.
- Hub canon, cited by name as authority and never imported or executed across skill folders: hitl_gate_validator rule R5 (id/depends_on acyclicity contract), the six-type exit-condition taxonomy and loop-engineering patterns of the agentic-system-architect flagship (duplicated verbatim above per the portability rule), and the hub workflow-template Definition block.
- Local knowledge base: `references/replan_decision_patterns.md` - decision strategies, cause classification, rebaselining change control, notification content rules.

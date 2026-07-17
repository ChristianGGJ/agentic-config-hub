---
title: "Plan Baseline Tracking — Project Planning & Requirements Elicitation"
description: "Use when tracking an approved project plan against reality -- diffing an immutable baseline plan.json against an append-only status.jsonl ledger to. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Plan Baseline Tracking

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `plan-baseline-tracking`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/plan-baseline-tracking/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


**Tier:** STANDARD
**Category:** Planning / Execution Control
**Dependencies:** None. `scripts/baseline_variance.py` is Python 3.8+ standard library only (no network, no LLM calls, deterministic and offline).

## Description

Plan-baseline-tracking owns exactly one transformation: **(immutable baseline plan, append-only status ledger) -> deterministic schedule-variance report**. The baseline is a `plan.json` in the hub canonical tasks shape (`id`, `description`, `depends_on`, plus the validator-tolerated extra fields `baseline_start`, `baseline_finish`, `milestone`, `owner`) that was approved at a Phase 3 HUMAN GATE and is never edited afterwards. Reality arrives as `status.jsonl`, one JSON event per line, appended and never rewritten. The bundled `baseline_variance.py` diffs the two and reports per-task start/finish variance in working days, percent-complete versus the percent the baseline window implies, a deterministic subset of DCMA-style schedule health checks, and an overall verdict (`HEALTHY` / `AT-RISK` / `UNHEALTHY`).

The design premise comes straight from the mined sources below: plans do not fail at computation time, they fail at *statusing* time -- subjective percent-complete, rubber baselines, green-enum watermelon reports, and stale ledgers. So the tool treats the status ledger as evidence to be audited, not as truth: data defects (future actuals, reopened `done` tasks, percent regressions) are CRITICAL findings in their own right, separate from honest schedule slips.

Everything else is out of scope by design: computing schedule dates or critical paths (that is `critical-path-scheduler`), deciding what to do about a slip (`slip-driven-replanning`), exporting to PM tools (`plan-ticket-export`), and cost/dollar earned value (CPI/EV/AC), which is deliberately excluded from v1 to keep schedule variance atomic.

### State Persistence Boundary

**This skill only diffs. It never stores.** Where plan state persists across sessions -- the approved baseline, its revision history, the slip ledger, episodic memories of past projects -- is owned by **hybrid-rag-memory**. In the static track the answer is even simpler: `plan.json` and `status.jsonl` are git-committed files and git history is the revision store. If you find yourself designing a database, vector store, or memory schema for plan state inside this skill, stop and route to hybrid-rag-memory by name.

## Features

- **Working-day variance** -- signed per-task start and finish variance (`+` = late, `-` = early) computed over a configurable workweek and holiday calendar, never raw calendar days
- **Percent-complete vs expected** -- compares reported percent against the schedule-elapsed percent implied by the baseline window at the data date, flagging gaps beyond a threshold
- **DCMA-style health-check subset** -- missed-task percentage (5% default threshold), actual dates in the future of the data date, invalid status transitions, percent regressions, and stale updates, each a deterministic rule
- **90-percent-syndrome detector** -- repeated high-percent events without `done` are flagged as a masked slip
- **Milestone breach flags** -- milestone tasks that finish late or blow past their baseline finish escalate to CRITICAL
- **Overall schedule health verdict** -- `HEALTHY` / `AT-RISK` / `UNHEALTHY` with meaningful exit codes (`0` / `1`) so the tool wires directly into CI and downstream escalation gates
- **Deterministic and reproducible** -- same plan + same ledger + same `--as-of` = same report, every run, offline

## Interface

### Inputs

| Input | Flag | Shape |
|-------|------|-------|
| Baseline plan | `--plan` | Hub canonical plan JSON (below); immutable after the Phase 3 gate |
| Status ledger | `--status` | JSON Lines, one event per line, append-only |
| Data date | `--as-of` | `YYYY-MM-DD`; defaults to today -- always pass it explicitly in CI |
| Calendar | `--calendar` | Optional `{"workweek": ["Mon",...], "holidays": ["YYYY-MM-DD",...]}`; default Mon-Fri, no holidays |
| Thresholds | `--slip-tolerance` (0 wd), `--stale-after` (7 d), `--gap-threshold` (20 pts), `--missed-threshold` (5.0 %), `--syndrome-percent` (90) | All optional, all deterministic |

Baseline `plan.json` (canonical shape shared across the planning skills; extra fields are tolerated, mirroring the `id`/`depends_on` contract that hub canon `hitl_gate_validator` rule R5 enforces on workflows):

```json
{
  "name": "customer-portal-launch",
  "version": "0.1.0",
  "tasks": [
    {
      "id": "api-build",
      "description": "Implement portal API endpoints",
      "depends_on": ["api-design"],
      "owner": "luis.dev",
      "duration_days": 15,
      "baseline_start": "2026-06-15",
      "baseline_finish": "2026-07-03",
      "milestone": false
    }
  ]
}
```

`status.jsonl` events (one per line; `actual_start`/`actual_finish`/`remaining_duration_days`/`source`/`evidence` optional):

```json
{"task_id": "api-build", "timestamp": "2026-07-03T16:30:00", "status": "done", "percent_complete": 100, "actual_finish": "2026-07-03", "evidence": "all endpoints merged, CI green"}
```

`status` is one of `not_started | in_progress | done | blocked`. Timestamps are `YYYY-MM-DDTHH:MM:SS` (no `Z` suffix -- `datetime.fromisoformat` rejects it before Python 3.11); all dates are ISO 8601 date-only, which sidesteps timezones entirely.

### Outputs

- Human-readable ASCII report: per-task variance table, DCMA-style health summary, findings list, verdict
- `--json`: the full report object (`tasks[]`, `findings[]`, `health{}`, `verdict`, `exit_code`) for agents and CI

### Exit codes and the validation split

| Code | Meaning |
|------|---------|
| `0` | HEALTHY -- zero findings at the configured thresholds |
| `1` | Findings present (WARNING and/or CRITICAL); the machine-readable early-warning trigger |
| `2` | Input error -- malformed plan/ledger/calendar or bad flag value |

Schema violations (unparseable JSON, unknown status enum, percent outside 0-100, unresolvable `depends_on`) are **exit 2**: a broken contract cannot be diffed. Semantic lies inside a well-formed ledger (future actuals, reopened `done`, regressions, unknown task ids) are **findings**: they are exactly what the tool exists to catch.

## Usage

Healthy plan (ships in `assets/`, exits `0`):

```bash
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_healthy.jsonl --as-of 2026-07-15
```

Slipped plan with seeded defects (exits `1`; full expected output ships as `assets/expected_variance_report.txt`):

```bash
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_slipped.jsonl --as-of 2026-07-15
```

Machine-readable, with a custom calendar and relaxed slip tolerance:

```bash
python scripts/baseline_variance.py --plan assets/sample_plan.json \
    --status assets/sample_status_healthy.jsonl --as-of 2026-07-15 \
    --calendar assets/sample_calendar.json --slip-tolerance 2 --json
```

CI wiring (the exit-1 contract is the handoff edge to escalation gates and to `slip-driven-replanning`):

```yaml
- name: schedule-health-gate
  run: python skills/plan-baseline-tracking/scripts/baseline_variance.py
       --plan plan.json --status status.jsonl --as-of "$(date +%F)" --json
```

## Examples

### Example 1: on-track project

`sample_status_healthy.jsonl` against `sample_plan.json` at `--as-of 2026-07-15`: six tasks due, all finished on or before baseline, one in flight and within its expected-percent band. Output ends with:

```
DCMA-STYLE HEALTH SUMMARY
  missed-task percentage : 0% (0 of 6 task(s) due by 2026-07-15)

VERDICT: HEALTHY (0 critical, 0 warning finding(s))
```

Exit code `0` -- CI proceeds, no escalation.

### Example 2: slipped project with data defects

`sample_status_slipped.jsonl` seeds honest slips (api-design +2 wd late, api-build overdue) *and* ledger lies (a reopened `done` task, a percent regression, a future `actual_start`, an unknown task id). Extract:

```
  [CRITICAL] <plan>: missed-task-percentage - 66.7% of the 6 task(s) due by
             2026-07-15 missed their baseline finish (threshold 5%; DCMA guideline is 5%)
  [CRITICAL] beta-release: milestone-breach - milestone baseline_finish 2026-07-08
             has passed and the task is not done
  [CRITICAL] uat-signoff: future-actual-date - actual_start 2026-07-20 is later than
             the data date 2026-07-15 (a forecast typed into an actual field is a data defect)
  [WARNING]  api-build: ninety-percent-syndrome - 2 event(s) at >= 90% complete
             without reaching done; subjective percent-complete is masking a slip

VERDICT: UNHEALTHY (7 critical, 12 warning finding(s))
```

Exit code `1` -- the hosting workflow's escalation gate fires; `slip-driven-replanning` consumes the `--json` report.

## Health Checks (DCMA-Style Subset)

| Check | Fires when | Severity | Mined from |
|-------|-----------|----------|------------|
| `missed-task-percentage` | > threshold (default 5%) of due tasks finished late or not at all | CRITICAL | DCMA 14-Point missed-tasks metric |
| `future-actual-date` | `actual_start`/`actual_finish`/event timestamp later than `--as-of` | CRITICAL | DCMA/GAO invalid-dates data-quality checks |
| `invalid-transition` | Status moves against the model (`done` is terminal) | CRITICAL | GAO-16-89G status-update integrity |
| `percent-regression` | `percent_complete` drops between events | CRITICAL | GAO-16-89G; append-only ledger discipline |
| `milestone-breach` | Milestone finishes late or is unfinished past baseline | CRITICAL | GAO-16-89G milestone tracking |
| `overdue` / `finish-slip` / `late-start` | Variance beyond `--slip-tolerance` working days | WARNING | ANSI/EIA-748 schedule variance |
| `behind-expected` | Reported percent lags the baseline-window percent by >= threshold | WARNING | Fleming & Koppelman, EVM percent-complete critique |
| `stale-update` / `no-status-reported` | Active task silent longer than `--stale-after` days | WARNING | Kerzner reporting-cadence failures; GAO statusing pitfalls |
| `ninety-percent-syndrome` | >= 2 events at >= 90% without `done` | WARNING | Fleming & Koppelman, 90%-complete syndrome |

## Anti-Patterns (Mined)

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| 90%-complete syndrome | Task sits at 90-95% across successive events while its finish date drifts week after week | Percent-complete is a subjective self-report with no date-bearing evidence behind it (Fleming & Koppelman, *Earned Value Project Management*, 4th ed., 2010) | Require dates and evidence on events; the `ninety-percent-syndrome` detector flags repeated >= 90% events without `done` |
| Rubber baseline | Variance is always near zero yet delivery keeps moving; baseline dates differ between reports | Baseline edited in place after approval, erasing variance (ANSI/EIA-748 baseline-churn literature; GAO-16-89G rebaselining abuse) | Baseline is immutable after the Phase 3 HUMAN GATE; a rebaseline is a new committed plan file through a new gate -- git history is the revision store |
| Watermelon reporting | Status enums read green (in_progress, on track) while dates and deliverables are red inside | Status carries no evidence fields, so optimistic enums go unchallenged (UK NAO / Infrastructure and Projects Authority major-programme reviews) | Events carry `evidence` and actual dates; `behind-expected` audits the enum against the baseline window instead of trusting it |
| Missed-task blindness | Every slip is individually excused; nobody notices most due tasks are past baseline | Task-by-task review with no aggregate metric (DCMA 14-Point Schedule Assessment, missed-tasks metric) | `missed-task-percentage` aggregates all due tasks against the 5% DCMA guideline and fails CRITICAL above it |
| Future actuals | `actual_finish` dated after the data date; progress claimed for work not yet done | Forecast dates typed into actual fields, or statusing ahead of the work (DCMA/GAO invalid-dates checks) | Any actual date or timestamp later than `--as-of` is a CRITICAL data defect: fix the ledger, never the report |
| Stale ledger | Active tasks show week-old or absent events; the report describes last month's project | Update cadence decays after kickoff; reporting driven by meetings, not the ledger (Kerzner, *Project Management*, 12th ed., reporting-cadence failures; GAO-16-89G statusing pitfalls) | `stale-update` and `no-status-reported` checks with a configurable `--stale-after`, run on a CI schedule |
| Reopened done | A `done` task silently returns to `in_progress`; percent drops between events | Work reopened or ledger rewritten without change control (GAO-16-89G baseline maintenance; hub canon: gates before execution) | `done` is terminal in the transition model; `invalid-transition` and `percent-regression` fire CRITICAL -- reopening requires a human-gated rebaseline |
| Late detection | Slips surface only at milestone reviews, when recovery options are gone | Variance computed at milestones instead of every reporting cadence (Standish Group CHAOS late-detection statistics) | Run `baseline_variance.py` on every ledger append or nightly in CI; exit `1` is the machine-readable early warning |

## When NOT to Use

Route by name -- never by path into another skill folder:

| You actually need | Use instead |
|-------------------|-------------|
| Persist plan state, baselines, or slip history across sessions | **hybrid-rag-memory** -- this skill only diffs the two files it is handed |
| Compute schedule dates, critical path, or float from durations | **critical-path-scheduler** -- this skill never does date math beyond variance counting |
| Decide how to answer a slip (absorb / fast-track / crash / rebaseline / escalate) | **slip-driven-replanning** -- it consumes this skill's exit-1 `--json` report |
| Decompose an objective into the baseline task list | **wbs-decomposition** |
| Critique plan realism before the baseline is approved | **plan-critique** |
| Export the plan or status into Jira / Asana / Trello payloads | **plan-ticket-export** -- this skill never documents PM-tool formats |
| Validate HITL gates in the workflow hosting this tracker | **agentic-system-architect** (`hitl_gate_validator`, rules R1-R6) |
| Cost/dollar earned value (EV, AC, CPI) | Out of scope in v1 by design -- this skill is schedule-only |

## Dual-Track Note

**FRAMEWORK TRACK** (delegated to framework skills; verify against current docs): at runtime, plan state persists through framework surfaces, never through this skill -- the LangGraph checkpointer holds in-flight execution state and the Store holds the approved baseline and its revision history (see **langgraph-state-design**); CrewAI passes typed status handoffs via `output_pydantic` (see **crewai-role-engineering**); Microsoft Agent Framework serializes state on the `AgentThread` (see **microsoft-agent-framework**). This skill documents none of those APIs.

**STATIC TRACK** (how this hub uses it): the baseline `plan.json` is a git-committed artifact approved at the Phase 3 HUMAN GATE and immutable thereafter; `status.jsonl` is an append-only in-repo ledger; `baseline_variance.py` is a deterministic, offline, CI-wireable gate whose exit `1` feeds workflow escalation gates; a rebaseline is a *new* gated commit, so git history is the revision store and every past baseline stays auditable.

## References

- DCMA 14-Point Schedule Assessment, US Defense Contract Management Agency -- external standard, verify against current docs
- GAO Schedule Assessment Guide, GAO-16-89G (December 2015) -- verify against current docs
- ANSI/EIA-748 Earned Value Management Systems -- schedule-variance concepts and baseline discipline only (cost EVM excluded here); verify against current revision
- PMBOK Guide, 6th ed. (2017), process 6.6 Control Schedule; PMBOK Guide, 7th ed. (2021), Measurement performance domain -- verify against current PMI docs
- Fleming, Q. & Koppelman, J., *Earned Value Project Management*, 4th ed., PMI, 2010 -- percent-complete subjectivity and the 90%-complete syndrome
- Kerzner, H., *Project Management: A Systems Approach*, 12th ed., 2017 -- status-reporting cadence failure modes
- Standish Group CHAOS Reports -- late-detection statistics motivating threshold and cadence design
- UK National Audit Office / Infrastructure and Projects Authority major-programme reviews -- watermelon reporting
- Python 3.8+ stdlib `datetime`: `date.fromisoformat` (3.7+); `datetime.fromisoformat` rejects a `Z` suffix before 3.11 -- date-only granularity avoids the timezone trap; verify against current docs
- Hub canon, cited by name as authority (never imported): `hitl_gate_validator` rule R5 (the `id`/`depends_on` acyclic contract the plan shape mirrors), the 5-Phase Protocol, and the six-type exit-condition taxonomy in **agentic-system-architect**

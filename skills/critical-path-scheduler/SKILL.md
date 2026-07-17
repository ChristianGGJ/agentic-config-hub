---
name: "critical-path-scheduler"
description: "Use when a task plan with depends_on links and working-day durations needs calendar dates -- validates the dependency graph (cycles with the path printed, dangling references, topological order, duplicating hub rule R5 semantics), then runs deterministic CPM forward/backward passes over a configurable working-day calendar to produce per-task early/late start/finish dates, total float, the critical path, and the project finish date."
---

# Critical-Path Scheduler

**Category:** Planning / Deterministic Tooling
**Dependencies:** None. Python 3.8+ standard library only, no network, no LLM calls.

## Description

This skill turns a validated task dependency graph with working-day
durations into a dated schedule. It is one capability with two halves that
share a single pass: precedence-graph modeling and validation (the
dependency-DAG methodology), and Critical Path Method date computation
over a working-day calendar. They ship together because the CPM forward
pass cannot run without the acyclicity check, and the acyclicity check's
topological order IS the forward pass's iteration order - splitting them
would duplicate the same validator in two skills.

The input contract is the hub canonical plan shape: `tasks[]` with unique
`id` and `depends_on` arrays, extra fields tolerated. That is deliberately
the same minimal graph contract that hub merge-gate rule R5
(`hitl_gate_validator.py`, agentic-system-architect skill) enforces on
workflow Definition blocks - so a plan validated here instantiates into a
gated workflow with zero reshaping. The validator in this skill duplicates
R5's cycle/dangling semantics (DFS coloring, full cycle path reported)
rather than importing them: hub portability rule, duplication beats DRY.

Everything is deterministic, offline, and git-friendly: same plan plus
same calendar produces byte-identical output, every run. This is the
algorithm-over-AI case - date arithmetic is code, never LLM judgment.

## Capabilities

- **Graph hygiene gate** (`--validate-only`): duplicate ids, dangling
  `depends_on` references, dependency cycles with the full cycle path
  printed, isolated-task warnings (DCMA 14-point check 1), and emission of
  a deterministic topological order (Kahn, plan-file order tiebreak).
- **CPM schedule computation**: forward pass (ES/EF), backward pass
  (LS/LF), total float per task, critical-path flagging, and the project
  finish date.
- **Working-day calendar engine**: workweek is configurable (weekends are
  not universally Sat-Sun), holidays are a user-supplied ISO-date list,
  date mapping uses stdlib `datetime.date` only - no times, no timezones,
  by design.
- **Milestone handling**: `duration_days: 0` or `"milestone": true` tasks
  are pinned to the finish date of their latest predecessor.
- **Dual output**: human-readable ASCII table and `--json` for CI and
  agent consumption.
- **CI-wireable exit codes**: a plan whose graph is broken cannot produce
  dates (fail-closed, exit 1 before any schedule is emitted).

## Interface

### Inputs

| Input | Shape | Required |
|-------|-------|----------|
| `--plan plan.json` | Hub canonical: `{"name", "version", "tasks": [{"id", "description", "depends_on": [ids], "duration_days": n, "milestone": bool, ...extras tolerated}]}` | Yes |
| `--calendar calendar.json` | `{"project_start": "YYYY-MM-DD", "workweek": ["Mon", ...], "holidays": ["YYYY-MM-DD", ...]}` | Schedule mode (or `--start-date`) |
| `--start-date YYYY-MM-DD` | Overrides `project_start`; defaults workweek Mon-Fri, no holidays when used alone | No |
| `--validate-only` | Graph hygiene only; no durations or calendar needed | No |
| `--json` | Machine-readable output | No |

`duration_days` are elapsed WORKING days (never person-days, never
calendar days). Fractional durations are rejected - the engine is
date-granular. `depends_on` edges are Finish-to-Start with zero lag; see
`references/pdm_dependency_types.md` for recipes that express SS/FF/SF and
lead/lag constructs inside this contract by task splitting.

### Outputs

Schedule mode (`--json`): `mode`, `plan`, `status`, `project_start`,
`first_working_day`, `project_finish_date`, `working_days_total`,
`calendar` (workweek + holidays actually applied inside the schedule
window), `tasks[]` in topological order with `early_start`,
`early_finish`, `late_start`, `late_finish`, `total_float_days`,
`is_critical`, `milestone`, and `critical_path` (zero-float task ids in
topological order). Validate mode: `status`, `findings[]`, `warnings[]`,
`topological_order[]`.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Pass: graph clean / schedule computed |
| 1 | Gate findings: duplicate id, dangling reference, or cycle (schedule refused) |
| 2 | Usage or input error: unreadable file, malformed JSON, bad date, fractional or missing duration, empty workweek |

Downstream consumers: the dated schedule is Phase-2 MANIFEST content for a
Phase-3 human gate; ticket exporters can stamp due dates from it; baseline
trackers diff later actuals against it.

## Usage

### Workflow 1: Validate the dependency graph

Run the hygiene gate as soon as `depends_on` edges exist - before
durations are even estimated:

```bash
python scripts/cpm_scheduler.py --plan assets/plan.json --validate-only
```

Fix every finding (exit 1) before proceeding: a cycle or dangling
reference makes all downstream dates meaningless. Treat ISOLATE warnings
as probable missing logic (DCMA point 1) unless the task is genuinely
independent.

### Workflow 2: Compute the dated schedule

Add `duration_days` to every task (milestones excepted) and provide a
calendar:

```bash
python scripts/cpm_scheduler.py --plan assets/plan.json --calendar assets/calendar.json
```

Read the FLOAT column, not just the finish date: float is where the
schedule's flexibility lives, and the critical path is where it has none.
Never present `project_finish_date` without the float table (see
Anti-Patterns).

### Workflow 3: Wire into CI and the human gate

```bash
python scripts/cpm_scheduler.py --plan plan.json --calendar calendar.json --json > schedule.json
```

Exit 1 fails the pipeline while the graph is broken. Commit `plan.json`,
`calendar.json`, and the emitted `schedule.json` together; the schedule is
part of the manifest a human approves before execution. To run DCMA point
12 (critical path test), bump one critical task's duration by N and rerun:
the finish date must slip exactly N working days.

## Examples

### Example 1: Hygiene gate on a broken graph

```
$ python scripts/cpm_scheduler.py --plan broken_plan.json --validate-only
CPM GRAPH VALIDATION: broken
Tasks: 4
FINDINGS (2):
  [DANGLING_REFERENCE] Task 'c' depends on unknown task 'ghost'.
  [CYCLE] Dependency cycle detected: a -> b -> a.
RESULT: FAIL
$ echo $?
1
```

### Example 2: Full schedule on the shipped sample

```
$ python scripts/cpm_scheduler.py --plan assets/plan.json --calendar assets/calendar.json
CPM SCHEDULE: product-launch-sample
Project start   : 2026-03-02 (first working day 2026-03-02)
Workweek        : Mon Tue Wed Thu Fri
Holidays applied: 2026-03-17
Project finish  : 2026-03-27 (19 working days)

ID              DUR  ES          EF          LS          LF          FLOAT  CRIT
--------------------------------------------------------------------------------
requirements      3  2026-03-02  2026-03-04  2026-03-02  2026-03-04      0  *
architecture      2  2026-03-05  2026-03-06  2026-03-06  2026-03-09      1
ui-design         4  2026-03-05  2026-03-10  2026-03-05  2026-03-10      0  *
backend-impl      6  2026-03-09  2026-03-16  2026-03-10  2026-03-18      1
frontend-impl     5  2026-03-11  2026-03-18  2026-03-11  2026-03-18      0  *
integration       3  2026-03-19  2026-03-23  2026-03-19  2026-03-23      0  *
qa-testing        4  2026-03-24  2026-03-27  2026-03-24  2026-03-27      0  *
launch            0  2026-03-27  2026-03-27  2026-03-27  2026-03-27      0  *

CRITICAL PATH: requirements -> ui-design -> frontend-impl -> integration -> qa-testing -> launch
```

Note the calendar at work: the 2026-03-17 holiday pushes every span that
crosses it, and 2026-04-03 is loaded but reported unapplied because the
schedule ends before it. The golden JSON vector for this exact run ships
as `assets/expected_schedule.json` - regenerating it must be a byte-level
no-op (determinism check).

## Anti-Patterns

Mined from the named audit catalogs and primary literature; each row is a
defect observed in real schedules, not generic advice.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Finish date presented as a forecast without float framing | Stakeholders treat `project_finish_date` as a commitment; overruns "surprise" everyone (Kahneman & Tversky 1979; Kahneman 2011, planning-fallacy chapters) | Single-point optimistic durations are the inside view; CPM faithfully compounds the optimism | Always publish the float table with the date; sanity-check durations against reference-class history (Flyvbjerg 2006) before scheduling |
| Padding every task instead of surfacing float | Durations 30-50% above estimates, yet the project still finishes late (Goldratt, Critical Chain, 1997) | Student syndrome and Parkinson's Law consume embedded per-task padding silently | Keep durations honest; manage visible float at path level, where the schedule table shows it eroding |
| Tasks with no predecessors and no successors | Isolated tasks get project-start ES and maximal float; the computed critical path is fiction (DCMA 14-point check 1; GAO-16-89G missing-logic audits) | Edges added only where obvious; nobody swept for orphans | Run `--validate-only` and clear every ISOLATE warning; only true start/end tasks may lack logic on one side |
| Hard constraint dates used in lieu of logic | Plans carry per-task "must start on" pins; the network stops responding to change (DCMA point 5; GAO-16-89G) | Dates negotiated politically, then typed in as inputs | Dates are OUTPUTS here; the engine accepts only `project_start`. Encode real external timing as explicit predecessor tasks |
| Dividing duration by headcount inside the scheduler | 6-working-day task scheduled as 3 days because "two people are on it" (Brooks, The Mythical Man-Month, 1975/1995 ed.) | Confusing effort (person-days) with elapsed working-day duration | `duration_days` is elapsed working time; convert effort to duration upstream, during estimation, with communication overhead priced in |
| Assuming Sat-Sun weekends and embedded holiday tables | Schedules for Israel/MENA teams (Sun-Thu workweek) land finishes on non-working days; shipped country tables rot every January (Sussman, "Falsehoods Programmers Believe About Time", 2012) | Calendar assumptions baked into code instead of configuration | `workweek` and `holidays` are mandatory user config; the skill ships no country tables by design |
| Waiting time hidden inside lags or durations | A "6-day" task is 2 days of work plus 4 days of vendor wait; slips are undiagnosable (DCMA points 2-3; NASA/SP-2010-3403 network logic errors) | PDM lags (or padded durations) hide the wait from tracking | Model waits as explicit zero-effort tasks with owners; the FS zero-lag contract makes this the only - and the auditable - way |

## When NOT to Use

Routing table - siblings are named, never path-referenced:

| Need | Route to |
|------|----------|
| Decomposing an objective into the task list itself | `wbs-decomposition` |
| Challenging estimates, assumptions, or plan completeness | `plan-critique` |
| Exporting the dated plan as Jira/Asana/Trello payloads | `plan-ticket-export` |
| Baseline-vs-actual variance once execution starts | `plan-baseline-tracking` |
| Executable agent-workflow step graphs (id/type/agent/on_failure) | `agent-workflow-designer` |
| Merge-gate validation of workflows containing HITL gates (R1-R6) | `agentic-system-architect` |
| Agent-graph wiring - LangGraph graphs are deliberately CYCLIC; do not confuse agent loops with task precedence | `langgraph-state-design` |
| Git-branch DAG analysis (a name collision, not this domain) | `agenthub` |
| Retrieving historical durations to ground estimates | `rag-architect` / `hybrid-rag-memory` |
| Resource leveling, PERT three-point, Monte Carlo, critical chain buffering | No hub skill; different transformations - do not bolt them on here |

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs - cite the framework skills, verify
against current docs): expose `cpm_scheduler.py` as a deterministic tool at
runtime - a CrewAI custom tool (`crewai-role-engineering`), a LangGraph
tool node (`langgraph-state-design`), or an MAF function tool
(`microsoft-agent-framework`). A replanning loop hosted in any framework
calls it as its measurement step; the loop's brakes (exit conditions,
gates) belong to those agent/workflow layers, never inside this skill.
Note the vocabulary trap: LangGraph's graphs are cyclic by design - task
precedence DAGs are a different object.

**STATIC TRACK** (how this hub uses it): `plan.json`, `calendar.json`, and
the emitted schedule are git-versioned artifacts validated offline. Exit
codes wire directly into CI (a plan whose schedule cannot be computed
fails before merge), and the dated schedule is Phase-2 MANIFEST content
reviewed at the Phase-3 human gate. Because the input shape is the same
id/depends_on contract R5 enforces, an approved plan instantiates into a
workflow Definition block without reshaping.

## References

Hub canon (cited as authority, semantics duplicated per the portability
rule - never imported):

- `hitl_gate_validator.py` rule R5 (agentic-system-architect skill) -
  dangling-reference and cycle-detection semantics for id/depends_on
  graphs; this skill's validator replicates the DFS-coloring pattern and
  the full-cycle-path reporting.
- Hub canonical plan/task shape and the six-type exit-condition taxonomy -
  agentic-system-architect flagship references.

External standards and literature (edition-pinned; verify against current
docs):

- PMBOK Guide, 6th ed. (PMI, 2017), Process 6.3 "Sequence Activities" -
  PDM, FS/SS/FF/SF, leads/lags, dependency classification, ES/EF/LS/LF and
  total-float definitions. (7th ed., 2021, moved this material to the
  Practice Standard line - verify against current PMI docs.)
- PMI Practice Standard for Scheduling, 3rd ed. (2019) - schedule model
  quality attributes.
- DCMA 14-Point Schedule Assessment (US Defense Contract Management
  Agency, EVMS guidance) - graph-hygiene thresholds; verify against
  current docs.
- GAO Schedule Assessment Guide, GAO-16-89G (2015) - audited schedule
  defects.
- NASA Schedule Management Handbook, NASA/SP-2010-3403 - network logic
  errors.
- Kahneman & Tversky, "Intuitive Prediction: Biases and Corrective
  Procedures" (1979); Kahneman, Thinking, Fast and Slow (2011) - planning
  fallacy.
- Flyvbjerg, "From Nobel Prize to Project Management: Getting Risks
  Right" (Project Management Journal, 2006) - reference-class forecasting.
- Goldratt, Critical Chain (1997) - float erosion mechanics.
- Brooks, The Mythical Man-Month (1975; 1995 anniversary ed.) - effort vs
  elapsed time.
- Sussman, "Falsehoods Programmers Believe About Time" (infiniteundo.com,
  2012) - calendar edge cases.
- Python 3.8+ standard library: `datetime.date`, `timedelta`,
  `date.weekday()`, `json`, `argparse` - the entire runtime surface.

Local knowledge bases: `references/pdm_dependency_types.md`,
`references/dcma_graph_hygiene.md`. Samples and golden vector:
`assets/plan.json`, `assets/calendar.json`, `assets/expected_schedule.json`.

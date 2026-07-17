# DCMA 14-Point Assessment: Graph-Hygiene Checks for Task Networks

Expert knowledge base for the critical-path-scheduler skill. The DCMA
14-Point Schedule Assessment is the de facto industry checklist for
schedule quality, published by the US Defense Contract Management Agency
as part of its Earned Value Management System compliance guidance and
adopted far beyond defense. Thresholds below are the commonly cited DCMA
values - verify against current DCMA/EVMS documentation before citing them
contractually.

Companion audit catalogs that mine the same defect space from real
programs:

- GAO Schedule Assessment Guide, GAO-16-89G (2015) - ten best practices
  with violations documented in federal program audits.
- NASA Schedule Management Handbook, NASA/SP-2010-3403 - network logic
  errors section.

## The 14 points, and which ones this skill covers

| # | Check | Threshold | Graph hygiene? | Where it lands in this skill |
|---|-------|-----------|----------------|------------------------------|
| 1 | Logic (missing predecessors/successors) | <= 5% of tasks | YES | `--validate-only` emits an ISOLATE warning per task with no predecessors and no successors |
| 2 | Leads (negative lag) | 0 | YES | Contract excludes leads by design; see modeling recipes in `pdm_dependency_types.md` |
| 3 | Lags | <= 5% of edges | YES | Contract excludes lags; waits are modeled as explicit tasks |
| 4 | Relationship types | >= 90% FS | YES | Contract is 100% FS by construction |
| 5 | Hard constraints | <= 5% of tasks | YES | Dates are outputs only; the engine accepts no per-task constraint dates, so constraint abuse is impossible downstream of this tool |
| 6 | High float | <= 5% of tasks with total float > 44 working days | YES | Read the FLOAT column of the schedule table; extreme float usually means missing logic |
| 7 | Negative float | 0 tasks | YES | Cannot occur in this engine (no deadline constraints); compare project_finish_date against external commitments manually |
| 8 | High duration | <= 5% of tasks > 44 working days | YES | Screen the DUR column; long tasks belong back in decomposition |
| 9 | Invalid dates (actuals in future, forecasts in past) | 0 | no (status tracking) | Out of scope: baseline-vs-actual concerns |
| 10 | Resources (tasks without assigned resources/costs) | 0 unassigned | no (resource mgmt) | Out of scope: resource leveling is a different transformation |
| 11 | Missed tasks (behind baseline) | <= 5% | no (status tracking) | Out of scope |
| 12 | Critical path test (network integrity probe) | pass | YES | Deterministic reruns make the test trivial: bump one critical task's duration and rerun; the finish date must move by the same amount |
| 13 | Critical Path Length Index (CPLI) | >= 0.95 | partially | Needs a baseline finish date; the engine supplies the current critical path length |
| 14 | Baseline Execution Index (BEI) | >= 0.95 | no (status tracking) | Out of scope |

Points 9, 11, 13 (denominator), and 14 require status/baseline data and are
deliberately outside this skill's transformation.

## The graph-hygiene points in depth

### Point 1 - Missing logic

A task with no predecessors and no successors floats free: the forward
pass gives it the project start, the backward pass gives it maximal float,
and neither is real information. GAO-16-89G documents audit cases where
double-digit percentages of activities lacked logic and the "critical
path" produced was fiction. `cpm_scheduler.py --validate-only` reports
every isolated task; the 5 percent threshold applies to large networks,
but in plans of agent-ecosystem size the sane target is zero.

### Points 2-4 - Leads, lags, relationship types

All three exist because SS/FF/SF edges and lead/lag offsets make networks
opaque to review. The hub contract solves them structurally: depends_on is
FS zero-lag only, and richer constructs are expressed by task splitting
(see the mapping recipes in `pdm_dependency_types.md`). The residual risk
is a modeler hiding a wait INSIDE a duration ("6 days" = 2 days work +
4 days vendor wait) - that is an estimation-transparency defect to raise
during plan critique, not a graph defect this tool can see.

### Point 5 - Hard constraints

Schedule tools allow "must start on" pins that override network logic;
DCMA flags them because a pinned network stops responding to change and
can silently go infeasible. This engine has no constraint-date inputs:
`baseline_start`/`baseline_finish` fields in the plan are tolerated as
inert metadata and never read by the scheduler. The single date input is
`project_start`.

### Points 6-7 - High and negative float

Total float = LS - ES. Interpretive rules:

- Float far above the project's scale (DCMA anchor: > 44 working days,
  about 2 months) usually means missing logic, not genuine slack.
- Many tasks sharing one large float value often trace to a single missing
  edge near the merge point.
- Negative float means a deadline constraint is violated. This engine
  cannot produce it (the backward pass anchors on the computed finish);
  if a stakeholder deadline is earlier than project_finish_date, that gap
  is the negative float - surface it at the human gate rather than
  compressing durations to hide it.

### Points 8 and 12 - High duration and the critical path test

Tasks longer than ~44 working days resist status measurement and usually
hide structure - route them back to decomposition. The critical path test
verifies the network actually drives the finish date: delay one critical
task by N days and the finish must slip N working days. Because this
engine is deterministic and offline, the test is a two-command diff.

## Order of operations

Run hygiene BEFORE reading the schedule. A cycle or dangling reference
(exit 1) makes every downstream date meaningless, which is why
`cpm_scheduler.py` refuses to emit a schedule while graph findings exist -
the same fail-closed posture as hub rule R5, whose cycle/dangling
semantics the validator duplicates.

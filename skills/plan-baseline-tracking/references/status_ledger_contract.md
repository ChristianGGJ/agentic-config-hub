# Status Ledger and Plan File Contracts

The exact file shapes `baseline_variance.py` consumes. These contracts are
DUPLICATED into this skill per the hub portability rule (skills never import
from or path-reference each other; anyone can copy this folder and use it
immediately). The plan shape mirrors the canonical `id`/`depends_on` contract
that hub canon `hitl_gate_validator` rule R5 enforces on workflow Definition
blocks -- cited here as authority, never called.

## plan.json (the baseline)

```json
{
  "name": "customer-portal-launch",
  "version": "0.1.0",
  "tasks": [
    {
      "id": "api-build",
      "description": "Implement portal API endpoints",
      "depends_on": ["api-design", "db-schema"],
      "wbs_id": "1.3.2",
      "deliverable": "portal API v1",
      "owner": "luis.dev",
      "duration_days": 15,
      "estimate_basis": "reference class: last two internal APIs",
      "baseline_start": "2026-06-15",
      "baseline_finish": "2026-07-03",
      "milestone": false
    }
  ]
}
```

Field rules:

- `id` -- required, unique string. `description` -- required.
- `depends_on` -- required array of existing task ids. Unresolvable references
  are an input error (exit 2). Acyclicity is enforced upstream by the R5
  contract; this tool does not re-walk the graph.
- `baseline_start` / `baseline_finish` -- ISO `YYYY-MM-DD`; both needed for
  variance (a task missing them draws a `no-baseline-dates` WARNING).
  `baseline_finish` must not precede `baseline_start` (exit 2).
- `milestone` -- optional bool; escalates finish slips to CRITICAL breaches.
- All other fields (`wbs_id`, `deliverable`, `owner`, `duration_days`,
  `estimate_basis`, ...) are tolerated extras and ride through untouched.
- The baseline is IMMUTABLE after its human gate. A rebaseline is a new
  committed file approved through a new gate.

## status.jsonl (the ledger)

One JSON object per line, appended in event order, never rewritten:

```json
{"task_id": "api-build", "timestamp": "2026-06-15T09:00:00", "status": "in_progress", "percent_complete": 10, "actual_start": "2026-06-15", "source": "standup", "evidence": "branch opened, first endpoint stubbed"}
{"task_id": "api-build", "timestamp": "2026-07-03T16:30:00", "status": "done", "percent_complete": 100, "actual_finish": "2026-07-03", "source": "standup", "evidence": "all endpoints merged, CI green"}
```

Required fields per event:

| Field | Type | Rule |
|-------|------|------|
| `task_id` | string | Should exist in the plan; an unknown id is a CRITICAL `unknown-task` finding (well-formed but lying) |
| `timestamp` | `YYYY-MM-DDTHH:MM:SS` | Local-naive; no `Z` suffix (rejected before Python 3.11). Orders events per task |
| `status` | enum | `not_started` / `in_progress` / `done` / `blocked`; anything else is exit 2 |
| `percent_complete` | number 0-100 | Outside the range is exit 2; decreasing across events is a CRITICAL finding |

Optional fields: `actual_start`, `actual_finish` (ISO dates; the last value
seen in timestamp order wins), `remaining_duration_days`, `source`,
`evidence`. Extra fields are tolerated. `evidence` matters more than it looks:
date-bearing, checkable evidence is the countermeasure to watermelon
reporting -- prefer "22 of 40 e2e suites passing" over "on track".

### Status transition model

```
not_started -> in_progress | blocked | done
in_progress -> in_progress | blocked | done
blocked     -> blocked | in_progress | done
done        -> done            (terminal)
```

Anything else fires a CRITICAL `invalid-transition`. Reopening a `done` task
is not a status event -- it is a plan change, which means a human-gated
rebaseline (hub canon: gates before execution).

## calendar.json (optional)

```json
{
  "project_start": "2026-06-01",
  "workweek": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "holidays": ["2026-06-19", "2026-07-03"]
}
```

`workweek` uses day names `Mon`..`Sun` (weekends are not universally Sat-Sun);
`holidays` is a list of ISO dates supplied by the user -- this skill ships no
country tables, which would rot annually. `project_start` is tolerated and
ignored here (it belongs to the scheduling capability).

## Validation split (what exits 2 vs what becomes a finding)

- **Exit 2 (input error)**: unreadable files, invalid JSON, missing required
  fields, unknown status enum, percent outside 0-100, malformed dates,
  duplicate task ids, unresolvable `depends_on`, reversed baselines. A broken
  contract cannot be diffed.
- **Findings (exit 1)**: everything a well-formed ledger can still lie about --
  future actual dates, reopened `done` tasks, percent regressions, unknown
  task ids, staleness, slips, breaches. Auditing these is the capability.

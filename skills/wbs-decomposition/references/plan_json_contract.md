# Hub Canonical plan.json Contract (duplicated copy)

This file duplicates the shared plan.json contract into this skill per the
hub portability rule: skills never import from or path-reference other skill
folders, so shared knowledge is copied, not linked. The authority for the
minimal id/depends_on shape is hub canon - the same contract
hitl_gate_validator rule R5 enforces on workflow Definition blocks (cited by
name; never invoked from this skill).

## Shape

```json
{
  "name": "Customer Portal MVP",
  "version": "0.1.0",
  "tasks": [
    {
      "id": "t-1-1",
      "description": "Stakeholder requirements workshop",
      "depends_on": [],

      "wbs_id": "1.1",
      "deliverable": "Signed requirements register",
      "owner": "business-analyst",
      "duration_days": 2,
      "estimate_hours": 16,
      "estimate_basis": "analogous: two prior discovery workshops",
      "baseline_start": "2026-08-03",
      "baseline_finish": "2026-08-04",
      "milestone": false
    }
  ]
}
```

## Field rules

| Field | Status | Rule |
|---|---|---|
| `name` | required | plan/project name (string) |
| `version` | required | contract version; this skill emits `"0.1.0"` |
| `tasks[].id` | required | unique string; this skill derives it from the WBS id (`"1.1"` -> `"t-1-1"`) |
| `tasks[].description` | required | non-empty string |
| `tasks[].depends_on` | required | array of task ids; **this skill always emits `[]` stubs** - precedence is a different transformation, owned by the critical-path-scheduler skill |
| `wbs_id` | optional extra | dotted WBS id for traceability back to the hierarchy |
| `deliverable`, `owner` | optional extras | pass-through from the leaf element |
| `duration_days`, `estimate_hours`, `estimate_basis` | optional extras | estimation metadata; consumed by schedulers and critics downstream |
| `baseline_start`, `baseline_finish` | optional extras | `YYYY-MM-DD`; set by scheduling/baselining skills, not here |
| `milestone` | optional extra | boolean pass-through |

Extra fields are tolerated everywhere in the hub: consumers must ignore
fields they do not understand, and producers must never require them. Pin
integrations to the minimal `id`/`depends_on` contract so plans keep
validating as the schema grows.

## Producer/consumer chain

- **Producer (this skill):** `wbs_validator.py --emit-tasks` writes the file
  only when the WBS passes all structural FAIL gates.
- **Consumers (by name, never by path):** critical-path-scheduler (fills
  `depends_on`), plan-critique (findings + verdict), critical-path-scheduler
  (dates from durations + calendar), plan-ticket-export (PM-tool payloads),
  plan-baseline-tracking (variance vs baseline), agent-workflow-designer
  (export to executable workflow schema).

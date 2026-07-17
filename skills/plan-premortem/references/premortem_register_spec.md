# The Premortem Register: Hub Canonical Risk Artifact

The premortem register is the agentic-config-hub's canonical risk artifact:
one git-versioned JSON file, committed beside the plan.json it hardens, whose
history is the project's episodic risk record. Any hub skill or workflow that
needs "the risks of this plan" reads this artifact; producing a second,
differently-shaped risk register elsewhere in an ecosystem is duplication.

## 1. File-level shape

```json
{
  "plan": "<path or name of the plan.json this register hardens>",
  "version": "0.1.0",
  "scenarios": [ { ...scenario entries... } ]
}
```

The referenced plan uses the hub canonical shape (the same id/depends_on
contract that hitl_gate_validator rule R5 enforces on workflow Definition
blocks - cited as authority, never called from this skill):

```json
{
  "name": "warehouse-launch",
  "version": "0.1.0",
  "tasks": [
    {"id": "T1", "description": "...", "depends_on": [],
     "owner": "...", "duration_days": 10, "milestone": false}
  ]
}
```

Extra task fields (wbs_id, deliverable, estimate_basis, baseline_start,
baseline_finish) are tolerated and ignored by this skill's validator.

## 2. Scenario entry: field-by-field contract

| Field | Type | Required | Contract |
|-------|------|----------|----------|
| scenario_id | string | yes | unique within the register (V0) |
| axes | object | recommended | stressor level assignment that produced the cell |
| failure_narrative | string | yes | past-tense prospective-hindsight story; must assert the failure as accomplished fact (V1) |
| likelihood | string | yes | one of low, medium, high (V2) |
| impact | string | yes | one of low, medium, high, critical (V3) |
| basis | string | recommended | evidence or judgment; unmarked ratings draw a V10 warning |
| evidence | string | conditional | required non-empty when basis = evidence (V10) |
| early_warning_signal | string | yes | observable leading indicator that fires before the failure (V4) |
| affected_task_ids | array | yes | non-empty; every id must exist in plan.json (V7) |
| contingency_trigger | object | yes | {task_id, condition}; task_id must exist in plan.json, condition non-empty (V5) |
| mitigation | string | conditional | plan delta (task, buffer, gate); required at/above threshold unless accepted_by is set (V8) |
| accepted_by | string | conditional | explicit named acceptance of an unmitigated risk (V8 alternative) |
| owner | string | yes | person accountable for the mitigation or acceptance (V6) |

## 3. Validation rules (premortem_register_validator.py)

| Rule | Severity | Checks |
|------|----------|--------|
| V0 | ERROR | scenarios array non-empty; scenario_id present and unique |
| V1 | ERROR / WARN | narrative present (ERROR); under 40 chars or no failure assertion (WARN) |
| V2 | ERROR | likelihood band membership |
| V3 | ERROR | impact band membership |
| V4 | ERROR | early_warning_signal present and non-empty |
| V5 | ERROR | contingency_trigger.task_id resolves against plan.json; condition non-empty |
| V6 | ERROR | owner present and non-empty |
| V7 | ERROR | affected_task_ids non-empty and all resolvable against plan.json |
| V8 | ERROR | mitigation or accepted_by present when impact >= threshold (default: high) |
| V9 | WARN | duplicate narratives (normalized-text hashing) |
| V10 | WARN | basis marked evidence or judgment; evidence cited when claimed |
| V11 | WARN | every plan milestone task touched by at least one scenario |

Gate contract: exit 0 = PASS (no ERROR findings; warnings alone pass unless
--strict), exit 1 = gate failure (findings), exit 2 = usage or input error
(malformed register, malformed plan, missing file).

## 4. What exit 0 means - and what it does not

The validator checks structure, band membership, and plan linkage. It cannot
verify that a narrative is plausible, that a likelihood is honest, or that a
mitigation would work. Exit 0 is a floor: it proves the register is not
premortem theater (unlinked, unrankable, unfalsifiable stories). Semantic
quality is the job of the authoring agents and the human approval gate in
the consuming workflow.

## 5. Lifecycle

1. DRAFT: scenario_matrix_expander.py emits stubs; authors fill them.
2. VALIDATED: premortem_register_validator.py exits 0.
3. PROPOSED DELTA: mitigations are expressed as canonical plan tasks or
   buffers and submitted with the register.
4. APPROVED: the consuming workflow's human gate approves the delta; the
   amended plan becomes the new baseline. The gate is workflow territory -
   this skill never embeds one.
5. HISTORY: the register stays in git beside the plan. Its diff history is
   the episodic record future premortems mine for seed scenarios.

## 6. Interfaces with sibling skills (by name, composed at agent level)

- plan-critique (assumption-register lints): CONTRADICTED and UNTESTABLE-CRITICAL assumption entries
  are priority scenario seeds for this register.
- plan-baseline-tracking (group C): contingency_trigger entries are exactly
  the replan and escalation triggers execution tracking consumes.
- agenthub: when scenario authoring fans out to parallel agents, one agent
  owns one scenario cell; the merged cells form this register.

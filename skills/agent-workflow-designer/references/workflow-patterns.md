# Workflow Patterns In Depth

The five patterns, each with trade-offs, failure modes, when NOT to use it, and
one complete worked config in the hub canonical schema. Every worked config in
this file passes this skill's `workflow_scaffolder.py --validate` and the
agentic-system-architect skill's `hitl_gate_validator.py` (rules R1-R6) as
written. Handoff payloads for the edges between steps are defined in
`references/handoff-contracts.md`.

**Vocabulary map (sibling skills describe the same shapes at other levels):**

| This skill (step graph) | agent-designer (agent topology) | agenthub (session coordination) |
|---|---|---|
| `sequential` | pipeline | pipeline dispatch |
| `parallel` | fan-out / fan-in | parallel session fan-out |
| `router` | dispatcher | -- |
| `orchestrator` | supervisor / hierarchical | hub coordinator |
| `evaluator` | critic loop | LLM-judge ranking |

This skill owns the step-graph expression of the shape: which topology to pick
and how agents talk belongs to agent-designer; dispatching parallel Claude Code
sessions belongs to agenthub.

---

## 1. Sequential

Linear chain: each step consumes the previous step's artifact. The default
pattern - everything else is an upgrade you must justify.

**Trade-offs**

| Dimension | Value | Note |
|---|---|---|
| Latency | Sum of all steps | No overlap; worst latency per unit of work |
| Token cost | Lowest of all patterns | One agent active at a time, artifacts stay small |
| Debuggability | Easiest | One path; replay from any step's input artifact |
| Failure blast radius | One step | Downstream simply never runs |
| Coupling | High | Every step's output schema is the next step's input contract |

**Failure modes**

| Symptom | Diagnosis | Fix |
|---|---|---|
| Quality degrades along the chain | Each step summarizes lossily; errors compound ("telephone game") | Pass the original source artifact alongside each derived artifact; cap chain at ~5 dependent steps |
| Middle step output drifts from what downstream expects | No handoff contract on the edge; producer changed format silently | Write the edge contract (handoff-contracts.md) and validate payloads at the edge |
| One slow step stalls everything | Sequential has zero overlap by construction | If >= 3 steps have no true data dependency, upgrade to `parallel` |

**When NOT to use**

- Subtasks are independent -> `parallel` (you are paying latency for no reason).
- The step list cannot be fixed at design time -> `orchestrator`.
- The chain exists only to "review" one artifact repeatedly -> `evaluator` loop
  around the single failing step, not a longer chain.

**Worked config - release-notes pipeline**

```json
{
  "name": "release-notes-pipeline",
  "version": "1.0.0",
  "pattern": "sequential",
  "agents": {
    "collector": {"role": "Collects merged PRs and commit messages since the last tag."},
    "writer": {"role": "Drafts user-facing release notes from the change list."},
    "reviewer": {"role": "Checks the notes against the acceptance checklist."}
  },
  "budget": {"max_total_tokens": 30000, "max_tool_calls": 25, "wall_clock_seconds": 900},
  "steps": [
    {
      "id": "collect-changes",
      "type": "action",
      "agent": "collector",
      "description": "Emit a change-list artifact: PR titles, labels, breaking flags.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "retry",
      "max_retries": 2,
      "depends_on": [],
      "budget": {"max_tokens": 6000, "timeout_seconds": 300}
    },
    {
      "id": "draft-notes",
      "type": "action",
      "agent": "writer",
      "description": "Draft release notes from the change-list artifact only.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "retry",
      "max_retries": 2,
      "depends_on": ["collect-changes"],
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "review",
      "type": "check",
      "agent": "reviewer",
      "description": "Self-review: every breaking change named, no internal ticket ids leaked.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["draft-notes"],
      "budget": {"max_tokens": 4000, "timeout_seconds": 300}
    }
  ],
  "escalation": {
    "contact": "release-manager",
    "trigger": "Retries exhausted on any step or review check fails."
  }
}
```

---

## 2. Parallel

Independent branches fan out, one fan-in step merges. Buy latency with tokens.

**Trade-offs**

| Dimension | Value | Note |
|---|---|---|
| Latency | Max of branches + fan-in | Best case: N-x speedup over sequential |
| Token cost | Sum of all branches | Every branch runs regardless of need |
| Debuggability | Medium | Per-branch replay is easy; fan-in bugs are not |
| Failure blast radius | Fan-in policy decides | `join: all` = one failed branch kills the run |
| Coupling | Low between branches | High at the fan-in edge (N contracts converge) |

**Failure modes**

| Symptom | Diagnosis | Fix |
|---|---|---|
| Fan-in output ignores a branch | Branch artifact exceeded the edge budget and was silently truncated | Summarize at source; set `truncated: true` explicitly; size fan-in budget at ~2x average branch output |
| Branches duplicate each other's work | Subtasks were not actually independent (shared subquestion) | Re-partition by data, not by topic adjective; sequentialize the dependent pair |
| Run cost scales faster than value | Fan-out width grew past usefulness | Cap width at 5; merge near-duplicate branches; measure marginal quality per branch |

**When NOT to use**

- Branches need each other's intermediate results -> `sequential` (hidden
  dependencies make parallel slower than serial via retries).
- Only one branch will ever be relevant per input -> `router` (run one, not all).
- Coordinating parallel Claude Code *sessions* rather than steps -> agenthub.

**Worked config - competitor scan**

```json
{
  "name": "competitor-scan",
  "version": "1.0.0",
  "pattern": "parallel",
  "agents": {
    "analyst": {"role": "Researches one independent competitor dimension per branch."},
    "synthesizer": {"role": "Merges branch artifacts into one comparison report."},
    "reviewer": {"role": "Confirms every branch is represented and cited."}
  },
  "budget": {"max_total_tokens": 60000, "max_tool_calls": 50, "wall_clock_seconds": 1800},
  "steps": [
    {
      "id": "scan-pricing",
      "type": "action",
      "agent": "analyst",
      "description": "Branch: competitor pricing pages -> pricing-summary artifact.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": [],
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "scan-features",
      "type": "action",
      "agent": "analyst",
      "description": "Branch: feature matrices and changelogs -> feature-summary artifact.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": [],
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "scan-reviews",
      "type": "action",
      "agent": "analyst",
      "description": "Branch: public reviews and complaints -> sentiment-summary artifact.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": [],
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "synthesize",
      "type": "action",
      "agent": "synthesizer",
      "description": "Fan-in: merge the three branch summaries into one comparison report.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 1,
      "depends_on": ["scan-pricing", "scan-features", "scan-reviews"],
      "join": "all",
      "budget": {"max_tokens": 16000, "timeout_seconds": 300}
    },
    {
      "id": "verify",
      "type": "check",
      "agent": "reviewer",
      "description": "Self-review: every branch cited in the report; no branch marked truncated without a note.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["synthesize"],
      "budget": {"max_tokens": 4000, "timeout_seconds": 300}
    }
  ],
  "escalation": {
    "contact": "research-lead",
    "trigger": "Any branch exhausts retries, or verify finds an unrepresented branch."
  }
}
```

---

## 3. Router

One classify step assigns a route label; exactly one handler branch runs.
`route` metadata on handler steps names the label; `join: any` on the
convergence step accepts whichever handler ran.

**Trade-offs**

| Dimension | Value | Note |
|---|---|---|
| Latency | Classify + one branch | Near-sequential latency at branch-level specialization |
| Token cost | Low | Only the chosen handler runs |
| Debuggability | Medium | Misroutes are silent unless the route label is logged |
| Failure blast radius | One route | A broken handler only breaks its category |
| Coupling | Low | Handlers never see each other |

**Failure modes**

| Symptom | Diagnosis | Fix |
|---|---|---|
| Most inputs land in `__default__` | Routes overlap, or the classify prompt lacks per-route examples | Rewrite routes as mutually exclusive; give the classifier 2-3 examples per route |
| Same input routes differently per run | Nondeterministic classification with no tie-break rule | Add an explicit tie-break order and a confidence floor that routes to `__default__` |
| A new input category silently degrades | No fallback route existed, or fallback handler is a stub | `__default__` is mandatory and must produce a real answer plus a "new category" signal |

**When NOT to use**

- More than ~8 routes -> classification accuracy collapses; group routes into a
  two-level router or rethink the taxonomy.
- Several handlers must run per input -> `parallel` (router is exclusive by
  definition).
- The "routing" decision needs multi-step reasoning over evolving state ->
  `orchestrator`.

**Worked config - support triage**

```json
{
  "name": "support-triage",
  "version": "1.0.0",
  "pattern": "router",
  "agents": {
    "classifier": {"role": "Assigns exactly one route label with a confidence score."},
    "billing-specialist": {"role": "Handles billing-route tickets."},
    "bug-specialist": {"role": "Handles bug-route tickets."},
    "generalist": {"role": "Handles anything below the confidence floor."},
    "reviewer": {"role": "Checks whichever handler ran."}
  },
  "budget": {"max_total_tokens": 40000, "max_tool_calls": 30, "wall_clock_seconds": 1200},
  "steps": [
    {
      "id": "classify",
      "type": "action",
      "agent": "classifier",
      "description": "Emit one route label (billing|bug|__default__); below 0.7 confidence emit __default__.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 1, "depends_on": [],
      "budget": {"max_tokens": 2000, "timeout_seconds": 120}
    },
    {
      "id": "handle-billing",
      "type": "action",
      "agent": "billing-specialist",
      "description": "Resolve the ticket on the billing route.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["classify"],
      "route": "billing",
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "handle-bug",
      "type": "action",
      "agent": "bug-specialist",
      "description": "Reproduce, triage, and answer the ticket on the bug route.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["classify"],
      "route": "bug",
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "handle-general",
      "type": "action",
      "agent": "generalist",
      "description": "Fallback: answer the ticket and flag a possible new category.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["classify"],
      "route": "__default__",
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "verify",
      "type": "check",
      "agent": "reviewer",
      "description": "Self-review: check the output of whichever handler ran; log the route label.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0,
      "depends_on": ["handle-billing", "handle-bug", "handle-general"],
      "join": "any",
      "budget": {"max_tokens": 4000, "timeout_seconds": 300}
    }
  ],
  "escalation": {
    "contact": "support-lead",
    "trigger": "Handler retries exhausted or verify rejects the answer."
  }
}
```

---

## 4. Orchestrator

A planner decomposes the goal into a milestone plan; specialists execute the
approved plan. The most expensive and hardest-to-debug pattern - use it only
when the step list genuinely cannot be fixed at design time.

**Trade-offs**

| Dimension | Value | Note |
|---|---|---|
| Latency | Highest | Planning, gating, and re-planning are on the critical path |
| Token cost | Highest | Plan + N specialists + integration + audit |
| Debuggability | Hardest | Failures can hide in the plan, the execution, or the merge |
| Failure blast radius | Whole run | A bad plan corrupts every downstream step |
| Coupling | Medium | Specialists couple to the plan, not to each other |

**Failure modes**

| Symptom | Diagnosis | Fix |
|---|---|---|
| Orchestrator re-plans every step | Plan granularity too fine; every observation looks like a deviation | Plan at milestone level; re-plan only when a milestone becomes impossible |
| Specialists drift from the plan | Plan not passed as a constraint in each handoff payload | Include the approved plan artifact in every execute-edge contract |
| Run burns budget before producing anything | No human gate after planning; a wrong plan executed at full cost | Keep the `approve-plan` gate; dry-run at half budgets first |

**When NOT to use**

- The step list is knowable at design time -> any fixed pattern above (the
  orchestrator tax is real: roughly 2-4x sequential cost for the same output).
- "Dynamic" really means 2-3 known variants -> `router` over fixed sub-workflows.
- Any step is irreversible and gate placement is the question ->
  agentic-system-architect owns gate design; this pattern only hosts the gate.

**Worked config - database migration (includes an irreversible step)**

This config demonstrates the canonical handling of an irreversible step:
`apply-migration` has a `type: gate` ancestor (R1) and a defined rollback (R2).
`workflow_scaffolder.py --validate` reports a routing WARNING for the
irreversible step - by design: run the flagship's `hitl_gate_validator.py`,
which this config passes.

```json
{
  "name": "db-migration",
  "version": "1.0.0",
  "pattern": "orchestrator",
  "agents": {
    "planner": {"role": "Decomposes the migration into a milestone plan (the manifest)."},
    "migration-engineer": {"role": "Prepares and applies migration scripts per the approved plan."},
    "reviewer": {"role": "Audits the migrated schema against the approved plan."}
  },
  "budget": {"max_total_tokens": 80000, "max_tool_calls": 60, "wall_clock_seconds": 3600},
  "execution": {"max_parallel": 1, "completion_policy": "all_required"},
  "steps": [
    {
      "id": "plan",
      "type": "action",
      "agent": "planner",
      "description": "MANIFEST: milestone plan with per-milestone risks, budgets, and rollback points.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 1, "depends_on": [],
      "budget": {"max_tokens": 8000, "timeout_seconds": 300}
    },
    {
      "id": "approve-plan",
      "type": "gate",
      "agent": "human",
      "description": "HUMAN GATE: DBA approves, edits, or rejects the plan. Hard stop.",
      "irreversible": false, "requires_approval": true, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["plan"],
      "budget": {"max_tokens": 0, "timeout_seconds": 86400}
    },
    {
      "id": "prepare-migration",
      "type": "action",
      "agent": "migration-engineer",
      "description": "Generate migration scripts and take a pre-migration snapshot.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["approve-plan"],
      "budget": {"max_tokens": 12000, "timeout_seconds": 600}
    },
    {
      "id": "apply-migration",
      "type": "action",
      "agent": "migration-engineer",
      "description": "Apply the migration to production per the approved plan.",
      "irreversible": true, "requires_approval": false,
      "rollback": "Restore from the pre-migration snapshot taken in prepare-migration; re-point connections; verify row counts.",
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["prepare-migration"],
      "budget": {"max_tokens": 8000, "timeout_seconds": 900}
    },
    {
      "id": "verify",
      "type": "check",
      "agent": "reviewer",
      "description": "SELF-REVIEW: audit the migrated schema against the approved plan; record deviations.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["apply-migration"],
      "budget": {"max_tokens": 6000, "timeout_seconds": 300}
    }
  ],
  "escalation": {
    "contact": "dba-oncall",
    "trigger": "Plan rejected twice, apply-migration fails, or verify finds a plan deviation."
  }
}
```

---

## 5. Evaluator

Generate/score loop: a generator produces a candidate, an evaluator scores it
against a frozen rubric, and iteration is declared as a `loop` object - never
as a `depends_on` back-edge (a back-edge fails both validators' cycle checks).

**Trade-offs**

| Dimension | Value | Note |
|---|---|---|
| Latency | Steps x iterations | Unbounded without exit conditions - hence the loop object |
| Token cost | x iterations | Each iteration re-reads candidate + critique |
| Debuggability | Medium | Score history makes progress visible; rubric drift does not show in logs |
| Failure blast radius | One deliverable | Loop exhaustion escalates; nothing else breaks |
| Coupling | Tight generator/evaluator | The rubric IS the contract between them |

**Failure modes**

| Symptom | Diagnosis | Fix |
|---|---|---|
| Loop always exits on `max_iterations` | `pass_threshold` never calibrated, or the rubric text drifts between iterations | Calibrate the threshold on golden samples; freeze the rubric for the whole run |
| Scores plateau but iterations continue | No `no_progress` window declared | Set `no_progress_window: 2` - a flat score over 2 iterations exits the loop |
| Candidate flips between two versions | Evaluator critique contradicts itself (A-B-A-B) | This is `oscillation`; the executor detects the alternating pair over a window of 4 and escalates |

**When NOT to use**

- Quality is not machine- or rubric-checkable -> a human review gate
  (`type: gate`), not an LLM evaluator pretending to be one.
- The evaluator would use the same model and prompt family as the generator ->
  self-grading inflates scores; use a different model tier or rubric anchors
  with golden examples.
- One review round is genuinely enough -> `sequential` with a final check step.

**Worked config - landing-copy quality loop**

```json
{
  "name": "landing-copy-loop",
  "version": "1.0.0",
  "pattern": "evaluator",
  "agents": {
    "copywriter": {"role": "Produces landing page copy candidates."},
    "copy-judge": {"role": "Scores candidates against the frozen rubric with per-criterion evidence."},
    "reviewer": {"role": "Final check on the accepted copy."}
  },
  "budget": {"max_total_tokens": 50000, "max_tool_calls": 30, "wall_clock_seconds": 1800},
  "steps": [
    {
      "id": "generate",
      "type": "action",
      "agent": "copywriter",
      "description": "Produce a copy candidate; on later iterations, apply the critique artifact.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 1, "depends_on": [],
      "budget": {"max_tokens": 6000, "timeout_seconds": 300}
    },
    {
      "id": "evaluate",
      "type": "action",
      "agent": "copy-judge",
      "description": "Score the candidate 0-1 against the rubric; emit critique artifact; loop until an exit condition fires.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["generate"],
      "loop": {
        "target": "generate",
        "max_iterations": 3,
        "pass_threshold": 0.8,
        "exit_conditions": ["success_predicate", "max_iterations", "no_progress"],
        "no_progress_window": 2,
        "on_exhaustion": "escalate"
      },
      "budget": {"max_tokens": 4000, "timeout_seconds": 300}
    },
    {
      "id": "finalize",
      "type": "check",
      "agent": "reviewer",
      "description": "Self-review: confirm accepted copy; record which exit condition ended the loop and the score history.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["evaluate"],
      "budget": {"max_tokens": 3000, "timeout_seconds": 300}
    }
  ],
  "escalation": {
    "contact": "marketing-lead",
    "trigger": "Loop exits on any condition other than success_predicate."
  }
}
```

---

## Validating the Worked Configs

```bash
# Structural validation (this skill)
python scripts/workflow_scaffolder.py --validate <config>.json

# Defensive gate validation (agentic-system-architect; mandatory once any
# step is irreversible - the db-migration config above exercises R1 and R2)
python ../agentic-system-architect/scripts/hitl_gate_validator.py <config>.json
```

Expected results: `--validate` reports PASS for all five (db-migration carries
one WARNING routing the irreversible step to the flagship validator);
`hitl_gate_validator.py` reports PASS for all five.

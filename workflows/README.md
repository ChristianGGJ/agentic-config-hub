# Workflows — Gated Multi-Agent Orchestrations

This pillar holds the executable process definitions of **agentic-config-hub**:
multi-step orchestrations in which agents do the work and humans hold the keys.
Each workflow file pairs human-readable prose (Purpose, Actors, Gate Map,
Rollback Plan, Escalation) with a machine-checkable JSON definition that is
validated on every change.

## What Is a Gated Workflow

A gated workflow classifies every step by reversibility (REVERSIBLE, COSTLY,
IRREVERSIBLE) and places a hard Human-in-the-Loop (HITL) gate in front of
anything that mutates state the agent cannot cheaply undo. All workflows here
follow the 5-phase protocol:

1. **Phase 1 DISCOVERY** (read-only) — map scope, constraints, and boundaries.
2. **Phase 2 MANIFEST** — produce an explicit change manifest with risks and rollback.
3. **Phase 3 HUMAN GATE** — hard stop; a human approves, edits, or rejects the manifest.
4. **Phase 4 IMPLEMENTATION** — bounded execution strictly against the approved manifest.
5. **Phase 5 SELF-REVIEW & HANDOFF** — audit the diff, verify, and hand off.

Every loop in a workflow is bounded by the exit-condition taxonomy:
`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
and `escalation_trigger`.

## Validating a Workflow

Every workflow `.md` file embeds a fenced json definition. The validator
extracts the **first** fenced json block and checks rules R1-R6:

```bash
python skills/agentic-system-architect/scripts/hitl_gate_validator.py workflows/<file>.md --json
```

The repo quality gate requires `"result": "PASS"` (zero CRITICAL and zero HIGH
violations) for every file in this directory.

## Rules R1-R6

| Rule | Severity | Requirement |
|---|---|---|
| R1 | CRITICAL | Every `irreversible: true` step has `requires_approval: true` OR a `type: gate` ancestor in its `depends_on` chain. |
| R2 | HIGH | Every irreversible step defines a non-null `rollback` (or a documented `none:justified:` waiver). |
| R3 | HIGH | The workflow defines a top-level `escalation` object (`contact`, `trigger`). |
| R4 | MEDIUM | Every `type: action` step defines `on_failure`; `retry` requires `max_retries >= 1`. |
| R5 | MEDIUM | All `depends_on` references exist and the dependency graph is acyclic. |
| R6 | LOW | The final step is `type: check` (self-review). |

PASS = no CRITICAL and no HIGH violations. A FAIL is a finding, not a crash:
the validator exits 0 whenever validation runs.

## Minimal Passing Definition

The smallest definition that satisfies R1-R6 (this block is what the validator
extracts from this README):

```json
{
  "name": "minimal-gated-workflow",
  "version": "0.1.0",
  "steps": [
    {
      "id": "manifest",
      "type": "action",
      "description": "MANIFEST: produce an explicit change manifest with risks and rollback plan.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "retry",
      "max_retries": 1,
      "depends_on": []
    },
    {
      "id": "human-gate",
      "type": "gate",
      "description": "HUMAN GATE: hard stop. A human approves, edits, or rejects the manifest.",
      "irreversible": false,
      "requires_approval": true,
      "rollback": null,
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["manifest"]
    },
    {
      "id": "implement",
      "type": "action",
      "description": "IMPLEMENTATION: bounded execution strictly against the approved manifest.",
      "irreversible": true,
      "requires_approval": true,
      "rollback": "git reset --hard to the pre-implementation snapshot branch.",
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["human-gate"]
    },
    {
      "id": "verify",
      "type": "check",
      "description": "SELF-REVIEW & HANDOFF: audit the diff against the manifest and report.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["implement"]
    }
  ],
  "escalation": {
    "contact": "human-reviewer",
    "trigger": "Gate rejection, failed verification, or exhausted retries."
  }
}
```

## Workflow Index

| Workflow | Purpose |
|---|---|
| [design-ecosystem.md](design-ecosystem.md) | Flagship 5-phase flow: design, scaffold, and author a complete agentic ecosystem, then audit every artifact through the quality gates. |
| [harden-agent.md](harden-agent.md) | Audit an existing agent with `loop_auditor.py`, remediate findings behind a human gate, and re-audit to `>= 90 HARDENED`. |
| [diagnose-runaway.md](diagnose-runaway.md) | Analyze a runaway agent trace with `react_trace_analyzer.py` (D1-D7), map detections to mitigations, and patch the agent config. |
| [gate-multiagent-workflow.md](gate-multiagent-workflow.md) | Retrofit an ungated multi-agent workflow: classify irreversibility, insert gates, and validate until R1-R6 PASS. |
| [team-development.md](team-development.md) | Supervisor-pattern team workflow: the four cs-* agents build a product ecosystem via typed handoff contracts (H1-H5), evaluator-optimizer audit loops, and team-level exit conditions. |

Workflows are orchestrated by `cs-agentic-system-architect` (see [../agents/](../agents/));
`team-development.md` is executed by the full four-agent team under the Supervisor pattern.
A human reviewer holds every gate.

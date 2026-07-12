---
name: team-development
version: 1.0.0
description: Supervisor-pattern team workflow in which the four cs-* agents develop a product ecosystem together via typed handoff contracts (H1-H5), evaluator-optimizer audit loops, and team-level exit conditions.
type: workflow
---

# Team Development Workflow

Gated team workflow in which the four cs-* agents operate as one development team on a product ecosystem under `ecosystems/<project>/` (product plane, boundaries B1-B6), following the 5-phase protocol with team-level loop engineering.

## Purpose

Coordinates the 4 cs-* agents working as one development team on a product ecosystem, under team-level loop engineering. The architect supervises, decomposes work into components, and assigns them; the designer and prompt-engineer produce artifacts in parallel; the security auditor gates every artifact; the human holds the HUMAN GATE. Every loop is bounded by the canonical exit-condition taxonomy applied at team scope.

## Actors

* **cs-agentic-system-architect** (Team Lead / Supervisor): Owns the Change Manifest, decomposes work into components, assigns them, maintains the Shared Iteration Ledger, runs the final integration audit.
* **cs-agent-designer** (Specialist, works in parallel): Produces agent specs and tool schemas.
* **cs-prompt-engineer** (Specialist, works in parallel): Produces system prompts, few-shot blocks, and eval sets.
* **cs-agent-security-auditor** (Adversarial Gate): Audits every artifact; never produces what it audits.
* **human-reviewer** (Gatekeeper): HUMAN GATE approvals and team-level escalations.

## Team Topology

Supervisor pattern: the architect sits at the center, the two specialists work in parallel, the auditor gates all artifacts, and the human sits above the team.

```text
                human-reviewer (HUMAN GATE)
                           |
              cs-agentic-system-architect
               (Team Lead / Supervisor)
                /                      \
   cs-agent-designer            cs-prompt-engineer
   (Specialist, ||)              (Specialist, ||)
                \                      /
            cs-agent-security-auditor
            (Adversarial Gate: H4 verdicts)
```

## Handoff Contracts

Typed artifacts — exactly these 5 names:

| Contract | Producer -> Consumer | Required Fields | Acceptance Criterion |
|---|---|---|---|
| **H1 Component Inventory** | architect -> specialists | Per component: id, type, purpose, assigned role, acceptance criteria, budget share | Lives in the ecosystem MANIFEST.md |
| **H2 Agent Spec Package** | designer -> auditor | Draft agent .md + tool schema JSON; must declare the 6 canonical exit conditions | `loop_auditor.py` score >= 90 (HARDENED) |
| **H3 Prompt Package** | prompt-engineer -> auditor | Prompt file(s) + eval set + baseline scores | Relevance and faithfulness >= 0.85 and no regression vs baseline |
| **H4 Audit Verdict** | auditor -> producer, cc architect | Verdict PASS/FAIL, findings with severity, remediation hints | FAIL returns the artifact to its producer (evaluator-optimizer loop) |
| **H5 Handoff Report** | architect -> human | Ledger summary, all scores, deviations (must be empty), open risks | Deviations empty; human-reviewer sign-off |

**Rejection rule:** an artifact missing any required field is rejected on sight (contract violation) without consuming an audit cycle; 2 malformed handoffs from the same role -> escalate to the human.

## Team Loop Engineering

The evaluator-optimizer loop between producer and auditor, per component: **produce -> audit -> if FAIL remediate -> re-audit**. max_iterations = 3 audit cycles per component, then escalation_trigger -> human decides. The auditor never audits its own remediation: producers fix, the auditor re-audits.

In the JSON definition below this loop is encoded on the `security-audit` step: each retry returns the FAILed artifacts to their producers for remediation and re-audits them — initial audit + 2 retries = the 3-cycle cap, after which the workflow escalates. The dependency graph stays acyclic; the cycle lives inside the step.

Team exit conditions (the canonical 6 types applied at team scope):

| Exit Condition | Team-Scope Definition |
|---|---|
| `max_iterations` | 3 audit cycles per component |
| `no_progress` | A full team cycle closes zero components -> stop and escalate |
| `oscillation` | The same artifact bounced between two roles twice -> human decides |
| `budget` | Declared in the MANIFEST (total tool calls / wall-clock for the engagement); architect halts the team when exhausted |
| `success_predicate` | Every component PASS + integration audit green |
| `escalation_trigger` | Any Red Line hit or 3 failed audit cycles |

**Shared Iteration Ledger** (a table in the ecosystem MANIFEST.md), one row per component:

```text
id | owner | state (draft / in-audit / remediation / closed) | audit cycles used (n/3) | current score | last verdict
```

The architect is the only writer of the ledger.

## Workflow Schema (JSON Definition)

```json
{
  "name": "team-development",
  "version": "1.0.0",
  "steps": [
    {
      "id": "discovery", "type": "action",
      "description": "DISCOVERY (read-only): architect maps the product scope, existing ecosystem state, constraints, and boundaries B1-B6. No writes allowed.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": []
    },
    {
      "id": "component-inventory", "type": "action",
      "description": "MANIFEST: architect decomposes the work into components and produces the H1 Component Inventory (id, type, purpose, assigned role, acceptance criteria, budget share per component) plus the team budget in the ecosystem MANIFEST.md.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["discovery"]
    },
    {
      "id": "manifest-gate", "type": "gate",
      "description": "HUMAN GATE: hard stop. The human-reviewer approves, edits, or rejects the H1 Component Inventory and the declared team budget before any implementation begins.",
      "irreversible": false, "requires_approval": true, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["component-inventory"]
    },
    {
      "id": "design-agents", "type": "action",
      "description": "IMPLEMENTATION (parallel): cs-agent-designer produces H2 Agent Spec Packages (draft agent .md + tool schema JSON declaring the 6 canonical exit conditions). Retries cover production errors before any audit runs (initial attempt + 2 retries).",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["manifest-gate"]
    },
    {
      "id": "engineer-prompts", "type": "action",
      "description": "IMPLEMENTATION (parallel): cs-prompt-engineer produces H3 Prompt Packages (prompt files + eval set + baseline scores; relevance and faithfulness >= 0.85, no regression). Retries cover production errors before any audit runs (initial attempt + 2 retries).",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["manifest-gate"]
    },
    {
      "id": "security-audit", "type": "action",
      "description": "AUDIT (evaluator-optimizer loop): cs-agent-security-auditor audits every H2/H3 artifact and issues H4 Audit Verdicts (PASS/FAIL, findings with severity, remediation hints). Each retry returns the FAILed artifacts to their producers for remediation and re-audits them (initial audit + 2 retries = the 3-cycle cap); the architect updates the Shared Iteration Ledger every cycle. After the 3rd failed cycle the workflow escalates to the human.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "retry", "max_retries": 2, "depends_on": ["design-agents", "engineer-prompts"]
    },
    {
      "id": "integrate", "type": "action",
      "description": "INTEGRATE: architect assembles the closed components into the ecosystem under ecosystems/<project>/ and commits the integration. Requires success_predicate: every component PASS + integration audit green.",
      "irreversible": true, "requires_approval": true,
      "rollback": "git revert the integration commit",
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["security-audit"]
    },
    {
      "id": "team-retro-check", "type": "check",
      "description": "SELF-REVIEW & HANDOFF: verify the Shared Iteration Ledger is complete (all components closed, cycles <= 3), and issue the H5 Handoff Report (ledger summary, all scores, deviations empty, open risks) to the human.",
      "irreversible": false, "requires_approval": false, "rollback": null,
      "on_failure": "escalate", "max_retries": 0, "depends_on": ["integrate"]
    }
  ],
  "escalation": {
    "contact": "human-reviewer (repository owner)",
    "trigger": "Any Red Line hit, 3 failed audit cycles on any component, team no_progress, oscillation between two roles, or budget exhaustion"
  }
}
```

## Rollback Plan

* **If Integration Fails:** `git revert` the integration commit; the ecosystem returns to its pre-integration state and the affected components reopen in the ledger.
* **If a Component Fails Mid-Cycle:** Discard the draft artifact; the ledger row returns to `remediation` and the producer restarts from the last H4 verdict's remediation hints.

## Escalation

* **Escalation Contact:** `human-reviewer (repository owner)`
* **Escalation Trigger:** Any Red Line hit, 3 failed audit cycles on any component, team no_progress, oscillation between two roles, or budget exhaustion.

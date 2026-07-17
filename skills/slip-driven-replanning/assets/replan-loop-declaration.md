# Replan Loop Declaration (template)

Copy this block into any agent or workflow that hosts autonomous
slip-driven replanning, and adjust the bounds to your context. The six
types are the hub canonical exit-condition taxonomy, duplicated verbatim
per the portability rule; canonical definitions live in the
agentic-system-architect flagship skill.

```markdown
## Loop: slip-driven-replan

**Trigger:** plan-baseline-tracking variance gate (exit 2) or a filed
slip_event.json, confirmed by a human or a trusted status source.

**Iteration body:** slip_injector.py -> critical-path-scheduler CPM
recompute (agent-level composition) -> replan_impact.py -> decision.

**Exit conditions (all six declared):**

| Type | Bound | Fires when |
|------|-------|-----------|
| max_iterations | 3 replan cycles per slip event | the shared replan_ledger reaches the cap - the ledger NEVER resets across replans |
| no_progress | 2 consecutive cycles | recomputed finish delta fails to improve two cycles in a row |
| oscillation | window of 4 ledger entries | a replan-revert-replan pattern appears in the replan_ledger events |
| budget | hosting agent's declared token/time ceiling | the ceiling is exhausted mid-loop; stop and report |
| success_predicate | replan_impact.py exit 0 | decision ABSORB against the approved baseline - verified by exit code, not assertion |
| escalation_trigger | replan_impact.py exit 1 with decision ESCALATE | milestone breach or finish delta beyond threshold; hand the impact report and notification draft to the human gate |

**Hard rules:**
- Rebaselining is ALWAYS behind a human gate (gates before execution).
- The notification draft is payload text; transmission happens only
  after gate approval, outside any script.
- Impact scores and reports are readings presented at the gate, never
  the loop's exit condition (self-eval constraint, by citation).
```

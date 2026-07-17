# slip-driven-replanning

Turn a confirmed schedule slip into a deterministic replan decision: inject the reported delay into `plan.json` (`scripts/slip_injector.py`), have the **critical-path-scheduler** skill recompute the schedule at agent level, then diff baseline vs recomputed schedules (`scripts/replan_impact.py`) for finish delta, critical-path changes, milestone breaches, and float consumption. A frozen decision table selects ABSORB / COMPRESS / ESCALATE and drafts an ASCII notification for the human approval gate - nothing is ever transmitted, and no dates are ever computed here.

## Quick start

```bash
python scripts/slip_injector.py --plan assets/sample_plan.json \
    --slip-event assets/sample_slip_event.json --out updated_plan.json

# recompute updated_plan.json with the critical-path-scheduler skill, then:

python scripts/replan_impact.py --baseline assets/sample_baseline_schedule.json \
    --recomputed assets/sample_recomputed_schedule.json \
    --milestones assets/sample_milestones.json --json
```

Exit codes: `0` = ABSORB / plan written, `1` = findings (COMPRESS or ESCALATE, or injection blocked), `2` = usage/input error.

Both scripts are Python 3.8+ standard library only - no network, no LLM calls, ASCII output. See `SKILL.md` for the full input contracts, the decision table, mined anti-patterns, and routing to sibling skills. The expected output of the shipped sample run lives in `assets/expected_impact_report.json`.

This skill is self-contained: copy the folder and use it. Shared knowledge (canonical plan schema, exit-condition taxonomy) is duplicated in per the hub portability rule, never referenced across skill folders.

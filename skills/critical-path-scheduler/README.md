# critical-path-scheduler

Deterministic task-graph validation and Critical Path Method scheduling
over a working-day calendar. One capability, two halves of the same pass:
dependency-DAG hygiene (cycles with the path printed, dangling
`depends_on` references, topological order - duplicating hub rule R5
semantics) and CPM date computation (forward/backward pass, per-task
ES/EF/LS/LF dates, total float, critical path, project finish date).

Python 3.8+ standard library only. No network, no LLM calls. Same plan
plus same calendar produces byte-identical output, every run.

## Quick start

```bash
# 1. Graph hygiene gate (no durations or calendar needed)
python scripts/cpm_scheduler.py --plan assets/plan.json --validate-only

# 2. Full dated schedule over the shipped sample calendar
python scripts/cpm_scheduler.py --plan assets/plan.json --calendar assets/calendar.json

# 3. Machine-readable output for CI / agents
python scripts/cpm_scheduler.py --plan assets/plan.json --calendar assets/calendar.json --json
```

Exit codes: `0` pass / schedule computed, `1` graph findings (schedule
refused), `2` usage or input error.

## Package contents

| Path | Purpose |
|------|---------|
| `SKILL.md` | Master documentation: interface, workflows, anti-patterns, routing |
| `scripts/cpm_scheduler.py` | The whole capability as one stdlib CLI |
| `references/pdm_dependency_types.md` | PDM knowledge: FS/SS/FF/SF, leads/lags, mapping onto the hub FS zero-lag contract |
| `references/dcma_graph_hygiene.md` | DCMA 14-point checks relevant to graph hygiene |
| `assets/plan.json` | Sample plan in the hub canonical tasks shape |
| `assets/calendar.json` | Sample working-day calendar (workweek + holidays) |
| `assets/expected_schedule.json` | Golden vector: exact `--json` output for the samples |

Copy this folder anywhere and it works - zero cross-skill dependencies,
per hub canon.

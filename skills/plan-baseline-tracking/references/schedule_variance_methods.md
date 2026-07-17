# Schedule Variance Methods

Method knowledge behind `baseline_variance.py`: what is measured, how each
number is computed, and where every rule was mined from. Schedule-only by
design -- cost/dollar earned value (EV, AC, CPI) is deliberately excluded from
this skill's v1 so the capability stays atomic.

## 1. Baseline discipline

A baseline is the plan the humans approved -- in hub terms, the artifact that
passed the Phase 3 HUMAN GATE of the 5-Phase Protocol. Two rules make variance
measurement meaningful at all:

1. **Immutability.** After approval, `baseline_start` / `baseline_finish` are
   never edited in place. ANSI/EIA-748 EVMS literature calls in-place edits the
   "rubber baseline": every edit silently erases variance, and after a few
   months the plan has "never slipped" while delivery moved by a quarter.
2. **Rebaseline = new file, new gate.** GAO-16-89G distinguishes legitimate
   rebaselining (formal change control, documented rationale) from
   rebaseline-to-hide-variance. The static-track mechanic is simple: a
   rebaseline is a new committed `plan.json` approved through a new human gate,
   and git history keeps every prior baseline auditable.

## 2. Working-day variance

All variances are counted in working days over a configurable calendar
(default workweek Mon-Fri, no holidays; override with `--calendar`), because
calendar-day variance overstates weekend-spanning slips and understates
holiday-spanning ones.

- `start_variance_wd = working_days(baseline_start -> actual_start)` (signed;
  positive = late)
- `finish_variance_wd = working_days(baseline_finish -> actual_finish)`
- The distance function walks day by day from the earlier to the later date,
  counting only days that are in the workweek and not in the holiday list.

Date-only granularity is a deliberate pin: `datetime.date.fromisoformat`
handles `YYYY-MM-DD` from Python 3.7, and staying below time-of-day resolution
sidesteps the timezone and DST traps entirely (note that
`datetime.fromisoformat` rejects a `Z` suffix before Python 3.11 -- ledger
timestamps are therefore local-naive `YYYY-MM-DDTHH:MM:SS`).

## 3. Percent-complete vs expected

Reported `percent_complete` is a self-report; the baseline window implies an
*expected* percent at any data date:

```
expected = 100 * working_days(baseline_start .. as_of, inclusive)
               / working_days(baseline_start .. baseline_finish, inclusive)
```

clamped to 0 before the window and 100 after it. The `behind-expected` check
fires when `expected - reported >= --gap-threshold` (default 20 points). This
is a linear-elapsed assumption -- crude, but deterministic, and its whole job
is to make the enum-only "on track" claim confront the calendar (the
watermelon-reporting countermeasure documented by UK NAO / IPA major-programme
reviews).

Fleming & Koppelman (Earned Value Project Management, 4th ed., 2010) document
why self-reported percent drifts optimistic: the last 10% of the work absorbs
the estimating error of the first 90%. Hence the companion
`ninety-percent-syndrome` detector: two or more events at or above
`--syndrome-percent` (default 90) without reaching `done` flags a masked slip.

## 4. The DCMA-style subset

The DCMA 14-Point Schedule Assessment defines mechanical schedule-quality
checks for full CPM networks. This skill has no float or logic-density inputs
(no CPM here -- that is the critical-path-scheduler capability), so it adopts
the subset that is computable from a baseline plus a status ledger:

| This tool | DCMA/GAO analog | Rule |
|-----------|-----------------|------|
| `missed-task-percentage` | DCMA missed tasks (guideline <= 5%) | due tasks that finished late or not at all / all tasks due by the data date |
| `future-actual-date` | DCMA invalid dates | any actual date or event timestamp after `--as-of` is a data defect, not a slip |
| `invalid-transition`, `percent-regression` | GAO status-update integrity | `done` is terminal; percent never decreases on an append-only ledger |
| `stale-update`, `no-status-reported` | GAO statusing pitfalls | active tasks must report within `--stale-after` days |

Checks that require network logic, durations, or float (leads/lags, high
float, negative float, hard constraints, baseline execution index) are
intentionally NOT implemented here -- they belong with the CPM data they need.

## 5. Severity and verdict model

- **CRITICAL**: data defects (future actuals, invalid transitions, percent
  regressions, done-with-percent<100, finish-without-done, unknown task ids),
  milestone breaches, and the aggregate missed-task-percentage breach. Data
  defects outrank slips because a lying ledger invalidates every other number.
- **WARNING**: honest schedule signals -- late starts, finish slips within
  non-milestone tasks, behind-expected gaps, staleness, 90-percent syndrome.
- **Verdict**: any CRITICAL -> `UNHEALTHY`; only WARNINGs -> `AT-RISK`;
  nothing -> `HEALTHY`. Exit codes: `0` healthy, `1` findings, `2` input error.
  Exit `1` is the machine-readable seam consumed by escalation gates and by
  the slip-driven-replanning capability.

## 6. Threshold rationale

| Threshold | Default | Why |
|-----------|---------|-----|
| `--slip-tolerance` | 0 wd | Any slip is information; raise it only when the baseline itself carries buffers |
| `--missed-threshold` | 5.0% | The DCMA guideline for the missed-task metric |
| `--gap-threshold` | 20 pts | Wide enough to survive the linear-elapsed assumption, narrow enough to catch watermelon enums |
| `--stale-after` | 7 days | One reporting week; Standish CHAOS late-detection data argues for at-least-weekly cadence |
| `--syndrome-percent` | 90 | The band Fleming & Koppelman name |

Every threshold is a CLI flag so a hosting workflow can tighten or relax the
gate without touching the tool.

## 7. Sources (pinned)

- DCMA 14-Point Schedule Assessment, US DCMA -- verify against current docs
- GAO Schedule Assessment Guide, GAO-16-89G, December 2015 -- verify against current docs
- ANSI/EIA-748 EVMS -- baseline discipline and schedule variance; verify against current revision
- PMBOK Guide 6th ed. (2017) 6.6 Control Schedule; 7th ed. (2021) Measurement domain -- verify against current PMI docs
- Fleming & Koppelman, Earned Value Project Management, 4th ed., PMI, 2010
- Kerzner, Project Management: A Systems Approach, 12th ed., 2017
- Standish Group CHAOS Reports; UK NAO / IPA major-programme reviews

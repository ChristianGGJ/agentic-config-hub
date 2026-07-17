#!/usr/bin/env python3
"""baseline_variance.py - Deterministic baseline-vs-actual schedule variance report.

Part of the plan-baseline-tracking skill (agentic-config-hub).

Diffs an immutable, human-approved baseline plan (plan.json, hub canonical
tasks shape carrying baseline_start / baseline_finish extra fields) against an
append-only status ledger (status.jsonl) and emits:

  * per-task start/finish variance in working days (signed, + = late)
  * percent-complete vs expected (schedule-elapsed) percent
  * a deterministic subset of DCMA-14-point-style schedule health checks:
      - missed-task percentage (due tasks finished late or not finished)
      - actual dates in the future of the data date (data defect)
      - invalid status transitions and percent-complete regressions
      - stale updates (active tasks with old or absent status events)
  * an overall schedule health verdict: HEALTHY / AT-RISK / UNHEALTHY

Exit codes:
  0  HEALTHY     - no findings at the configured thresholds
  1  FINDINGS    - at least one WARNING or CRITICAL finding
  2  INPUT ERROR - malformed plan/status/calendar file or bad flag value

Boundary: this tool only DIFFS two files it is handed. It never stores plan
state (see hybrid-rag-memory for persistence) and never computes CPM dates
(see critical-path-scheduler). Hub script rules apply: Python 3.8+ standard
library only, no network, no LLM calls, ASCII-only output, deterministic
(same inputs + same --as-of produce the same report, every run).
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta

TOOL_NAME = "baseline_variance"
SKILL_NAME = "plan-baseline-tracking"

STATUS_VALUES = ("not_started", "in_progress", "done", "blocked")

# 'done' is terminal: reopening requires a human-gated rebaseline, not an event.
ALLOWED_TRANSITIONS = {
    "not_started": {"not_started", "in_progress", "blocked", "done"},
    "in_progress": {"in_progress", "blocked", "done"},
    "blocked": {"blocked", "in_progress", "done"},
    "done": {"done"},
}

WEEKDAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
WEEKDAY_NAMES = {v: k for k, v in WEEKDAY_INDEX.items()}
DEFAULT_WORKWEEK = frozenset({0, 1, 2, 3, 4})  # Mon-Fri

SEV_CRITICAL = "CRITICAL"
SEV_WARNING = "WARNING"

VERDICT_HEALTHY = "HEALTHY"
VERDICT_AT_RISK = "AT-RISK"
VERDICT_UNHEALTHY = "UNHEALTHY"

EXIT_HEALTHY = 0
EXIT_FINDINGS = 1
EXIT_INPUT_ERROR = 2


class InputError(Exception):
    """Raised for malformed input files or values (mapped to exit code 2)."""


def parse_iso_date(value, context):
    """Parse a strict YYYY-MM-DD date (date-only granularity, no timezones)."""
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise InputError("%s: invalid ISO date %r (expected YYYY-MM-DD)" % (context, value))


def parse_iso_timestamp(value, context):
    """Parse YYYY-MM-DDTHH:MM:SS. Note: 'Z' suffix is rejected before Python 3.11."""
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise InputError(
            "%s: invalid ISO timestamp %r (expected YYYY-MM-DDTHH:MM:SS; a 'Z' "
            "suffix is not accepted by datetime.fromisoformat before Python 3.11)"
            % (context, value))


def load_plan(path):
    """Load and structurally validate the baseline plan (hub canonical shape)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise InputError("cannot read plan file: %s" % exc)
    except json.JSONDecodeError as exc:
        raise InputError("plan file is not valid JSON: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise InputError("plan file must be a JSON object with a 'tasks' array")
    seen_ids = set()
    for index, task in enumerate(data["tasks"]):
        context = "plan task[%d]" % index
        if not isinstance(task, dict) or not task.get("id"):
            raise InputError("%s: every task needs a non-empty string 'id'" % context)
        task_id = task["id"]
        if task_id in seen_ids:
            raise InputError("plan: duplicate task id %r" % task_id)
        seen_ids.add(task_id)
        if not isinstance(task.get("depends_on", []), list):
            raise InputError("%s: 'depends_on' must be an array of task ids" % context)
        for key in ("baseline_start", "baseline_finish"):
            raw = task.get(key)
            task["_" + key] = (parse_iso_date(raw, "%s.%s" % (context, key))
                               if raw is not None else None)
        start, finish = task["_baseline_start"], task["_baseline_finish"]
        if start is not None and finish is not None and finish < start:
            raise InputError("plan task %r: baseline_finish precedes baseline_start" % task_id)
    for task in data["tasks"]:
        for dep in task.get("depends_on", []):
            if dep not in seen_ids:
                raise InputError(
                    "plan task %r: depends_on references unknown id %r (graph "
                    "acyclicity is hub canon enforced upstream by hitl_gate_validator "
                    "rule R5; this tool only requires resolvable references)"
                    % (task["id"], dep))
    return data


def load_status(path):
    """Load the append-only status ledger (JSON Lines, one event per line)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise InputError("cannot read status ledger: %s" % exc)
    events = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        context = "status line %d" % lineno
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InputError("%s: invalid JSON (%s)" % (context, exc))
        if not isinstance(event, dict):
            raise InputError("%s: each line must be a JSON object" % context)
        for key in ("task_id", "timestamp", "status", "percent_complete"):
            if key not in event:
                raise InputError("%s: missing required field %r" % (context, key))
        if event["status"] not in STATUS_VALUES:
            raise InputError("%s: status %r not one of %s"
                             % (context, event["status"], "|".join(STATUS_VALUES)))
        percent = event["percent_complete"]
        if isinstance(percent, bool) or not isinstance(percent, (int, float)) \
                or not 0 <= percent <= 100:
            raise InputError("%s: percent_complete must be a number in 0..100" % context)
        event["_ts"] = parse_iso_timestamp(event["timestamp"], context)
        for key in ("actual_start", "actual_finish"):
            raw_date = event.get(key)
            event["_" + key] = (parse_iso_date(raw_date, "%s.%s" % (context, key))
                                if raw_date is not None else None)
        event["_line"] = lineno
        events.append(event)
    return events


def load_calendar(path):
    """Optional calendar JSON: {workweek: [Mon..], holidays: [YYYY-MM-DD]}."""
    if path is None:
        return DEFAULT_WORKWEEK, frozenset()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise InputError("cannot read calendar file: %s" % exc)
    except json.JSONDecodeError as exc:
        raise InputError("calendar file is not valid JSON: %s" % exc)
    names = data.get("workweek", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    try:
        workweek = frozenset(WEEKDAY_INDEX[name] for name in names)
    except (KeyError, TypeError):
        raise InputError("calendar workweek must be a list of day names Mon..Sun")
    if not workweek:
        raise InputError("calendar workweek must contain at least one day")
    holidays = frozenset(parse_iso_date(item, "calendar.holidays")
                         for item in data.get("holidays", []))
    return workweek, holidays


def is_working_day(day, workweek, holidays):
    return day.weekday() in workweek and day not in holidays


def working_days_between(start, end, workweek, holidays):
    """Signed working-day distance from start to end (positive = end is later)."""
    if start == end:
        return 0
    sign = 1 if end > start else -1
    low, high = (start, end) if sign > 0 else (end, start)
    count, cursor = 0, low
    while cursor < high:
        cursor += timedelta(days=1)
        if is_working_day(cursor, workweek, holidays):
            count += 1
    return sign * count


def working_days_inclusive(start, end, workweek, holidays):
    """Count of working days in the closed interval [start, end]."""
    if end < start:
        return 0
    count, cursor = 0, start
    while cursor <= end:
        if is_working_day(cursor, workweek, holidays):
            count += 1
        cursor += timedelta(days=1)
    return count


def expected_percent(start, finish, as_of, workweek, holidays):
    """Schedule-elapsed percent implied by the baseline window at the data date."""
    if as_of < start:
        return 0.0
    if as_of >= finish:
        return 100.0
    total = working_days_inclusive(start, finish, workweek, holidays)
    if total <= 0:
        return 100.0
    elapsed = working_days_inclusive(start, as_of, workweek, holidays)
    return round(100.0 * elapsed / total, 1)


def fmt_num(value):
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def analyze(plan, events, as_of, args, workweek, holidays):
    """Compute per-task variance rows, findings, health metrics, and the verdict."""
    tasks_by_id = {task["id"]: task for task in plan["tasks"]}
    findings = []

    def add_finding(check, severity, task_id, message, flags=None):
        findings.append({"check": check, "severity": severity,
                         "task_id": task_id, "message": message})
        if flags is not None:
            flags.add(check)

    events_by_task = {}
    for event in events:
        task_id = event["task_id"]
        if task_id not in tasks_by_id:
            add_finding("unknown-task", SEV_CRITICAL, task_id,
                        "status event (line %d) references a task_id absent from "
                        "the baseline plan" % event["_line"])
            continue
        events_by_task.setdefault(task_id, []).append(event)
    for task_events in events_by_task.values():
        task_events.sort(key=lambda ev: (ev["_ts"], ev["_line"]))

    rows = []
    eligible, missed = [], []
    for task in plan["tasks"]:
        task_id = task["id"]
        milestone = bool(task.get("milestone"))
        task_events = events_by_task.get(task_id, [])
        flags = set()

        status, percent = "not_started", 0.0
        actual_start = actual_finish = None
        last_update = None
        prev_status = prev_percent = None
        regression_reported = transition_reported = False
        high_percent_events = 0
        for event in task_events:
            new_status = event["status"]
            if (prev_status is not None and not transition_reported
                    and new_status not in ALLOWED_TRANSITIONS[prev_status]):
                add_finding("invalid-transition", SEV_CRITICAL, task_id,
                            "status moved %s -> %s at %s (line %d); 'done' is terminal "
                            "without a human-gated rebaseline"
                            % (prev_status, new_status, event["timestamp"],
                               event["_line"]), flags)
                transition_reported = True
            if (prev_percent is not None and not regression_reported
                    and event["percent_complete"] < prev_percent):
                add_finding("percent-regression", SEV_CRITICAL, task_id,
                            "percent_complete fell from %s to %s at %s (line %d); "
                            "the status ledger is append-only, never rewritten"
                            % (fmt_num(prev_percent), fmt_num(event["percent_complete"]),
                               event["timestamp"], event["_line"]), flags)
                regression_reported = True
            if event["percent_complete"] >= args.syndrome_percent and new_status != "done":
                high_percent_events += 1
            if event["_actual_start"] is not None:
                actual_start = event["_actual_start"]
            if event["_actual_finish"] is not None:
                actual_finish = event["_actual_finish"]
            prev_status, prev_percent = new_status, event["percent_complete"]
            status, percent = new_status, event["percent_complete"]
            last_update = event["_ts"]

        if status == "done" and percent < 100:
            add_finding("done-percent-mismatch", SEV_CRITICAL, task_id,
                        "latest status is done but percent_complete is %s"
                        % fmt_num(percent), flags)
        if actual_finish is not None and status != "done":
            add_finding("finish-without-done", SEV_CRITICAL, task_id,
                        "actual_finish %s is on the ledger but latest status is %s"
                        % (actual_finish.isoformat(), status), flags)
        for label, actual in (("actual_start", actual_start),
                              ("actual_finish", actual_finish)):
            if actual is not None and actual > as_of:
                add_finding("future-actual-date", SEV_CRITICAL, task_id,
                            "%s %s is later than the data date %s (a forecast typed "
                            "into an actual field is a data defect)"
                            % (label, actual.isoformat(), as_of.isoformat()), flags)
        if last_update is not None and last_update.date() > as_of:
            add_finding("future-actual-date", SEV_CRITICAL, task_id,
                        "event timestamp %s is later than the data date %s"
                        % (last_update.isoformat(), as_of.isoformat()), flags)

        base_start = task["_baseline_start"]
        base_finish = task["_baseline_finish"]
        start_var = finish_var = exp_pct = None
        if base_start is None or base_finish is None:
            add_finding("no-baseline-dates", SEV_WARNING, task_id,
                        "task carries no baseline_start/baseline_finish; schedule "
                        "variance is not computable", flags)
        else:
            if actual_start is not None:
                start_var = working_days_between(base_start, actual_start,
                                                 workweek, holidays)
            if actual_finish is not None:
                finish_var = working_days_between(base_finish, actual_finish,
                                                  workweek, holidays)
            exp_pct = expected_percent(base_start, base_finish, as_of,
                                       workweek, holidays)

            if start_var is not None and start_var > args.slip_tolerance:
                add_finding("late-start", SEV_WARNING, task_id,
                            "started %+d working day(s) after baseline_start %s"
                            % (start_var, base_start.isoformat()), flags)
            if finish_var is not None and finish_var > args.slip_tolerance:
                if milestone:
                    add_finding("milestone-breach", SEV_CRITICAL, task_id,
                                "milestone finished %+d working day(s) after "
                                "baseline_finish %s"
                                % (finish_var, base_finish.isoformat()), flags)
                else:
                    add_finding("finish-slip", SEV_WARNING, task_id,
                                "finished %+d working day(s) after baseline_finish %s"
                                % (finish_var, base_finish.isoformat()), flags)

            if base_finish <= as_of:
                eligible.append(task_id)
                if actual_finish is None or actual_finish > base_finish:
                    missed.append(task_id)
                    if actual_finish is None:
                        if milestone:
                            add_finding("milestone-breach", SEV_CRITICAL, task_id,
                                        "milestone baseline_finish %s has passed and "
                                        "the task is not done"
                                        % base_finish.isoformat(), flags)
                        else:
                            add_finding("overdue", SEV_WARNING, task_id,
                                        "baseline_finish %s has passed and the task "
                                        "is not done" % base_finish.isoformat(), flags)

            if status != "done" and exp_pct is not None:
                gap = round(exp_pct - float(percent), 1)
                if gap >= args.gap_threshold:
                    add_finding("behind-expected", SEV_WARNING, task_id,
                                "reported %s%% vs %s%% expected from the baseline "
                                "window (gap %s points)"
                                % (fmt_num(percent), fmt_num(exp_pct),
                                   fmt_num(gap)), flags)

            if status != "done" and base_start <= as_of:
                if last_update is None:
                    add_finding("no-status-reported", SEV_WARNING, task_id,
                                "baseline_start %s has passed and no status event "
                                "was ever recorded" % base_start.isoformat(), flags)
                else:
                    age_days = (as_of - last_update.date()).days
                    if age_days > args.stale_after:
                        add_finding("stale-update", SEV_WARNING, task_id,
                                    "last status event is %d day(s) old (threshold "
                                    "%d); active tasks must report" %
                                    (age_days, args.stale_after), flags)

        if status != "done" and high_percent_events >= 2:
            add_finding("ninety-percent-syndrome", SEV_WARNING, task_id,
                        "%d event(s) at >= %s%% complete without reaching done; "
                        "subjective percent-complete is masking a slip"
                        % (high_percent_events, fmt_num(args.syndrome_percent)), flags)

        rows.append({
            "id": task_id,
            "milestone": milestone,
            "baseline_start": base_start.isoformat() if base_start else None,
            "baseline_finish": base_finish.isoformat() if base_finish else None,
            "status": status,
            "percent_complete": percent,
            "expected_percent": exp_pct,
            "start_variance_wd": start_var,
            "finish_variance_wd": finish_var,
            "actual_start": actual_start.isoformat() if actual_start else None,
            "actual_finish": actual_finish.isoformat() if actual_finish else None,
            "last_update": last_update.isoformat() if last_update else None,
            "flags": sorted(flags),
        })

    missed_pct = round(100.0 * len(missed) / len(eligible), 1) if eligible else 0.0
    if eligible and missed_pct > args.missed_threshold:
        add_finding("missed-task-percentage", SEV_CRITICAL, None,
                    "%s%% of the %d task(s) due by %s missed their baseline finish "
                    "(threshold %s%%; DCMA guideline is 5%%)"
                    % (fmt_num(missed_pct), len(eligible), as_of.isoformat(),
                       fmt_num(args.missed_threshold)))

    critical_count = sum(1 for f in findings if f["severity"] == SEV_CRITICAL)
    warning_count = sum(1 for f in findings if f["severity"] == SEV_WARNING)
    if critical_count:
        verdict = VERDICT_UNHEALTHY
    elif warning_count:
        verdict = VERDICT_AT_RISK
    else:
        verdict = VERDICT_HEALTHY

    return {
        "tool": TOOL_NAME,
        "skill": SKILL_NAME,
        "plan_name": plan.get("name"),
        "as_of": as_of.isoformat(),
        "thresholds": {
            "slip_tolerance_wd": args.slip_tolerance,
            "stale_after_days": args.stale_after,
            "gap_threshold_pct": args.gap_threshold,
            "missed_threshold_pct": args.missed_threshold,
            "syndrome_percent": args.syndrome_percent,
        },
        "calendar": {
            "workweek": [WEEKDAY_NAMES[i] for i in sorted(workweek)],
            "holidays": sorted(day.isoformat() for day in holidays),
        },
        "tasks": rows,
        "findings": findings,
        "health": {
            "eligible_task_count": len(eligible),
            "missed_task_count": len(missed),
            "missed_task_pct": missed_pct,
            "missed_tasks": missed,
            "critical_count": critical_count,
            "warning_count": warning_count,
        },
        "verdict": verdict,
        "exit_code": EXIT_HEALTHY if not findings else EXIT_FINDINGS,
    }


def format_human(report):
    """Render the report as an ASCII-only table plus findings and verdict."""
    lines = []
    lines.append("BASELINE VARIANCE REPORT (%s)" % SKILL_NAME)
    lines.append("=" * 64)
    lines.append("Plan      : %s" % (report["plan_name"] or "<unnamed>"))
    lines.append("Data date : %s" % report["as_of"])
    thresholds = report["thresholds"]
    lines.append("Thresholds: slip>%dwd stale>%dd gap>=%spct missed>%spct"
                 % (thresholds["slip_tolerance_wd"], thresholds["stale_after_days"],
                    fmt_num(thresholds["gap_threshold_pct"]),
                    fmt_num(thresholds["missed_threshold_pct"])))
    lines.append("Calendar  : workweek=%s holidays=%d"
                 % (",".join(report["calendar"]["workweek"]),
                    len(report["calendar"]["holidays"])))
    lines.append("")

    id_width = max([len("TASK")] + [len(row["id"]) for row in report["tasks"]])
    header = "%-*s MS STATUS       PCT    EXP   SVAR  FVAR  FLAGS" % (id_width, "TASK")
    lines.append(header)
    lines.append("-" * len(header))

    def fmt_var(value):
        return "." if value is None else "%+d" % value

    for row in report["tasks"]:
        expected = "." if row["expected_percent"] is None \
            else fmt_num(row["expected_percent"])
        lines.append("%-*s %-2s %-11s %5s %6s %5s %5s  %s"
                     % (id_width, row["id"], "M" if row["milestone"] else ".",
                        row["status"], fmt_num(row["percent_complete"]), expected,
                        fmt_var(row["start_variance_wd"]),
                        fmt_var(row["finish_variance_wd"]),
                        ",".join(row["flags"]) if row["flags"] else "-"))
    lines.append("")

    health = report["health"]
    lines.append("DCMA-STYLE HEALTH SUMMARY")
    lines.append("  missed-task percentage : %s%% (%d of %d task(s) due by %s)"
                 % (fmt_num(health["missed_task_pct"]), health["missed_task_count"],
                    health["eligible_task_count"], report["as_of"]))
    check_counts = {}
    for finding in report["findings"]:
        check_counts[finding["check"]] = check_counts.get(finding["check"], 0) + 1
    for check in sorted(check_counts):
        lines.append("  %-22s : %d finding(s)" % (check, check_counts[check]))
    lines.append("")

    if report["findings"]:
        lines.append("FINDINGS (%d):" % len(report["findings"]))
        ordered = sorted(report["findings"],
                         key=lambda f: (f["severity"] != SEV_CRITICAL,
                                        f["task_id"] or "", f["check"]))
        for finding in ordered:
            lines.append("  [%s] %s: %s - %s"
                         % (finding["severity"], finding["task_id"] or "<plan>",
                            finding["check"], finding["message"]))
        lines.append("")

    lines.append("VERDICT: %s (%d critical, %d warning finding(s))"
                 % (report["verdict"], health["critical_count"],
                    health["warning_count"]))
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="baseline_variance.py",
        description="Diff an approved baseline plan.json against an append-only "
                    "status.jsonl ledger: per-task schedule variance in working "
                    "days, percent-complete vs expected, DCMA-style health checks, "
                    "and an overall schedule health verdict.",
        epilog="Exit codes: 0 = HEALTHY (no findings), 1 = findings present, "
               "2 = input/usage error. Deterministic and offline: no network, "
               "no LLM calls. Pass --as-of explicitly for reproducible reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", required=True,
                        help="baseline plan JSON (hub canonical tasks shape with "
                             "baseline_start/baseline_finish extra fields)")
    parser.add_argument("--status", required=True,
                        help="append-only status ledger (JSON Lines, one event per line)")
    parser.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                        help="data date for all checks (default: today; always pass "
                             "it explicitly in CI so reports are reproducible)")
    parser.add_argument("--calendar", default=None, metavar="FILE",
                        help="optional calendar JSON {workweek:[Mon..],holidays:[...]}; "
                             "default workweek Mon-Fri with no holidays")
    parser.add_argument("--slip-tolerance", type=int, default=0, metavar="N",
                        help="working days of start/finish slip tolerated before a "
                             "finding fires (default 0)")
    parser.add_argument("--stale-after", type=int, default=7, metavar="N",
                        help="calendar days without a status event before an active "
                             "task is flagged stale (default 7)")
    parser.add_argument("--gap-threshold", type=float, default=20.0, metavar="PCT",
                        help="percentage points behind expected percent-complete "
                             "before a finding fires (default 20)")
    parser.add_argument("--missed-threshold", type=float, default=5.0, metavar="PCT",
                        help="missed-task percentage above which the aggregate check "
                             "fails (default 5.0, the DCMA guideline)")
    parser.add_argument("--syndrome-percent", type=float, default=90.0, metavar="PCT",
                        help="percent-complete band for the 90-percent-syndrome "
                             "detector (default 90)")
    parser.add_argument("--json", action="store_true",
                        help="emit the full report as machine-readable JSON")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        as_of = parse_iso_date(args.as_of, "--as-of") if args.as_of else date.today()
        workweek, holidays = load_calendar(args.calendar)
        plan = load_plan(args.plan)
        events = load_status(args.status)
        report = analyze(plan, events, as_of, args, workweek, holidays)
    except InputError as exc:
        print("INPUT ERROR: %s" % exc, file=sys.stderr)
        return EXIT_INPUT_ERROR
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_human(report))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

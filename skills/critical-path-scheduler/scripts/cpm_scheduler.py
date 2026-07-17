#!/usr/bin/env python3
"""cpm_scheduler.py - Critical Path Method scheduler over a working-day calendar.

Part of the critical-path-scheduler skill (agentic-config-hub).

Two modes:

  --validate-only   Graph hygiene gate: duplicate ids, dangling depends_on
                    references, dependency cycles (full cycle path printed),
                    topological order emission. Cycle and dangling-reference
                    semantics duplicate hub merge-gate rule R5
                    (hitl_gate_validator.py, agentic-system-architect skill).
                    Duplicated, never imported, per the hub portability rule
                    (skills/CLAUDE.md: portability beats DRY).

  (default)         Full CPM schedule: forward/backward pass over duration_days
                    mapped onto a working-day calendar (workweek + holidays)
                    producing per-task ES/EF/LS/LF dates, total float, the
                    critical path, and the project finish date.

Input contracts (hub canonical shapes):
  plan.json      {"name": str, "version": str, "tasks": [{"id": str,
                  "description": str, "depends_on": [ids], "duration_days": n,
                  "milestone": bool, ...extra fields tolerated}]}
  calendar.json  {"project_start": "YYYY-MM-DD", "workweek": ["Mon", ...],
                  "holidays": ["YYYY-MM-DD", ...]}

Exit codes: 0 = pass / schedule computed
            1 = gate findings (duplicate id, dangling reference, cycle)
            2 = usage or input error

Python 3.8+ standard library only. No network, no LLM calls. Deterministic:
same plan + same calendar = same output, every run.
"""

import argparse
import json
import sys
from datetime import date, timedelta

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


def fail_usage(message):
    """Print an input/usage error to stderr and exit 2."""
    print("ERROR: " + message, file=sys.stderr)
    sys.exit(EXIT_USAGE)


def load_json_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        fail_usage("cannot read {0} file '{1}': {2}".format(label, path, exc))
    except json.JSONDecodeError as exc:
        fail_usage("{0} file '{1}' is not valid JSON: {2}".format(label, path, exc))


def parse_iso_date(text, label):
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        fail_usage("{0} '{1}' is not a valid ISO date (YYYY-MM-DD)".format(label, text))


def extract_tasks(plan):
    """Validate the canonical plan shape; exit 2 on malformed input."""
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        fail_usage("plan must be a JSON object with a 'tasks' array (hub canonical shape)")
    tasks = []
    for pos, raw in enumerate(plan["tasks"]):
        if not isinstance(raw, dict):
            fail_usage("tasks[{0}] is not an object".format(pos))
        tid = raw.get("id")
        if not isinstance(tid, str) or not tid.strip():
            fail_usage("tasks[{0}] is missing a non-empty string 'id'".format(pos))
        deps = raw.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            fail_usage("task '{0}': depends_on must be an array of task-id strings".format(tid))
        tasks.append({"id": tid, "depends_on": list(deps), "raw": raw})
    return tasks


def find_duplicates(tasks):
    seen = set()
    findings = []
    for task in tasks:
        if task["id"] in seen:
            findings.append({
                "check": "duplicate_id", "task": task["id"],
                "message": "Task id '{0}' is declared more than once.".format(task["id"])})
        seen.add(task["id"])
    return findings


def find_dangling(tasks, index):
    """Dangling depends_on references. Semantics of hub rule R5 (see module docstring)."""
    findings = []
    for task in tasks:
        for dep in task["depends_on"]:
            if dep not in index:
                findings.append({
                    "check": "dangling_reference", "task": task["id"],
                    "message": "Task '{0}' depends on unknown task '{1}'.".format(task["id"], dep)})
    return findings


def find_cycles(index):
    """Cycle detection via iterative DFS with white/grey/black coloring.

    Semantics duplicated from the hub merge-gate authority, rule R5 in
    hitl_gate_validator.py (agentic-system-architect skill): every distinct
    cycle is reported once, with the full cycle path printed. Duplicated,
    never imported, per the hub portability rule.
    """
    white, grey, black = 0, 1, 2
    color = {tid: white for tid in index}
    reported = set()
    findings = []
    for root in index:
        if color[root] != white:
            continue
        stack = [(root, iter(index[root]["depends_on"]))]
        color[root] = grey
        path = [root]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in index:
                    continue
                if color[child] == grey:
                    cycle = path[path.index(child):] + [child]
                    key = tuple(sorted(set(cycle)))
                    if key not in reported:
                        reported.add(key)
                        findings.append({
                            "check": "cycle", "task": node,
                            "message": "Dependency cycle detected: {0}.".format(" -> ".join(cycle))})
                elif color[child] == white:
                    color[child] = grey
                    stack.append((child, iter(index[child]["depends_on"])))
                    path.append(child)
                    advanced = True
                    break
            if not advanced:
                color[node] = black
                stack.pop()
                path.pop()
    return findings


def find_isolates(tasks, index):
    """Tasks with no predecessors and no successors (DCMA 14-point check 1)."""
    if len(index) < 2:
        return []
    has_pred = {tid: False for tid in index}
    has_succ = {tid: False for tid in index}
    for tid in index:
        for dep in index[tid]["depends_on"]:
            if dep in index and dep != tid:
                has_pred[tid] = True
                has_succ[dep] = True
    warnings = []
    for tid in index:
        if not has_pred[tid] and not has_succ[tid]:
            warnings.append({
                "check": "isolate", "task": tid,
                "message": "Task '{0}' has no predecessors and no successors "
                           "(DCMA 14-point check 1: missing logic).".format(tid)})
    return warnings


def topological_order(tasks, index):
    """Kahn topological sort, deterministic: ties broken by plan-file order."""
    file_order = []
    seen = set()
    for task in tasks:
        if task["id"] not in seen:
            seen.add(task["id"])
            file_order.append(task["id"])
    position = {tid: i for i, tid in enumerate(file_order)}
    indegree = {}
    dependents = {tid: [] for tid in index}
    for tid in index:
        valid = [d for d in index[tid]["depends_on"] if d in index and d != tid]
        indegree[tid] = len(valid)
        for dep in valid:
            dependents[dep].append(tid)
    ready = [tid for tid in file_order if indegree[tid] == 0]
    order = []
    while ready:
        ready.sort(key=position.get)
        tid = ready.pop(0)
        order.append(tid)
        for dep in dependents[tid]:
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(dep)
    return order


def resolve_durations(tasks):
    """Attach integer working-day durations; exit 2 on malformed input."""
    for task in tasks:
        raw = task["raw"]
        dur = raw.get("duration_days")
        if dur is None:
            if raw.get("milestone") is True:
                dur = 0
            else:
                fail_usage("task '{0}' has no duration_days "
                           "(only milestone: true tasks may omit it)".format(task["id"]))
        if isinstance(dur, bool) or not isinstance(dur, (int, float)):
            fail_usage("task '{0}': duration_days must be a number".format(task["id"]))
        if dur < 0:
            fail_usage("task '{0}': duration_days must be >= 0".format(task["id"]))
        if float(dur) != int(dur):
            fail_usage("task '{0}': fractional duration_days ({1}) is not supported "
                       "at date granularity".format(task["id"], dur))
        task["duration"] = int(dur)
        task["milestone"] = bool(raw.get("milestone", False)) or int(dur) == 0


class WorkingDayCalendar:
    """Maps working-day indices to calendar dates (index 0 = first working
    day on or after project_start). Weekends come from the workweek config;
    holidays are user-supplied ISO dates. Date granularity only: no times,
    no timezones, by design."""

    def __init__(self, project_start, workweek, holidays):
        self.project_start = project_start
        self.workweek = list(workweek)
        self.workday_indices = {DAY_NAMES.index(name) for name in workweek}
        self.holidays = set(holidays)
        self._cache = []

    def _is_working(self, day):
        return day.weekday() in self.workday_indices and day not in self.holidays

    def day(self, k):
        while len(self._cache) <= k:
            candidate = (self._cache[-1] + timedelta(days=1)) if self._cache else self.project_start
            guard = 0
            while not self._is_working(candidate):
                candidate += timedelta(days=1)
                guard += 1
                if guard > 3660:
                    fail_usage("calendar produced no working day within 10 years - "
                               "check workweek and holidays")
            self._cache.append(candidate)
        return self._cache[k]


def build_calendar(args):
    config = {}
    if args.calendar:
        config = load_json_file(args.calendar, "calendar")
        if not isinstance(config, dict):
            fail_usage("calendar file must be a JSON object")
    start_text = args.start_date or config.get("project_start")
    if not start_text:
        fail_usage("schedule mode needs a start date: pass --start-date or a "
                   "--calendar file with project_start")
    start = parse_iso_date(start_text, "project start date")
    workweek_raw = config.get("workweek", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    if not isinstance(workweek_raw, list) or not workweek_raw:
        fail_usage("calendar workweek must be a non-empty array of day names")
    chosen = set()
    for name in workweek_raw:
        title = str(name).strip()[:3].title()
        if title not in DAY_NAMES:
            fail_usage("unknown workweek day name '{0}' (use Mon..Sun)".format(name))
        chosen.add(title)
    workweek = [name for name in DAY_NAMES if name in chosen]
    holidays_raw = config.get("holidays", [])
    if not isinstance(holidays_raw, list):
        fail_usage("calendar holidays must be an array of ISO dates")
    holidays = [parse_iso_date(item, "holiday") for item in holidays_raw]
    return WorkingDayCalendar(start, workweek, holidays)


def compute_cpm(order, index):
    """Forward and backward pass in working-day index space (half-open spans)."""
    es, ef = {}, {}
    for tid in order:
        deps = [d for d in index[tid]["depends_on"] if d in index]
        start = max((ef[d] for d in deps), default=0)
        es[tid] = start
        ef[tid] = start + index[tid]["duration"]
    total = max(ef.values(), default=0)
    dependents = {tid: [] for tid in index}
    for tid in index:
        for dep in index[tid]["depends_on"]:
            if dep in index:
                dependents[dep].append(tid)
    ls, lf = {}, {}
    for tid in reversed(order):
        finish = min((ls[s] for s in dependents[tid]), default=total)
        lf[tid] = finish
        ls[tid] = finish - index[tid]["duration"]
    return es, ef, ls, lf, total


def span_to_dates(cal, start_idx, finish_idx, duration):
    """Half-open index span -> inclusive ISO dates. Zero-duration milestones
    are pinned to the finish date of their latest predecessor (or the first
    working day when they have none)."""
    if duration == 0:
        pin = start_idx - 1 if start_idx > 0 else 0
        pinned = cal.day(pin).isoformat()
        return pinned, pinned
    return cal.day(start_idx).isoformat(), cal.day(finish_idx - 1).isoformat()


def build_schedule(plan, order, index, cal):
    es, ef, ls, lf, total = compute_cpm(order, index)
    rows = []
    for tid in order:
        task = index[tid]
        early_s, early_f = span_to_dates(cal, es[tid], ef[tid], task["duration"])
        late_s, late_f = span_to_dates(cal, ls[tid], lf[tid], task["duration"])
        slack = ls[tid] - es[tid]
        rows.append({
            "id": tid,
            "duration_days": task["duration"],
            "milestone": task["milestone"],
            "early_start": early_s,
            "early_finish": early_f,
            "late_start": late_s,
            "late_finish": late_f,
            "total_float_days": slack,
            "is_critical": slack == 0,
        })
    finish_date = cal.day(total - 1) if total > 0 else cal.day(0)
    first_day = cal.day(0)
    applied = sorted(h.isoformat() for h in cal.holidays if first_day <= h <= finish_date)
    return {
        "mode": "schedule",
        "plan": plan.get("name", ""),
        "status": "PASS",
        "project_start": cal.project_start.isoformat(),
        "first_working_day": first_day.isoformat(),
        "project_finish_date": finish_date.isoformat(),
        "working_days_total": total,
        "calendar": {"workweek": list(cal.workweek), "holidays_applied": applied},
        "tasks": rows,
        "critical_path": [row["id"] for row in rows if row["is_critical"]],
    }


def print_findings_human(report):
    print("CPM GRAPH VALIDATION: {0}".format(report["plan"] or "(unnamed plan)"))
    print("Tasks: {0}".format(report["task_count"]))
    if report["findings"]:
        print("FINDINGS ({0}):".format(len(report["findings"])))
        for finding in report["findings"]:
            print("  [{0}] {1}".format(finding["check"].upper(), finding["message"]))
    else:
        print("Findings: none")
    if report["warnings"]:
        print("WARNINGS ({0}):".format(len(report["warnings"])))
        for warning in report["warnings"]:
            print("  [{0}] {1}".format(warning["check"].upper(), warning["message"]))
    if report["topological_order"]:
        print("Topological order: {0}".format(" -> ".join(report["topological_order"])))
    print("RESULT: {0}".format(report["status"]))


def print_schedule_human(report):
    print("CPM SCHEDULE: {0}".format(report["plan"] or "(unnamed plan)"))
    print("Project start   : {0} (first working day {1})".format(
        report["project_start"], report["first_working_day"]))
    print("Workweek        : {0}".format(" ".join(report["calendar"]["workweek"])))
    print("Holidays applied: {0}".format(
        ", ".join(report["calendar"]["holidays_applied"]) or "none"))
    print("Project finish  : {0} ({1} working days)".format(
        report["project_finish_date"], report["working_days_total"]))
    print("")
    id_width = max([len(row["id"]) for row in report["tasks"]] + [4])
    fmt = "{0:<{w}}  {1:>4}  {2:<10}  {3:<10}  {4:<10}  {5:<10}  {6:>5}  {7}"
    header = fmt.format("ID", "DUR", "ES", "EF", "LS", "LF", "FLOAT", "CRIT", w=id_width)
    print(header)
    print("-" * len(header))
    for row in report["tasks"]:
        print(fmt.format(
            row["id"], row["duration_days"], row["early_start"], row["early_finish"],
            row["late_start"], row["late_finish"], row["total_float_days"],
            "*" if row["is_critical"] else "", w=id_width))
    print("")
    print("CRITICAL PATH: {0}".format(" -> ".join(report["critical_path"]) or "(none)"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cpm_scheduler.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Validate a task dependency graph (hub rule R5 semantics) and "
                    "compute a CPM schedule over a working-day calendar.",
        epilog="Examples:\n"
               "  python cpm_scheduler.py --plan assets/plan.json --validate-only\n"
               "  python cpm_scheduler.py --plan assets/plan.json "
               "--calendar assets/calendar.json\n"
               "  python cpm_scheduler.py --plan assets/plan.json "
               "--calendar assets/calendar.json --json\n\n"
               "Exit codes: 0 pass/schedule computed, 1 graph findings, "
               "2 usage/input error.")
    parser.add_argument("--plan", required=True,
                        help="plan.json in the hub canonical tasks shape (id, depends_on, "
                             "duration_days; extra fields tolerated)")
    parser.add_argument("--calendar",
                        help="calendar.json with project_start, workweek, holidays")
    parser.add_argument("--start-date", metavar="YYYY-MM-DD",
                        help="project start date; overrides project_start from --calendar")
    parser.add_argument("--validate-only", action="store_true",
                        help="graph hygiene only: duplicates, dangling refs, cycles "
                             "(cycle path printed), topological order; no dates needed")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of the human report")
    args = parser.parse_args(argv)

    plan = load_json_file(args.plan, "plan")
    tasks = extract_tasks(plan)
    index = {}
    for task in tasks:
        index.setdefault(task["id"], task)

    findings = find_duplicates(tasks) + find_dangling(tasks, index) + find_cycles(index)
    warnings = find_isolates(tasks, index)
    blocked = any(f["check"] in ("cycle", "duplicate_id") for f in findings)
    order = [] if blocked else topological_order(tasks, index)

    if args.validate_only or findings:
        report = {
            "mode": "validate" if args.validate_only else "schedule",
            "plan": plan.get("name", ""),
            "status": "PASS" if not findings else "FAIL",
            "task_count": len(index),
            "findings": findings,
            "warnings": warnings,
            "topological_order": order,
        }
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_findings_human(report)
        return EXIT_OK if not findings else EXIT_FINDINGS

    resolve_durations(tasks)
    cal = build_calendar(args)
    report = build_schedule(plan, order, index, cal)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_schedule_human(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

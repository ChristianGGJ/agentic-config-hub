#!/usr/bin/env python3
"""replan_impact.py - diff a baseline schedule against a recomputed one.

Part of the slip-driven-replanning skill (agentic-config-hub).

Input:  baseline_schedule.json and recomputed_schedule.json - the CPM-style
        schedule outputs of the critical-path-scheduler skill, run before
        and after slip_injector.py updated the plan. Expected task fields:
        id, start, finish, is_critical, total_float_days (aliases
        early_start/early_finish and project_finish_date are tolerated so
        that skill's output chains in unchanged).

Output: deterministic impact report - project finish delta, critical-path
        membership changes, milestone breaches, float consumption - plus a
        decision-table recommendation and, on ESCALATE, an ASCII
        notification draft (payload text only; this tool never transmits
        anything).

Decision table (evaluated top-down, first match wins):
  1. any milestone breach                      -> ESCALATE
  2. finish delta > --threshold-days           -> ESCALATE
  3. 0 < finish delta <= --threshold-days      -> COMPRESS (candidates listed)
  4. finish delta <= 0 and no breach           -> ABSORB

BOUNDARY: this script never computes dates. It diffs two schedules that
the critical-path-scheduler skill computed; the forward/backward pass is
never re-implemented here. Deltas are measured in calendar days by date
subtraction - working-day arithmetic belongs to that skill.

Exit codes:
  0 - decision ABSORB (no deadline impact)
  1 - findings: decision COMPRESS or ESCALATE
  2 - usage or input error (missing file, malformed JSON, bad registry)

Python 3.8+ standard library only. No network. No LLM calls. ASCII output.
"""

import argparse
import json
import sys
from datetime import date

HARDNESS_CLASSES = ("contractual", "internal", "aspirational")
DEFAULT_THRESHOLD_DAYS = 5
BROOKS_WARNING = ("Brooks's Law: crashing by adding people to a late task "
                  "makes it later (ramp-up plus communication overhead). "
                  "Prefer fast-tracking discretionary dependencies; treat "
                  "added-resource re-estimates as suspect.")


class InputError(Exception):
    """Usage or input problem (exit code 2)."""


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise InputError("cannot read {0}: {1}".format(path, exc))
    except json.JSONDecodeError as exc:
        raise InputError("malformed JSON in {0}: {1}".format(path, exc))


def parse_date(value, context):
    if not isinstance(value, str):
        raise InputError("{0}: expected ISO date string, got {1!r}"
                         .format(context, value))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError("{0}: expected ISO date YYYY-MM-DD, got {1!r}"
                         .format(context, value))


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_schedule(raw, label):
    """Validate and normalize one schedule file into a comparable shape."""
    if not isinstance(raw, dict):
        raise InputError("{0} schedule is not a JSON object".format(label))
    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise InputError("{0} schedule has no non-empty tasks array".format(label))
    tasks = {}
    for index, entry in enumerate(tasks_raw):
        if not isinstance(entry, dict):
            raise InputError("{0} schedule: task at index {1} is not an object"
                             .format(label, index))
        task_id = entry.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise InputError("{0} schedule: task at index {1} has no string id"
                             .format(label, index))
        if task_id in tasks:
            raise InputError("{0} schedule: duplicate task id '{1}'"
                             .format(label, task_id))
        start = parse_date(entry.get("start", entry.get("early_start")),
                           "{0} schedule task '{1}' start".format(label, task_id))
        finish = parse_date(entry.get("finish", entry.get("early_finish")),
                            "{0} schedule task '{1}' finish".format(label, task_id))
        if finish < start:
            raise InputError("{0} schedule task '{1}': finish precedes start"
                             .format(label, task_id))
        float_value = entry.get("total_float_days")
        if float_value is not None and not is_number(float_value):
            raise InputError("{0} schedule task '{1}': total_float_days "
                             "must be a number".format(label, task_id))
        tasks[task_id] = {
            "start": start,
            "finish": finish,
            "is_critical": bool(entry.get("is_critical", False)),
            "total_float_days": float_value,
            "milestone": bool(entry.get("milestone", False)),
        }
    finish_value = raw.get("project_finish", raw.get("project_finish_date"))
    if finish_value is not None:
        project_finish = parse_date(
            finish_value, "{0} schedule project_finish".format(label))
    else:
        project_finish = max(task["finish"] for task in tasks.values())
    return {
        "name": raw.get("plan_name", raw.get("name", "")),
        "project_finish": project_finish,
        "tasks": tasks,
    }


def load_registry(path, recomputed):
    """Load the optional milestone registry (hardness class required)."""
    raw = load_json(path)
    entries = raw.get("milestones") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise InputError("milestone registry has no non-empty milestones array")
    registry = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise InputError("milestone registry entry is not an object")
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise InputError("milestone registry entry has no string task_id")
        if task_id not in recomputed["tasks"]:
            raise InputError("milestone registry references unknown task '{0}'"
                             .format(task_id))
        deadline = parse_date(entry.get("deadline"),
                              "milestone '{0}' deadline".format(task_id))
        hardness = entry.get("hardness")
        if hardness not in HARDNESS_CLASSES:
            raise InputError(
                "milestone '{0}': hardness must be one of: {1} "
                "(unclassified deadlines produce false escalations)"
                .format(task_id, ", ".join(HARDNESS_CLASSES)))
        registry.append({"task_id": task_id, "deadline": deadline,
                         "hardness": hardness, "source": "registry"})
    return registry


def implicit_milestones(baseline, recomputed):
    """Fallback when no registry is given: milestone-flagged tasks use their
    baseline finish as the deadline, with hardness 'unspecified'."""
    registry = []
    for task_id in sorted(baseline["tasks"]):
        task = baseline["tasks"][task_id]
        if task["milestone"] and task_id in recomputed["tasks"]:
            registry.append({"task_id": task_id, "deadline": task["finish"],
                             "hardness": "unspecified",
                             "source": "implicit-baseline-finish"})
    return registry


def find_breaches(registry, recomputed):
    breaches = []
    for entry in registry:
        forecast = recomputed["tasks"][entry["task_id"]]["finish"]
        if forecast > entry["deadline"]:
            breaches.append({
                "task_id": entry["task_id"],
                "deadline": entry["deadline"].isoformat(),
                "recomputed_finish": forecast.isoformat(),
                "breach_days": (forecast - entry["deadline"]).days,
                "hardness": entry["hardness"],
                "source": entry["source"],
            })
    return breaches


def diff_schedules(baseline, recomputed):
    base_tasks = baseline["tasks"]
    rec_tasks = recomputed["tasks"]
    shared = [t for t in base_tasks if t in rec_tasks]
    entered = sorted(t for t in shared
                     if not base_tasks[t]["is_critical"]
                     and rec_tasks[t]["is_critical"])
    left = sorted(t for t in shared
                  if base_tasks[t]["is_critical"]
                  and not rec_tasks[t]["is_critical"])
    slips = []
    for task_id in shared:
        delta = (rec_tasks[task_id]["finish"] - base_tasks[task_id]["finish"]).days
        if delta != 0:
            slips.append({
                "id": task_id,
                "baseline_finish": base_tasks[task_id]["finish"].isoformat(),
                "recomputed_finish": rec_tasks[task_id]["finish"].isoformat(),
                "slip_days": delta,
            })
    slips.sort(key=lambda e: (-e["slip_days"], e["id"]))
    floats = []
    for task_id in shared:
        base_float = base_tasks[task_id]["total_float_days"]
        rec_float = rec_tasks[task_id]["total_float_days"]
        if base_float is None or rec_float is None or base_float == rec_float:
            continue
        floats.append({
            "id": task_id,
            "baseline_float_days": base_float,
            "recomputed_float_days": rec_float,
            "float_consumed_days": base_float - rec_float,
        })
    floats.sort(key=lambda e: (-e["float_consumed_days"], e["id"]))
    return {
        "entered_critical": entered,
        "left_critical": left,
        "task_slips": slips,
        "float_consumption": floats,
        "tasks_added": sorted(t for t in rec_tasks if t not in base_tasks),
        "tasks_removed": sorted(t for t in base_tasks if t not in rec_tasks),
    }


def decide(finish_delta, breaches, threshold):
    if breaches:
        worst = max(b["breach_days"] for b in breaches)
        return "ESCALATE", ("{0} milestone breach(es), worst {1:+d} days"
                            .format(len(breaches), worst))
    if finish_delta > threshold:
        return "ESCALATE", ("finish delta {0:+d} days exceeds threshold {1}"
                            .format(finish_delta, threshold))
    if finish_delta > 0:
        return "COMPRESS", ("finish delta {0:+d} days within threshold {1}; "
                            "compression candidates listed"
                            .format(finish_delta, threshold))
    return "ABSORB", ("finish delta {0:+d} days; slip absorbed in float, "
                      "no replan needed".format(finish_delta))


def compression_candidates(recomputed):
    """Tasks on the recomputed critical path, longest calendar span first."""
    candidates = []
    for task_id, task in recomputed["tasks"].items():
        if not task["is_critical"] or task["milestone"]:
            continue
        span = (task["finish"] - task["start"]).days + 1
        candidates.append({"id": task_id, "calendar_span_days": span,
                           "techniques": ["fast_track", "crash"]})
    candidates.sort(key=lambda e: (-e["calendar_span_days"], e["id"]))
    return candidates


def build_notification(name, baseline, recomputed, finish_delta, breaches,
                       candidates, slip_event):
    lines = []
    lines.append("SUBJECT: Schedule impact: {0} finish moves {1} -> {2} ({3:+d} days)"
                 .format(name or "project",
                         baseline["project_finish"].isoformat(),
                         recomputed["project_finish"].isoformat(),
                         finish_delta))
    if slip_event:
        lines.append("Trigger: confirmed slip on task '{0}' ({1:+g} days; cause: {2})"
                     .format(slip_event.get("task_id", "unknown"),
                             slip_event.get("reported_delay_days", 0),
                             slip_event.get("cause", "unspecified")))
    else:
        lines.append("Trigger: confirmed schedule slip (see attached impact report).")
    lines.append("Impact: forecast project finish moves from {0} to {1} "
                 "({2:+d} calendar days)."
                 .format(baseline["project_finish"].isoformat(),
                         recomputed["project_finish"].isoformat(), finish_delta))
    for breach in breaches:
        lines.append("Milestone breach: '{0}' ({1}) deadline {2}, new forecast "
                     "{3} ({4:+d} days)."
                     .format(breach["task_id"], breach["hardness"],
                             breach["deadline"], breach["recomputed_finish"],
                             breach["breach_days"]))
    lines.append("Options for the approval gate:")
    if candidates:
        lines.append("  1. COMPRESS - candidates on the new critical path: {0}"
                     .format(", ".join(c["id"] for c in candidates)))
        lines.append("     {0}".format(BROOKS_WARNING))
    else:
        lines.append("  1. COMPRESS - no non-milestone critical tasks available")
    lines.append("  2. REBASELINE - requires change-control approval at a "
                 "human gate; the old baseline stays in git history")
    lines.append("  3. DESCOPE or renegotiate the breached milestone(s)")
    lines.append("No plan changes have been applied. This replan is held for "
                 "human approval.")
    return "\n".join(lines)


def human_report(result):
    lines = []
    lines.append("REPLAN IMPACT REPORT - {0}".format(result["plan_name"] or "(unnamed)"))
    lines.append("=" * 60)
    finish = result["project_finish"]
    lines.append("Project finish : baseline {0} -> recomputed {1} "
                 "(delta {2:+d} calendar days, threshold {3})"
                 .format(finish["baseline"], finish["recomputed"],
                         finish["delta_calendar_days"], result["threshold_days"]))
    lines.append("Decision       : {0} ({1})".format(result["decision"],
                                                     result["decision_reason"]))
    changes = result["critical_path_changes"]
    lines.append("Critical-path changes:")
    lines.append("  entered : {0}".format(", ".join(changes["entered"]) or "(none)"))
    lines.append("  left    : {0}".format(", ".join(changes["left"]) or "(none)"))
    if result["task_slips"]:
        lines.append("Task slips (nonzero, calendar days):")
        for slip in result["task_slips"]:
            lines.append("  {0}: {1} -> {2} ({3:+d} days)".format(
                slip["id"], slip["baseline_finish"],
                slip["recomputed_finish"], slip["slip_days"]))
    if result["float_consumption"]:
        lines.append("Float consumption (positive = consumed):")
        for entry in result["float_consumption"]:
            lines.append("  {0}: float {1} -> {2} ({3:+g} consumed)".format(
                entry["id"], entry["baseline_float_days"],
                entry["recomputed_float_days"], entry["float_consumed_days"]))
    if result["milestone_breaches"]:
        lines.append("Milestone breaches:")
        for breach in result["milestone_breaches"]:
            lines.append("  {0} ({1}): deadline {2}, forecast {3} ({4:+d} days)"
                         .format(breach["task_id"], breach["hardness"],
                                 breach["deadline"], breach["recomputed_finish"],
                                 breach["breach_days"]))
    if result["compression_candidates"]:
        lines.append("Compression candidates (recomputed critical path, "
                     "longest span first):")
        for candidate in result["compression_candidates"]:
            lines.append("  {0} (calendar span {1} days; techniques: {2})"
                         .format(candidate["id"], candidate["calendar_span_days"],
                                 ", ".join(candidate["techniques"])))
        lines.append("  WARNING - {0}".format(BROOKS_WARNING))
    if result["notification_draft"]:
        lines.append("")
        lines.append("--- NOTIFICATION DRAFT (payload text only; this tool "
                     "never transmits) ---")
        lines.append(result["notification_draft"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="replan_impact.py",
        description=("Diff a baseline schedule against a recomputed one "
                     "(both produced by the critical-path-scheduler skill) "
                     "and emit a deterministic replan decision: ABSORB, "
                     "COMPRESS, or ESCALATE with a notification draft. "
                     "This tool never computes dates and never transmits "
                     "notifications."))
    parser.add_argument("--baseline", required=True,
                        help="path to baseline_schedule.json")
    parser.add_argument("--recomputed", required=True,
                        help="path to recomputed_schedule.json")
    parser.add_argument("--milestones",
                        help="optional milestone registry JSON: {milestones: "
                             "[{task_id, deadline, hardness}]}; hardness must "
                             "be contractual|internal|aspirational; replaces "
                             "implicit milestone-flag detection")
    parser.add_argument("--slip-event",
                        help="optional slip_event.json used to name the "
                             "trigger in the notification draft")
    parser.add_argument("--threshold-days", type=int,
                        default=DEFAULT_THRESHOLD_DAYS,
                        help="finish-delta tolerance in calendar days before "
                             "ESCALATE (default {0})".format(DEFAULT_THRESHOLD_DAYS))
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable impact report")
    args = parser.parse_args(argv)

    try:
        if args.threshold_days < 0:
            raise InputError("--threshold-days must be >= 0")
        baseline = normalize_schedule(load_json(args.baseline), "baseline")
        recomputed = normalize_schedule(load_json(args.recomputed), "recomputed")
        if args.milestones:
            registry = load_registry(args.milestones, recomputed)
        else:
            registry = implicit_milestones(baseline, recomputed)
        slip_event = load_json(args.slip_event) if args.slip_event else None
    except InputError as exc:
        print("INPUT ERROR: {0}".format(exc), file=sys.stderr)
        return 2

    finish_delta = (recomputed["project_finish"] - baseline["project_finish"]).days
    breaches = find_breaches(registry, recomputed)
    decision, reason = decide(finish_delta, breaches, args.threshold_days)
    candidates = compression_candidates(recomputed) if finish_delta > 0 else []
    name = recomputed["name"] or baseline["name"]
    notification = None
    if decision == "ESCALATE":
        notification = build_notification(name, baseline, recomputed,
                                          finish_delta, breaches, candidates,
                                          slip_event)
    diff = diff_schedules(baseline, recomputed)
    exit_code = 0 if decision == "ABSORB" else 1
    result = {
        "plan_name": name,
        "decision": decision,
        "decision_reason": reason,
        "exit_code": exit_code,
        "threshold_days": args.threshold_days,
        "project_finish": {
            "baseline": baseline["project_finish"].isoformat(),
            "recomputed": recomputed["project_finish"].isoformat(),
            "delta_calendar_days": finish_delta,
        },
        "critical_path_changes": {
            "entered": diff["entered_critical"],
            "left": diff["left_critical"],
        },
        "task_slips": diff["task_slips"],
        "float_consumption": diff["float_consumption"],
        "tasks_added": diff["tasks_added"],
        "tasks_removed": diff["tasks_removed"],
        "milestone_breaches": breaches,
        "compression_candidates": candidates,
        "brooks_law_warning": BROOKS_WARNING if candidates else None,
        "notification_draft": notification,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(human_report(result))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

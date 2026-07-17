#!/usr/bin/env python3
"""slip_injector.py - apply confirmed schedule slips onto a plan.json.

Part of the slip-driven-replanning skill (agentic-config-hub).

Input:  plan.json in the hub canonical tasks shape, plus ONE slip source:
          --slip-event       slip_event.json:
                             {task_id, reported_delay_days, cause, timestamp}
                             (optional extra field: cause_class)
          --variance-report  the --json output of the plan-baseline-tracking
                             skill. Minimal contract read here: an object
                             whose "variances" (or "tasks") array carries
                             entries with task_id and slip_days.

Output: updated plan.json (--out) with duration_days adjusted for the
        slipped tasks, a per-task slip_history entry, and a plan-level
        replan_ledger that increments and NEVER resets (guard against the
        "replan-as-reset" anti-pattern: replans share one attempt budget).

BOUNDARY: this script never computes dates and never re-implements the
CPM forward/backward pass. The recompute engine is the
critical-path-scheduler skill, consumed at AGENT level: the hosting agent
runs this injector, then that skill's CPM tool on the emitted plan, then
replan_impact.py on the baseline/recomputed schedule pair.

Exit codes:
  0 - updated plan written
  1 - validation findings (unknown task, non-positive resulting duration,
      malformed plan graph); nothing is written
  2 - usage or input error (missing file, malformed JSON, bad flags)

Python 3.8+ standard library only. No network. No LLM calls. ASCII output.
"""

import argparse
import json
import sys

VALID_CAUSE_CLASSES = ("estimate", "dependency", "resource", "scope", "external")


class InputError(Exception):
    """Usage or input problem (exit code 2)."""


def load_json(path):
    """Load a JSON file or raise InputError."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise InputError("cannot read {0}: {1}".format(path, exc))
    except json.JSONDecodeError as exc:
        raise InputError("malformed JSON in {0}: {1}".format(path, exc))


def validate_plan(plan):
    """Structural checks on the hub canonical plan shape.

    Duplicates the id/depends_on validation pattern whose merge-gate
    authority is hitl_gate_validator rule R5 (hub canon). The pattern is
    duplicated here per the hub portability rule - never imported or
    executed across skill folders.
    """
    findings = []
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        findings.append("plan has no non-empty tasks array")
        return findings, {}
    by_id = {}
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            findings.append("task at index {0} is not an object".format(index))
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            findings.append("task at index {0} has no string id".format(index))
            continue
        if task_id in by_id:
            findings.append("duplicate task id '{0}'".format(task_id))
            continue
        by_id[task_id] = task
    for task_id, task in by_id.items():
        deps = task.get("depends_on", []) or []
        if not isinstance(deps, list):
            findings.append("task '{0}': depends_on is not an array".format(task_id))
            continue
        for dep in deps:
            if dep not in by_id:
                findings.append(
                    "task '{0}' depends on unknown task '{1}'".format(task_id, dep))
    findings.extend(detect_cycles(by_id))
    return findings, by_id


def detect_cycles(by_id):
    """DFS-coloring cycle detection (mirrors R5 semantics, duplicated in)."""
    white, gray, black = 0, 1, 2
    color = {task_id: white for task_id in by_id}
    findings = []

    def visit(node, stack):
        color[node] = gray
        stack.append(node)
        deps = by_id[node].get("depends_on", []) or []
        if isinstance(deps, list):
            for dep in deps:
                if dep not in color:
                    continue
                if color[dep] == gray:
                    cycle = stack[stack.index(dep):] + [dep]
                    findings.append(
                        "dependency cycle: {0}".format(" -> ".join(cycle)))
                elif color[dep] == white:
                    visit(dep, stack)
        stack.pop()
        color[node] = black

    for task_id in by_id:
        if color[task_id] == white:
            visit(task_id, [])
    return findings


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def slips_from_event(event):
    """Extract the single slip carried by a slip_event.json object."""
    task_id = event.get("task_id")
    delay = event.get("reported_delay_days")
    if not isinstance(task_id, str) or not task_id:
        raise InputError("slip event has no string task_id")
    if not is_number(delay):
        raise InputError("slip event reported_delay_days must be a number")
    return [{
        "task_id": task_id,
        "delay_days": delay,
        "cause": event.get("cause", ""),
        "cause_class": event.get("cause_class"),
        "timestamp": event.get("timestamp", ""),
        "source": "slip_event",
    }]


def slips_from_variance(report):
    """Extract nonzero slips from a plan-baseline-tracking --json report."""
    entries = None
    for key in ("variances", "tasks"):
        value = report.get(key)
        if isinstance(value, list):
            entries = value
            break
    if entries is None:
        raise InputError(
            "variance report has no 'variances' or 'tasks' array "
            "(minimal contract: entries with task_id and slip_days)")
    slips = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        task_id = entry.get("task_id")
        delay = entry.get("slip_days", entry.get("reported_delay_days"))
        if not isinstance(task_id, str) or not task_id or not is_number(delay):
            continue
        if delay == 0:
            continue
        slips.append({
            "task_id": task_id,
            "delay_days": delay,
            "cause": entry.get("cause", ""),
            "cause_class": entry.get("cause_class"),
            "timestamp": entry.get("timestamp", entry.get("ts", "")),
            "source": "variance_report",
        })
    if not slips:
        raise InputError("variance report contains no nonzero slips to apply")
    return slips


def stage_slips(by_id, slips):
    """Validate every slip before touching the plan. All-or-nothing."""
    findings = []
    warnings = []
    staged = []
    for slip in slips:
        task = by_id.get(slip["task_id"])
        if task is None:
            findings.append(
                "slip references unknown task '{0}'".format(slip["task_id"]))
            continue
        duration = task.get("duration_days")
        if not is_number(duration) or duration <= 0:
            findings.append(
                "task '{0}' has no positive numeric duration_days to adjust"
                .format(slip["task_id"]))
            continue
        new_duration = duration + slip["delay_days"]
        if new_duration <= 0:
            findings.append(
                "slip of {0} days on task '{1}' yields non-positive duration {2}"
                .format(slip["delay_days"], slip["task_id"], new_duration))
            continue
        cause_class = slip.get("cause_class")
        if cause_class is not None and cause_class not in VALID_CAUSE_CLASSES:
            warnings.append(
                "task '{0}': unknown cause_class '{1}' (expected one of: {2})"
                .format(slip["task_id"], cause_class,
                        ", ".join(VALID_CAUSE_CLASSES)))
        staged.append({
            "task_id": slip["task_id"],
            "old_duration_days": duration,
            "new_duration_days": new_duration,
            "delay_days": slip["delay_days"],
            "cause": slip.get("cause", ""),
            "cause_class": cause_class,
            "timestamp": slip.get("timestamp", ""),
            "source": slip["source"],
        })
    return findings, warnings, staged


def commit_slips(plan, by_id, staged):
    """Apply staged slips and advance the never-resetting replan ledger."""
    for record in staged:
        task = by_id[record["task_id"]]
        task["duration_days"] = record["new_duration_days"]
        history = task.setdefault("slip_history", [])
        history.append({
            "delay_days": record["delay_days"],
            "old_duration_days": record["old_duration_days"],
            "new_duration_days": record["new_duration_days"],
            "cause": record["cause"],
            "cause_class": record["cause_class"],
            "timestamp": record["timestamp"],
            "source": record["source"],
        })
    ledger = plan.setdefault("replan_ledger", {"iterations": 0, "events": []})
    ledger["iterations"] = int(ledger.get("iterations", 0)) + 1
    events = ledger.setdefault("events", [])
    for record in staged:
        events.append({
            "iteration": ledger["iterations"],
            "task_id": record["task_id"],
            "delay_days": record["delay_days"],
            "cause": record["cause"],
            "timestamp": record["timestamp"],
            "source": record["source"],
        })
    return ledger["iterations"]


def write_plan(plan, path):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(plan, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise InputError("cannot write {0}: {1}".format(path, exc))


NEXT_STEP = ("recompute dates with the critical-path-scheduler skill's CPM "
             "tool (agent-level composition), then diff the baseline and "
             "recomputed schedules with replan_impact.py")


def human_report(plan_name, staged, warnings, iterations, out_path):
    lines = []
    lines.append("SLIP INJECTION REPORT - {0}".format(plan_name or "(unnamed plan)"))
    lines.append("=" * 60)
    lines.append("Applied slips:")
    for record in staged:
        lines.append(
            "  task '{0}': duration_days {1} -> {2} (delay {3:+g}, cause_class {4})"
            .format(record["task_id"], record["old_duration_days"],
                    record["new_duration_days"], record["delay_days"],
                    record["cause_class"] or "unclassified"))
    lines.append("Replan ledger: iteration {0} (ledger never resets; replans "
                 "share one attempt budget)".format(iterations))
    for warning in warnings:
        lines.append("WARNING: {0}".format(warning))
    lines.append("Updated plan written to: {0}".format(out_path))
    lines.append("Next step: {0}.".format(NEXT_STEP))
    lines.append("This script never computes dates.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="slip_injector.py",
        description=("Apply a confirmed schedule slip (slip event or "
                     "plan-baseline-tracking variance report) onto plan.json, "
                     "emitting an updated plan ready for a CPM recompute by "
                     "the critical-path-scheduler skill. This tool never "
                     "computes dates itself."))
    parser.add_argument("--plan", required=True,
                        help="path to plan.json (hub canonical tasks shape)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--slip-event",
                        help="path to slip_event.json "
                             "{task_id, reported_delay_days, cause, timestamp}")
    source.add_argument("--variance-report",
                        help="path to a plan-baseline-tracking --json report "
                             "(entries with task_id and slip_days)")
    parser.add_argument("--out", required=True,
                        help="path to write the updated plan.json")
    parser.add_argument("--json", action="store_true",
                        help="print a machine-readable summary instead of text")
    args = parser.parse_args(argv)

    try:
        plan = load_json(args.plan)
        findings, by_id = validate_plan(plan)
        if findings:
            report_findings(findings, args.json)
            return 1
        if args.slip_event:
            slips = slips_from_event(load_json(args.slip_event))
        else:
            slips = slips_from_variance(load_json(args.variance_report))
        findings, warnings, staged = stage_slips(by_id, slips)
        if findings:
            report_findings(findings, args.json)
            return 1
        iterations = commit_slips(plan, by_id, staged)
        write_plan(plan, args.out)
    except InputError as exc:
        print("INPUT ERROR: {0}".format(exc), file=sys.stderr)
        return 2

    plan_name = plan.get("name", "")
    if args.json:
        print(json.dumps({
            "plan": plan_name,
            "applied": staged,
            "warnings": warnings,
            "replan_iterations": iterations,
            "output": args.out,
            "next_step": NEXT_STEP,
        }, indent=2))
    else:
        print(human_report(plan_name, staged, warnings, iterations, args.out))
    return 0


def report_findings(findings, as_json):
    if as_json:
        print(json.dumps({"findings": findings, "applied": []}, indent=2))
    else:
        print("VALIDATION FINDINGS (nothing written):")
        for finding in findings:
            print("  - {0}".format(finding))


if __name__ == "__main__":
    sys.exit(main())

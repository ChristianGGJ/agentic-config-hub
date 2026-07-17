#!/usr/bin/env python3
"""wbs_validator.py - Structural validator for Work Breakdown Structure (WBS) JSON.

Validates a WBS hierarchy (nested "wbs" tree or flat "elements" list) against
deterministic structural rules, and optionally serializes the leaf tasks into
the hub canonical plan.json contract (id / description / depends_on, with
depends_on emitted as empty stubs for the critical-path-scheduler skill to fill).

Checks:
  U1  unique, non-empty element ids                                    FAIL
  B1  every non-leaf has >= 2 children (structural proxy for the
      100-percent rule: a parent with one child merely restates it)    FAIL
  D1  tree depth within bounds (--min-depth 2 .. --max-depth 4)        FAIL
  E1  empty or missing descriptions                                    FAIL
  X1  exact duplicate descriptions (mutual-exclusivity proxy)          FAIL
  X2  near-duplicate descriptions (difflib ratio >= --similarity)      WARN
  O1  orphans: flat elements whose parent id does not exist, and
      parent-chain cycles                                              FAIL
  N1  dotted-id numbering drift (nested form, e.g. child "3.1"
      under parent "2")                                                WARN
  G1  leaf without a named deliverable                                 WARN
  H1  (--check-estimates only) leaf estimate_hours outside the 8/80
      bounds = FAIL; leaf missing estimate_hours = WARN

Exit codes: 0 = PASS (zero FAIL findings), 1 = gate fail, 2 = usage/input error.

No network access, no LLM calls: same input, same output, every run, offline.
"""

import argparse
import difflib
import json
import re
import sys

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

HONESTY_NOTE = (
    "HONESTY NOTE: this validator checks STRUCTURE only. Exit code 0 means the"
    " hierarchy is well-formed, not that the plan is complete or correct. The"
    " 100-percent rule (children capture ALL of the parent scope) and task"
    " manageability are semantic judgments no script can make. Semantic"
    " completeness review belongs to the plan-critique skill and to the"
    " Phase-3 HUMAN GATE, never to this exit code."
)

DOTTED_ID = re.compile(r"^[0-9]+(\.[0-9]+)*$")

# Fields copied verbatim from a leaf WBS element onto its emitted plan.json
# task. All are OPTIONAL extras tolerated by the hub canonical contract
# (the minimal contract is id/description/depends_on, per the same
# id/depends_on shape hitl_gate_validator rule R5 enforces on workflows).
PASSTHROUGH_FIELDS = (
    "deliverable", "owner", "estimate_hours", "estimate_basis",
    "duration_days", "baseline_start", "baseline_finish", "milestone",
)


def add_finding(findings, check, severity, message, elements=None):
    findings.append({
        "check": check,
        "severity": severity,
        "message": message,
        "elements": sorted(elements) if elements else [],
    })


def walk_nested(nodes, parent_id, depth, out):
    """Flatten a nested 'wbs' tree into normalized element records."""
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError(
                "nested 'wbs' entries must be JSON objects (found %s at depth %d)"
                % (type(node).__name__, depth))
        children = node.get("children") or []
        if not isinstance(children, list):
            raise ValueError(
                "'children' of element %r must be a list" % node.get("id"))
        entry = {
            "id": str(node.get("id", "") or "").strip(),
            "description": str(node.get("description", "") or "").strip(),
            "parent": parent_id,
            "depth": depth,
            "children_count": len(children),
            "raw": node,
        }
        out.append(entry)
        if children:
            walk_nested(children, entry["id"], depth + 1, out)


def build_flat(elements, findings):
    """Normalize a flat 'elements' list; detect orphans and parent cycles."""
    out = []
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError("flat 'elements' entries must be JSON objects")
        parent = element.get("parent")
        parent = str(parent).strip() if parent not in (None, "") else None
        out.append({
            "id": str(element.get("id", "") or "").strip(),
            "description": str(element.get("description", "") or "").strip(),
            "parent": parent,
            "depth": 1,
            "children_count": 0,
            "raw": element,
        })
    by_id = {}
    for entry in out:
        by_id.setdefault(entry["id"], entry)
    orphans = []
    for entry in out:
        if entry["parent"] is None:
            continue
        if entry["parent"] in by_id:
            by_id[entry["parent"]]["children_count"] += 1
        else:
            orphans.append(entry["id"])
    if orphans:
        add_finding(findings, "O1", "FAIL",
                    "orphan element(s): declared parent id does not exist",
                    orphans)
    for entry in out:
        depth, seen, cursor = 1, {entry["id"]}, entry
        while cursor["parent"] is not None and cursor["parent"] in by_id:
            cursor = by_id[cursor["parent"]]
            if cursor["id"] in seen:
                add_finding(findings, "O1", "FAIL",
                            "parent-chain cycle detected", [entry["id"]])
                break
            seen.add(cursor["id"])
            depth += 1
        entry["depth"] = depth
    return out


def check_unique_ids(elements, findings):
    seen, dupes, empty = set(), set(), 0
    for entry in elements:
        if not entry["id"]:
            empty += 1
        elif entry["id"] in seen:
            dupes.add(entry["id"])
        else:
            seen.add(entry["id"])
    if empty:
        add_finding(findings, "U1", "FAIL",
                    "%d element(s) have an empty id" % empty)
    if dupes:
        add_finding(findings, "U1", "FAIL",
                    "duplicate element id(s)", list(dupes))


def check_branching(elements, findings):
    single = [e["id"] for e in elements if e["children_count"] == 1]
    if single:
        add_finding(findings, "B1", "FAIL",
                    "non-leaf element(s) with a single child break the"
                    " 100-percent-rule structural proxy (>= 2 children"
                    " required; a lone child restates its parent)", single)


def check_depth(elements, min_depth, max_depth, findings):
    if not elements:
        add_finding(findings, "D1", "FAIL", "WBS contains no elements")
        return 0
    max_seen = max(e["depth"] for e in elements)
    too_deep = [e["id"] for e in elements if e["depth"] > max_depth]
    if too_deep:
        add_finding(findings, "D1", "FAIL",
                    "element(s) deeper than --max-depth %d (over-decomposition;"
                    " consider rolling-wave elaboration)" % max_depth, too_deep)
    if max_seen < min_depth:
        add_finding(findings, "D1", "FAIL",
                    "tree depth %d is shallower than --min-depth %d (the"
                    " objective was not actually decomposed)"
                    % (max_seen, min_depth))
    return max_seen


def normalize_text(text):
    return " ".join(text.lower().split())


def check_descriptions(elements, similarity, findings):
    empty = [e["id"] for e in elements if not e["description"]]
    if empty:
        add_finding(findings, "E1", "FAIL",
                    "element(s) missing a description", empty)
    groups = {}
    for entry in elements:
        if entry["description"]:
            key = normalize_text(entry["description"])
            groups.setdefault(key, []).append(entry["id"])
    exact_flagged = set()
    for text, ids in sorted(groups.items()):
        if len(ids) > 1:
            add_finding(findings, "X1", "FAIL",
                        "exact duplicate description (mutual exclusivity"
                        " broken): '%s'" % text, ids)
            exact_flagged.add(text)
    uniques = sorted(t for t in groups if t not in exact_flagged)
    for i in range(len(uniques)):
        for j in range(i + 1, len(uniques)):
            ratio = difflib.SequenceMatcher(None, uniques[i], uniques[j]).ratio()
            if ratio >= similarity:
                add_finding(findings, "X2", "WARN",
                            "near-duplicate descriptions (ratio %.2f >= %.2f):"
                            " '%s' vs '%s'"
                            % (ratio, similarity, uniques[i], uniques[j]),
                            groups[uniques[i]] + groups[uniques[j]])


def check_numbering(elements, findings):
    bad = []
    for entry in elements:
        if (entry["parent"] and DOTTED_ID.match(entry["id"] or "")
                and DOTTED_ID.match(entry["parent"])):
            if not entry["id"].startswith(entry["parent"] + "."):
                bad.append(entry["id"])
    if bad:
        add_finding(findings, "N1", "WARN",
                    "dotted id(s) do not extend the parent id"
                    " (numbering drift)", bad)


def check_deliverables(elements, findings):
    missing = [e["id"] for e in elements if e["children_count"] == 0
               and not str(e["raw"].get("deliverable", "") or "").strip()]
    if missing:
        add_finding(findings, "G1", "WARN",
                    "leaf element(s) without a named deliverable"
                    " (deliverable-oriented WBS expected)", missing)


def check_estimates(elements, min_hours, max_hours, findings):
    missing, invalid, out_of_bounds = [], [], []
    for entry in elements:
        if entry["children_count"] != 0:
            continue
        value = entry["raw"].get("estimate_hours")
        if value is None:
            missing.append(entry["id"])
        elif (not isinstance(value, (int, float)) or isinstance(value, bool)
                or value <= 0):
            invalid.append(entry["id"])
        elif value < min_hours or value > max_hours:
            out_of_bounds.append(entry["id"])
    if invalid:
        add_finding(findings, "H1", "FAIL",
                    "leaf estimate_hours must be a positive number", invalid)
    if out_of_bounds:
        add_finding(findings, "H1", "FAIL",
                    "leaf estimate_hours outside the %g/%g bounds (8/80 rule:"
                    " decompose further or roll up)" % (min_hours, max_hours),
                    out_of_bounds)
    if missing:
        add_finding(findings, "H1", "WARN",
                    "leaf element(s) missing estimate_hours", missing)


def slug(text):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return cleaned or "task"


def emit_tasks(name, elements, out_path):
    """Serialize leaf elements to the hub canonical plan.json contract."""
    tasks, used = [], set()
    for entry in elements:
        if entry["children_count"] != 0:
            continue
        base = "t-" + slug(entry["id"])
        task_id, suffix = base, 2
        while task_id in used:
            task_id = "%s-%d" % (base, suffix)
            suffix += 1
        used.add(task_id)
        task = {
            "id": task_id,
            "description": entry["description"],
            "depends_on": [],
            "wbs_id": entry["id"],
        }
        for field in PASSTHROUGH_FIELDS:
            if field in entry["raw"]:
                task[field] = entry["raw"][field]
        tasks.append(task)
    plan = {"name": name, "version": "0.1.0", "tasks": tasks}
    with open(out_path, "w", encoding="ascii") as handle:
        json.dump(plan, handle, indent=2)
        handle.write("\n")
    return len(tasks)


def human_report(summary):
    lines = []
    lines.append("WBS STRUCTURAL VALIDATION")
    lines.append("=" * 64)
    lines.append("File      : %s" % summary["file"])
    lines.append("Format    : %s" % summary["format"])
    lines.append("Elements  : %d (leaves: %d)"
                 % (summary["elements"], summary["leaves"]))
    lines.append("Max depth : %d (bounds %d-%d)"
                 % (summary["max_depth"], summary["depth_bounds"]["min"],
                    summary["depth_bounds"]["max"]))
    if summary["estimate_bounds"]:
        lines.append("Estimates : enforced at %g-%g hours per leaf (8/80 rule)"
                     % (summary["estimate_bounds"]["min_hours"],
                        summary["estimate_bounds"]["max_hours"]))
    lines.append("")
    if summary["findings"]:
        lines.append("FINDINGS:")
        for finding in summary["findings"]:
            ids = ""
            if finding["elements"]:
                ids = " [%s]" % ", ".join(finding["elements"])
            lines.append("  %-4s %-3s %s%s" % (finding["severity"],
                                               finding["check"],
                                               finding["message"], ids))
    else:
        lines.append("FINDINGS: none")
    lines.append("")
    lines.append("RESULT: %s (%d FAIL / %d WARN)"
                 % (summary["result"], summary["fail_count"],
                    summary["warn_count"]))
    if summary["emitted_tasks"]:
        lines.append("Emitted %d leaf task(s) to %s (depends_on stubs are"
                     " empty; populate them via the critical-path-scheduler"
                     " skill)" % (summary["emitted_tasks"]["tasks"],
                                  summary["emitted_tasks"]["path"]))
    elif summary["emit_skipped"]:
        lines.append("Task emission SKIPPED: resolve the FAIL findings first.")
    lines.append("")
    lines.append(HONESTY_NOTE)
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wbs_validator.py",
        description=(
            "Deterministic structural validator for WBS JSON hierarchies"
            " (nested 'wbs' tree or flat 'elements' list with parent"
            " references). Optionally emits leaf tasks in the hub canonical"
            " plan.json contract with empty depends_on stubs."),
        epilog=(
            "Examples:\n"
            "  python wbs_validator.py assets/sample_wbs.json\n"
            "  python wbs_validator.py assets/sample_wbs.json"
            " --check-estimates --json\n"
            "  python wbs_validator.py assets/sample_wbs.json"
            " --emit-tasks plan.json\n\n" + HONESTY_NOTE),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wbs_file", help="path to the WBS JSON file")
    parser.add_argument("--min-depth", type=int, default=2,
                        help="minimum required tree depth (default: 2)")
    parser.add_argument("--max-depth", type=int, default=4,
                        help="maximum allowed tree depth (default: 4)")
    parser.add_argument("--similarity", type=float, default=0.85,
                        help="near-duplicate description threshold, 0-1"
                             " (default: 0.85)")
    parser.add_argument("--check-estimates", action="store_true",
                        help="enforce the 8/80 estimate bounds on leaf"
                             " estimate_hours (off by default)")
    parser.add_argument("--min-hours", type=float, default=8.0,
                        help="lower estimate bound in hours (default: 8)")
    parser.add_argument("--max-hours", type=float, default=80.0,
                        help="upper estimate bound in hours (default: 80)")
    parser.add_argument("--emit-tasks", metavar="OUT_FILE",
                        help="on PASS, serialize leaf tasks to OUT_FILE in the"
                             " hub canonical plan.json contract (id,"
                             " description, depends_on: [] stubs, wbs_id and"
                             " other extras passed through)")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable JSON report")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.min_depth < 1 or args.max_depth < args.min_depth:
        print("usage error: require 1 <= --min-depth <= --max-depth",
              file=sys.stderr)
        return EXIT_USAGE
    if not 0.0 < args.similarity <= 1.0:
        print("usage error: --similarity must be in (0, 1]", file=sys.stderr)
        return EXIT_USAGE
    if args.check_estimates and (args.min_hours <= 0
                                 or args.max_hours < args.min_hours):
        print("usage error: require 0 < --min-hours <= --max-hours",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        with open(args.wbs_file, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        print("input error: cannot read WBS JSON: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    findings = []
    try:
        if isinstance(doc, dict) and isinstance(doc.get("wbs"), list):
            fmt = "nested"
            elements = []
            walk_nested(doc["wbs"], None, 1, elements)
        elif isinstance(doc, dict) and isinstance(doc.get("elements"), list):
            fmt = "flat"
            elements = build_flat(doc["elements"], findings)
        else:
            print("input error: top level must be an object carrying a nested"
                  " 'wbs' list or a flat 'elements' list", file=sys.stderr)
            return EXIT_USAGE
    except (ValueError, RecursionError) as exc:
        print("input error: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    check_unique_ids(elements, findings)
    check_branching(elements, findings)
    max_depth_seen = check_depth(elements, args.min_depth, args.max_depth,
                                 findings)
    check_descriptions(elements, args.similarity, findings)
    if fmt == "nested":
        check_numbering(elements, findings)
    check_deliverables(elements, findings)
    if args.check_estimates:
        check_estimates(elements, args.min_hours, args.max_hours, findings)

    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")

    emitted, emit_skipped = None, False
    if args.emit_tasks:
        if fail_count == 0:
            try:
                count = emit_tasks(str(doc.get("name", "unnamed-wbs")),
                                   elements, args.emit_tasks)
                emitted = {"path": args.emit_tasks, "tasks": count}
            except OSError as exc:
                print("input error: cannot write %s: %s"
                      % (args.emit_tasks, exc), file=sys.stderr)
                return EXIT_USAGE
        else:
            emit_skipped = True

    summary = {
        "file": args.wbs_file,
        "format": fmt,
        "elements": len(elements),
        "leaves": sum(1 for e in elements if e["children_count"] == 0),
        "max_depth": max_depth_seen,
        "depth_bounds": {"min": args.min_depth, "max": args.max_depth},
        "estimate_bounds": ({"min_hours": args.min_hours,
                             "max_hours": args.max_hours}
                            if args.check_estimates else None),
        "findings": findings,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "result": "PASS" if fail_count == 0 else "FAIL",
        "emitted_tasks": emitted,
        "emit_skipped": emit_skipped,
        "honesty_note": HONESTY_NOTE,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(human_report(summary))
    return EXIT_PASS if fail_count == 0 else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Runaway-prevention auditor for CrewAI code (crewai-role-engineering skill).

Statically audits CrewAI Python source via the `ast` module -- the file is parsed,
never imported or executed -- for missing runaway-prevention controls that map to the
hub's exit-condition canon:

  - Agent(...) without max_iter                         -> unbounded loop (max_iterations)
  - Agent(...) with neither max_execution_time nor max_rpm -> no budget ceiling (budget)
  - Task(...) missing expected_output                   -> unverifiable output (success_predicate)
  - Task(...) with an irreversible-verb description and no human_input=True -> missing HITL gate (escalation_trigger)
  - Crew(..., process=Process.hierarchical) without manager_llm/manager_agent -> undefined coordination

Stdlib only (ast, argparse, json). No imports of crewai, no execution, no network.

Usage:
  python crewai_runaway_auditor.py path/to/crew.py
  python crewai_runaway_auditor.py src/ --json        # scans *.py recursively
  python crewai_runaway_auditor.py crew.py --strict    # warnings also fail the run

Exit codes:
  0  no blocking findings (HIGH; and MEDIUM too under --strict)
  1  blocking findings present, or I/O / parse / usage error
"""

import argparse
import ast
import json
import sys
from pathlib import Path

TOOL = "crewai_runaway_auditor"
IRREVERSIBLE_VERBS = ("delete", "deploy", "publish", "send", "drop", "migrate",
                      "purchase", "transfer", "email", "post", "remove", "overwrite")


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def _callee(node):
    """Return the simple name of a call target, e.g. 'Agent', 'Crew', 'Task'."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _kwargs(node):
    return {kw.arg: kw.value for kw in node.keywords if kw.arg}


def _literal(value):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None


def audit_tree(tree, path):
    findings = []  # (path, line, severity, message)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node)
        if name not in ("Agent", "Task", "Crew"):
            continue
        kw = _kwargs(node)
        line = getattr(node, "lineno", 0)

        if name == "Agent":
            if "max_iter" not in kw:
                findings.append((path, line, "HIGH",
                    "Agent(...) without max_iter -> unbounded reasoning loop (map to max_iterations)"))
            if "max_execution_time" not in kw and "max_rpm" not in kw:
                findings.append((path, line, "MEDIUM",
                    "Agent(...) without max_execution_time or max_rpm -> no budget ceiling (map to budget)"))

        elif name == "Task":
            if "expected_output" not in kw:
                findings.append((path, line, "MEDIUM",
                    "Task(...) missing expected_output -> output cannot be machine-verified (success_predicate)"))
            desc = _literal(kw["description"]) if "description" in kw else None
            if isinstance(desc, str) and any(v in desc.lower() for v in IRREVERSIBLE_VERBS):
                hi = kw.get("human_input")
                approved = isinstance(hi, ast.Constant) and hi.value is True
                if not approved:
                    findings.append((path, line, "HIGH",
                        "Task with an irreversible-verb description and no human_input=True -> missing HITL gate (escalation_trigger)"))

        elif name == "Crew":
            proc = kw.get("process")
            is_hier = False
            if isinstance(proc, ast.Attribute) and proc.attr == "hierarchical":
                is_hier = True
            elif isinstance(proc, ast.Constant) and proc.value == "hierarchical":
                is_hier = True
            if is_hier and "manager_llm" not in kw and "manager_agent" not in kw:
                findings.append((path, line, "HIGH",
                    "hierarchical Crew without manager_llm/manager_agent -> undefined coordination"))

    return findings


def iter_py(target):
    if target.is_file():
        return [target] if target.suffix == ".py" else []
    return sorted(target.rglob("*.py"))


def main(argv=None):
    p = UsageError(prog="crewai_runaway_auditor.py",
                   description="AST audit of CrewAI source for missing runaway-prevention controls.")
    p.add_argument("path", help="a .py file or a directory to scan recursively")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="MEDIUM findings also fail the run")
    args = p.parse_args(argv)

    target = Path(args.path)
    if not target.exists():
        sys.stderr.write("%s: error: path not found: %s\n" % (TOOL, target))
        return 1
    files = iter_py(target)
    if not files:
        sys.stderr.write("%s: error: no .py files at %s\n" % (TOOL, target))
        return 1

    findings = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except SyntaxError as exc:
            sys.stderr.write("%s: warning: skipping unparseable %s: %s\n" % (TOOL, f, exc))
            continue
        findings.extend(audit_tree(tree, str(f)))

    highs = [x for x in findings if x[2] == "HIGH"]
    mediums = [x for x in findings if x[2] == "MEDIUM"]
    blocking = highs + (mediums if args.strict else [])

    if args.json:
        print(json.dumps({
            "scanned": len(files), "strict": args.strict,
            "findings": [{"file": a, "line": b, "severity": c, "issue": d}
                         for a, b, c, d in findings],
            "blocking": len(blocking),
        }, indent=2))
    else:
        print("CrewAI runaway audit: %d file(s), %d finding(s)%s"
              % (len(files), len(findings), " [--strict]" if args.strict else ""))
        for a, b, c, d in findings:
            print("  [%s] %s:%d %s" % (c, a, b, d))
        if not findings:
            print("  clean -- all Agent/Task/Crew constructs carry their controls")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())

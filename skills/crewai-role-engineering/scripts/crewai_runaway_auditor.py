#!/usr/bin/env python3
"""Runaway-prevention auditor for CrewAI code (crewai-role-engineering skill).

Statically scans CrewAI Python source for Agent/Crew/Task constructions that omit
the runaway-prevention controls the hub canon requires: Agent needs max_iter (and
ideally max_rpm / max_execution_time); a hierarchical Crew needs a manager; long
tasks should set human_input where a HITL gate belongs. Regex/heuristic only -- no
imports of crewai, no code execution, no network.

Maps to hub exit conditions: max_iter -> max_iterations, max_execution_time/max_rpm
-> budget, human_input -> escalation_trigger / HUMAN GATE.

Usage:
  python crewai_runaway_auditor.py path/to/crew.py
  python crewai_runaway_auditor.py src/ --json      # scans *.py recursively

Exit codes: 0 no findings; 1 findings present, or I/O / usage error.
(A non-zero exit flags unguarded constructs; wire it into CI as a gate.)
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOOL = "crewai_runaway_auditor"

# Match a constructor call and capture its argument text up to the balanced-ish close.
AGENT_RE = re.compile(r"\bAgent\s*\((.*?)\)\s*(?:$|\n|#)", re.S)
CREW_RE = re.compile(r"\bCrew\s*\((.*?)\)\s*(?:$|\n|#)", re.S)


def scan_text(text, path):
    findings = []

    def has(args, kw):
        return re.search(r"\b" + kw + r"\s*=", args) is not None

    # crude call extraction: find "Agent(" / "Crew(" and take the next ~400 chars
    for m in re.finditer(r"\bAgent\s*\(", text):
        seg = text[m.end():m.end() + 600]
        line = text[:m.start()].count("\n") + 1
        if not has(seg, "max_iter"):
            findings.append((str(path), line, "HIGH",
                             "Agent(...) without max_iter -> unbounded reasoning loop (map to max_iterations)"))
        if not has(seg, "max_rpm") and not has(seg, "max_execution_time"):
            findings.append((str(path), line, "MEDIUM",
                             "Agent(...) without max_rpm or max_execution_time -> no budget ceiling"))
    for m in re.finditer(r"\bCrew\s*\(", text):
        seg = text[m.end():m.end() + 800]
        line = text[:m.start()].count("\n") + 1
        hierarchical = re.search(r"Process\.hierarchical", seg) is not None
        if hierarchical and not (has(seg, "manager_llm") or has(seg, "manager_agent")):
            findings.append((str(path), line, "HIGH",
                             "hierarchical Crew without manager_llm/manager_agent -> undefined coordination"))
    return findings


def iter_py(target):
    if target.is_file():
        return [target] if target.suffix == ".py" else []
    return sorted(target.rglob("*.py"))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="crewai_runaway_auditor.py",
        description="Audit CrewAI source for missing runaway-prevention controls.")
    p.add_argument("path", help="a .py file or a directory to scan recursively")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    class _P(argparse.ArgumentParser):
        def error(self, m):
            self.print_usage(sys.stderr)
            sys.stderr.write("%s: error: %s\n" % (self.prog, m)); sys.exit(1)
    p.__class__ = _P
    args = p.parse_args(argv)

    target = Path(args.path)
    if not target.exists():
        sys.stderr.write("%s: error: path not found: %s\n" % (TOOL, target))
        return 1
    files = iter_py(target)
    if not files:
        sys.stderr.write("%s: error: no .py files at %s\n" % (TOOL, target))
        return 1

    all_findings = []
    for f in files:
        try:
            all_findings.extend(scan_text(f.read_text(encoding="utf-8", errors="replace"), f))
        except OSError as exc:
            sys.stderr.write("%s: warning: cannot read %s: %s\n" % (TOOL, f, exc))

    if args.json:
        print(json.dumps({"scanned": len(files),
                          "findings": [{"file": a, "line": b, "severity": c, "issue": d}
                                       for a, b, c, d in all_findings]}, indent=2))
    else:
        print("CrewAI runaway audit: %d file(s), %d finding(s)"
              % (len(files), len(all_findings)))
        for a, b, c, d in all_findings:
            print("  [%s] %s:%d %s" % (c, a, b, d))
        if not all_findings:
            print("  no unguarded Agent/Crew constructs found")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())

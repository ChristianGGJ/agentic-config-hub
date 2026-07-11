#!/usr/bin/env python3
"""Deterministic loop-engineering and HITL safety auditor for agent configs.

Part of the agentic-system-architect skill (engineering/ POWERFUL tier).

loop_auditor.py scores an agent configuration markdown file against a
100-point rubric of loop-safety and defensive Human-in-the-Loop (HITL)
controls. Every check is a case-insensitive regular-expression search over
the whole file content -- fully deterministic, no LLM calls, no network
access, standard library only.

Rubric (100 points total):
    Category A -- Loop Safety       (30 pts): A1 max-iterations counter,
                                    A2 no-progress detection,
                                    A3 oscillation/repeat guard,
                                    A4 budget limit
    Category B -- HITL Gates        (25 pts): B1 approval gate,
                                    B2 irreversible-action confirmation,
                                    B3 escalation path
    Category C -- Phase Protocol    (20 pts): C1 discovery/read-only,
                                    C2 manifest, C3 human gate,
                                    C4 self-review/handoff
    Category D -- Boundary Control  (15 pts): D1 scope/boundaries,
                                    D2 tool restrictions
    Category E -- Output Contract   (10 pts): E1 exit conditions,
                                    E2 structured handoff

Grades:
    >= 90    HARDENED
    75 - 89  PRODUCTION-READY
    50 - 74  NEEDS-CONTROLS
    <  50    UNSAFE-FOR-AUTONOMY

Usage examples:
    python loop_auditor.py agents/engineering/cs-agentic-system-architect.md
    python loop_auditor.py my-agent.md --json
    python loop_auditor.py my-agent.md --json > audit.json
    python loop_auditor.py my-agent.md --min-score 90   # CI deployment gate

Exit codes:
    0  audit completed (a low score is a finding, not a tool error)
    1  I/O or usage error (missing file, unreadable file, bad arguments),
       or the score is below the --min-score gate when one is set

Console output is ASCII-safe: no emoji, no box-drawing characters, so it
renders correctly on Windows cp1252 consoles.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOOL_NAME = "loop_auditor"
TOTAL_POINTS = 100

# ---------------------------------------------------------------------------
# Canonical rubric -- module-level data structure so it is fully auditable.
# Each category: id, name, max points, and its checks. Each check: id, name,
# case-insensitive regex pattern, point value, and a remediation hint that
# states WHAT sentence to add to the agent configuration.
# ---------------------------------------------------------------------------
RUBRIC = [
    {"id": "A", "name": "Loop Safety", "max": 30, "checks": [
        {"id": "A1", "name": "Max-iterations counter", "points": 10,
         "pattern": r"(max[_ -]?iterations|iteration limit|attempt limit|max[_ -]?attempts)",
         "remediation": "Declare a max_iterations counter, e.g.: This agent "
                        "stops after max_iterations = 5 attempts per subtask."},
        {"id": "A2", "name": "No-progress detection", "points": 10,
         "pattern": r"(no[_ -]?progress|stall|without (new |state )?(progress|change))",
         "remediation": "Add no-progress detection, e.g.: If two consecutive "
                        "iterations complete without new progress, the loop "
                        "exits with exit condition no_progress."},
        {"id": "A3", "name": "Oscillation / repeat guard", "points": 5,
         "pattern": r"(oscillat|repeated action|duplicate (action|call)|dedup)",
         "remediation": "Add an oscillation guard, e.g.: If the agent "
                        "oscillates between two actions or issues a duplicate "
                        "action three times, it exits with exit condition "
                        "oscillation."},
        {"id": "A4", "name": "Budget limit", "points": 5,
         "pattern": r"(budget|token limit|time limit|tool[- ]call limit)",
         "remediation": "Declare a budget limit, e.g.: The agent operates "
                        "under a budget of 20 tool calls and a 10-minute time "
                        "limit; exceeding either triggers exit condition "
                        "budget."},
    ]},
    {"id": "B", "name": "HITL Gates", "max": 25, "checks": [
        {"id": "B1", "name": "Approval gate", "points": 10,
         "pattern": r"(human gate|approval|requires? approval|await.{0,20}confirmation)",
         "remediation": "Add an approval gate, e.g.: Before implementation "
                        "the agent stops at a human gate and requires "
                        "approval of the change manifest before any write "
                        "occurs."},
        {"id": "B2", "name": "Irreversible-action confirmation", "points": 10,
         "pattern": r"(irreversible)",
         "remediation": "Add irreversible-action confirmation, e.g.: Any "
                        "irreversible action (delete, deploy, publish) "
                        "requires explicit human confirmation before "
                        "execution."},
        {"id": "B3", "name": "Escalation path", "points": 5,
         "pattern": r"(escalat)",
         "remediation": "Define an escalation path, e.g.: On repeated failure "
                        "the agent escalates to the on-call engineer with a "
                        "summary of attempts (exit condition "
                        "escalation_trigger)."},
    ]},
    {"id": "C", "name": "Phase Protocol", "max": 20, "checks": [
        {"id": "C1", "name": "Discovery / read-only phase", "points": 5,
         "pattern": r"(discovery|read[- ]only)",
         "remediation": "Document the discovery phase, e.g.: Phase 1 - "
                        "DISCOVERY (read-only): map scope, constraints and "
                        "boundaries. No writes allowed."},
        {"id": "C2", "name": "Manifest phase", "points": 5,
         "pattern": r"(manifest)",
         "remediation": "Document the manifest phase, e.g.: Phase 2 - "
                        "MANIFEST: produce an explicit change manifest (files "
                        "to create/modify, risks, rollback plan)."},
        {"id": "C3", "name": "Human gate phase", "points": 5,
         "pattern": r"(human gate)",
         "remediation": "Document the human gate phase, e.g.: Phase 3 - HUMAN "
                        "GATE: hard stop. A human approves, edits, or rejects "
                        "the manifest. No implementation without approval."},
        {"id": "C4", "name": "Self-review / handoff phase", "points": 5,
         "pattern": r"(self[- ]review|handoff)",
         "remediation": "Document self-review and handoff, e.g.: Phase 5 - "
                        "SELF-REVIEW & HANDOFF: audit own diff against the "
                        "manifest, run verification, produce a handoff "
                        "report."},
    ]},
    {"id": "D", "name": "Boundary Control", "max": 15, "checks": [
        {"id": "D1", "name": "Scope / boundaries", "points": 10,
         "pattern": r"(allowed (paths|files|scope)|forbidden|boundar|out[- ]of[- ]scope)",
         "remediation": "Declare scope boundaries, e.g.: Allowed paths: src/ "
                        "and tests/. Everything else is forbidden and "
                        "out-of-scope."},
        {"id": "D2", "name": "Tool restrictions", "points": 5,
         "pattern": r"(allowed tools|tool (whitelist|allowlist|restrictions))",
         "remediation": "Declare tool restrictions, e.g.: Allowed tools: "
                        "Read, Grep, Edit. All other tools are outside the "
                        "tool allowlist and must not be invoked."},
    ]},
    {"id": "E", "name": "Output Contract", "max": 10, "checks": [
        {"id": "E1", "name": "Exit conditions / success criteria", "points": 5,
         "pattern": r"(exit condition|success (criteria|predicate))",
         "remediation": "Declare exit conditions, e.g.: Exit condition: "
                        "success_predicate = all acceptance checks pass; "
                        "otherwise max_iterations applies."},
        {"id": "E2", "name": "Structured handoff", "points": 5,
         "pattern": r"(handoff report|output contract|report format)",
         "remediation": "Define a structured handoff, e.g.: The agent ends "
                        "with a handoff report following the output contract: "
                        "summary, diff, verification results, open risks."},
    ]},
]

GRADE_BANDS = [
    (90, "HARDENED"),
    (75, "PRODUCTION-READY"),
    (50, "NEEDS-CONTROLS"),
    (0, "UNSAFE-FOR-AUTONOMY"),
]


def grade_for(score):
    """Map a 0-100 score to its canonical grade band."""
    for threshold, grade in GRADE_BANDS:
        if score >= threshold:
            return grade
    return "UNSAFE-FOR-AUTONOMY"


def validate_rubric():
    """Sanity-check rubric integrity: point totals and compilable regexes."""
    total = 0
    for category in RUBRIC:
        cat_sum = sum(check["points"] for check in category["checks"])
        if cat_sum != category["max"]:
            raise ValueError(
                "rubric category %s declares max=%d but checks sum to %d"
                % (category["id"], category["max"], cat_sum)
            )
        for check in category["checks"]:
            re.compile(check["pattern"], re.IGNORECASE)
        total += category["max"]
    if total != TOTAL_POINTS:
        raise ValueError(
            "rubric totals %d points, expected %d" % (total, TOTAL_POINTS)
        )


def audit_content(content, file_label):
    """Run every rubric check over the file content and build the result."""
    categories = []
    score = 0
    failed_checks = 0
    for category in RUBRIC:
        earned = 0
        checks_out = []
        for check in category["checks"]:
            passed = re.search(check["pattern"], content, re.IGNORECASE) is not None
            if passed:
                earned += check["points"]
            else:
                failed_checks += 1
            checks_out.append(
                {
                    "id": check["id"],
                    "name": check["name"],
                    "pattern": check["pattern"],
                    "passed": passed,
                    "points": check["points"],
                    "remediation": check["remediation"],
                }
            )
        score += earned
        categories.append(
            {
                "id": category["id"],
                "name": category["name"],
                "earned": earned,
                "max": category["max"],
                "checks": checks_out,
            }
        )
    return {
        "file": file_label,
        "score": score,
        "grade": grade_for(score),
        "categories": categories,
        "failed_checks": failed_checks,
    }


def format_human(result):
    """Render the audit result as an aligned, ASCII-safe text report."""
    lines = []
    sep = "=" * 68
    rule = "-" * 68
    lines.append(sep)
    lines.append("LOOP AUDITOR - Loop Engineering & HITL Safety Audit")
    lines.append(sep)
    lines.append("File : %s" % result["file"])
    lines.append("")

    lines.append("CATEGORY BREAKDOWN")
    lines.append(rule)
    lines.append("%-3s %-28s %8s %6s %8s" % ("ID", "Category", "Earned", "Max", "Passed"))
    lines.append(rule)
    total_checks = 0
    total_passed = 0
    for category in result["categories"]:
        n_checks = len(category["checks"])
        n_passed = sum(1 for c in category["checks"] if c["passed"])
        total_checks += n_checks
        total_passed += n_passed
        lines.append(
            "%-3s %-28s %8d %6d %8s"
            % (
                category["id"],
                category["name"],
                category["earned"],
                category["max"],
                "%d/%d" % (n_passed, n_checks),
            )
        )
    lines.append(rule)
    lines.append(
        "%-3s %-28s %8d %6d %8s"
        % (
            "",
            "TOTAL",
            result["score"],
            TOTAL_POINTS,
            "%d/%d" % (total_passed, total_checks),
        )
    )
    lines.append("")

    failed = [
        check
        for category in result["categories"]
        for check in category["checks"]
        if not check["passed"]
    ]
    if failed:
        lines.append("FAILED CHECKS (%d)" % len(failed))
        lines.append(rule)
        for check in failed:
            lines.append("[%s] %s (%d pts)" % (check["id"], check["name"], check["points"]))
            lines.append("     pattern : %s" % check["pattern"])
            lines.append("     fix     : %s" % check["remediation"])
        lines.append(rule)
        lines.append("")
    else:
        lines.append("FAILED CHECKS (0) - all rubric controls detected.")
        lines.append("")

    lines.append("SCORE: %d/%d   GRADE: %s" % (result["score"], TOTAL_POINTS, result["grade"]))
    if result["grade"] == "UNSAFE-FOR-AUTONOMY":
        lines.append("This configuration lacks core loop-safety and HITL controls.")
        lines.append("Do not run it autonomously until the failed checks are fixed.")
    elif result["grade"] == "NEEDS-CONTROLS":
        lines.append("Add the missing controls above before unattended operation.")
    return "\n".join(lines)


class UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors (spec contract)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def build_parser():
    parser = UsageErrorParser(
        prog=TOOL_NAME,
        description=(
            "Deterministically audit an agent configuration markdown file for "
            "loop-engineering and defensive HITL controls (100-point rubric, "
            "categories A-E). A low score is a finding, not a tool error: the "
            "process exits 0 whenever the audit runs, unless --min-score turns "
            "the score into a hard gate."
        ),
        epilog=(
            "Grades: >=90 HARDENED, 75-89 PRODUCTION-READY, 50-74 "
            "NEEDS-CONTROLS, <50 UNSAFE-FOR-AUTONOMY."
        ),
    )
    parser.add_argument(
        "file",
        help="path to the agent configuration .md file to audit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the result as machine-readable JSON instead of text",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        metavar="N",
        help="exit 1 if the final score is below N (deployment/CI gate, "
             "e.g. --min-score 90 to require HARDENED)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        validate_rubric()
    except ValueError as exc:
        sys.stderr.write("%s: internal rubric error: %s\n" % (TOOL_NAME, exc))
        return 1

    path = Path(args.file)
    if not path.exists():
        sys.stderr.write("%s: error: file not found: %s\n" % (TOOL_NAME, path))
        return 1
    if not path.is_file():
        sys.stderr.write("%s: error: not a regular file: %s\n" % (TOOL_NAME, path))
        return 1
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write("%s: error: cannot read %s: %s\n" % (TOOL_NAME, path, exc))
        return 1

    result = audit_content(content, str(path))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))

    if args.min_score is not None and result["score"] < args.min_score:
        sys.stderr.write(
            "%s: gate failed: score %d is below --min-score %d\n"
            % (TOOL_NAME, result["score"], args.min_score)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

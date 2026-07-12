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
    python loop_auditor.py agents/cs-agentic-system-architect.md
    python loop_auditor.py my-agent.md --json
    python loop_auditor.py my-agent.md --json > audit.json
    python loop_auditor.py my-agent.md --min-score 90   # CI deployment gate
    python loop_auditor.py my-agent.md --history .audit/ledger.json

Optional cross-run reflection memory (--history):
    Without --history the tool is stateless and behaves exactly as before.
    With --history <ledger.json> it APPENDS this run's verdict (file, score,
    grade, failed_check_ids, timestamp) to a JSON ledger, then reads prior
    records for the SAME file and computes score_delta, a no_progress flag
    (>= 2 consecutive runs with no score increase and the same failed checks),
    an oscillation flag (a failed check that disappeared then reappeared), and
    a recurring-findings digest. This is the deterministic, git-versionable
    critique ledger that turns the single-trial evaluator-optimizer loop into a
    Reflexion-style episodic-memory loop (see
    references/self_reflection_critique_loops.md). It is still stdlib-only and
    makes no LLM or network call; --timestamp overrides the recorded time.

Exit codes:
    0  audit completed (a low score is a finding, not a tool error)
    1  I/O or usage error (missing file, unreadable file, bad arguments,
       unreadable/malformed --history ledger, or unwritable ledger path),
       or the score is below the --min-score gate when one is set

Console output is ASCII-safe: no emoji, no box-drawing characters, so it
renders correctly on Windows cp1252 consoles.
"""

import argparse
import datetime
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


# ---------------------------------------------------------------------------
# Optional cross-run reflection memory (--history). Everything below is inert
# unless --history is passed, so the default code path is unchanged. No LLM or
# network calls; stdlib only; ASCII-safe output.
# ---------------------------------------------------------------------------

def failed_ids_from_result(result):
    """Return the sorted list of failed check ids from an audit result."""
    return sorted(
        check["id"]
        for category in result["categories"]
        for check in category["checks"]
        if not check["passed"]
    )


def current_timestamp():
    """ISO-8601 UTC timestamp (seconds precision), used when --timestamp is absent."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def load_ledger(path):
    """Load an audit-history ledger (a JSON array of records).

    A missing or empty file yields an empty ledger. A file that exists but does
    not contain a JSON array raises ValueError (surfaced as a usage error).
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    data = json.loads(text)  # ValueError on malformed JSON -> handled by caller
    if not isinstance(data, list):
        raise ValueError("ledger root is not a JSON array")
    return data


def _oscillated(presence):
    """True if a check was present, then absent, then present again.

    presence is a chronological list of 1/0 flags (1 = the check FAILED that
    run). Collapse consecutive duplicates; if the value 1 appears >= 2 times in
    the collapsed sequence, the failure disappeared and later reappeared.
    """
    collapsed = []
    for flag in presence:
        if not collapsed or collapsed[-1] != flag:
            collapsed.append(flag)
    return collapsed.count(1) >= 2


def analyze_history(prior_records, current_record):
    """Compare the current verdict against prior runs for the SAME file.

    prior_records: chronological prior ledger records for this file.
    current_record: the record about to be appended.
    Returns a JSON-serializable analysis dict (the 'history' block).
    """
    sequence = prior_records + [current_record]
    runs = len(sequence)
    current_score = current_record["score"]

    previous_score = prior_records[-1]["score"] if prior_records else None
    score_delta = (
        current_score - previous_score if previous_score is not None else None
    )

    # no_progress: trailing streak of runs with an identical failed-check set
    # and non-increasing score. A streak of >= 2 records means at least this
    # run plus one prior run sat at the same wall (a score plateau).
    streak = 1
    for i in range(len(sequence) - 1, 0, -1):
        cur = set(sequence[i]["failed_check_ids"])
        prev = set(sequence[i - 1]["failed_check_ids"])
        no_increase = sequence[i]["score"] <= sequence[i - 1]["score"]
        if cur == prev and no_increase:
            streak += 1
        else:
            break
    no_progress = streak >= 2

    # oscillation + recurrence: walk each check id across the full sequence.
    all_ids = set()
    for rec in sequence:
        all_ids.update(rec["failed_check_ids"])
    oscillating = []
    counts = {}
    for cid in sorted(all_ids):
        presence = [1 if cid in set(rec["failed_check_ids"]) else 0 for rec in sequence]
        counts[cid] = sum(presence)
        if _oscillated(presence):
            oscillating.append(cid)

    recurring = [
        {"id": cid, "runs_failed": counts[cid], "total_runs": runs}
        for cid in sorted(counts)
        if counts[cid] >= 2
    ]

    return {
        "runs_for_file": runs,
        "current_score": current_score,
        "previous_score": previous_score,
        "score_delta": score_delta,
        "no_progress": no_progress,
        "no_progress_streak": streak if no_progress else 0,
        "oscillating_checks": oscillating,
        "recurring_failures": recurring,
    }


def format_history(analysis, ledger_label):
    """Render the recurring-findings digest as an ASCII-safe text block."""
    rule = "-" * 68
    lines = ["", "RECURRING FINDINGS DIGEST", rule]
    lines.append("Ledger             : %s" % ledger_label)
    lines.append("Runs for this file : %d" % analysis["runs_for_file"])

    if analysis["previous_score"] is None:
        lines.append(
            "History            : first recorded run for this file; "
            "nothing to compare yet."
        )
        lines.append(rule)
        return "\n".join(lines)

    delta = analysis["score_delta"]
    sign = "+" if delta >= 0 else ""
    lines.append(
        "Score              : %d -> %d  (delta %s%d)"
        % (analysis["previous_score"], analysis["current_score"], sign, delta)
    )
    if analysis["no_progress"]:
        lines.append(
            "No-progress        : YES - score plateau across %d runs with an "
            "identical failed-check set" % analysis["no_progress_streak"]
        )
    else:
        lines.append("No-progress        : no")
    if analysis["oscillating_checks"]:
        lines.append(
            "Oscillation        : YES - %s (failed -> fixed -> failed again)"
            % ", ".join(analysis["oscillating_checks"])
        )
    else:
        lines.append("Oscillation        : no")
    if analysis["recurring_failures"]:
        lines.append("Recurring failed checks (failed in >= 2 runs):")
        for rec in analysis["recurring_failures"]:
            lines.append(
                "  %-4s failed in %d/%d runs"
                % (rec["id"], rec["runs_failed"], rec["total_runs"])
            )
    else:
        lines.append("Recurring failed checks: none")
    lines.append(rule)
    lines.append(
        "A recurring or oscillating finding is a candidate to graduate into an"
    )
    lines.append(
        "enforced authoring rule. Route it through the self-improving-agent"
    )
    lines.append("promotion pipeline; a human approves the graduation (Phase 3).")
    lines.append(rule)
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
    parser.add_argument(
        "--history",
        default=None,
        metavar="LEDGER.JSON",
        help="append this run's verdict to a JSON audit-history ledger and "
             "print a recurring-findings digest (score delta, no_progress, "
             "oscillation) computed from prior runs for the same file. Without "
             "this flag the tool is stateless and behaves exactly as before.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        metavar="ISO8601",
        help="timestamp recorded in the --history ledger for this run "
             "(default: current UTC time). Ignored without --history.",
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

    history_text = None
    if args.history is not None:
        ledger_path = Path(args.history)
        try:
            ledger = load_ledger(ledger_path)
        except ValueError as exc:
            sys.stderr.write(
                "%s: error: cannot parse --history ledger %s: %s\n"
                % (TOOL_NAME, ledger_path, exc)
            )
            return 1
        except OSError as exc:
            sys.stderr.write(
                "%s: error: cannot read --history ledger %s: %s\n"
                % (TOOL_NAME, ledger_path, exc)
            )
            return 1

        record = {
            "file": result["file"],
            "score": result["score"],
            "grade": result["grade"],
            "failed_check_ids": failed_ids_from_result(result),
            "timestamp": args.timestamp or current_timestamp(),
        }
        prior_for_file = [r for r in ledger if r.get("file") == record["file"]]
        analysis = analyze_history(prior_for_file, record)
        analysis["ledger"] = str(ledger_path)

        ledger.append(record)
        try:
            if ledger_path.parent and not ledger_path.parent.exists():
                ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_text(
                json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            sys.stderr.write(
                "%s: error: cannot write --history ledger %s: %s\n"
                % (TOOL_NAME, ledger_path, exc)
            )
            return 1

        result["history"] = analysis
        history_text = format_history(analysis, str(ledger_path))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))
        if history_text is not None:
            print(history_text)

    if args.min_score is not None and result["score"] < args.min_score:
        sys.stderr.write(
            "%s: gate failed: score %d is below --min-score %d\n"
            % (TOOL_NAME, result["score"], args.min_score)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

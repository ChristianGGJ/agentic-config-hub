#!/usr/bin/env python3
"""plan_audit.py - Severity-classified pre-execution plan critique.

Part of the plan-critique skill (agentic-config-hub). Audits a plan.json in
the hub canonical tasks shape plus an optional assumptions.json register and
emits severity-classified findings (CRITICAL / HIGH / MEDIUM / LOW), each
carrying a concrete failure scenario and a fix hint.

Check families:
  PC1-PC8  structural plan critique: missing lifecycle phases (testing/QA,
           legal-compliance review, deployment/rollout, training/handoff),
           estimates without estimate_basis, single-point-of-failure owners,
           missing milestones, duration outliers vs sibling tasks.
  AS1-AS5  assumption-register lints: assumption without evidence source,
           without invalidation test, without owner, stale review date,
           missing/empty register.

HONESTY NOTE: this tool verifies PRESENCE and STRUCTURE only. A plan can
contain the word "testing" without a real test task, and an estimate_basis
of "gut feel" still counts as present. The persona layer in SKILL.md owns
semantics; the Phase-3 HUMAN GATE owns judgment. Exit 0 means "no structural
defect found", never "this plan is realistic".

Graph semantics (cycles, dangling depends_on) are deliberately NOT checked
here - that is the critical-path-scheduler skill's transformation, and the hub
merge-gate authority for workflow-embedded graphs is hitl_gate_validator
rule R5 (cited as canon, never called).

Python 3.8+ standard library only. No network calls, no LLM calls.
Exit codes: 0 = pass, 1 = gate fail (findings at or above --fail-on, or
score below --min-score), 2 = usage/input error.
"""

import argparse
import json
import re
import statistics
import sys
from datetime import date

TOOL_NAME = "plan_audit"
TOOL_VERSION = "1.0.0"

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
SEV_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}

# Score deductions per finding severity (100-point scale, floor 0).
SCORE_DEDUCTION = {"CRITICAL": 25, "HIGH": 10, "MEDIUM": 4, "LOW": 1}

# Duration-outlier thresholds (ratio of task duration to sibling median).
SEVERE_HIGH_RATIO = 4.0
SEVERE_LOW_RATIO = 0.25
MILD_HIGH_RATIO = 2.5
MILD_LOW_RATIO = 0.4

# Owner-concentration thresholds (share of owned tasks held by one owner).
SPOF_HIGH_SHARE = 0.75
SPOF_MEDIUM_SHARE = 0.5
SPOF_MIN_OWNED_TASKS = 3

# ---------------------------------------------------------------------------
# FROZEN RUBRIC. House pattern shared with loop_auditor.py: the rubric lives
# at module level and the audit may never rewrite it mid-run (the frozen-
# rubric rule from self_reflection_critique_loops.md in the
# agentic-system-architect skill - cited as canon, duplicated by pattern).
# ---------------------------------------------------------------------------
LIFECYCLE_PHASES = (
    ("PC1", "testing / quality assurance", "CRITICAL",
     (r"\btest", r"\bqa\b", r"quality assurance", r"\bverif", r"\bvalidat",
      r"\buat\b"),
     "The build completes on schedule and ships unverified. The first "
     "integration defect is found by a customer in production, where no "
     "task, owner, or budgeted time exists to absorb the fix, so every "
     "downstream date slips silently.",
     "Add explicit testing/QA tasks with owners and durations, positioned "
     "in depends_on before any rollout task."),
    ("PC2", "legal / compliance review", "HIGH",
     (r"\blegal\b", r"\bcomplian", r"\bregulat", r"\bprivacy\b", r"\bgdpr\b",
      r"\blicens"),
     "The deliverable reaches release week before anyone asks whether it "
     "needs legal or regulatory sign-off. A late compliance objection "
     "(licensing, privacy, contract terms) blocks the launch after all "
     "engineering budget is spent - the most expensive moment to find it.",
     "Add a legal/compliance review task with a named approver, scheduled "
     "early enough that an objection can still change the design."),
    ("PC3", "deployment / rollout", "HIGH",
     (r"\bdeploy", r"\broll-?out\b", r"\brelease\b", r"\blaunch\b",
      r"\bcutover\b", r"\bgo[- ]live\b"),
     "The team declares the work done in the repository, but nobody planned "
     "the cutover: no rollout window, no rollback owner, no environment "
     "checklist. Go-live becomes an unplanned emergency performed under "
     "pressure.",
     "Add deployment/rollout tasks covering the release window, rollback "
     "path, and a named owner for the cutover."),
    ("PC4", "training / handoff", "MEDIUM",
     (r"\btrain", r"\bhand-?off\b", r"\bhandover\b", r"\bonboard",
      r"\bknowledge transfer"),
     "The system ships, the build team rolls off, and the operating team "
     "receives no training or handoff material. The first incident is "
     "handled by people who have never seen the system, turning a minor "
     "fault into an outage.",
     "Add training and handoff tasks with the receiving team named as the "
     "acceptance signal."),
)


class AuditInputError(Exception):
    """Raised for unreadable/invalid inputs; mapped to exit code 2."""


def load_json_file(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise AuditInputError("cannot read %s file '%s': %s" % (what, path, exc))
    except json.JSONDecodeError as exc:
        raise AuditInputError("%s file '%s' is not valid JSON: %s" % (what, path, exc))


def validate_plan(data):
    """Enforce the hub canonical plan shape; return the tasks list."""
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise AuditInputError(
            "plan must be a JSON object with a 'tasks' array (hub canonical shape)")
    tasks = data["tasks"]
    if not tasks:
        raise AuditInputError("plan has an empty 'tasks' array - nothing to critique")
    seen_ids = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise AuditInputError("task at index %d is not a JSON object" % index)
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise AuditInputError("task at index %d has no non-empty string 'id'" % index)
        if task_id in seen_ids:
            raise AuditInputError("duplicate task id '%s'" % task_id)
        seen_ids.add(task_id)
        description = task.get("description")
        if not isinstance(description, str) or not description.strip():
            raise AuditInputError("task '%s' has no non-empty 'description'" % task_id)
        duration = task.get("duration_days")
        if duration is not None and (isinstance(duration, bool)
                                     or not isinstance(duration, (int, float))
                                     or duration < 0):
            raise AuditInputError(
                "task '%s' has a non-numeric or negative 'duration_days'" % task_id)
        depends = task.get("depends_on")
        if depends is not None and not isinstance(depends, list):
            raise AuditInputError("task '%s' field 'depends_on' must be an array" % task_id)
    return tasks


def validate_assumptions(data):
    """Accept {"assumptions": [...]} or a bare array; return the list."""
    if isinstance(data, dict) and isinstance(data.get("assumptions"), list):
        items = data["assumptions"]
    elif isinstance(data, list):
        items = data
    else:
        raise AuditInputError(
            "assumptions register must be a JSON object with an 'assumptions' "
            "array (or a bare array of assumption objects)")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AuditInputError("assumption at index %d is not a JSON object" % index)
    return items


def make_finding(check_id, severity, location, summary, failure_scenario, fix):
    return {
        "check_id": check_id,
        "severity": severity,
        "location": location,
        "summary": summary,
        "failure_scenario": failure_scenario,
        "fix": fix,
    }


def fmt_num(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def task_text(task):
    parts = (str(task.get("description", "")), str(task.get("deliverable", "")),
             str(task.get("id", "")))
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# PC family: structural plan critique
# ---------------------------------------------------------------------------

def check_lifecycle(tasks):
    """PC1-PC4: every standard lifecycle phase appears somewhere in the plan."""
    findings = []
    blobs = [task_text(task) for task in tasks]
    for check_id, phase, severity, patterns, scenario, fix in LIFECYCLE_PHASES:
        found = any(re.search(pattern, blob)
                    for blob in blobs for pattern in patterns)
        if not found:
            findings.append(make_finding(
                check_id, severity, "plan-level",
                "Missing lifecycle phase: no %s task found anywhere in the plan" % phase,
                scenario, fix))
    return findings


def check_estimate_basis(tasks):
    """PC5: any task with a duration must record how the number was produced."""
    findings = []
    for task in tasks:
        duration = task.get("duration_days")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            continue
        if str(task.get("estimate_basis", "")).strip():
            continue
        findings.append(make_finding(
            "PC5", "HIGH", "task:" + task["id"],
            "Estimate without basis: task '%s' commits to %s day(s) with no "
            "'estimate_basis'" % (task["id"], fmt_num(duration)),
            "Under schedule pressure the number for task '%s' cannot be "
            "defended or re-derived; the planning-fallacy default (a "
            "best-case inside-view guess) silently becomes the baseline "
            "every downstream task and date depends on." % task["id"],
            "Record how the estimate was produced - ideally a reference "
            "class of comparable completed work plus the adjustment applied "
            "(see references/planning_fallacy_and_reference_class.md)."))
    return findings


def check_owner_concentration(tasks):
    """PC6: one owner holding most of the plan is a bus factor of one."""
    findings = []
    owned = [(task["id"], str(task.get("owner", "")).strip()) for task in tasks]
    owned = [(task_id, owner) for task_id, owner in owned if owner]
    if len(owned) < SPOF_MIN_OWNED_TASKS:
        return findings
    counts = {}
    for _task_id, owner in owned:
        counts[owner] = counts.get(owner, 0) + 1
    total = len(owned)
    for owner in sorted(counts):
        share = counts[owner] / total
        if share < SPOF_MEDIUM_SHARE:
            continue
        severity = "HIGH" if share >= SPOF_HIGH_SHARE else "MEDIUM"
        findings.append(make_finding(
            "PC6", severity, "owner:" + owner,
            "Single-point-of-failure owner: '%s' owns %d of %d owned tasks "
            "(%d%%)" % (owner, counts[owner], total, round(share * 100)),
            "One resignation, illness, or reassignment of '%s' stalls most "
            "of the plan at once, and no second owner has the context to "
            "resume the work mid-stream." % owner,
            "Redistribute ownership, or record an explicit human-approved "
            "risk acceptance for the concentration at the gate."))
    return findings


def check_milestones(tasks):
    """PC7: a plan with no milestones has no slip-detection points."""
    if any(task.get("milestone") is True for task in tasks):
        return []
    return [make_finding(
        "PC7", "MEDIUM", "plan-level",
        "No milestones declared: no task carries 'milestone': true",
        "With no intermediate checkpoint, the first hard signal that the "
        "plan is off track is the final deadline itself; slippage "
        "accumulates invisibly because there is no point at which promised "
        "is compared against actual.",
        "Mark verifiable checkpoints as 'milestone': true and attach an "
        "acceptance signal to each; baseline tracking keys on them.")]


def sibling_groups(tasks):
    """Group tasks by wbs_id parent prefix for duration comparison."""
    groups = {}
    for task in tasks:
        duration = task.get("duration_days")
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or duration <= 0):
            continue
        wbs = str(task.get("wbs_id", "")).strip()
        if wbs and "." in wbs:
            parent = wbs.rsplit(".", 1)[0]
        elif wbs:
            parent = "(root)"
        else:
            parent = "(ungrouped)"
        groups.setdefault(parent, []).append(task)
    return groups


def check_duration_outliers(tasks):
    """PC8: a task far from its sibling median hides undecomposed work."""
    findings = []
    for parent, group in sorted(sibling_groups(tasks).items()):
        if len(group) < 3:
            continue
        median = statistics.median(float(t["duration_days"]) for t in group)
        if median <= 0:
            continue
        for task in group:
            ratio = float(task["duration_days"]) / median
            if ratio >= SEVERE_HIGH_RATIO or ratio <= SEVERE_LOW_RATIO:
                severity = "MEDIUM"
            elif ratio >= MILD_HIGH_RATIO or ratio <= MILD_LOW_RATIO:
                severity = "LOW"
            else:
                continue
            findings.append(make_finding(
                "PC8", severity, "task:" + task["id"],
                "Duration outlier: task '%s' at %s day(s) vs sibling median "
                "%s day(s) in group '%s' (ratio %.2f)"
                % (task["id"], fmt_num(task["duration_days"]), fmt_num(median),
                   parent, ratio),
                "Task '%s' is estimated far from its siblings: either it "
                "hides undecomposed work and will blow up on contact, or "
                "its siblings are underestimated. Both readings invalidate "
                "the schedule that downstream tasks and dates are built "
                "on." % task["id"],
                "Decompose the outlier (or re-estimate its siblings) until "
                "sibling durations are comparable, and record the basis for "
                "the corrected numbers."))
    return findings


# ---------------------------------------------------------------------------
# AS family: assumption-register lints
# ---------------------------------------------------------------------------

def check_register_presence(register_path, assumptions):
    """AS5: an absent or empty register is itself a mandatory CRITICAL finding."""
    if register_path is not None and assumptions:
        return []
    return [make_finding(
        "AS5", "CRITICAL", "plan-level",
        "No assumption register provided, or the register is empty",
        "A plan that declares zero assumptions never has zero assumptions - "
        "it has only implicit ones. Every unstated premise is untested by "
        "definition and is discovered only at the moment it fails, "
        "mid-execution, when changing course is most expensive.",
        "Create an assumptions.json register (see "
        "assets/assumption-register-template.json) and run the Key "
        "Assumptions Check in references/assumption_register_method.md.")]


def check_assumptions(assumptions, as_of, stale_days):
    """AS1-AS4: per-assumption lints on the register entries."""
    findings = []
    for index, item in enumerate(assumptions):
        raw_id = item.get("id")
        assumption_id = str(raw_id) if raw_id else "ASM-%d" % (index + 1)
        location = "assumption:" + assumption_id
        if not str(item.get("evidence_source", "")).strip():
            findings.append(make_finding(
                "AS1", "HIGH", location,
                "Assumption '%s' has no evidence source" % assumption_id,
                "The premise is treated as fact with no traceable origin; "
                "if it is wrong, nobody can tell where the belief came "
                "from, and the tasks that depend on it fail without "
                "warning.",
                "Fill 'evidence_source' with the document, dataset, or "
                "named commitment the belief rests on; never with a "
                "restatement of the assumption itself."))
        if not str(item.get("invalidation_test", "")).strip():
            findings.append(make_finding(
                "AS2", "HIGH", location,
                "Assumption '%s' has no invalidation test" % assumption_id,
                "There is no defined observation that would reveal the "
                "premise is false before execution bets on it, so the "
                "first disproof arrives as a production failure instead of "
                "a cheap early signal.",
                "Design the cheapest observation that would falsify the "
                "assumption and record it in 'invalidation_test'; if it is "
                "genuinely untestable, escalate it at the human gate."))
        if not str(item.get("owner", "")).strip():
            findings.append(make_finding(
                "AS3", "MEDIUM", location,
                "Assumption '%s' has no owner" % assumption_id,
                "When contradicting evidence appears, no one is accountable "
                "for re-testing the premise or escalating it, and the "
                "register entry rots while the plan keeps executing on "
                "it.",
                "Assign a named owner accountable for re-testing and "
                "escalation."))
        findings.extend(check_review_date(item, assumption_id, location,
                                          as_of, stale_days))
    return findings


def check_review_date(item, assumption_id, location, as_of, stale_days):
    """AS4: the review date must exist, parse, and be recent enough."""
    raw = str(item.get("last_reviewed", "")).strip()
    scenario = ("The world has moved since assumption '%s' was last checked, "
                "and the plan is executing against a premise nobody has "
                "re-verified - the write-once assumption-log failure "
                "documented against PMBOK assumption logs." % assumption_id)
    fix = ("Re-run the Key Assumptions Check for this entry and update "
           "'last_reviewed'; re-review the register at every replan.")
    if not raw:
        return [make_finding(
            "AS4", "MEDIUM", location,
            "Assumption '%s' has never been reviewed (no 'last_reviewed' "
            "date)" % assumption_id, scenario, fix)]
    try:
        reviewed = date.fromisoformat(raw)
    except ValueError:
        return [make_finding(
            "AS4", "MEDIUM", location,
            "Assumption '%s' has an unparseable 'last_reviewed' value '%s' "
            "(expected YYYY-MM-DD)" % (assumption_id, raw), scenario, fix)]
    age_days = (as_of - reviewed).days
    if age_days < 0:
        return [make_finding(
            "AS4", "LOW", location,
            "Assumption '%s' has a 'last_reviewed' date (%s) after the "
            "as-of date (%s)" % (assumption_id, raw, as_of.isoformat()),
            "A future-dated review means the register was edited without "
            "an actual re-check, or the dates are wrong; either way the "
            "review trail cannot be trusted.", fix)]
    if age_days >= 2 * stale_days:
        return [make_finding(
            "AS4", "MEDIUM", location,
            "Assumption '%s' review is stale: last reviewed %s, %d days "
            "before the as-of date (threshold %d)"
            % (assumption_id, raw, age_days, stale_days), scenario, fix)]
    if age_days >= stale_days:
        return [make_finding(
            "AS4", "LOW", location,
            "Assumption '%s' review is aging: last reviewed %s, %d days "
            "before the as-of date (threshold %d)"
            % (assumption_id, raw, age_days, stale_days), scenario, fix)]
    return []


# ---------------------------------------------------------------------------
# Aggregation, verdict, gate, rendering
# ---------------------------------------------------------------------------

def compute_score(findings):
    score = 100
    for finding in findings:
        score -= SCORE_DEDUCTION[finding["severity"]]
    return max(score, 0)


def compute_verdict(findings):
    present = {finding["severity"] for finding in findings}
    if "CRITICAL" in present:
        return "BLOCK"
    if "HIGH" in present or "MEDIUM" in present:
        return "CONCERNS"
    return "CLEAN"


def gate_failed(findings, fail_on, score, min_score):
    if min_score is not None and score < min_score:
        return True
    if fail_on == "never":
        return False
    threshold = SEV_RANK[fail_on.upper()]
    return any(SEV_RANK[f["severity"]] <= threshold for f in findings)


VERDICT_HINTS = {
    "BLOCK": "return the plan to Phase-2 MANIFEST before the human gate",
    "CONCERNS": "annotate the findings for the Phase-3 HUMAN GATE",
    "CLEAN": "proceed to the Phase-3 HUMAN GATE",
}

HONESTY_NOTE = ("Exit 0 means 'no structural defect found', never 'this plan "
                "is realistic'. Presence checks are keyword-level; the "
                "persona layer in SKILL.md owns semantics and the human gate "
                "owns judgment.")


def render_human(payload):
    lines = []
    lines.append("=" * 64)
    lines.append("PLAN AUDIT - plan-critique skill (%s v%s)" % (TOOL_NAME, TOOL_VERSION))
    lines.append("=" * 64)
    lines.append("Plan file:        %s" % payload["plan_file"])
    lines.append("Plan name:        %s" % payload["plan_name"])
    lines.append("Tasks:            %d" % payload["task_count"])
    if payload["assumptions_file"]:
        lines.append("Assumptions file: %s (%d entries)"
                     % (payload["assumptions_file"], payload["assumption_count"]))
    else:
        lines.append("Assumptions file: (none provided)")
    lines.append("As-of date:       %s (stale threshold: %d days)"
                 % (payload["as_of"], payload["stale_days"]))
    lines.append("")
    findings = payload["findings"]
    if findings:
        lines.append("FINDINGS (%d):" % len(findings))
        lines.append("")
        for finding in findings:
            lines.append("[%s] %s at %s" % (finding["severity"],
                                            finding["check_id"],
                                            finding["location"]))
            lines.append("  Summary:  %s" % finding["summary"])
            lines.append("  Scenario: %s" % finding["failure_scenario"])
            lines.append("  Fix:      %s" % finding["fix"])
            lines.append("")
    else:
        lines.append("FINDINGS: none")
        lines.append("")
    counts = payload["severity_counts"]
    lines.append("SEVERITY COUNTS: " + " ".join(
        "%s=%d" % (name, counts[name]) for name in SEVERITIES))
    lines.append("SCORE:   %d/100" % payload["score"])
    lines.append("VERDICT: %s (%s)" % (payload["verdict"],
                                       VERDICT_HINTS[payload["verdict"]]))
    lines.append("GATE:    %s (--fail-on %s%s)"
                 % (payload["gate"]["result"], payload["gate"]["fail_on"],
                    ", --min-score %d" % payload["gate"]["min_score"]
                    if payload["gate"]["min_score"] is not None else ""))
    lines.append("")
    lines.append("NOTE: " + HONESTY_NOTE)
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="plan_audit.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=("Severity-classified pre-execution plan critique: "
                     "structural checks PC1-PC8 on plan.json plus "
                     "assumption-register lints AS1-AS5 on assumptions.json. "
                     "Every finding carries a concrete failure scenario."),
        epilog=("Exit codes: 0 = pass, 1 = gate fail (findings at or above "
                "--fail-on, or score below --min-score), 2 = usage/input "
                "error.\n\nHONESTY NOTE: " + HONESTY_NOTE + "\n\nExamples:\n"
                "  python plan_audit.py plan.json --assumptions assumptions.json\n"
                "  python plan_audit.py plan.json --assumptions assumptions.json "
                "--as-of 2026-07-16 --json\n"
                "  python plan_audit.py plan.json --fail-on critical --min-score 60"))
    parser.add_argument("plan",
                        help="path to plan.json in the hub canonical tasks shape "
                             "(tasks[] with id, description, depends_on, plus "
                             "tolerated extras such as owner, duration_days, "
                             "estimate_basis, milestone, wbs_id)")
    parser.add_argument("--assumptions", metavar="FILE",
                        help="path to the optional assumptions.json register; "
                             "omitting it (or shipping an empty register) is "
                             "itself a mandatory CRITICAL finding (AS5)")
    parser.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD",
                        help="reference date for staleness checks (default: "
                             "today; pin it explicitly for reproducible runs)")
    parser.add_argument("--stale-days", type=int, default=90, metavar="N",
                        help="review-date age in days at which an assumption "
                             "is flagged aging (LOW) and, at 2x, stale "
                             "(MEDIUM); default 90")
    parser.add_argument("--fail-on",
                        choices=["critical", "high", "medium", "low", "never"],
                        default="high",
                        help="lowest severity that fails the gate (exit 1); "
                             "'never' reports findings but always exits 0 "
                             "unless --min-score fails; default: high")
    parser.add_argument("--min-score", type=int, metavar="N",
                        help="optional CI gate: exit 1 when the 100-point "
                             "score falls below N")
    parser.add_argument("--json", action="store_true",
                        help="emit the machine-readable JSON report instead "
                             "of the human-readable one")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.stale_days <= 0:
        print("ERROR: --stale-days must be a positive integer", file=sys.stderr)
        return 2
    if args.min_score is not None and not 0 <= args.min_score <= 100:
        print("ERROR: --min-score must be between 0 and 100", file=sys.stderr)
        return 2
    try:
        if args.as_of:
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError:
                raise AuditInputError(
                    "--as-of must be YYYY-MM-DD, got '%s'" % args.as_of)
        else:
            as_of = date.today()
        plan_data = load_json_file(args.plan, "plan")
        tasks = validate_plan(plan_data)
        assumptions = []
        if args.assumptions:
            assumptions = validate_assumptions(
                load_json_file(args.assumptions, "assumptions"))
    except AuditInputError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    findings = []
    findings.extend(check_lifecycle(tasks))
    findings.extend(check_estimate_basis(tasks))
    findings.extend(check_owner_concentration(tasks))
    findings.extend(check_milestones(tasks))
    findings.extend(check_duration_outliers(tasks))
    findings.extend(check_register_presence(args.assumptions, assumptions))
    findings.extend(check_assumptions(assumptions, as_of, args.stale_days))
    findings.sort(key=lambda f: (SEV_RANK[f["severity"]], f["check_id"],
                                 f["location"]))

    counts = {name: 0 for name in SEVERITIES}
    for finding in findings:
        counts[finding["severity"]] += 1
    score = compute_score(findings)
    verdict = compute_verdict(findings)
    failed = gate_failed(findings, args.fail_on, score, args.min_score)

    payload = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "plan_file": args.plan,
        "plan_name": str(plan_data.get("name", "(unnamed)")),
        "task_count": len(tasks),
        "assumptions_file": args.assumptions,
        "assumption_count": len(assumptions),
        "as_of": as_of.isoformat(),
        "stale_days": args.stale_days,
        "findings": findings,
        "severity_counts": counts,
        "score": score,
        "verdict": verdict,
        "gate": {
            "fail_on": args.fail_on,
            "min_score": args.min_score,
            "result": "FAIL" if failed else "PASS",
        },
        "honesty_note": HONESTY_NOTE,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_human(payload))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

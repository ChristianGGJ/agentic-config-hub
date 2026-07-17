#!/usr/bin/env python3
"""Premortem Register Validator - deterministic gate for the premortem register.

Part of the plan-premortem skill (agentic-config-hub). Validates a premortem
register JSON (the hub canonical risk artifact) against the plan it hardens.
Every scenario entry must carry: a prospective-hindsight failure narrative,
a likelihood band, an impact band, an early-warning signal, a contingency
trigger linked to a task id that exists in plan.json, and an accountable
owner. Scenarios at or above the severity threshold must carry a mitigation
or an explicit accepted_by entry.

This validator is the CRITIC-style grounding tool for the skill: it checks
presence, band membership, and plan linkage deterministically. It cannot
judge whether a narrative is plausible - that remains agent and human work.
Python 3.8+ standard library only. No network, no LLM.

Exit codes:
    0 - PASS: no ERROR findings (WARN findings alone do not fail the gate
        unless --strict is set)
    1 - gate failure: one or more ERROR findings (or WARN findings under
        --strict)
    2 - usage or input error (missing file, malformed JSON, malformed plan)
"""

import argparse
import hashlib
import json
import re
import sys

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

LIKELIHOOD_BANDS = ("low", "medium", "high")
IMPACT_BANDS = ("low", "medium", "high", "critical")
IMPACT_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
BASIS_VALUES = ("evidence", "judgment")
MIN_NARRATIVE_CHARS = 40


def load_json(path, label):
    """Load a JSON file. Returns (object, error_message)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), None
    except OSError as exc:
        return None, "cannot read %s '%s': %s" % (label, path, exc)
    except json.JSONDecodeError as exc:
        return None, "%s '%s' is not valid JSON: %s" % (label, path, exc)


def collect_plan_tasks(plan):
    """Extract task ids and milestone ids from a canonical plan.json.

    Returns (task_ids, milestone_ids, errors). Errors here mean the plan
    itself is malformed, which is an input error (exit 2), not a register
    finding.
    """
    errors = []
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        return set(), set(), ["plan must be an object with a 'tasks' array"]
    task_ids = set()
    milestone_ids = set()
    for index, task in enumerate(plan["tasks"]):
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            errors.append("plan tasks[%d] is missing a string 'id'" % index)
            continue
        task_id = task["id"]
        if task_id in task_ids:
            errors.append("plan task id '%s' is duplicated" % task_id)
        task_ids.add(task_id)
        if task.get("milestone") is True:
            milestone_ids.add(task_id)
    return task_ids, milestone_ids, errors


def normalize_narrative(text):
    """Collapse a narrative to a normalized hash for duplicate detection."""
    collapsed = re.sub(r"[^a-z0-9]+", "", text.lower())
    return hashlib.sha1(collapsed.encode("ascii", "ignore")).hexdigest()


def nonempty_str(value):
    return isinstance(value, str) and bool(value.strip())


def validate_register(register, task_ids, milestone_ids, threshold):
    """Run all checks. Returns a list of finding dicts."""
    findings = []

    def add(severity, scenario_id, check, message):
        findings.append({"severity": severity, "scenario_id": scenario_id,
                         "check": check, "message": message})

    scenarios = register.get("scenarios")
    if not scenarios:
        add("ERROR", "-", "V0", "register has no scenarios; a premortem with "
            "zero simulated failures is premortem theater")
        return findings

    threshold_rank = IMPACT_RANK[threshold]
    seen_ids = set()
    seen_hashes = {}
    touched_task_ids = set()

    for index, scenario in enumerate(scenarios):
        sid = scenario.get("scenario_id")
        if not nonempty_str(sid):
            sid = "scenarios[%d]" % index
            add("ERROR", sid, "V0", "scenario is missing 'scenario_id'")
        elif sid in seen_ids:
            add("ERROR", sid, "V0", "duplicate scenario_id '%s'" % sid)
        else:
            seen_ids.add(sid)

        # V1: prospective-hindsight failure narrative
        narrative = scenario.get("failure_narrative")
        if not nonempty_str(narrative):
            add("ERROR", sid, "V1", "failure_narrative is missing or empty")
        else:
            if len(narrative.strip()) < MIN_NARRATIVE_CHARS:
                add("WARN", sid, "V1", "failure_narrative is under %d chars; "
                    "specific mechanisms need room" % MIN_NARRATIVE_CHARS)
            if "fail" not in narrative.lower():
                add("WARN", sid, "V1", "narrative never asserts failure; "
                    "prospective hindsight requires stating the failure as "
                    "accomplished fact (Klein framing)")
            digest = normalize_narrative(narrative)
            if digest in seen_hashes:
                add("WARN", sid, "V9", "narrative duplicates scenario '%s' "
                    "after normalization" % seen_hashes[digest])
            else:
                seen_hashes[digest] = sid

        # V2: likelihood band
        likelihood = scenario.get("likelihood")
        if likelihood not in LIKELIHOOD_BANDS:
            add("ERROR", sid, "V2", "likelihood '%s' is not one of %s"
                % (likelihood, "|".join(LIKELIHOOD_BANDS)))

        # V3: impact band
        impact = scenario.get("impact")
        if impact not in IMPACT_BANDS:
            add("ERROR", sid, "V3", "impact '%s' is not one of %s"
                % (impact, "|".join(IMPACT_BANDS)))

        # V4: early-warning signal
        if not nonempty_str(scenario.get("early_warning_signal")):
            add("ERROR", sid, "V4", "early_warning_signal is missing or "
                "empty; a scenario without a leading indicator is an "
                "unfalsifiable story")

        # V5: contingency trigger linked to a real plan task
        trigger = scenario.get("contingency_trigger")
        if not isinstance(trigger, dict):
            add("ERROR", sid, "V5", "contingency_trigger is missing or not "
                "an object with 'task_id' and 'condition'")
        else:
            trigger_task = trigger.get("task_id")
            if not nonempty_str(trigger_task):
                add("ERROR", sid, "V5", "contingency_trigger.task_id is "
                    "missing or empty")
            elif trigger_task not in task_ids:
                add("ERROR", sid, "V5", "contingency_trigger.task_id '%s' "
                    "does not exist in the plan" % trigger_task)
            if not nonempty_str(trigger.get("condition")):
                add("ERROR", sid, "V5", "contingency_trigger.condition is "
                    "missing or empty")

        # V6: accountable owner
        if not nonempty_str(scenario.get("owner")):
            add("ERROR", sid, "V6", "owner is missing or empty; every "
                "scenario needs a person accountable for its mitigation")

        # V7: affected task ids resolve against the plan
        affected = scenario.get("affected_task_ids")
        if not isinstance(affected, list) or not affected:
            add("ERROR", sid, "V7", "affected_task_ids must be a non-empty "
                "array of plan task ids")
        else:
            for task_id in affected:
                if task_id not in task_ids:
                    add("ERROR", sid, "V7", "affected task id '%s' does not "
                        "exist in the plan" % task_id)
                else:
                    touched_task_ids.add(task_id)

        # V8: mitigation or explicit acceptance at/above threshold
        if impact in IMPACT_RANK and IMPACT_RANK[impact] >= threshold_rank:
            has_mitigation = nonempty_str(scenario.get("mitigation"))
            has_acceptance = nonempty_str(scenario.get("accepted_by"))
            if not has_mitigation and not has_acceptance:
                add("ERROR", sid, "V8", "impact '%s' is at or above the "
                    "'%s' threshold but the scenario has neither a "
                    "mitigation nor an explicit accepted_by"
                    % (impact, threshold))

        # V10: rating basis (IEC 60812 discipline: evidence or marked judgment)
        basis = scenario.get("basis")
        if basis not in BASIS_VALUES:
            add("WARN", sid, "V10", "basis '%s' is not 'evidence' or "
                "'judgment'; unmarked ratings invite fabricated likelihoods"
                % basis)
        elif basis == "evidence" and not nonempty_str(scenario.get("evidence")):
            add("WARN", sid, "V10", "basis is 'evidence' but the evidence "
                "field is empty; cite the data or mark the rating 'judgment'")

    # V11: milestone coverage
    for milestone_id in sorted(milestone_ids - touched_task_ids):
        add("WARN", "-", "V11", "milestone task '%s' is not touched by any "
            "scenario; consider a stressor axis that threatens it"
            % milestone_id)

    return findings


def render_human(result):
    lines = []
    lines.append("PREMORTEM REGISTER VALIDATION")
    lines.append("Register:  %s" % result["register"])
    lines.append("Plan:      %s" % result["plan"])
    lines.append("Scenarios: %d  Threshold: %s"
                 % (result["scenario_count"], result["threshold"]))
    lines.append("-" * 60)
    if not result["findings"]:
        lines.append("No findings.")
    for finding in result["findings"]:
        lines.append("%-5s [%s] %s: %s" % (finding["severity"],
                                           finding["scenario_id"],
                                           finding["check"],
                                           finding["message"]))
    lines.append("-" * 60)
    lines.append("RESULT: %s (%d errors, %d warnings)"
                 % (result["status"], result["error_count"],
                    result["warning_count"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="premortem_register_validator.py",
        description=("Validate a premortem register JSON (the hub canonical "
                     "risk artifact) against the plan.json it hardens: "
                     "narrative, likelihood and impact bands, early-warning "
                     "signal, contingency trigger linked to a plan task id, "
                     "owner, and mitigation-or-acceptance at the severity "
                     "threshold."))
    parser.add_argument("register",
                        help="path to the premortem register JSON")
    parser.add_argument("--plan", required=True, metavar="FILE",
                        help="path to the canonical plan.json the register "
                             "refers to")
    parser.add_argument("--threshold", choices=IMPACT_BANDS, default="high",
                        help="impact band at or above which a mitigation or "
                             "accepted_by is mandatory (default: high)")
    parser.add_argument("--strict", action="store_true",
                        help="treat WARN findings as gate failures too")
    parser.add_argument("--json", action="store_true",
                        help="print the validation report as JSON")
    args = parser.parse_args(argv)

    register, register_error = load_json(args.register, "register")
    if register_error:
        print("ERROR: %s" % register_error, file=sys.stderr)
        return EXIT_USAGE
    if not isinstance(register, dict) or \
            not isinstance(register.get("scenarios"), list):
        print("ERROR: register must be an object with a 'scenarios' array",
              file=sys.stderr)
        return EXIT_USAGE

    plan, plan_error = load_json(args.plan, "plan")
    if plan_error:
        print("ERROR: %s" % plan_error, file=sys.stderr)
        return EXIT_USAGE
    task_ids, milestone_ids, plan_errors = collect_plan_tasks(plan)
    if plan_errors:
        for error in plan_errors:
            print("ERROR: %s" % error, file=sys.stderr)
        return EXIT_USAGE

    findings = validate_register(register, task_ids, milestone_ids,
                                 args.threshold)
    error_count = sum(1 for f in findings if f["severity"] == "ERROR")
    warning_count = sum(1 for f in findings if f["severity"] == "WARN")
    failed = error_count > 0 or (args.strict and warning_count > 0)

    result = {
        "register": args.register,
        "plan": args.plan,
        "scenario_count": len(register["scenarios"]),
        "threshold": args.threshold,
        "strict": args.strict,
        "findings": findings,
        "error_count": error_count,
        "warning_count": warning_count,
        "status": "FAIL" if failed else "PASS"
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_human(result))

    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

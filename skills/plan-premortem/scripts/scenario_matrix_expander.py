#!/usr/bin/env python3
"""Scenario Matrix Expander - deterministic stressor-axes expansion for premortems.

Part of the plan-premortem skill (agentic-config-hub). Expands a stressor-axes
specification JSON (e.g. supplier_delay x demand_multiplier x key_person_loss,
each with discrete levels) into the full cartesian scenario matrix. Each
scenario cell carries a prospective-hindsight narrative prompt and an empty
register stub that authors (human or fanned-out agents) fill in.

Deterministic by design: axes are expanded in listed order, levels in listed
order, so the same spec always yields the same matrix. The --max-scenarios cap
bounds combinatorial explosion; truncation is always reported with an explicit
notice, never silent. Python 3.8+ standard library only. No network, no LLM.

Exit codes:
    0 - matrix expanded successfully (a capped expansion still exits 0
        unless --fail-on-truncation is set)
    1 - gate failure: expansion was truncated and --fail-on-truncation was set
    2 - usage or input error (missing file, malformed JSON, invalid axes spec)
"""

import argparse
import itertools
import json
import sys

EXIT_OK = 0
EXIT_GATE_FAIL = 1
EXIT_USAGE = 2

PROMPT_TEMPLATE = (
    "It is <PROJECT_END_DATE>. The plan '<PLAN_NAME>' has failed. "
    "In this future the following stressors held: {stressors}. "
    "Write the specific story of how the failure unfolded, in past tense, "
    "as accomplished fact (prospective hindsight, Klein 2007). Name the "
    "failure mechanism, the first observable early-warning signal, and the "
    "plan task ids the failure hit. Do not hedge and do not assign blame; "
    "describe the mechanism."
)


def register_stub():
    """One empty register entry, matching the hub canonical risk artifact."""
    return {
        "failure_narrative": "<FILL: past-tense failure story asserting the failure as fact>",
        "likelihood": "<FILL: low|medium|high>",
        "impact": "<FILL: low|medium|high|critical>",
        "basis": "<FILL: evidence|judgment>",
        "evidence": "<FILL: cited data if basis=evidence, else empty>",
        "early_warning_signal": "<FILL: observable leading indicator>",
        "affected_task_ids": ["<FILL: plan task id>"],
        "contingency_trigger": {
            "task_id": "<FILL: plan task id>",
            "condition": "<FILL: threshold that activates the contingency>"
        },
        "mitigation": "<FILL: plan delta, or remove and set accepted_by instead>",
        "owner": "<FILL: person accountable for the mitigation>"
    }


def load_spec(path):
    """Load the axes spec JSON. Returns (spec, error_message)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), None
    except OSError as exc:
        return None, "cannot read axes spec '%s': %s" % (path, exc)
    except json.JSONDecodeError as exc:
        return None, "axes spec '%s' is not valid JSON: %s" % (path, exc)


def validate_spec(spec):
    """Structural validation of the axes spec. Returns a list of error strings."""
    errors = []
    if not isinstance(spec, dict):
        return ["axes spec root must be a JSON object"]
    axes = spec.get("axes")
    if not isinstance(axes, list) or not axes:
        return ["axes spec must contain a non-empty 'axes' array"]
    seen_names = set()
    for index, axis in enumerate(axes):
        label = "axes[%d]" % index
        if not isinstance(axis, dict):
            errors.append("%s must be an object with 'name' and 'levels'" % label)
            continue
        name = axis.get("name")
        levels = axis.get("levels")
        if not isinstance(name, str) or not name.strip():
            errors.append("%s is missing a non-empty string 'name'" % label)
        elif name in seen_names:
            errors.append("duplicate axis name '%s'" % name)
        else:
            seen_names.add(name)
        if not isinstance(levels, list) or not levels:
            errors.append("%s ('%s') must have a non-empty 'levels' array"
                          % (label, name if isinstance(name, str) else "?"))
            continue
        level_seen = set()
        for level in levels:
            if not isinstance(level, str) or not level.strip():
                errors.append("%s: every level must be a non-empty string" % label)
                break
            if level in level_seen:
                errors.append("%s: duplicate level '%s'" % (label, level))
                break
            level_seen.add(level)
    return errors


def expand(spec, max_scenarios, prefix):
    """Deterministic cartesian expansion of the validated spec."""
    axes = spec["axes"]
    names = [axis["name"] for axis in axes]
    level_lists = [axis["levels"] for axis in axes]
    total = 1
    for levels in level_lists:
        total *= len(levels)
    cap = total if max_scenarios <= 0 else min(total, max_scenarios)
    scenarios = []
    for index, combo in enumerate(itertools.product(*level_lists), start=1):
        if index > cap:
            break
        assignment = list(zip(names, combo))
        stressors = ", ".join("%s=%s" % (key, value) for key, value in assignment)
        scenarios.append({
            "scenario_id": "%s-%03d" % (prefix, index),
            "axes": dict(assignment),
            "narrative_prompt": PROMPT_TEMPLATE.format(stressors=stressors),
            "register_stub": register_stub()
        })
    return {
        "spec_name": spec.get("name", "unnamed"),
        "axes": names,
        "total_combinations": total,
        "emitted": len(scenarios),
        "truncated": len(scenarios) < total,
        "scenarios": scenarios
    }


def truncation_notice(matrix, max_scenarios):
    dropped = matrix["total_combinations"] - matrix["emitted"]
    return ("TRUNCATION NOTICE: emitted %d of %d combinations "
            "(--max-scenarios %d). %d combinations were NOT expanded. "
            "Raise --max-scenarios or prune axis levels to decision-relevant "
            "magnitudes." % (matrix["emitted"], matrix["total_combinations"],
                             max_scenarios, dropped))


def render_human(matrix, max_scenarios):
    lines = []
    lines.append("SCENARIO MATRIX: %s" % matrix["spec_name"])
    lines.append("Axes: %s" % " x ".join(matrix["axes"]))
    lines.append("Combinations: %d total, %d emitted"
                 % (matrix["total_combinations"], matrix["emitted"]))
    lines.append("-" * 60)
    for scenario in matrix["scenarios"]:
        cells = " | ".join("%s=%s" % (key, value)
                           for key, value in scenario["axes"].items())
        lines.append("%s  %s" % (scenario["scenario_id"], cells))
    lines.append("-" * 60)
    if matrix["truncated"]:
        lines.append(truncation_notice(matrix, max_scenarios))
    else:
        lines.append("Full cartesian expansion emitted; no truncation.")
    lines.append("Next step: fill each register_stub with a past-tense failure")
    lines.append("narrative, then gate with premortem_register_validator.py.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="scenario_matrix_expander.py",
        description=("Expand a stressor-axes spec JSON into a deterministic "
                     "cartesian scenario matrix with prospective-hindsight "
                     "narrative prompts and empty premortem register stubs."))
    parser.add_argument("axes_spec",
                        help="path to the stressor-axes spec JSON")
    parser.add_argument("--max-scenarios", type=int, default=0, metavar="N",
                        help="cap emitted scenarios at N (0 = no cap); "
                             "truncation is reported with an explicit notice")
    parser.add_argument("--prefix", default="PM", metavar="PREFIX",
                        help="scenario id prefix (default: PM)")
    parser.add_argument("--out", metavar="FILE",
                        help="write the matrix JSON to FILE instead of stdout")
    parser.add_argument("--json", action="store_true",
                        help="print the matrix as JSON (machine-readable)")
    parser.add_argument("--fail-on-truncation", action="store_true",
                        help="exit 1 when the cap truncates the expansion "
                             "(for CI use)")
    args = parser.parse_args(argv)

    spec, load_error = load_spec(args.axes_spec)
    if load_error:
        print("ERROR: %s" % load_error, file=sys.stderr)
        return EXIT_USAGE
    spec_errors = validate_spec(spec)
    if spec_errors:
        for error in spec_errors:
            print("ERROR: %s" % error, file=sys.stderr)
        return EXIT_USAGE

    matrix = expand(spec, args.max_scenarios, args.prefix)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(matrix, handle, indent=2)
                handle.write("\n")
        except OSError as exc:
            print("ERROR: cannot write '%s': %s" % (args.out, exc),
                  file=sys.stderr)
            return EXIT_USAGE
        print("Wrote %d scenarios to %s" % (matrix["emitted"], args.out))
        if matrix["truncated"]:
            print(truncation_notice(matrix, args.max_scenarios))
    elif args.json:
        print(json.dumps(matrix, indent=2))
        if matrix["truncated"]:
            print(truncation_notice(matrix, args.max_scenarios),
                  file=sys.stderr)
    else:
        print(render_human(matrix, args.max_scenarios))

    if matrix["truncated"] and args.fail_on_truncation:
        return EXIT_GATE_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

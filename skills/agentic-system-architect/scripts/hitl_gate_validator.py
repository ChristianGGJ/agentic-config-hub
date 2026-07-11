#!/usr/bin/env python3
"""hitl_gate_validator.py - Validate a workflow definition against defensive
Human-in-the-Loop (HITL) gate rules R1-R6.

Part of the agentic-system-architect skill. Canonical rule set:

  R1 CRITICAL  Every step with irreversible=true must have
               requires_approval=true OR be preceded (via its transitive
               depends_on chain) by a type=gate step.
  R2 HIGH      Every irreversible step must define a non-null rollback
               (or a literal string starting with "none:justified:").
  R3 HIGH      The workflow must define the top-level escalation object.
  R4 MEDIUM    Every type=action step must define on_failure;
               on_failure=retry requires max_retries >= 1.
  R5 MEDIUM    All depends_on references must exist and the dependency
               graph must be acyclic.
  R6 LOW       The final step should be type=check (self-review).

Result is PASS when there are no CRITICAL and no HIGH violations, otherwise
FAIL. A FAIL result is a finding, not an error: the process exits 0 whenever
validation runs; exit code 1 is reserved for I/O, parse, and usage errors.
Input is a .json file (parsed directly as the workflow object) or a .md file
(the FIRST fenced json code block -- delimited by lines starting with three
backticks and an optional "json" tag -- is extracted and parsed; no block
found = exit 1 with a clear message).

Usage examples:
  python hitl_gate_validator.py workflow.json
  python hitl_gate_validator.py workflow.json --json
  python hitl_gate_validator.py deployment-workflow.md
  python hitl_gate_validator.py deployment-workflow.md --json

Standard library only. ASCII-safe output (no emoji, no box-drawing
characters). No LLM or network calls.
"""

import argparse
import json
import re
import sys

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

STEP_DEFAULTS = {
    "irreversible": False,
    "requires_approval": False,
    "rollback": None,
    "depends_on": [],
}

ROLLBACK_WAIVER_PREFIX = "none:justified:"


class InputError(Exception):
    """Raised for I/O, parse, and schema errors (exit code 1)."""


def extract_first_json_block(markdown_text):
    """Return the first fenced json code block (untagged or json-tagged),
    or None. Blocks tagged with another language are skipped."""
    fence_re = re.compile(r"^```(\S*)\s*$")
    in_block = False
    block_matches = False
    lines = []
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        match = fence_re.match(stripped)
        if not in_block:
            if match:
                in_block = True
                block_matches = match.group(1).lower() in ("", "json")
                lines = []
            continue
        if stripped.startswith("```"):
            if block_matches:
                return "\n".join(lines)
            in_block = False
            continue
        if block_matches:
            lines.append(raw_line)
    return None


def load_workflow(path):
    """Load a workflow dict from a .json or .md file. Raises InputError."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise InputError("Cannot read file '{0}': {1}".format(path, exc))

    if path.lower().endswith(".md"):
        payload = extract_first_json_block(text)
        if payload is None:
            raise InputError(
                "No fenced json code block found in '{0}'. Add a block opened "
                "with three backticks and a 'json' tag containing the "
                "workflow definition.".format(path))
    else:
        payload = text

    try:
        workflow = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InputError("Invalid JSON in '{0}': {1}".format(path, exc))
    if not isinstance(workflow, dict):
        raise InputError("Workflow root in '{0}' must be a JSON object.".format(path))
    return workflow


def normalize_steps(workflow):
    """Return the steps list with defaults applied. Raises InputError."""
    steps = workflow.get("steps")
    if not isinstance(steps, list):
        raise InputError("Workflow is missing a 'steps' list. Define "
                         "\"steps\": [{...}] with at least one step object.")
    normalized = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise InputError("Step at position {0} is not a JSON object.".format(index + 1))
        step = dict(raw)
        for key, default in STEP_DEFAULTS.items():
            if step.get(key) is None:
                step[key] = list(default) if isinstance(default, list) else default
        if not step.get("id"):
            step["id"] = "step-{0}".format(index + 1)
        if not isinstance(step["depends_on"], list):
            step["depends_on"] = [step["depends_on"]]
        normalized.append(step)
    return normalized


def violation(rule, severity, step, issue, remediation):
    """Build one violation record."""
    return {"rule": rule, "severity": severity, "step": step,
            "issue": issue, "remediation": remediation}


def has_gate_ancestor(step_id, index):
    """True if any transitive depends_on ancestor of step_id has type=gate.

    Cycles and dangling references are tolerated here (R5 reports them).
    """
    visited = set()
    stack = list(index.get(step_id, {}).get("depends_on", []))
    while stack:
        ancestor_id = stack.pop()
        if ancestor_id in visited:
            continue
        visited.add(ancestor_id)
        ancestor = index.get(ancestor_id)
        if ancestor is None:
            continue
        if ancestor.get("type") == "gate":
            return True
        stack.extend(ancestor.get("depends_on", []))
    return False


# Rules R1-R6: small pure functions, each returning a list of violations.

def check_r1(steps, index):
    """R1 CRITICAL: irreversible steps need approval or a gate ancestor."""
    found = []
    for step in steps:
        if not step["irreversible"] or step["requires_approval"] is True:
            continue
        if has_gate_ancestor(step["id"], index):
            continue
        sid = step["id"]
        found.append(violation(
            "R1", "CRITICAL", sid,
            "Irreversible step '{0}' has requires_approval=false and no "
            "type=gate step in its depends_on chain.".format(sid),
            "Insert a type=gate step before '{0}' or set "
            "requires_approval=true on it.".format(sid)))
    return found


def check_r2(steps):
    """R2 HIGH: irreversible steps must define a rollback."""
    found = []
    for step in steps:
        if not step["irreversible"]:
            continue
        rollback = step["rollback"]
        if isinstance(rollback, str) and rollback.strip():
            continue  # real rollback or "none:justified:..." waiver
        sid = step["id"]
        found.append(violation(
            "R2", "HIGH", sid,
            "Irreversible step '{0}' has no rollback defined.".format(sid),
            "Define a rollback procedure for '{0}', or document the waiver as "
            "a string starting with \"{1}\".".format(sid, ROLLBACK_WAIVER_PREFIX)))
    return found


def check_r3(workflow):
    """R3 HIGH: the workflow must define a top-level escalation object."""
    escalation = workflow.get("escalation")
    if isinstance(escalation, dict) and escalation:
        return []
    return [violation(
        "R3", "HIGH", None,
        "Workflow does not define a top-level escalation object.",
        "Add \"escalation\": {\"contact\": \"<role-or-person>\", "
        "\"trigger\": \"<condition>\"} at the workflow root.")]


def check_r4(steps):
    """R4 MEDIUM: action steps need on_failure; retry needs max_retries."""
    found = []
    for step in steps:
        if step.get("type") != "action":
            continue
        sid = step["id"]
        on_failure = step.get("on_failure")
        if not on_failure:
            found.append(violation(
                "R4", "MEDIUM", sid,
                "Action step '{0}' does not define on_failure.".format(sid),
                "Set on_failure to one of retry, escalate, or abort on '{0}'.".format(sid)))
        elif on_failure == "retry":
            max_retries = step.get("max_retries")
            if not isinstance(max_retries, int) or max_retries < 1:
                found.append(violation(
                    "R4", "MEDIUM", sid,
                    "Action step '{0}' uses on_failure=retry without "
                    "max_retries >= 1.".format(sid),
                    "Set max_retries to an integer >= 1 on '{0}'.".format(sid)))
    return found


def check_r5(steps, index):
    """R5 MEDIUM: depends_on refs must exist; graph must be acyclic."""
    found = []
    for step in steps:
        for dep in step["depends_on"]:
            if dep not in index:
                found.append(violation(
                    "R5", "MEDIUM", step["id"],
                    "Step '{0}' depends on unknown step '{1}'.".format(step["id"], dep),
                    "Remove the reference or add a step with id '{0}'.".format(dep)))

    # Cycle detection via iterative DFS with white/grey/black coloring.
    WHITE, GREY, BLACK = 0, 1, 2
    color = {step_id: WHITE for step_id in index}
    reported = set()
    for root in index:
        if color[root] != WHITE:
            continue
        stack = [(root, iter(index[root]["depends_on"]))]
        color[root] = GREY
        path = [root]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in index:
                    continue
                if color[child] == GREY:
                    cycle = path[path.index(child):] + [child]
                    key = tuple(sorted(set(cycle)))
                    if key not in reported:
                        reported.add(key)
                        found.append(violation(
                            "R5", "MEDIUM", node,
                            "Dependency cycle detected: {0}.".format(" -> ".join(cycle)),
                            "Break the cycle so the dependency graph is acyclic."))
                elif color[child] == WHITE:
                    color[child] = GREY
                    stack.append((child, iter(index[child]["depends_on"])))
                    path.append(child)
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                path.pop()
    return found


def check_r6(steps):
    """R6 LOW: the final step should be type=check (self-review)."""
    if not steps:
        return [violation(
            "R6", "LOW", None,
            "Workflow defines no steps, so it ends without a self-review check.",
            "Add steps and finish with a type=check self-review step.")]
    last = steps[-1]
    if last.get("type") == "check":
        return []
    return [violation(
        "R6", "LOW", last["id"],
        "Final step '{0}' is type={1}, not type=check.".format(
            last["id"], last.get("type", "undefined")),
        "Append a type=check self-review step as the final step.")]


def validate(workflow):
    """Run all rules and return (steps, violations)."""
    steps = normalize_steps(workflow)
    index = {}
    for step in steps:
        index.setdefault(step["id"], step)
    violations = (check_r1(steps, index) + check_r2(steps) + check_r3(workflow)
                  + check_r4(steps) + check_r5(steps, index) + check_r6(steps))
    violations.sort(key=lambda v: (SEVERITY_ORDER.index(v["severity"]), v["rule"]))
    return steps, violations


def compute_result(violations):
    """PASS when there are no CRITICAL and no HIGH violations."""
    blocking = any(v["severity"] in ("CRITICAL", "HIGH") for v in violations)
    return "FAIL" if blocking else "PASS"


def render_human(workflow, path, steps, violations, result):
    lines = ["HITL Gate Validator", "=" * 60]
    lines.append("Workflow : {0}".format(workflow.get("name", "unnamed")))
    lines.append("Version  : {0}".format(workflow.get("version", "unspecified")))
    lines.append("File     : {0}".format(path))
    lines.append("Steps    : {0}".format(len(steps)))
    lines.append("")
    if not violations:
        lines.append("No violations found.")
    for severity in SEVERITY_ORDER:
        group = [v for v in violations if v["severity"] == severity]
        if not group:
            continue
        lines.append("{0} ({1})".format(severity, len(group)))
        lines.append("-" * 60)
        for item in group:
            step_label = item["step"] if item["step"] else "workflow"
            lines.append("  [{0}] {1}: {2}".format(item["rule"], step_label, item["issue"]))
            lines.append("       remediation: {0}".format(item["remediation"]))
        lines.append("")
    counts = {sev: 0 for sev in SEVERITY_ORDER}
    for item in violations:
        counts[item["severity"]] += 1
    summary = ", ".join("{0} {1}".format(counts[s], s) for s in SEVERITY_ORDER if counts[s])
    lines.append("Result: {0}{1}".format(result, " ({0})".format(summary) if summary else ""))
    if result == "PASS":
        lines.append("No CRITICAL or HIGH violations. Workflow gates are acceptable.")
    else:
        lines.append("CRITICAL or HIGH violations present. Fix them before "
                     "granting this workflow autonomy.")
    return "\n".join(lines)


def render_json(workflow, path, steps, violations, result):
    return json.dumps({
        "workflow": workflow.get("name", "unnamed"),
        "file": path,
        "steps": len(steps),
        "result": result,
        "violations": violations,
    }, indent=2)


class UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors (spec contract)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def build_parser():
    parser = UsageErrorParser(
        prog="hitl_gate_validator.py",
        description=(
            "Validate a workflow definition against defensive HITL gate "
            "rules R1-R6. PASS requires zero CRITICAL and zero HIGH "
            "violations. Accepts a .json workflow file or a .md file "
            "containing a fenced json code block."),
        epilog=("Exit codes: 0 when validation runs (PASS or FAIL), "
                "1 on I/O, parse, or usage errors."))
    parser.add_argument(
        "workflow",
        help="Path to a workflow .json file, or a .md file whose first "
             "fenced json code block holds the workflow definition.")
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        workflow = load_workflow(args.workflow)
        steps, violations = validate(workflow)
    except InputError as exc:
        sys.stderr.write("error: {0}\n".format(exc))
        return 1
    result = compute_result(violations)
    renderer = render_json if args.json else render_human
    print(renderer(workflow, args.workflow, steps, violations, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

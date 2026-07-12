#!/usr/bin/env python3
"""workflow_scaffolder.py - Generate and validate multi-agent workflow configs
in the hub canonical workflow schema.

Canonical schema (the same step shape checked by the agentic-system-architect
skill's hitl_gate_validator.py): every step carries
id / type (action|gate|check) / agent / description / irreversible /
requires_approval / rollback / on_failure / max_retries / depends_on, and the
workflow root carries name / version / pattern / agents / budget / steps /
escalation. Iteration (evaluator loops) is declared as a "loop" object on a
step -- NEVER as a depends_on back-edge -- so the dependency graph stays a DAG.

Scaffold mode:
  python workflow_scaffolder.py sequential --name content-pipeline
  python workflow_scaffolder.py orchestrator --name release --output wf.json

Validate mode (deterministic structural checks owned by this skill; defensive
gate rules R1-R6 for irreversible steps are owned by agentic-system-architect's
hitl_gate_validator.py and are NOT re-implemented here):
  python workflow_scaffolder.py --validate wf.json
  python workflow_scaffolder.py --validate wf.json --json

Python 3.8+ standard library only. ASCII-safe output. No LLM or network calls.
Exit codes: 0 = scaffold written / validation found no ERROR findings,
1 = ERROR findings present, or I/O, parse, or usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STEP_TYPES = ("action", "gate", "check")
ON_FAILURE_VALUES = ("retry", "escalate", "abort")
CANONICAL_EXIT_CONDITIONS = (
    "max_iterations", "no_progress", "oscillation",
    "budget", "success_predicate", "escalation_trigger",
)

DEFAULT_STEP_BUDGET = {"max_tokens": 8000, "timeout_seconds": 300}
DEFAULT_WORKFLOW_BUDGET = {
    "max_total_tokens": 60000,
    "max_tool_calls": 50,
    "wall_clock_seconds": 1800,
}
DEFAULT_ESCALATION = {
    "contact": "workflow-owner",
    "trigger": ("Retries exhausted on any step, any workflow budget exceeded, "
                "or any loop exiting on a condition other than success_predicate."),
}


def make_step(step_id, agent, description, step_type="action", depends_on=None,
              on_failure="retry", max_retries=2, budget=None, **extra):
    """Build one canonical step dict. Extra keys (route, join, loop) pass through."""
    step = {
        "id": step_id,
        "type": step_type,
        "agent": agent,
        "description": description,
        "irreversible": False,
        "requires_approval": step_type == "gate",
        "rollback": None,
        "on_failure": on_failure,
        "max_retries": max_retries,
        "depends_on": depends_on or [],
        "budget": budget or dict(DEFAULT_STEP_BUDGET),
    }
    step.update(extra)
    return step


def envelope(name, pattern, agents, steps, budget=None, **extra):
    workflow = {
        "name": name,
        "version": "1.0.0",
        "pattern": pattern,
        "agents": agents,
        "budget": budget or dict(DEFAULT_WORKFLOW_BUDGET),
        "steps": steps,
        "escalation": dict(DEFAULT_ESCALATION),
    }
    workflow.update(extra)
    return workflow


def sequential_template(name):
    agents = {
        "researcher": {"role": "Gathers sources and produces a research brief."},
        "writer": {"role": "Drafts the deliverable from the research brief."},
        "reviewer": {"role": "Checks the draft against acceptance criteria."},
    }
    steps = [
        make_step("research", "researcher",
                  "Collect sources and emit a research brief artifact."),
        make_step("draft", "writer",
                  "Produce the draft from the research brief only (not the full transcript).",
                  depends_on=["research"]),
        make_step("review", "reviewer",
                  "Self-review: check the draft against acceptance criteria and emit a verdict.",
                  step_type="check", depends_on=["draft"],
                  on_failure="escalate", max_retries=0),
    ]
    return envelope(name, "sequential", agents, steps)


def parallel_template(name):
    agents = {
        "analyst": {"role": "Researches one independent subtopic per branch."},
        "synthesizer": {"role": "Merges branch artifacts into one report."},
        "reviewer": {"role": "Checks the merged report for coverage and consistency."},
    }
    steps = [
        make_step("research-a", "analyst", "Branch A: research subtopic A and emit a summary artifact."),
        make_step("research-b", "analyst", "Branch B: research subtopic B and emit a summary artifact."),
        make_step("research-c", "analyst", "Branch C: research subtopic C and emit a summary artifact."),
        make_step("synthesize", "synthesizer",
                  "Fan-in: merge the three branch summaries into one report.",
                  depends_on=["research-a", "research-b", "research-c"],
                  max_retries=1, join="all",
                  budget={"max_tokens": 12000, "timeout_seconds": 300}),
        make_step("verify", "reviewer",
                  "Self-review: confirm every branch is represented in the merged report.",
                  step_type="check", depends_on=["synthesize"],
                  on_failure="escalate", max_retries=0),
    ]
    return envelope(name, "parallel", agents, steps)


def router_template(name):
    agents = {
        "classifier": {"role": "Assigns exactly one route label to the input."},
        "sales-specialist": {"role": "Handles sales-route requests."},
        "support-specialist": {"role": "Handles support-route requests."},
        "engineering-specialist": {"role": "Handles engineering-route requests."},
        "generalist": {"role": "Handles anything the classifier cannot place."},
        "reviewer": {"role": "Checks the chosen handler's output."},
    }
    handlers = ["handle-sales", "handle-support", "handle-engineering", "handle-general"]
    steps = [
        make_step("classify", "classifier",
                  "Assign exactly one route label; emit '__default__' when confidence is low.",
                  max_retries=1),
        make_step("handle-sales", "sales-specialist",
                  "Handle the request on the sales route.",
                  depends_on=["classify"], route="sales"),
        make_step("handle-support", "support-specialist",
                  "Handle the request on the support route.",
                  depends_on=["classify"], route="support"),
        make_step("handle-engineering", "engineering-specialist",
                  "Handle the request on the engineering route.",
                  depends_on=["classify"], route="engineering"),
        make_step("handle-general", "generalist",
                  "Fallback: handle anything routed to '__default__'.",
                  depends_on=["classify"], route="__default__"),
        make_step("verify", "reviewer",
                  "Self-review: check the output of whichever handler ran.",
                  step_type="check", depends_on=handlers,
                  on_failure="escalate", max_retries=0, join="any"),
    ]
    return envelope(name, "router", agents, steps)


def orchestrator_template(name):
    agents = {
        "planner": {"role": "Decomposes the goal into a milestone-level plan (the manifest)."},
        "researcher": {"role": "Executes research milestones from the approved plan."},
        "implementer": {"role": "Executes implementation milestones from the approved plan."},
        "integrator": {"role": "Merges milestone outputs into the final deliverable."},
        "reviewer": {"role": "Audits the deliverable against the approved plan."},
    }
    steps = [
        make_step("plan", "planner",
                  "MANIFEST: emit a milestone plan with per-milestone budgets and risks.",
                  max_retries=1),
        make_step("approve-plan", "human",
                  "HUMAN GATE: a human approves, edits, or rejects the plan. Hard stop.",
                  step_type="gate", depends_on=["plan"],
                  on_failure="escalate", max_retries=0,
                  budget={"max_tokens": 0, "timeout_seconds": 86400}),
        make_step("execute-research", "researcher",
                  "Execute research milestones strictly against the approved plan.",
                  depends_on=["approve-plan"]),
        make_step("execute-implementation", "implementer",
                  "Execute implementation milestones strictly against the approved plan.",
                  depends_on=["approve-plan"]),
        make_step("integrate", "integrator",
                  "Merge milestone artifacts; any deviation from the plan returns to 'plan'.",
                  depends_on=["execute-research", "execute-implementation"],
                  max_retries=1),
        make_step("verify", "reviewer",
                  "SELF-REVIEW: audit the deliverable against the approved plan.",
                  step_type="check", depends_on=["integrate"],
                  on_failure="escalate", max_retries=0),
    ]
    return envelope(name, "orchestrator", agents, steps,
                    execution={"max_parallel": 3, "completion_policy": "all_required"})


def evaluator_template(name):
    agents = {
        "generator": {"role": "Produces the candidate output."},
        "evaluator": {"role": "Scores the candidate against a frozen rubric."},
        "reviewer": {"role": "Final check on the accepted output."},
    }
    steps = [
        make_step("generate", "generator",
                  "Produce a candidate output for evaluation.",
                  max_retries=1),
        make_step("evaluate", "evaluator",
                  "Score the candidate against the rubric; loop back to 'generate' with "
                  "the critique until an exit condition fires.",
                  depends_on=["generate"], on_failure="escalate", max_retries=0,
                  loop={
                      "target": "generate",
                      "max_iterations": 3,
                      "pass_threshold": 0.8,
                      "exit_conditions": ["success_predicate", "max_iterations", "no_progress"],
                      "no_progress_window": 2,
                      "on_exhaustion": "escalate",
                  }),
        make_step("finalize", "reviewer",
                  "Self-review: confirm the accepted output and record the loop exit condition.",
                  step_type="check", depends_on=["evaluate"],
                  on_failure="escalate", max_retries=0),
    ]
    return envelope(name, "evaluator", agents, steps)


PATTERNS = {
    "sequential": sequential_template,
    "parallel": parallel_template,
    "router": router_template,
    "orchestrator": orchestrator_template,
    "evaluator": evaluator_template,
}


# ---------------------------------------------------------------------------
# Validation (structural contract owned by this skill)
# ---------------------------------------------------------------------------

def finding(severity, location, issue, fix):
    return {"severity": severity, "location": location, "issue": issue, "fix": fix}


def _check_top_level(config, findings):
    for key in ("name", "pattern", "steps"):
        if not config.get(key):
            findings.append(finding(
                "ERROR", "workflow",
                "Missing or empty required top-level key '{0}'.".format(key),
                "Add '{0}' at the workflow root.".format(key)))
    escalation = config.get("escalation")
    if not isinstance(escalation, dict) or not escalation.get("contact") \
            or not escalation.get("trigger"):
        findings.append(finding(
            "ERROR", "workflow",
            "Missing escalation object with non-empty 'contact' and 'trigger'.",
            "Add \"escalation\": {\"contact\": \"<role>\", \"trigger\": \"<condition>\"}."))
    if not isinstance(config.get("budget"), dict):
        findings.append(finding(
            "WARNING", "workflow",
            "No workflow-level budget object (maps to the 'budget' exit condition).",
            "Add \"budget\": {\"max_total_tokens\", \"max_tool_calls\", \"wall_clock_seconds\"}."))


def _check_steps(config, findings):
    steps = config.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}
    index = {}
    for pos, step in enumerate(steps):
        loc = step.get("id") or "step-{0}".format(pos + 1) if isinstance(step, dict) else "step-{0}".format(pos + 1)
        if not isinstance(step, dict):
            findings.append(finding("ERROR", loc, "Step is not a JSON object.",
                                    "Replace with a step object."))
            continue
        sid = step.get("id")
        if not sid or not isinstance(sid, str):
            findings.append(finding("ERROR", loc, "Step has no string 'id'.",
                                    "Give every step a unique kebab-case id."))
            continue
        if sid in index:
            findings.append(finding("ERROR", sid, "Duplicate step id.",
                                    "Make every step id unique."))
            continue
        index[sid] = step
        stype = step.get("type")
        if stype not in STEP_TYPES:
            findings.append(finding(
                "ERROR", sid,
                "Step type '{0}' is not one of {1}.".format(stype, "/".join(STEP_TYPES)),
                "Set type to action, gate, or check."))
        if stype == "action":
            if not step.get("agent"):
                findings.append(finding("ERROR", sid, "Action step has no 'agent'.",
                                        "Bind the step to an agent id."))
            on_failure = step.get("on_failure")
            if on_failure not in ON_FAILURE_VALUES:
                findings.append(finding(
                    "ERROR", sid,
                    "Action step on_failure '{0}' is not one of {1}.".format(
                        on_failure, "/".join(ON_FAILURE_VALUES)),
                    "Set on_failure to retry, escalate, or abort."))
            elif on_failure == "retry":
                retries = step.get("max_retries")
                if not isinstance(retries, int) or retries < 1:
                    findings.append(finding(
                        "ERROR", sid,
                        "on_failure=retry requires integer max_retries >= 1.",
                        "Set max_retries to an integer >= 1."))
        if stype == "gate" and step.get("requires_approval") is not True:
            findings.append(finding(
                "ERROR", sid, "Gate step must set requires_approval=true.",
                "Set requires_approval to true on the gate step."))
        if step.get("irreversible") is True:
            findings.append(finding(
                "WARNING", sid,
                "Step is irreversible: gate rules R1-R6 are out of this tool's scope.",
                "Run the agentic-system-architect skill's hitl_gate_validator.py "
                "before granting this workflow autonomy."))
    return index


def _check_references(config, index, findings):
    agents = config.get("agents")
    for sid, step in index.items():
        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            findings.append(finding("ERROR", sid, "depends_on is not a list.",
                                    "Make depends_on a list of step ids."))
            continue
        for dep in deps:
            if dep not in index:
                findings.append(finding(
                    "ERROR", sid,
                    "depends_on references unknown step '{0}'.".format(dep),
                    "Remove the reference or add a step with id '{0}'.".format(dep)))
        agent = step.get("agent")
        if isinstance(agents, dict) and agent and agent != "human" and agent not in agents:
            findings.append(finding(
                "ERROR", sid,
                "Step agent '{0}' is not declared in the top-level agents map.".format(agent),
                "Add '{0}' to \"agents\" or fix the reference.".format(agent)))
        loop = step.get("loop")
        if loop is not None:
            _check_loop(sid, loop, index, findings)


def _check_loop(sid, loop, index, findings):
    if not isinstance(loop, dict):
        findings.append(finding("ERROR", sid, "loop is not an object.",
                                "Define loop as an object with target and max_iterations."))
        return
    target = loop.get("target")
    if target not in index:
        findings.append(finding(
            "ERROR", sid,
            "loop.target '{0}' is not an existing step id.".format(target),
            "Point loop.target at the step to re-run."))
    max_iter = loop.get("max_iterations")
    if not isinstance(max_iter, int) or max_iter < 1:
        findings.append(finding(
            "ERROR", sid, "loop.max_iterations must be an integer >= 1.",
            "Set loop.max_iterations (calibrated default: 3)."))
    conditions = loop.get("exit_conditions")
    if not isinstance(conditions, list) or not conditions:
        findings.append(finding(
            "WARNING", sid,
            "loop declares no exit_conditions list.",
            "Declare exit conditions from the canonical taxonomy: {0}.".format(
                ", ".join(CANONICAL_EXIT_CONDITIONS))))
    else:
        for name in conditions:
            if name not in CANONICAL_EXIT_CONDITIONS:
                findings.append(finding(
                    "WARNING", sid,
                    "exit condition '{0}' is not in the canonical 6-type taxonomy.".format(name),
                    "Use one of: {0}.".format(", ".join(CANONICAL_EXIT_CONDITIONS))))


def _check_acyclic(index, findings):
    """Kahn's algorithm: leftover nodes mean a depends_on cycle."""
    in_degree = {sid: 0 for sid in index}
    for step in index.values():
        for dep in step.get("depends_on", []):
            if isinstance(dep, str) and step["id"] in index and dep in index:
                in_degree[step["id"]] += 1
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    seen = 0
    while queue:
        node = queue.pop()
        seen += 1
        for sid, step in index.items():
            deps = step.get("depends_on", [])
            if isinstance(deps, list) and node in deps:
                in_degree[sid] -= 1
                if in_degree[sid] == 0:
                    queue.append(sid)
    if seen < len(index):
        cyclic = sorted(sid for sid, deg in in_degree.items() if deg > 0)
        findings.append(finding(
            "ERROR", ", ".join(cyclic),
            "depends_on graph contains a cycle among these steps.",
            "Express iteration as a 'loop' object with exit conditions, "
            "never as a depends_on back-edge."))


def _check_final_step(config, findings):
    steps = config.get("steps")
    if isinstance(steps, list) and steps and isinstance(steps[-1], dict):
        if steps[-1].get("type") != "check":
            findings.append(finding(
                "WARNING", steps[-1].get("id", "final step"),
                "Final step is not type=check (self-review).",
                "End the workflow with a type=check step."))


def validate_config(config):
    findings = []
    _check_top_level(config, findings)
    index = _check_steps(config, findings)
    _check_references(config, index, findings)
    _check_acyclic(index, findings)
    _check_final_step(config, findings)
    findings.sort(key=lambda f: (f["severity"] != "ERROR", f["location"] or ""))
    return findings


def render_findings_human(path, config, findings):
    errors = sum(1 for f in findings if f["severity"] == "ERROR")
    warnings = len(findings) - errors
    lines = ["Workflow Scaffolder - Validate", "=" * 60]
    lines.append("File     : {0}".format(path))
    lines.append("Workflow : {0}".format(config.get("name", "unnamed")))
    lines.append("Pattern  : {0}".format(config.get("pattern", "unspecified")))
    lines.append("")
    if not findings:
        lines.append("No findings.")
    for item in findings:
        lines.append("  [{0}] {1}: {2}".format(
            item["severity"], item["location"], item["issue"]))
        lines.append("       fix: {0}".format(item["fix"]))
    lines.append("")
    result = "FAIL" if errors else "PASS"
    lines.append("Result: {0} ({1} ERROR, {2} WARNING)".format(result, errors, warnings))
    if errors:
        lines.append("Fix ERROR findings before running the workflow.")
    return "\n".join(lines), errors


def run_validate(path, as_json):
    try:
        text = Path(path).read_text(encoding="utf-8")
        config = json.loads(text)
    except OSError as exc:
        sys.stderr.write("error: cannot read '{0}': {1}\n".format(path, exc))
        return 1
    except json.JSONDecodeError as exc:
        sys.stderr.write("error: invalid JSON in '{0}': {1}\n".format(path, exc))
        return 1
    if not isinstance(config, dict):
        sys.stderr.write("error: workflow root in '{0}' must be a JSON object.\n".format(path))
        return 1
    findings = validate_config(config)
    errors = sum(1 for f in findings if f["severity"] == "ERROR")
    if as_json:
        print(json.dumps({
            "file": path,
            "workflow": config.get("name", "unnamed"),
            "result": "FAIL" if errors else "PASS",
            "errors": errors,
            "warnings": len(findings) - errors,
            "findings": findings,
        }, indent=2))
    else:
        report, errors = render_findings_human(path, config, findings)
        print(report)
    return 1 if errors else 0


def run_scaffold(pattern, name, output, as_json):
    config = PATTERNS[pattern](name)
    payload = json.dumps(config, indent=2)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        if as_json:
            print(json.dumps({"written": str(out), "pattern": pattern,
                              "workflow": name, "steps": len(config["steps"])}))
        else:
            print("Wrote {0} workflow '{1}' ({2} steps) to {3}".format(
                pattern, name, len(config["steps"]), out))
    else:
        print(payload)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="workflow_scaffolder.py",
        description=("Generate a multi-agent workflow config in the hub canonical "
                     "schema, or validate an existing config's structure. "
                     "Scaffolded configs pass agentic-system-architect's "
                     "hitl_gate_validator.py as generated."),
        epilog=("Exit codes: 0 = scaffold written or validation passed; "
                "1 = ERROR findings, or I/O, parse, or usage error."))
    parser.add_argument("pattern", nargs="?", choices=sorted(PATTERNS.keys()),
                        help="Workflow pattern to scaffold")
    parser.add_argument("--name", default="new-workflow",
                        help="Workflow name (default: new-workflow)")
    parser.add_argument("--output", help="Output path for the scaffolded JSON config")
    parser.add_argument("--validate", metavar="FILE",
                        help="Validate an existing workflow .json instead of scaffolding")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output (validate report / write receipt)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.validate and args.pattern:
        parser.error("give either a pattern to scaffold or --validate FILE, not both")
    if args.validate:
        return run_validate(args.validate, args.json)
    if not args.pattern:
        parser.error("a pattern is required unless --validate FILE is given")
    return run_scaffold(args.pattern, args.name, args.output, args.json)


if __name__ == "__main__":
    sys.exit(main())

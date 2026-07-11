#!/usr/bin/env python3
"""react_trace_analyzer.py - Detect runaway patterns in ReAct execution traces.
Part of the agentic-system-architect skill (engineering/ POWERFUL tier).

Analyzes a ReAct (Thought -> Action -> Observation) execution trace and flags
loop pathologies before they burn budget in production. Implements the
canonical detection set D1-D7:

    D1  CRITICAL  action loop               same (tool, input) executed >= 3 times
    D2  HIGH      oscillation               alternating A-B-A-B actions in a window of 4
    D3  HIGH      error cascade             consecutive error statuses >= budget.max_errors
    D4  MEDIUM    ReAct contract violation  step missing a non-empty thought or observation
    D5  CRITICAL  budget overrun            len(steps) >= budget.max_steps
    D6  MEDIUM    no convergence            final_answer null/absent while last step is ok
    D7  MEDIUM    reasoning loop            identical thought text appears >= 3 times

Scoring: start at 100, subtract 30 per CRITICAL, 15 per HIGH, 5 per MEDIUM
finding (floor 0). Verdicts: >= 90 HEALTHY, 60-89 DEGRADED, < 60 RUNAWAY.

Every mitigation hint maps back to the canonical exit-condition taxonomy:
max_iterations, no_progress, oscillation, budget, success_predicate,
escalation_trigger.

Expected trace schema (JSON): an object with "agent", "task", "budget"
(defaults: {"max_steps": 20, "max_errors": 3}), "steps" (a list of objects
{"step", "thought", "action": {"tool", "input"}, "observation",
"status": "ok|error"}), and "final_answer" (string or null).

Usage:
    python react_trace_analyzer.py trace.json
    python react_trace_analyzer.py trace.json --json

Exit codes:
    0  analysis completed (regardless of verdict)
    1  I/O or parse error (unreadable file, invalid JSON, missing "steps")

Standard library only. No network or LLM calls. ASCII-safe console output.
"""

import argparse
import json
import sys

# --- Canonical constants ---------------------------------------------------

DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_ERRORS = 3
REPEATED_ACTION_THRESHOLD = 3   # D1
REPEATED_THOUGHT_THRESHOLD = 3  # D7
OSCILLATION_WINDOW = 4          # D2

SEVERITY_WEIGHTS = {"CRITICAL": 30, "HIGH": 15, "MEDIUM": 5}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}

SEVERITIES = {"D1": "CRITICAL", "D2": "HIGH", "D3": "HIGH", "D4": "MEDIUM",
              "D5": "CRITICAL", "D6": "MEDIUM", "D7": "MEDIUM"}

TITLES = {"D1": "action loop", "D2": "oscillation", "D3": "error cascade",
          "D4": "ReAct contract violation", "D5": "budget overrun",
          "D6": "no convergence", "D7": "reasoning loop"}

MITIGATIONS = {
    "D1": ("Add an 'oscillation' exit condition and a dedup rule on "
           "(tool, input); cap retries with a 'max_iterations' counter."),
    "D2": ("Add an 'oscillation' exit condition that halts the loop when an "
           "A-B-A-B action pattern is detected within a sliding window."),
    "D3": ("Wire an 'escalation_trigger' exit condition to consecutive "
           "errors and enforce the error 'budget' (max_errors)."),
    "D4": ("Enforce the ReAct contract (non-empty thought and observation on "
           "every step); treat contract gaps as 'no_progress' and stop."),
    "D5": ("Enforce a 'max_iterations' exit condition backed by a hard "
           "'budget' on total steps; stop before the ceiling, not at it."),
    "D6": ("Define an explicit 'success_predicate' exit condition so the "
           "loop only terminates by emitting a final answer or escalating."),
    "D7": ("Add a 'no_progress' exit condition that fires when the same "
           "reasoning repeats without producing new state."),
}


# --- Small pure helpers ----------------------------------------------------

def _shorten(text, limit=70):
    """Trim long strings for one-line report details."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _is_blank(value):
    """True when a field is missing, null, or an empty/whitespace string."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _positive_int(value, fallback):
    """Coerce a budget value to a positive int, else use the default."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value > 0:
        return value
    return fallback


def step_number(step, index):
    """Prefer the declared step number; fall back to 1-based position."""
    number = step.get("step")
    if isinstance(number, int) and not isinstance(number, bool):
        return number
    return index + 1


def action_key(step):
    """Stable (tool, input) identity for a step's action, or None."""
    action = step.get("action")
    if not isinstance(action, dict):
        return None
    tool = str(action.get("tool", ""))
    raw = action.get("input", "")
    payload = raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True)
    return (tool, payload)


def make_finding(fid, detail, steps):
    """Assemble one finding with its canonical severity/title/mitigation."""
    return {
        "id": fid,
        "severity": SEVERITIES[fid],
        "title": TITLES[fid],
        "detail": detail,
        "steps": sorted(set(steps)),
        "mitigation": MITIGATIONS[fid],
    }


# --- Detections D1-D7 (small pure functions over the steps list) -----------

def detect_repeated_actions(steps):
    """D1: same (tool, input) pair executed >= 3 times."""
    occurrences = {}
    for idx, step in enumerate(steps):
        key = action_key(step)
        if key is None:
            continue
        occurrences.setdefault(key, []).append(step_number(step, idx))
    findings = []
    for (tool, payload), numbers in sorted(occurrences.items()):
        if len(numbers) >= REPEATED_ACTION_THRESHOLD:
            detail = ("Tool '%s' was called %d times with the identical "
                      "input '%s'." % (tool, len(numbers), _shorten(payload)))
            findings.append(make_finding("D1", detail, numbers))
    return findings


def detect_oscillation(steps):
    """D2: alternating A-B-A-B action pattern within a window of 4."""
    keys = [action_key(s) for s in steps]
    numbers = [step_number(s, i) for i, s in enumerate(steps)]
    involved = []
    first_pair = None
    for i in range(len(keys) - (OSCILLATION_WINDOW - 1)):
        a, b, c, d = keys[i], keys[i + 1], keys[i + 2], keys[i + 3]
        if a is None or b is None:
            continue
        if a == c and b == d and a != b:
            involved.extend(numbers[i:i + OSCILLATION_WINDOW])
            if first_pair is None:
                first_pair = (a, b)
    if not involved:
        return []
    (tool_a, in_a), (tool_b, in_b) = first_pair
    detail = ("Actions alternate A-B-A-B between '%s'(%s) and '%s'(%s) "
              "without new progress." % (tool_a, _shorten(in_a, 40),
                                         tool_b, _shorten(in_b, 40)))
    return [make_finding("D2", detail, involved)]


def detect_error_cascade(steps, max_errors):
    """D3: a run of consecutive 'error' statuses >= budget.max_errors."""
    runs = []
    run = []
    for idx, step in enumerate(steps):
        status = str(step.get("status", "")).strip().lower()
        if status == "error":
            run.append(step_number(step, idx))
        else:
            if len(run) >= max_errors:
                runs.append(list(run))
            run = []
    if len(run) >= max_errors:
        runs.append(list(run))
    findings = []
    for numbers in runs:
        detail = ("%d consecutive steps returned status 'error' "
                  "(threshold: max_errors=%d)." % (len(numbers), max_errors))
        findings.append(make_finding("D3", detail, numbers))
    return findings


def detect_contract_violations(steps):
    """D4: any step missing a non-empty thought or observation."""
    offenders = []
    for idx, step in enumerate(steps):
        if _is_blank(step.get("thought")) or _is_blank(step.get("observation")):
            offenders.append(step_number(step, idx))
    if not offenders:
        return []
    detail = ("%d step(s) are missing a non-empty thought or observation "
              "field, breaking the Thought -> Action -> Observation "
              "contract." % len(offenders))
    return [make_finding("D4", detail, offenders)]


def detect_budget_overrun(steps, max_steps):
    """D5: the trace consumed its full step budget."""
    if len(steps) < max_steps:
        return []
    overrun = [step_number(s, i) for i, s in enumerate(steps) if i >= max_steps - 1]
    detail = ("Trace contains %d steps, reaching the configured ceiling of "
              "max_steps=%d." % (len(steps), max_steps))
    return [make_finding("D5", detail, overrun)]


def detect_no_convergence(trace, steps):
    """D6: final_answer null/absent although the last step ended ok."""
    if not steps:
        return []
    last = steps[-1]
    last_status = str(last.get("status", "")).strip().lower()
    answer_missing = ("final_answer" not in trace
                      or trace.get("final_answer") is None)
    if last_status == "ok" and answer_missing:
        detail = ("The last step finished with status 'ok' but no "
                  "final_answer was recorded; the loop ended without an "
                  "explicit result.")
        return [make_finding("D6", detail, [step_number(last, len(steps) - 1)])]
    return []


def detect_reasoning_loops(steps):
    """D7: identical thought text recurs >= 3 times."""
    occurrences = {}
    for idx, step in enumerate(steps):
        thought = step.get("thought")
        if _is_blank(thought):
            continue  # blank thoughts belong to D4, not D7
        text = str(thought).strip()
        occurrences.setdefault(text, []).append(step_number(step, idx))
    findings = []
    for text, numbers in sorted(occurrences.items()):
        if len(numbers) >= REPEATED_THOUGHT_THRESHOLD:
            detail = ("The thought '%s' recurs %d times verbatim, indicating "
                      "stalled reasoning." % (_shorten(text, 50), len(numbers)))
            findings.append(make_finding("D7", detail, numbers))
    return findings


# --- Scoring and orchestration ----------------------------------------------

def compute_score(findings):
    """100 minus 30 per CRITICAL, 15 per HIGH, 5 per MEDIUM; floor 0."""
    penalty = sum(SEVERITY_WEIGHTS[f["severity"]] for f in findings)
    return max(0, 100 - penalty)


def verdict_for(score):
    """Map score to canonical verdict."""
    if score >= 90:
        return "HEALTHY"
    if score >= 60:
        return "DEGRADED"
    return "RUNAWAY"


def analyze(trace):
    """Run all detections and return findings, score, verdict, budgets."""
    steps = trace["steps"]
    budget = trace.get("budget")
    budget = budget if isinstance(budget, dict) else {}
    max_steps = _positive_int(budget.get("max_steps"), DEFAULT_MAX_STEPS)
    max_errors = _positive_int(budget.get("max_errors"), DEFAULT_MAX_ERRORS)

    findings = []
    findings.extend(detect_repeated_actions(steps))
    findings.extend(detect_oscillation(steps))
    findings.extend(detect_error_cascade(steps, max_errors))
    findings.extend(detect_contract_violations(steps))
    findings.extend(detect_budget_overrun(steps, max_steps))
    findings.extend(detect_no_convergence(trace, steps))
    findings.extend(detect_reasoning_loops(steps))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]],
                                 f["id"], f["steps"]))

    score = compute_score(findings)
    return {
        "findings": findings,
        "score": score,
        "verdict": verdict_for(score),
        "max_steps": max_steps,
        "max_errors": max_errors,
    }


def load_trace(path):
    """Read and validate the trace file. Returns (trace, error_message)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            trace = json.load(handle)
    except OSError as exc:
        return None, "cannot read '%s': %s" % (path, exc)
    except json.JSONDecodeError as exc:
        return None, "invalid JSON in '%s': %s" % (path, exc)
    if not isinstance(trace, dict):
        return None, "trace root in '%s' must be a JSON object" % path
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return None, "trace '%s' is missing the required 'steps' array" % path
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return None, "steps[%d] in '%s' must be a JSON object" % (idx, path)
    return trace, None


# --- Output rendering --------------------------------------------------------

def render_human(path, trace, result):
    """Print the default human-readable report (ASCII only)."""
    lines = []
    lines.append("ReAct Trace Analysis")
    lines.append("=" * 44)
    lines.append("Trace:   %s" % path)
    lines.append("Agent:   %s" % trace.get("agent", "(unknown)"))
    lines.append("Task:    %s" % trace.get("task", "(unknown)"))
    lines.append("Steps:   %d analyzed" % len(trace["steps"]))
    lines.append("Budget:  max_steps=%d, max_errors=%d"
                 % (result["max_steps"], result["max_errors"]))
    lines.append("")
    findings = result["findings"]
    if findings:
        lines.append("Findings: %d" % len(findings))
        for finding in findings:
            lines.append("")
            lines.append("[%s] %s %s" % (finding["severity"],
                                         finding["id"], finding["title"]))
            lines.append("  Steps:      %s"
                         % ", ".join(str(n) for n in finding["steps"]))
            lines.append("  Detail:     %s" % finding["detail"])
            lines.append("  Mitigation: %s" % finding["mitigation"])
    else:
        lines.append("Findings: none. No loop pathologies detected.")
    lines.append("")
    lines.append("-" * 44)
    lines.append("Score:   %d/100" % result["score"])
    lines.append("Verdict: %s" % result["verdict"])
    print("\n".join(lines))


class UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors (spec contract)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def build_parser():
    parser = UsageErrorParser(
        prog="react_trace_analyzer.py",
        description=("Analyze a ReAct execution trace for runaway loop "
                     "patterns (canonical detections D1-D7)."),
        epilog=("Exit code 0 when the analysis completes (any verdict); "
                "1 on I/O or parse errors."),
    )
    parser.add_argument("trace", help="path to the ReAct trace .json file")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="emit machine-readable JSON instead of the "
                             "human report")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    trace, error = load_trace(args.trace)
    if error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    result = analyze(trace)
    if args.as_json:
        payload = {
            "trace": args.trace,
            "agent": trace.get("agent"),
            "steps_analyzed": len(trace["steps"]),
            "score": result["score"],
            "verdict": result["verdict"],
            "findings": result["findings"],
        }
        print(json.dumps(payload, indent=2))
    else:
        render_human(args.trace, trace, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

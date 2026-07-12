#!/usr/bin/env python3
"""loop_guard.py - deterministic reference implementation of the six
canonical loop exit conditions (hub canon: agentic-system-architect /
loop_engineering_patterns.md).

Two modes:

  --self-test          Prove each detector fires exactly where canon says
                       it should -- and nowhere else. Exit 0 if all tests
                       pass, 1 otherwise.

  --trace FILE.jsonl   Replay a recorded iteration trace (one pass per
                       line) through the guards and report the first exit
                       condition that fires.

Python 3.8+ standard library only. No network calls, no LLM calls.
Output is ASCII-safe. Add --json for machine-readable output.

Exit codes:
  0  success_predicate fired, or the trace was consumed cleanly
  1  a non-success exit condition fired, or a self-test failed
  2  usage error or trace-format error
"""

import argparse
import hashlib
import json
import re
import sys
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

REPORT_SCHEMA = "loop-exit-report/v1"

CONDITIONS = ("max_iterations", "no_progress", "oscillation", "budget",
              "success_predicate", "escalation_trigger")

DEFAULT_NEXT_STEPS = {
    "max_iterations": "Review the best output so far; decide whether to "
                      "raise the cap deliberately or change approach.",
    "no_progress": "Inspect the last two attempted actions; the loop is "
                   "stalled, not slow.",
    "oscillation": "Two constraints likely conflict; a human must break "
                   "the tie between the alternating actions.",
    "budget": "Review work completed vs remaining; re-scope before "
              "allocating more budget.",
    "success_predicate": "Accept the output; evidence attached.",
    "escalation_trigger": "Human decision required before any further "
                          "iteration.",
}

TRACE_HELP = """\
Trace format (JSONL: one JSON object per loop pass, in order):

  {"actions": [{"tool": "edit_file", "input": "src/a.py",
                "status": "ok", "tokens": 120}],
   "state": {"failing_tests": ["test_a"]},
   "success": false}

Per-pass fields (all optional):
  actions    list of tool calls made during the pass. Each entry:
               tool   (string, REQUIRED)
               input  (any JSON value; default "")
               status ("ok" | "error"; default "ok")
               tokens (integer; default 0)
  state      observable task state after the pass. Canonicalized
             (volatile keys such as timestamps/run IDs stripped) and
             hashed for the no_progress detector. Omit to record no
             state observation for that pass.
  success    boolean result of the task's success predicate, evaluated
             externally before the trace was recorded. Pair with
             "evidence".
  evidence   object: the observable proof behind "success": true.
  escalate   string: reason text of a declared escalation trigger that
             fired externally during the pass.

Notes:
  - Wall-clock budgets (--max-wall-seconds) measure live elapsed time
    and are not meaningful during replay; they exist for parity with
    live loops.
  - Exit codes: 0 = success_predicate fired or trace consumed cleanly;
    1 = a non-success exit condition fired (or a self-test failed);
    2 = usage or trace-format error.
"""


# ---------------------------------------------------------------------------
# Canonicalization helpers (identical semantics to the reference file)
# ---------------------------------------------------------------------------

VOLATILE_KEY_PATTERN = re.compile(
    r"(timestamp|_at$|_time$|run_id|trace_id|session_id|tmp_path)",
    re.IGNORECASE)


def canonicalize(state: Any) -> Any:
    """Strip volatile fields from a JSON-serializable state, recursively."""
    if isinstance(state, dict):
        return {k: canonicalize(v) for k, v in state.items()
                if not VOLATILE_KEY_PATTERN.search(k)}
    if isinstance(state, list):
        return [canonicalize(v) for v in state]
    return state


def state_hash(state: Any) -> str:
    """Deterministic short hash of a canonicalized state."""
    blob = json.dumps(canonicalize(state), sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def action_signature(tool: str, tool_input: Any) -> Tuple[str, str]:
    """Normalized (tool, input) signature for oscillation detection."""
    if isinstance(tool_input, str):
        payload = " ".join(tool_input.split()).lower()
    else:
        payload = json.dumps(tool_input, sort_keys=True,
                             separators=(",", ":"), default=str).lower()
    return (tool.strip().lower(), payload)


# ---------------------------------------------------------------------------
# LoopGuard: controller-owned ledger with all six exit conditions
# ---------------------------------------------------------------------------

class LoopGuard:
    """All six canonical exit conditions behind three hooks.

    Usage per pass:
        report = guard.before_pass()                  # max_iterations, budget
        report = guard.record_action(tool, inp, ...)  # oscillation, cascade
        report = guard.after_pass(state)              # success, escalation,
                                                      # no_progress
    The first non-None report terminates the loop. Counters never reset
    mid-task (sole exception: consecutive_errors after a successful action).
    """

    def __init__(
        self,
        max_iterations: int = 5,
        no_progress_window: int = 2,
        oscillation_window: int = 4,
        max_tool_calls: int = 20,
        max_errors: int = 3,
        max_tokens: Optional[int] = None,
        max_wall_seconds: Optional[float] = None,
        success_predicate: Optional[Callable[[Any], Tuple[bool, Any]]] = None,
        escalation_triggers: Optional[
            List[Callable[[Any], Optional[str]]]] = None,
    ):
        self.max_iterations = max_iterations
        self.no_progress_window = no_progress_window
        self.oscillation_window = oscillation_window
        self.max_tool_calls = max_tool_calls
        self.max_errors = max_errors
        self.max_tokens = max_tokens
        self.max_wall_seconds = max_wall_seconds
        self.success_predicate = success_predicate
        self.escalation_triggers = escalation_triggers or []

        self.attempts = 0
        self.tool_calls_used = 0
        self.tokens_used = 0
        self.consecutive_errors = 0
        self.state_hashes = deque(maxlen=max(no_progress_window, 8))
        self.action_history = deque(maxlen=max(oscillation_window, 8))
        self.fired_counts = {}  # type: Dict[str, int]
        self._started = time.monotonic()

    # -- hooks --------------------------------------------------------------

    def before_pass(self) -> Optional[dict]:
        """Call at the top of every pass, before any work."""
        self.attempts += 1
        if self.attempts > self.max_iterations:
            return self._fire("max_iterations",
                              {"attempts": self.attempts,
                               "cap": self.max_iterations})
        return self._check_budget()

    def record_action(self, tool: str, tool_input: Any,
                      status: str = "ok", tokens: int = 0) -> Optional[dict]:
        """Call after every tool call inside the pass."""
        if self.tool_calls_used + 1 > self.max_tool_calls:
            return self._fire("budget",
                              {"denomination": "tool_calls",
                               "used": self.tool_calls_used,
                               "cap": self.max_tool_calls})
        self.tool_calls_used += 1
        self.tokens_used += tokens

        sig = action_signature(tool, tool_input)
        self.action_history.append(sig)
        window = list(self.action_history)[-self.oscillation_window:]
        # Canonical A-B-A-B test: strict pairwise alternation over the
        # window (positions i and i+2 match, positions 0 and 1 differ).
        # Repetition of ONE action (A-A-A-A) is no_progress territory,
        # never oscillation.
        if (len(window) == self.oscillation_window
                and window[0] != window[1]
                and all(window[i] == window[i + 2]
                        for i in range(len(window) - 2))):
            return self._fire("oscillation",
                              {"alternating": [list(window[0]),
                                               list(window[1])],
                               "window": self.oscillation_window})

        if status == "error":
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.max_errors:
                return self._fire("escalation_trigger",
                                  {"reason": "error_cascade",
                                   "consecutive_errors":
                                       self.consecutive_errors})
        else:
            self.consecutive_errors = 0  # the ONLY legal mid-task reset
        return self._check_budget()

    def after_pass(self, state: Any) -> Optional[dict]:
        """Call at the end of every pass with fresh observable state."""
        if self.success_predicate is not None:
            passed, evidence = self.success_predicate(state)
            if passed:
                return self._fire("success_predicate",
                                  {"evidence": evidence})

        for trigger in self.escalation_triggers:
            reason = trigger(state)
            if reason:
                return self._fire("escalation_trigger", {"reason": reason})

        h = state_hash(state)
        self.state_hashes.append(h)
        recent = list(self.state_hashes)[-self.no_progress_window:]
        if (len(recent) == self.no_progress_window
                and len(set(recent)) == 1):
            return self._fire("no_progress",
                              {"state_hash": h,
                               "window": self.no_progress_window})
        return None

    # -- internals ----------------------------------------------------------

    def _check_budget(self) -> Optional[dict]:
        if self.max_tokens is not None and self.tokens_used > self.max_tokens:
            return self._fire("budget", {"denomination": "tokens",
                                         "used": self.tokens_used,
                                         "cap": self.max_tokens})
        if self.max_wall_seconds is not None:
            elapsed = time.monotonic() - self._started
            if elapsed > self.max_wall_seconds:
                return self._fire("budget",
                                  {"denomination": "wall_clock_seconds",
                                   "used": round(elapsed, 1),
                                   "cap": self.max_wall_seconds})
        return None

    def _fire(self, condition: str, evidence: dict) -> dict:
        self.fired_counts[condition] = self.fired_counts.get(condition, 0) + 1
        # Two-strikes rule: any non-success condition firing twice for the
        # same subtask converts to escalation_trigger.
        if (condition not in ("success_predicate", "escalation_trigger")
                and self.fired_counts[condition] >= 2):
            evidence = {"reason": "two_strikes",
                        "original_condition": condition,
                        "original_evidence": evidence}
            condition = "escalation_trigger"
            self.fired_counts[condition] = (
                self.fired_counts.get(condition, 0) + 1)
        return {
            "schema": REPORT_SCHEMA,
            "condition_fired": condition,
            "success": condition == "success_predicate",
            "evidence": evidence,
            "counters": {
                "iterations": self.attempts,
                "tool_calls": self.tool_calls_used,
                "tokens": self.tokens_used,
                "consecutive_errors": self.consecutive_errors,
            },
            "work_completed": [],
            "work_remaining": [],
            "recommended_next_step": DEFAULT_NEXT_STEPS[condition],
        }


# ---------------------------------------------------------------------------
# Trace replay
# ---------------------------------------------------------------------------

class TraceFormatError(Exception):
    pass


def load_trace(path: str) -> List[dict]:
    passes = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise TraceFormatError(
                        "line {}: invalid JSON ({})".format(lineno, e.msg))
                if not isinstance(obj, dict):
                    raise TraceFormatError(
                        "line {}: each pass must be a JSON object".format(
                            lineno))
                actions = obj.get("actions", [])
                if not isinstance(actions, list):
                    raise TraceFormatError(
                        "line {}: 'actions' must be a list".format(lineno))
                for i, action in enumerate(actions):
                    if not isinstance(action, dict) or "tool" not in action:
                        raise TraceFormatError(
                            "line {}: actions[{}] must be an object with a "
                            "'tool' field".format(lineno, i))
                    if not isinstance(action.get("tokens", 0), int):
                        raise TraceFormatError(
                            "line {}: actions[{}].tokens must be an "
                            "integer".format(lineno, i))
                passes.append(obj)
    except OSError as e:
        raise TraceFormatError("cannot read {}: {}".format(path, e))
    if not passes:
        raise TraceFormatError("trace is empty: {}".format(path))
    return passes


def replay_trace(passes: List[dict], guard: LoopGuard,
                 current: dict) -> Tuple[Optional[dict], int]:
    """Replay passes through the guard.

    Returns (report_or_None, pass_number_reached).
    """
    for pass_no, pass_obj in enumerate(passes, 1):
        current["success"] = bool(pass_obj.get("success", False))
        current["evidence"] = pass_obj.get("evidence")
        current["escalate"] = pass_obj.get("escalate")

        report = guard.before_pass()
        if report:
            return report, pass_no

        for action in pass_obj.get("actions", []):
            report = guard.record_action(
                action["tool"], action.get("input", ""),
                status=action.get("status", "ok"),
                tokens=action.get("tokens", 0))
            if report:
                return report, pass_no

        if ("state" in pass_obj or current["success"]
                or current["escalate"]):
            report = guard.after_pass(pass_obj.get("state", {}))
            if report:
                return report, pass_no
    return None, len(passes)


def run_trace_mode(args) -> int:
    try:
        passes = load_trace(args.trace)
    except TraceFormatError as e:
        if args.json:
            print(json.dumps({"result": "error", "error": str(e)}))
        else:
            print("[ERROR] {}".format(e))
        return 2

    current = {"success": False, "evidence": None, "escalate": None}
    guard = LoopGuard(
        max_iterations=args.max_iterations,
        no_progress_window=args.no_progress_window,
        oscillation_window=args.oscillation_window,
        max_tool_calls=args.max_tool_calls,
        max_errors=args.max_errors,
        max_tokens=args.max_tokens,
        max_wall_seconds=args.max_wall_seconds,
        success_predicate=lambda s: (current["success"],
                                     current["evidence"]),
        escalation_triggers=[lambda s: current["escalate"]],
    )
    report, pass_no = replay_trace(passes, guard, current)

    counters = {
        "iterations": guard.attempts,
        "tool_calls": guard.tool_calls_used,
        "tokens": guard.tokens_used,
        "consecutive_errors": guard.consecutive_errors,
    }
    if report is None:
        if args.json:
            print(json.dumps({"result": "clean", "passes": pass_no,
                              "counters": counters}, sort_keys=True))
        else:
            print("[CLEAN] trace consumed: {} passes, {} tool calls, "
                  "no exit condition fired".format(
                      pass_no, guard.tool_calls_used))
        return 0

    if args.json:
        print(json.dumps({"result": "fired", "pass": pass_no,
                          "report": report}, sort_keys=True))
    else:
        print("[FIRED] {} at pass {} (success={})".format(
            report["condition_fired"], pass_no,
            str(report["success"]).lower()))
        print("  evidence: {}".format(
            json.dumps(report["evidence"], sort_keys=True)))
        print("  counters: iterations={iterations} tool_calls={tool_calls} "
              "tokens={tokens} consecutive_errors={consecutive_errors}"
              .format(**report["counters"]))
        print("  next step: {}".format(report["recommended_next_step"]))
    return 0 if report["success"] else 1


# ---------------------------------------------------------------------------
# Self-test: each detector fires where canon says -- and nowhere else
# ---------------------------------------------------------------------------

def _expect(condition_ok: bool, detail: str) -> Optional[str]:
    return None if condition_ok else detail


def test_max_iterations_fires_at_cap() -> Optional[str]:
    g = LoopGuard(max_iterations=3)
    for i in range(3):
        r = g.before_pass()
        if r is not None:
            return "fired early at pass {}".format(i + 1)
    r = g.before_pass()
    if r is None or r["condition_fired"] != "max_iterations":
        return "did not fire at cap+1: {}".format(r)
    return None


def test_no_progress_window_2() -> Optional[str]:
    g = LoopGuard()
    if g.after_pass({"v": 1}) is not None:
        return "fired on first observation"
    if g.after_pass({"v": 2}) is not None:
        return "fired on a changed state"
    r = g.after_pass({"v": 2})
    if r is None or r["condition_fired"] != "no_progress":
        return "did not fire on 2 identical consecutive hashes: {}".format(r)
    return None


def test_canonicalization_strips_volatile() -> Optional[str]:
    h1 = state_hash({"v": 1, "timestamp": "2026-01-01", "run_id": "a"})
    h2 = state_hash({"v": 1, "timestamp": "2026-06-30", "run_id": "b"})
    if h1 != h2:
        return "volatile keys leaked into the hash"
    g = LoopGuard()
    g.after_pass({"v": 1, "timestamp": "t1"})
    r = g.after_pass({"v": 1, "timestamp": "t2"})
    if r is None or r["condition_fired"] != "no_progress":
        return "no_progress blind to timestamp-only changes: {}".format(r)
    return None


def test_oscillation_abab_window_4() -> Optional[str]:
    g = LoopGuard()
    seq = [("edit", "a.py"), ("revert", "a.py"),
           ("edit", "a.py"), ("revert", "a.py")]
    r = None
    for i, (tool, inp) in enumerate(seq):
        r = g.record_action(tool, inp)
        if r is not None and i < 3:
            return "fired before the window filled (call {})".format(i + 1)
    if r is None or r["condition_fired"] != "oscillation":
        return "A-B-A-B did not fire oscillation: {}".format(r)
    if r["evidence"].get("window") != 4:
        return "evidence window is not 4"
    return None


def test_oscillation_not_on_pure_repeat() -> Optional[str]:
    g = LoopGuard()
    for _ in range(4):
        r = g.record_action("edit", "a.py")
        if r is not None:
            return ("A-A-A-A fired {} -- unchanged repetition is "
                    "no_progress territory, never oscillation".format(
                        r["condition_fired"]))
    return None


def test_signature_normalization() -> Optional[str]:
    g = LoopGuard()
    seq = [("run", "tests"), ("Lint", "src"),
           ("RUN", "  tests "), ("LINT", "src ")]
    r = None
    for tool, inp in seq:
        r = g.record_action(tool, inp)
    if r is None or r["condition_fired"] != "oscillation":
        return ("case/whitespace variants defeated the signature "
                "normalization: {}".format(r))
    return None


def test_budget_tool_calls() -> Optional[str]:
    g = LoopGuard(max_tool_calls=2)
    if g.record_action("t1", "x") is not None:
        return "fired below the cap (call 1)"
    if g.record_action("t2", "y") is not None:
        return "fired below the cap (call 2)"
    r = g.record_action("t3", "z")
    if (r is None or r["condition_fired"] != "budget"
            or r["evidence"].get("denomination") != "tool_calls"):
        return "did not fire tool-call budget at cap+1: {}".format(r)
    return None


def test_budget_tokens() -> Optional[str]:
    g = LoopGuard(max_tokens=100)
    if g.record_action("t1", "x", tokens=60) is not None:
        return "fired below the token cap"
    r = g.record_action("t2", "y", tokens=60)
    if (r is None or r["condition_fired"] != "budget"
            or r["evidence"].get("denomination") != "tokens"):
        return "did not fire token budget when exceeded: {}".format(r)
    return None


def test_budget_wall_clock() -> Optional[str]:
    g = LoopGuard(max_wall_seconds=0.5)
    g._started = time.monotonic() - 1.0  # simulate elapsed time
    r = g.before_pass()
    if (r is None or r["condition_fired"] != "budget"
            or r["evidence"].get("denomination") != "wall_clock_seconds"):
        return "did not fire wall-clock budget: {}".format(r)
    return None


def test_error_cascade_escalates() -> Optional[str]:
    g = LoopGuard(max_errors=3)
    if g.record_action("t1", "a", status="error") is not None:
        return "fired at 1 consecutive error"
    if g.record_action("t2", "b", status="error") is not None:
        return "fired at 2 consecutive errors"
    if g.record_action("t3", "c", status="ok") is not None:
        return "fired on a successful action"
    if g.consecutive_errors != 0:
        return "successful action did not reset consecutive_errors"
    for tool, inp in (("t4", "d"), ("t5", "e")):
        if g.record_action(tool, inp, status="error") is not None:
            return "fired before the third consecutive error"
    r = g.record_action("t6", "f", status="error")
    if (r is None or r["condition_fired"] != "escalation_trigger"
            or r["evidence"].get("reason") != "error_cascade"):
        return "3 consecutive errors did not escalate: {}".format(r)
    return None


def test_success_predicate_evidence() -> Optional[str]:
    g = LoopGuard(success_predicate=lambda s: (s.get("done", False),
                                               {"proof": 42}))
    if g.after_pass({"done": False}) is not None:
        return "fired while the predicate was false"
    r = g.after_pass({"done": True})
    if (r is None or r["condition_fired"] != "success_predicate"
            or r["success"] is not True
            or r["evidence"].get("evidence", {}).get("proof") != 42):
        return "success exit missing evidence or success flag: {}".format(r)
    return None


def test_escalation_trigger_declared() -> Optional[str]:
    g = LoopGuard(escalation_triggers=[
        lambda s: "irreversible_action_requested"
        if s.get("wants_irreversible") else None])
    if g.after_pass({"wants_irreversible": False}) is not None:
        return "fired while the trigger predicate was false"
    r = g.after_pass({"wants_irreversible": True})
    if (r is None or r["condition_fired"] != "escalation_trigger"
            or r["evidence"].get("reason")
            != "irreversible_action_requested"):
        return "declared trigger did not fire: {}".format(r)
    return None


def test_two_strikes_conversion() -> Optional[str]:
    g = LoopGuard()
    g.after_pass({"s": 1})
    r1 = g.after_pass({"s": 1})
    if r1 is None or r1["condition_fired"] != "no_progress":
        return "first strike did not fire no_progress: {}".format(r1)
    r2 = g.after_pass({"s": 1})  # same wall, second strike
    if (r2 is None or r2["condition_fired"] != "escalation_trigger"
            or r2["evidence"].get("reason") != "two_strikes"
            or r2["evidence"].get("original_condition") != "no_progress"):
        return "second strike did not convert to escalation: {}".format(r2)
    return None


def test_report_contract() -> Optional[str]:
    g = LoopGuard(max_iterations=0)
    r = g.before_pass()
    if r is None:
        return "no report produced"
    if r.get("schema") != REPORT_SCHEMA:
        return "schema field is not {}".format(REPORT_SCHEMA)
    if r.get("condition_fired") not in CONDITIONS:
        return "condition_fired outside the canonical six"
    for key in ("iterations", "tool_calls", "tokens", "consecutive_errors"):
        if key not in r.get("counters", {}):
            return "counters missing '{}'".format(key)
    if not r.get("recommended_next_step"):
        return "recommended_next_step is empty"
    return None


SELF_TESTS = [
    ("max_iterations fires at cap+1, not before",
     test_max_iterations_fires_at_cap),
    ("no_progress fires on 2 identical consecutive state hashes",
     test_no_progress_window_2),
    ("canonicalization strips volatile keys before hashing",
     test_canonicalization_strips_volatile),
    ("oscillation fires on A-B-A-B over window 4",
     test_oscillation_abab_window_4),
    ("oscillation does NOT fire on pure repetition (A-A-A-A)",
     test_oscillation_not_on_pure_repeat),
    ("action signatures normalize case and whitespace",
     test_signature_normalization),
    ("budget fires on the tool-call cap",
     test_budget_tool_calls),
    ("budget fires on the token cap",
     test_budget_tokens),
    ("budget fires on the wall-clock cap",
     test_budget_wall_clock),
    ("3 consecutive errors escalate; success resets the counter",
     test_error_cascade_escalates),
    ("success_predicate exits with success=true and evidence",
     test_success_predicate_evidence),
    ("declared escalation trigger fires with its reason",
     test_escalation_trigger_declared),
    ("two strikes convert any condition to escalation_trigger",
     test_two_strikes_conversion),
    ("exit report honors the loop-exit-report/v1 contract",
     test_report_contract),
]


def run_self_test(args) -> int:
    results = []
    for name, fn in SELF_TESTS:
        try:
            detail = fn()
        except Exception as e:  # a crash is a failure, not an abort
            detail = "raised {}: {}".format(type(e).__name__, e)
        results.append({"name": name,
                        "status": "pass" if detail is None else "fail",
                        "detail": detail})

    failed = [r for r in results if r["status"] == "fail"]
    if args.json:
        print(json.dumps({
            "result": "pass" if not failed else "fail",
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "tests": results,
        }, sort_keys=True))
    else:
        for r in results:
            tag = "[PASS]" if r["status"] == "pass" else "[FAIL]"
            line = "{} {}".format(tag, r["name"])
            if r["detail"]:
                line += " -- {}".format(r["detail"])
            print(line)
        print("self-test: {} passed, {} failed".format(
            len(results) - len(failed), len(failed)))
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop_guard.py",
        description="Deterministic reference implementation of the six "
                    "canonical loop exit conditions: max_iterations, "
                    "no_progress (state-hash window 2), oscillation "
                    "(A-B-A-B window 4), budget, success_predicate, "
                    "escalation_trigger.",
        epilog=TRACE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true",
                      help="run the detector self-test suite")
    mode.add_argument("--trace", metavar="FILE",
                      help="replay a JSONL iteration trace through the "
                           "guards (format below)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable JSON output")
    parser.add_argument("--max-iterations", type=int, default=5,
                        help="iteration cap (default: 5)")
    parser.add_argument("--no-progress-window", type=int, default=2,
                        help="identical consecutive state hashes to fire "
                             "no_progress (default: 2, canon)")
    parser.add_argument("--oscillation-window", type=int, default=4,
                        help="ring-buffer window for the A-B-A-B test "
                             "(default: 4, canon)")
    parser.add_argument("--max-tool-calls", type=int, default=20,
                        help="tool-call budget (default: 20, canon)")
    parser.add_argument("--max-errors", type=int, default=3,
                        help="consecutive errors before escalation "
                             "(default: 3, canon)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="optional token budget (default: off)")
    parser.add_argument("--max-wall-seconds", type=float, default=None,
                        help="optional wall-clock budget in seconds; not "
                             "meaningful in replay (default: off)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return run_self_test(args)
    return run_trace_mode(args)


if __name__ == "__main__":
    sys.exit(main())

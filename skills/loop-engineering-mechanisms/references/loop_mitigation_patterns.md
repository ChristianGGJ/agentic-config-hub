# Exit-Condition Implementations (Python Standard Library)

Runnable implementations of the six canonical exit conditions —
`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger` — plus the controller-owned ledger that makes them
trustworthy and the structured stop-and-report exit contract.

Scope: this file is code. The definitions, recommended defaults, and design
rationale behind these mechanisms are hub canon owned by the
`agentic-system-architect` skill; the numbers used here (stall window 2,
oscillation window 4, 20 tool calls, 3 consecutive errors, two-strikes
escalation) match that canon exactly.

Requirements: Python 3.8+, standard library only.

---

## 1. Canonicalization Helpers

Detectors are only as good as their inputs. Hash canonicalized state and
normalize action signatures, or `no_progress` and `oscillation` go blind.

```python
import hashlib
import json
import re

VOLATILE_KEY_PATTERN = re.compile(
    r"(timestamp|_at$|_time$|run_id|trace_id|session_id|tmp_path)", re.IGNORECASE
)


def canonicalize(state):
    """Strip volatile fields from a JSON-serializable state, recursively.

    Timestamps, run IDs, and temp paths change every pass; if they reach the
    hash, no_progress never fires. Extend VOLATILE_KEY_PATTERN per project.
    """
    if isinstance(state, dict):
        return {
            k: canonicalize(v)
            for k, v in state.items()
            if not VOLATILE_KEY_PATTERN.search(k)
        }
    if isinstance(state, list):
        return [canonicalize(v) for v in state]
    return state


def state_hash(state):
    """Deterministic short hash of a canonicalized state."""
    blob = json.dumps(canonicalize(state), sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def action_signature(tool, tool_input):
    """Normalized (tool, input) signature for oscillation/dedup detection.

    'run tests' and 'run  Tests' must produce the same signature.
    """
    if isinstance(tool_input, str):
        payload = " ".join(tool_input.split()).lower()
    else:
        payload = json.dumps(tool_input, sort_keys=True,
                             separators=(",", ":"), default=str).lower()
    return (tool.strip().lower(), payload)
```

---

## 2. LoopGuard: The Controller-Owned Ledger

One object owns every counter. Step logic reports outcomes through the three
hook methods and can never reset anything. Every hook returns either `None`
(continue) or a `loop-exit-report/v1` dict (stop now).

```python
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

REPORT_SCHEMA = "loop-exit-report/v1"

DEFAULT_NEXT_STEPS = {
    "max_iterations": "Review the best output so far; decide whether to raise "
                      "the cap deliberately or change approach.",
    "no_progress": "Inspect the last two attempted actions; the loop is "
                   "stalled, not slow.",
    "oscillation": "Two constraints likely conflict; a human must break the "
                   "tie between the alternating actions.",
    "budget": "Review work completed vs remaining; re-scope before "
              "allocating more budget.",
    "success_predicate": "Accept the output; evidence attached.",
    "escalation_trigger": "Human decision required before any further "
                          "iteration.",
}


class LoopGuard:
    """All six canonical exit conditions behind three hooks.

    Usage per pass:
        report = guard.before_pass()                  # max_iterations, budget
        report = guard.record_action(tool, inp, ...)  # oscillation, cascade, budget
        report = guard.after_pass(state)              # success, escalation, no_progress
    First non-None report terminates the loop. Counters never reset mid-task.
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
        # success_predicate returns (passed, evidence); evidence is mandatory.
        self.success_predicate = success_predicate
        self.escalation_triggers = escalation_triggers or []

        self.attempts = 0
        self.tool_calls_used = 0
        self.tokens_used = 0
        self.consecutive_errors = 0
        self.state_hashes = deque(maxlen=max(no_progress_window, 8))
        self.action_history = deque(maxlen=max(oscillation_window, 8))
        self.fired_counts: Dict[str, int] = {}
        self._started = time.monotonic()

    # -- hooks ------------------------------------------------------------

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
        # Canonical A-B-A-B test over window 4: positions 0/2 and 1/3 match,
        # 0 != 1. Repetition of ONE action (A-A) is no_progress territory,
        # never oscillation.
        if (len(window) == 4 and window[0] == window[2]
                and window[1] == window[3] and window[0] != window[1]):
            return self._fire("oscillation",
                              {"alternating": [list(window[0]),
                                               list(window[1])],
                               "window": 4})

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
                return self._fire("success_predicate", {"evidence": evidence})

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

    # -- internals --------------------------------------------------------

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
            "work_completed": [],   # controller fills from task state
            "work_remaining": [],   # controller fills from task state
            "recommended_next_step": DEFAULT_NEXT_STEPS[condition],
        }
```

---

## 3. Wiring a Convergence Loop

Complete, runnable skeleton. Replace `call_llm` and `apply_and_observe` with
real implementations; everything else ships as-is.

```python
import json


def make_predicate_from_failing_tests():
    """success_predicate example: 'the failing-test list is empty'.

    Predicates return (passed, evidence). Evidence is mandatory -- 'I believe
    it works' is not evidence; the observable result is.
    """
    def predicate(state):
        failing = state.get("failing_tests", None)
        return (failing == [], {"failing_tests": failing})
    return predicate


def run_convergence_loop(task_input, call_llm, apply_and_observe):
    # Declare ALL exit conditions BEFORE iteration 1 (hub canon).
    guard = LoopGuard(
        max_iterations=5,
        max_tool_calls=20,
        max_errors=3,
        success_predicate=make_predicate_from_failing_tests(),
        escalation_triggers=[
            lambda s: "irreversible_action_requested"
            if s.get("wants_irreversible") else None,
        ],
    )
    history = [{"role": "user", "content": task_input}]

    while True:
        report = guard.before_pass()
        if report:
            return stop_and_report(report, history)

        action = call_llm(history)  # -> {"tool": ..., "input": ...}
        outcome = apply_and_observe(action)  # -> {"status", "state", "tokens"}

        report = guard.record_action(action["tool"], action["input"],
                                     status=outcome["status"],
                                     tokens=outcome.get("tokens", 0))
        if report:
            return stop_and_report(report, history)

        report = guard.after_pass(outcome["state"])
        if report:
            return stop_and_report(report, history)

        history.append({
            "role": "user",
            "content": "OBSERVATION:\n" + json.dumps(
                {"status": outcome["status"],
                 "state": canonicalize(outcome["state"])},
                indent=2, sort_keys=True),
        })


def stop_and_report(report, history):
    """Stop means stop AND report -- never a bare exception."""
    report["work_remaining"] = summarize_remaining(history)
    with open("loop_exit_report.json", "w", encoding="utf-8") as f:
        json.dump({"report": report, "history": history}, f, indent=2)
    return report


def summarize_remaining(history):
    return []  # project-specific: derive from task state, not from vibes
```

Notes on the wiring:

- The three hooks are checked in order **within** each pass; the first
  non-None report wins. This is the OR-ing of exit conditions in code form.
- The observation appended to history is machine-readable JSON, not prose —
  see `validation_and_observation.md` for the full observation format and the
  validation gate that should run before `after_pass`.
- On success the same report shape is returned with `"success": true` and the
  predicate's evidence attached. One exit contract for every trajectory.

---

## 4. The Stop-and-Report Exit Contract

Every exit — success or not — produces one `loop-exit-report/v1` object.
Consumers (orchestrators, HITL gates, humans) parse it; nobody greps logs.

```json
{
  "schema": "loop-exit-report/v1",
  "condition_fired": "oscillation",
  "success": false,
  "evidence": {
    "alternating": [["edit_file", "src/auth.py"], ["revert_file", "src/auth.py"]],
    "window": 4
  },
  "counters": {
    "iterations": 4,
    "tool_calls": 11,
    "tokens": 18234,
    "consecutive_errors": 0
  },
  "work_completed": ["fixed test_login", "fixed test_logout"],
  "work_remaining": ["test_token_refresh still failing"],
  "recommended_next_step": "Two constraints likely conflict; a human must break the tie between the alternating actions."
}
```

Field semantics:

| Field | Type | Rule |
|---|---|---|
| `schema` | string | always `loop-exit-report/v1`; version bumps are breaking |
| `condition_fired` | enum | exactly one of the six canonical types |
| `success` | bool | true iff `condition_fired == "success_predicate"` |
| `evidence` | object | mandatory; the observable proof (window contents, counter values, predicate output) — never empty |
| `counters` | object | ledger snapshot at exit; consumers use it for budget accounting across nested loops |
| `work_completed` / `work_remaining` | arrays | controller-filled from task state; empty allowed for success exits only |
| `recommended_next_step` | string | one actionable sentence; a human should know what to do without reading the transcript |

A raised exception may *carry* this object (`raise LoopExit(report)`), but the
object is the contract — the exception is transport. This report is also the
escalation object the hub's HITL gate rules require and the handoff artifact
for Phase 5 (SELF-REVIEW & HANDOFF) when the work is loop-shaped.

---

## 5. Nested-Loop Budgeting

One rule: **inner loops consume the outer loop's budget; the outer loop keeps
an independent iteration cap.** Implement it by sharing the ledger's budget
counters while giving the inner loop its own attempt counter:

```python
def run_inner_retry_loop(guard, action, apply_and_observe, max_inner=3):
    """Inner loop draws down the OUTER guard's tool-call/token budget.

    Its own cap (max_inner) is independent and private; its consumption is not.
    """
    for attempt in range(1, max_inner + 1):
        outcome = apply_and_observe(action)
        report = guard.record_action(  # charges the OUTER budget
            action["tool"], action["input"],
            status=outcome["status"], tokens=outcome.get("tokens", 0))
        if report:
            return report, None          # outer guard fired mid-inner-loop
        if outcome["status"] == "ok":
            return None, outcome
    return None, outcome  # inner cap exhausted; outer loop decides next
```

An inner loop with a private budget is invisible to the outer guard and can
burn the entire task allocation before the outer loop notices. Sharing the
`LoopGuard` instance for budget while capping inner attempts locally gives
both properties: bounded inner behavior, globally accounted consumption.

---

## 6. Calibration Summary

| Parameter | Default | Source of the number |
|---|---|---|
| `max_iterations` | 3-5 (reflection/evaluator), 10-20 (convergence) | hub canon recommended defaults |
| `no_progress_window` | 2 | hub canon: two consecutive identical state hashes |
| `oscillation_window` | 4 | hub canon: A-B-A-B test, matches trace detection D2 |
| `max_tool_calls` | 20 | hub canon: mirrors `budget.max_steps` |
| `max_errors` | 3 | hub canon: error cascade, matches trace detection D3 |
| two-strikes conversion | always on | hub canon anti-runaway rule 5 |

Deviating from these defaults is legitimate; deviating silently is not.
Record any override next to the declared exit conditions, before iteration 1.

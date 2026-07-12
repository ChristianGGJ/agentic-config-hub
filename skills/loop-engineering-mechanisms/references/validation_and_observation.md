# Validation Gates, Observations, and Error Recovery

Implementation patterns for the accept/reject side of a loop iteration:
deterministic output validation gates, machine-readable observation messages,
structured error formatters, and classified recovery strategies.

Requirements: Python 3.8+ standard library, except the one Pydantic section
which is explicitly marked third-party (Pydantic 2.x).

Principle: **never rely on an LLM to validate its own output.** A validation
gate is deterministic code that runs before an iteration's output is accepted.
Its failure output is not a log line — it is the next iteration's input.

---

## 1. Output Validation Gates (stdlib)

Run gates cheapest-first; stop at the first failure so the observation carries
one precise error instead of a stack of them.

### 1.1 Structure gate: JSON parse + contract check

```python
import json


def check_structure(raw_output, contract):
    """Validate raw LLM output against a minimal field contract.

    contract example:
        {
            "file_path":  {"type": str,  "required": True},
            "refactored_code": {"type": str, "required": True},
            "complexity_score": {"type": int, "required": True,
                                 "min": 1, "max": 10},
        }
    Returns (parsed_or_None, errors: list of dicts).
    """
    errors = []
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError as e:
        return None, [{"field": None, "error": "invalid_json",
                       "detail": "{} at line {} col {}".format(
                           e.msg, e.lineno, e.colno)}]
    if not isinstance(data, dict):
        return None, [{"field": None, "error": "not_an_object",
                       "detail": "top-level value must be a JSON object"}]

    for field, spec in contract.items():
        if field not in data:
            if spec.get("required", False):
                errors.append({"field": field, "error": "missing_required"})
            continue
        value = data[field]
        if not isinstance(value, spec["type"]):
            errors.append({"field": field, "error": "wrong_type",
                           "detail": "expected {}, got {}".format(
                               spec["type"].__name__,
                               type(value).__name__)})
            continue
        if "min" in spec and value < spec["min"]:
            errors.append({"field": field, "error": "below_min",
                           "detail": "min {}, got {}".format(
                               spec["min"], value)})
        if "max" in spec and value > spec["max"]:
            errors.append({"field": field, "error": "above_max",
                           "detail": "max {}, got {}".format(
                               spec["max"], value)})
        if "pattern" in spec:
            import re
            if not re.fullmatch(spec["pattern"], str(value)):
                errors.append({"field": field, "error": "pattern_mismatch",
                               "detail": "must match {}".format(
                                   spec["pattern"])})
    return (data if not errors else None), errors
```

### 1.2 Syntax gate: generated code must parse

```python
import ast


def check_python_syntax(code):
    """Syntax-gate generated Python. Returns (ok, errors)."""
    errors = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [{"field": "code", "error": "syntax_error",
                        "detail": "{} at line {}".format(e.msg, e.lineno),
                        "line": e.lineno}]
    # Policy gate on the AST, not on substrings: "eval(" in a comment or
    # string literal is not a call.
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("eval", "exec")):
            errors.append({"field": "code", "error": "forbidden_call",
                           "detail": "call to {}() is prohibited".format(
                               node.func.id),
                           "line": node.lineno})
    return (not errors), errors
```

### 1.3 Behavior gate: run the tests (final gate only)

```python
import subprocess


def check_tests(test_command=("python", "-m", "pytest", "-q"),
                timeout_seconds=300):
    """Run the test suite as the last, most expensive gate.

    Returns (ok, evidence). The evidence dict is exactly what a
    success_predicate should hand back: exit code + summary, fresh.
    """
    try:
        proc = subprocess.run(list(test_command), capture_output=True,
                              text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return False, {"error": "timeout",
                       "detail": "tests exceeded {}s".format(timeout_seconds)}
    summary = (proc.stdout or "").strip().splitlines()
    return proc.returncode == 0, {
        "exit_code": proc.returncode,
        "summary": summary[-1] if summary else "",
    }
```

This is also how `success_predicate` earns its evidence: the gate's output
(exit code, summary line) goes verbatim into the exit report. A predicate that
cannot produce evidence like this is a belief, not a predicate.

---

## 2. Schema Validation with Pydantic (third-party, Pydantic 2.x)

When the project already depends on Pydantic, a model with field validators is
the highest-leverage gate. This is the one non-stdlib pattern in this skill;
API surface is Pydantic 2.x (`field_validator`, `model_validate_json`,
`ValidationError.errors()`).

```python
# requires: pydantic>=2  (third-party -- not usable inside hub scripts/)
from pydantic import BaseModel, Field, ValidationError, field_validator
import ast


class CodeRefactoringTask(BaseModel):
    file_path: str = Field(description="Path to the target source file.")
    refactored_code: str = Field(description="Refactored Python source.")
    complexity_score: int = Field(ge=1, le=10,
                                  description="1 (simple) to 10 (complex).")

    @field_validator("refactored_code")
    @classmethod
    def code_must_parse(cls, code: str) -> str:
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValueError(
                "syntax error: {} at line {}".format(e.msg, e.lineno))
        return code


def gate_with_pydantic(raw_output):
    """Returns (instance_or_None, errors) in the same shape as sec 1.1."""
    try:
        return CodeRefactoringTask.model_validate_json(raw_output), []
    except ValidationError as e:
        return None, [
            {"field": ".".join(str(p) for p in err["loc"]),
             "error": err["type"],
             "detail": err["msg"]}
            for err in e.errors()
        ]
```

Choose stdlib (section 1) when the skill/script must stay dependency-free;
choose Pydantic when the surrounding application already models its data with
it. Do not mix both gates on the same output — one owner per contract.

---

## 3. Machine-Readable Observation Messages

When a gate fails, the error report is injected into the message history as a
structured observation. Prose ("that didn't work, try again") reproduces the
failure; structure corrects it.

### 3.1 Observation format

```python
import json

OBSERVATION_SCHEMA = "loop-observation/v1"


def format_validation_observation(errors, attempt, max_attempts,
                                  corrective_hint=None):
    """Build the observation message injected after a failed gate."""
    report = {
        "schema": OBSERVATION_SCHEMA,
        "status": "VALIDATION_FAILED",
        "attempt": attempt,
        "attempts_remaining": max_attempts - attempt,
        "errors": errors,          # list of {field, error, detail, line?}
        "instruction": (
            "Correct ONLY the errors listed above. Keep every field that "
            "passed validation unchanged. Return the full corrected JSON."),
    }
    if corrective_hint:
        report["hint"] = corrective_hint
    return {
        "role": "user",
        "content": "OBSERVATION:\n" + json.dumps(report, indent=2,
                                                 sort_keys=True),
    }
```

Design rules for observations:

- **Versioned schema field.** Downstream parsing and trace analysis depend on
  a stable shape; `loop-observation/v1` makes drift detectable.
- **Errors are itemized objects**, each naming the field, the error class, and
  the smallest useful detail (expected type, offending line). One vague string
  produces one vague correction.
- **`attempts_remaining` is stated.** Models allocate effort differently on a
  last attempt; the loop should not hide the ledger from the worker.
- **The instruction pins the diff scope** ("correct ONLY the errors listed")
  to prevent the correction pass from regressing fields that already passed —
  the classic source of oscillating edits.
- **Inject with a consistent role.** Use the same role every time (shown here:
  `user`-role with an `OBSERVATION:` prefix, the ReAct convention). Verify the
  exact role/content conventions against your framework's message API.

### 3.2 Full gate-and-retry cycle

```python
def run_validation_cycle(model_output, history, contract,
                         attempt, max_attempts):
    """Gate one iteration's output. Returns (accepted, parsed, history)."""
    parsed, errors = check_structure(model_output, contract)
    if parsed is not None:
        ok, syntax_errors = check_python_syntax(parsed["refactored_code"])
        if not ok:
            parsed, errors = None, syntax_errors
    if parsed is not None:
        return True, parsed, history

    history.append(format_validation_observation(
        errors, attempt=attempt, max_attempts=max_attempts))
    return False, None, history
```

The retry loop around this cycle is not shown here on purpose: iteration
control (caps, stall/oscillation detection, budgets, escalation) belongs to
`LoopGuard` in `loop_mitigation_patterns.md`. Gates decide *accept or retry*;
guards decide *whether a retry is still allowed*.

---

## 4. Error Classification

Uniform retry is the failure mode: retrying a deterministic error N times
yields N identical failures. Classify first, then select a strategy.

```python
import re

ERROR_CLASSES = ("transient", "bad_input", "wrong_tool", "permission",
                 "unknown")

_CLASSIFIER_RULES = [
    # (class, compiled pattern over the error text)
    ("permission", re.compile(
        r"(permission denied|access denied|forbidden|401|403|"
        r"not authorized|read-?only)", re.IGNORECASE)),
    ("transient", re.compile(
        r"(timeout|timed out|connection (reset|refused|aborted)|"
        r"temporarily unavailable|429|too many requests|"
        r"50[234]|rate limit)", re.IGNORECASE)),
    ("bad_input", re.compile(
        r"(400|bad request|invalid (argument|parameter|input|json)|"
        r"no such file|not found|does not exist|validation (error|failed)|"
        r"unexpected (token|keyword))", re.IGNORECASE)),
    ("wrong_tool", re.compile(
        r"(unsupported operation|not implemented|wrong (format|type) for|"
        r"cannot handle|unknown (command|subcommand|tool))", re.IGNORECASE)),
]


def classify_error(error_text):
    """Map an error message to one of the five recovery classes."""
    for cls, pattern in _CLASSIFIER_RULES:
        if pattern.search(error_text):
            return cls
    return "unknown"
```

The rule order matters: permission signals win over transient ones (a 403
inside a retry storm must escalate, not back off). Extend `_CLASSIFIER_RULES`
with project-specific signatures; keep the five classes fixed so strategy
selection stays a closed table.

---

## 5. Recovery Strategies per Class

```python
import random
import time

RECOVERY_POLICY = {
    #  class        strategy            max_attempts  backoff
    "transient":  {"strategy": "retry_backoff", "max_attempts": 3,
                   "backoff_base": 1.0, "backoff_factor": 2.0,
                   "jitter": "full"},
    "bad_input":  {"strategy": "reformulate",   "max_attempts": 2},
    "wrong_tool": {"strategy": "fallback",      "max_attempts": 1},
    "permission": {"strategy": "escalate",      "max_attempts": 0},
    "unknown":    {"strategy": "retry_then_escalate", "max_attempts": 1},
}


def backoff_delay(attempt, base=1.0, factor=2.0):
    """Exponential backoff with full jitter: sleep in [0, base*factor^n]."""
    return random.uniform(0, base * (factor ** (attempt - 1)))


def recover(error_text, attempt, guard):
    """Decide the next move for a failed action.

    Returns one of:
      ("retry", delay_seconds)     -- re-attempt the same action after delay
      ("reformulate", observation) -- inject observation, let model fix input
      ("fallback", None)           -- switch tool/approach; log why
      ("escalate", report)         -- stop; report comes from the guard
    """
    cls = classify_error(error_text)
    policy = RECOVERY_POLICY[cls]

    if policy["strategy"] == "escalate" or attempt > policy["max_attempts"]:
        report = guard._fire("escalation_trigger",
                             {"reason": "recovery_exhausted",
                              "error_class": cls,
                              "last_error": error_text[:500]})
        return "escalate", report

    if policy["strategy"] == "retry_backoff":
        return "retry", backoff_delay(attempt,
                                      base=policy["backoff_base"],
                                      factor=policy["backoff_factor"])

    if policy["strategy"] == "reformulate":
        observation = format_validation_observation(
            errors=[{"field": None, "error": "tool_rejected_input",
                     "detail": error_text[:500]}],
            attempt=attempt, max_attempts=policy["max_attempts"],
            corrective_hint="The tool rejected the input. Change the input, "
                            "not the goal.")
        return "reformulate", observation

    if policy["strategy"] == "fallback":
        return "fallback", None

    # retry_then_escalate: one conservative retry without backoff
    return "retry", 0.0
```

Rules that keep recovery honest:

- **Every recovery attempt is still a tool call.** It goes through
  `guard.record_action(...)` and charges the budget. Recovery that bypasses
  the ledger is a private inner loop — the exact runaway shape the nested-loop
  budgeting rule forbids.
- **Never repeat an identical failed call.** Same tool + same input + previous
  status error is a guaranteed identical failure; reformulate or fall back
  instead. (This is also what keeps the oscillation and dedup detectors quiet.)
- **Fallbacks are logged, not silent.** Record the classification and the
  reason for the switch in the exit report's `work_completed` trail; silent
  fallback hides systemic tool problems.
- **Permission errors never retry.** No backoff schedule fixes a 403. Zero
  retries, straight to `escalation_trigger`.

---

## 6. Putting It Together

Per iteration, the order of operations is fixed:

```text
before_pass (guard)                      max_iterations, budget
   -> model produces output
   -> VALIDATION GATES (this file)       accept | itemized errors
        accepted -> after_pass (guard)   success_predicate w/ gate evidence
        rejected -> classify + recover   retry | reformulate | fallback | escalate
                    -> observation into history
                    -> record_action (guard)  oscillation, cascade, budget
```

Gates produce the evidence; observations carry the correction; the classifier
picks the strategy; the guard decides whether any of it is still allowed.
Four small mechanisms, one bounded loop.

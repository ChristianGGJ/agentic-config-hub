# Loop Engineering Patterns

Loop Engineering is the discipline of designing bounded, observable, self-terminating iteration into autonomous agents. Every capable agent iterates: it retries failed tool calls, critiques its own drafts, and refines outputs against criteria. Without engineered controls, those same loops become the primary failure mode of agentic systems — runaway retries, oscillating edits, silent stalls, and budget exhaustion. This reference defines the four canonical loop patterns, the six-type exit-condition taxonomy (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger`), counter design, anti-runaway rules, a worked hardening example, anti-patterns, and an audit checklist mapped to the `loop_auditor.py` rubric.

The governing principle: **a loop that terminates by design is a control system; a loop that terminates by luck is an incident report.**

---

## Loop Taxonomy

Four loop patterns cover the vast majority of agentic iteration needs. Each is defined by its purpose, structure, applicability, and known failure modes. Combine them, but never nest a loop inside another loop without giving the outer loop its own independent exit conditions.

### 1. Self-Reflection Loop

**Purpose:** The agent produces an output, critiques its own output against explicit criteria, and revises. A single role performs both production and critique. Bounded at N passes (recommended: 3-5).

**Structure:**

```text
+-----------+     +----------------------------+     +---------+
|   ACT     | --> | CRITIQUE own output        | --> | REVISE  |
| (produce  |     | against explicit criteria  |     | (apply  |
|  output)  |     | (checklist or rubric)      |     |  fixes) |
+-----------+     +----------------------------+     +----+----+
      ^                                                   |
      |          pass count < max_iterations (3-5)        |
      +---------------------------------------------------+
                           |
              criteria met OR max passes reached
                           v
                   EMIT output + pass count
```

**When to use:**
- Single-artifact quality improvement: a document, a code diff, a plan, a query.
- The quality criteria can be written down as a checklist the agent can verify itself.
- Latency budget allows 2-4x the single-pass cost.

**Failure modes:**
- *Reflection without rubric:* "review your work and improve it" with no criteria produces cosmetic churn — the agent rewrites style, not substance, and each pass can regress prior fixes.
- *Self-agreement bias:* the same role that wrote the output tends to approve it; mitigate with a concrete checklist ("all acceptance criteria quoted and marked pass/fail") rather than a vibe check.
- *Unbounded passes:* without `max_iterations`, borderline outputs ping-pong forever. Fire `max_iterations` at 3-5 and emit the best version so far with a note of unmet criteria.

### 2. Evaluator-Optimizer Loop

**Purpose:** Separate the roles. An evaluator scores the output against a rubric and returns a numeric score plus itemized feedback; an optimizer revises using only that feedback. Iterate until `score >= threshold` or `max_iterations` fires.

**Structure:**

```text
+-------------+   output    +-------------------+
|  OPTIMIZER  | ----------> |  EVALUATOR        |
| (produces / |             | (scores against   |
|  revises)   | <---------- |  rubric, returns  |
+-------------+  itemized   |  score + feedback)|
      ^          feedback   +---------+---------+
      |                               |
      |    score < threshold AND      |
      |    iterations < max_iterations|
      +-------------------------------+
                    |
      score >= threshold OR max_iterations fired
                    v
        EMIT output + final score + iteration count
```

**When to use:**
- Quality is measurable on a rubric (clarity score, test coverage, lint findings, factual checks).
- You can afford two roles (two prompts or two agents) and want to defeat self-agreement bias.
- The threshold is meaningful: "score >= 85/100 on the rubric" not "until it looks good."

**Failure modes:**
- *Moving-target rubric:* if the evaluator's criteria drift between iterations, the score never converges. Freeze the rubric before the first iteration.
- *Score plateau:* the optimizer makes changes but the score stops improving — this is `no_progress`, not a reason for more iterations. Detect a flat or declining score over a window of 2 and exit.
- *Threshold set at 100:* perfection thresholds guarantee `max_iterations` fires every run. Set the threshold at the acceptance bar, typically 80-90.

### 3. Error-Mitigation Loop

**Purpose:** Turn tool failures into classified, strategy-driven recovery instead of blind retry. Classify the error, select a recovery strategy, and escalate when strategies are exhausted.

**Structure:**

```text
                 +--------------------+
   tool error -->|  CLASSIFY error    |
                 |  (transient? bad   |
                 |  input? wrong tool?|
                 |  permission? bug?) |
                 +---------+----------+
                           |
        +---------+--------+--------+-----------+
        v         v                 v           v
   RETRY with  REFORMULATE      FALLBACK     ESCALATE
   backoff     the input        tool or      to human
   (transient) (bad input)      approach     (permission,
        |         |             (wrong tool)  unknown, or
        |         |                 |         retries
        +---------+--------+--------+         exhausted)
                           |
              retry count < max_errors (default 3)
                           v
                   re-attempt the action
```

**When to use:**
- Any agent that calls tools with nondeterministic outcomes: network calls, file systems, builds, test runs, external APIs.
- Always. An agent with tool access and no error-mitigation loop is an agent one flaky call away from a runaway retry storm.

**Failure modes:**
- *Retry-as-only-strategy:* retrying a deterministic failure (bad path, syntax error, denied permission) three times produces three identical failures. Classification must precede strategy selection.
- *Error cascade:* consecutive errors compound (each recovery attempt itself errors). Cap consecutive errors at `budget.max_errors` (default 3) and escalate — this is exactly detection D3 in `react_trace_analyzer.py`.
- *Silent fallback:* switching tools without recording why hides systemic problems. Log every classification and strategy choice in the handoff report.

### 4. Convergence Loop

**Purpose:** The general-purpose "iterate until done" loop for multi-step goals: iterate until an explicit `success_predicate` evaluates true, guarded by **all six** exit conditions from the canonical taxonomy.

**Structure:**

```text
   DECLARE exit conditions (all 6) BEFORE iteration 1
                        |
                        v
        +------------------------------+
        |  PLAN next step toward goal  |
        +--------------+---------------+
                       v
        +------------------------------+
        |  EXECUTE step (tool call)    |
        +--------------+---------------+
                       v
        +------------------------------+
        |  CHECK all exit conditions:  |
        |  success_predicate  -> DONE  |
        |  max_iterations     -> STOP  |
        |  no_progress        -> STOP  |
        |  oscillation        -> STOP  |
        |  budget             -> STOP  |
        |  escalation_trigger -> STOP  |
        +------+----------------+------+
               |                |
          none fired       one fired
               |                v
               +----->  STOP + REPORT which condition
                        fired, state, and evidence
```

**When to use:**
- Open-ended goals where the number of steps is unknown in advance: "make the build pass", "migrate these files", "resolve all lint errors".
- Whenever the loop body contains tool calls with side effects — the full guard set is mandatory here.

**Failure modes:**
- *Vague success predicate:* "when the task is done" is not evaluable. The predicate must be machine-checkable: "pytest exits 0", "validator reports PASS", "zero remaining items in the queue".
- *Guard subset:* implementing only `max_iterations` and skipping `no_progress`/`oscillation` lets the agent burn its full iteration budget doing nothing. All six conditions, OR-ed.
- *Predicate checked before side effects settle:* checking "tests pass" against a stale test run converges on a false positive. Re-evaluate the predicate from fresh evidence each iteration.

---

## Exit-Condition Engineering

Every loop must declare its exit conditions before the first iteration. The canonical taxonomy contains exactly six types. Exit conditions are OR-ed: the first one to fire terminates the loop. When any condition other than `success_predicate` fires, the agent must **stop and report** — never silently continue, never quietly reset a counter, never "try one more time."

### 1. `max_iterations`

- **Definition:** A hard cap on the number of loop passes, fixed before iteration 1.
- **Implementation:** A monotonically increasing counter incremented at the top of every pass; compare `counter >= cap` before doing any work in the pass.
- **Recommended defaults:** 3-5 for Self-Reflection loops; 3-5 for Evaluator-Optimizer; 3 recovery attempts per error class in Error-Mitigation; 10-20 steps for Convergence loops (align with `budget.max_steps` in the ReAct trace schema, default 20).
- **When it fires:** Stop. Report the cap, the number of passes consumed, the best output so far, and the criteria still unmet. Do not extend the cap mid-run.

### 2. `no_progress`

- **Definition:** The loop is running but the observable state is not changing — stall detection.
- **Implementation:** Hash the relevant state after each pass (output text, file checksums, failing-test list, evaluator score). If the hash is identical for `window` consecutive passes, fire.
- **Recommended default:** window of 2 (two consecutive passes with an unchanged state hash).
- **When it fires:** Stop. Report the state hash, the window, and the last two attempted actions so a human can see what the agent was trying. A stalled loop consuming budget is worse than an honest early stop.

### 3. `oscillation`

- **Definition:** The loop alternates between states or actions (A-B-A-B), undoing and redoing the same change — a two-cycle the state hash alone may miss.
- **Implementation:** Keep a ring buffer of recent action signatures (tool + normalized input, or state hash). Inspect the last `window` entries; if positions 0/2 match and positions 1/3 match with 0 != 1, fire.
- **Recommended default:** window of 4 (matches detection D2 in `react_trace_analyzer.py`).
- **When it fires:** Stop. Report both alternating states/actions verbatim. Oscillation almost always means two constraints are in conflict; the report must name both sides so a human can break the tie.

### 4. `budget`

- **Definition:** A resource ceiling independent of iteration count: tool calls, tokens, wall-clock time, or cost.
- **Implementation:** Decrementing counters checked before every resource-consuming action; the loop refuses the action if the budget would be exceeded.
- **Recommended defaults:** budget denominated in tool calls (most portable): 20 tool calls per task (mirrors `budget.max_steps`); 3 consecutive errors (`budget.max_errors`). Add wall-clock ceilings for interactive contexts.
- **When it fires:** Stop. Report budget consumed vs. allocated, work completed, and work remaining. Never borrow against a hypothetical extension.

### 5. `success_predicate`

- **Definition:** The one exit condition that means "done": an explicit, machine-checkable test that the goal is achieved.
- **Implementation:** A concrete check executed at the end of every pass against fresh evidence: an exit code, a validator verdict, a score threshold, an empty error list.
- **Recommended default:** There is no default — it must be written per task, before iteration 1. If you cannot write the predicate, the task is not ready for an autonomous loop.
- **When it fires:** Stop and report success **with the evidence** (the command output, the score, the validator verdict). "I believe it works" is not evidence; the predicate's observable result is.

### 6. `escalation_trigger`

- **Definition:** A condition that routes the loop to a human instead of terminating silently: irreversible action required, permission denied, conflicting instructions, confidence below floor, or any other condition fired twice in the same session.
- **Implementation:** A declared list of trigger predicates checked each pass; on fire, the loop packages state and question, then halts pending human input (a hard stop in the sense of Phase 3 — HUMAN GATE of the 5-Phase Protocol).
- **Recommended default:** Always escalate on: irreversible operations without prior approval, authentication/permission failures, and the second firing of any other exit condition for the same subtask.
- **When it fires:** Stop and produce an escalation report: what was attempted, what fired, the specific decision needed from the human, and the options considered. Never guess through an escalation.

---

## Counter Design

Exit conditions are only as reliable as the counters and detectors behind them. The reference implementation is an **iteration ledger** owned by the loop controller — never by the step logic, which must not be able to reset it.

```text
LEDGER = {
  attempts:        map<subtask_id, int>   # per-subtask pass count
  state_hashes:    map<subtask_id, list>  # recent state hashes (newest last)
  action_history:  ring_buffer(size=8)    # (tool, normalized_input) tuples
  tool_calls_used: int                    # global budget counter
  consecutive_errors: int                 # resets ONLY on a successful action
}

function BEFORE_PASS(subtask_id):
  LEDGER.attempts[subtask_id] += 1
  if LEDGER.attempts[subtask_id] > MAX_ITERATIONS:
      fire("max_iterations", evidence=LEDGER.attempts[subtask_id])
  if LEDGER.tool_calls_used >= BUDGET_TOOL_CALLS:
      fire("budget", evidence=LEDGER.tool_calls_used)

function AFTER_PASS(subtask_id, new_state, action, status):
  # --- no_progress: state-hash window ---
  h = hash(canonicalize(new_state))
  LEDGER.state_hashes[subtask_id].append(h)
  last = LEDGER.state_hashes[subtask_id][-NO_PROGRESS_WINDOW:]   # window = 2
  if len(last) == NO_PROGRESS_WINDOW and all_equal(last):
      fire("no_progress", evidence=last)

  # --- oscillation: A-B-A-B over the ring buffer ---
  LEDGER.action_history.push((action.tool, normalize(action.input)))
  w = LEDGER.action_history.last(OSCILLATION_WINDOW)             # window = 4
  if len(w) == 4 and w[0] == w[2] and w[1] == w[3] and w[0] != w[1]:
      fire("oscillation", evidence=w)

  # --- error cascade feeding budget/escalation ---
  if status == "error":
      LEDGER.consecutive_errors += 1
      if LEDGER.consecutive_errors >= MAX_ERRORS:                # default 3
          fire("escalation_trigger", evidence="error cascade")
  else:
      LEDGER.consecutive_errors = 0

  # --- success_predicate: fresh evidence only ---
  if SUCCESS_PREDICATE(new_state):
      fire("success_predicate", evidence=predicate_output)
```

Design notes:

- **Canonicalize before hashing.** Strip timestamps, absolute paths, and run IDs from the state before hashing, or `no_progress` never fires because trivia changes every pass.
- **Normalize action inputs.** "run tests" and "run  tests" must produce the same signature or oscillation detection is blind.
- **Counters never reset mid-task.** The only legal reset of `consecutive_errors` is a genuinely successful action. `attempts` never resets within a subtask's lifetime.
- **The ledger is append-only from the step's perspective.** Steps report outcomes; only the controller writes and reads counters.

---

## Anti-Runaway Design Rules

1. **Declare before iterating.** Every loop states its exit conditions — all that apply from the six-type taxonomy — before the first iteration executes. An undeclared exit condition does not exist.
2. **Exit conditions are OR-ed.** The first condition to fire terminates the loop. Conditions never vote, average, or defer to each other.
3. **Firing is a control-system success, not an agent failure.** An agent that stops after 3 stalled passes and reports cleanly has *succeeded* at self-governance. Frame it that way in prompts, or the agent will learn to evade its own guards.
4. **Stop means stop and report.** On any non-success exit, the agent produces a structured report (condition fired, evidence, state, work remaining, recommended next step) and halts. It does not retry "just once more", widen its own scope, or reset counters.
5. **Two strikes escalate.** Any exit condition firing twice for the same subtask converts to `escalation_trigger`. Loops do not get a third attempt at the same wall.
6. **Outer loops guard inner loops.** Nesting is allowed only when the outer loop carries its own independent budget and iteration cap; inner-loop consumption counts against the outer budget.

---

## Worked Example: Hardening a "Fix the Tests" Agent

**Before (naive, runaway-prone):**

```text
You are a test-fixing agent. Run the test suite, find failing
tests, and fix the code until all tests pass. Keep trying
until everything is green.
```

Problems: no iteration cap ("keep trying"), no stall detection, no budget, no oscillation guard, an implicit success predicate never verified with evidence, and no escalation path. One flaky test makes this agent run forever.

**After (loop-engineered):**

```text
You are a test-fixing agent operating a Convergence Loop.

Exit conditions (declared now, checked after every pass, OR-ed):
- success_predicate: `pytest -q` exits 0. Report the exit code
  and summary line as evidence.
- max_iterations: 5 fix passes. One pass = diagnose, patch,
  re-run tests.
- no_progress: the set of failing test names is identical for
  2 consecutive passes.
- oscillation: the last 4 patches alternate between reverting
  and re-applying the same change (window of 4).
- budget: at most 20 tool calls total; at most 3 consecutive
  tool errors.
- escalation_trigger: a fix would modify test files or delete
  code, OR any condition above fires twice for the same test.

Per pass: run tests, classify each failure (assertion, import,
environment, flake), patch the smallest responsible unit, re-run.
Recovery for tool errors: retry with backoff for transients,
reformulate for bad invocations, escalate on permission errors.

On ANY exit: STOP and produce a handoff report — which condition
fired, evidence, tests fixed, tests remaining, patches applied,
and the recommended next action. Never continue past a fired
exit condition. Stopping on a fired condition is correct behavior.
```

The hardened prompt is longer, but every added line is a control the naive version pays for in incidents.

---

## Anti-Patterns

| Anti-pattern | Why it fails | Correction |
|---|---|---|
| **Unbounded retry** ("keep trying until it works") | Deterministic failures repeat forever; flaky failures burn budget randomly | Error-Mitigation Loop: classify, cap at 3, escalate |
| **Reflection without rubric** ("review and improve your answer") | Cosmetic churn, regressions, self-agreement bias | Explicit checklist or Evaluator-Optimizer with frozen rubric |
| **Counters that reset** (retry counter cleared on each "new approach") | The loop launders its history and evades `max_iterations` | Ledger owned by the controller; resets only on genuine success |
| **Exit condition only on success** (loop ends solely when done) | Every non-success trajectory is an infinite loop | All six conditions, OR-ed, declared before iteration 1 |
| **Silent continuation after a fired condition** ("limit hit, trying once more") | Guards become suggestions; runaway resumes | Stop + report is mandatory; two strikes escalate |
| **Vague success predicate** ("until the task is complete") | Not machine-checkable; convergence is unverifiable | Evidence-producing predicate: exit codes, scores, validator verdicts |
| **Guard subset** (only `max_iterations` implemented) | Agent burns the full cap while stalled or oscillating | `no_progress` window 2 + `oscillation` window 4 + budget, always |

---

## Audit Checklist (maps to `loop_auditor.py` rubric)

Use this checklist when reviewing any agent configuration. Each item maps to a category and check in the `loop_auditor.py` 100-point rubric.

| # | Question | Rubric check | Points |
|---|---|---|---|
| 1 | Does every loop declare a max-iterations / attempt limit? | A1 (Loop Safety) | 10 |
| 2 | Is no-progress / stall detection specified (state-hash window)? | A2 (Loop Safety) | 10 |
| 3 | Is there an oscillation / repeated-action / dedup guard? | A3 (Loop Safety) | 5 |
| 4 | Is a budget defined (tool-call, token, or time limit)? | A4 (Loop Safety) | 5 |
| 5 | Is there a human approval gate before consequential work? | B1 (HITL Gates) | 10 |
| 6 | Are irreversible actions named and gated on confirmation? | B2 (HITL Gates) | 10 |
| 7 | Is an escalation path defined (who, and on what trigger)? | B3 (HITL Gates) | 5 |
| 8 | Does the flow include a read-only discovery phase? | C1 (Phase Protocol) | 5 |
| 9 | Is a change manifest produced before implementation? | C2 (Phase Protocol) | 5 |
| 10 | Is there a hard human gate between manifest and implementation? | C3 (Phase Protocol) | 5 |
| 11 | Does the flow end with self-review and a handoff? | C4 (Phase Protocol) | 5 |
| 12 | Are scope boundaries explicit (allowed paths, forbidden areas)? | D1 (Boundary Control) | 10 |
| 13 | Are tool restrictions declared (allowlist)? | D2 (Boundary Control) | 5 |
| 14 | Are exit conditions / success criteria written down? | E1 (Output Contract) | 5 |
| 15 | Is a structured handoff report format defined? | E2 (Output Contract) | 5 |

Checks 8-11 correspond to the 5-Phase Protocol: Phase 1 — DISCOVERY (read-only), Phase 2 — MANIFEST, Phase 3 — HUMAN GATE, Phase 4 — IMPLEMENTATION, Phase 5 — SELF-REVIEW & HANDOFF. A configuration scoring below 50 (UNSAFE-FOR-AUTONOMY) must not run unattended; 50-74 (NEEDS-CONTROLS) may run only with a human watching; 75-89 is PRODUCTION-READY; 90+ is HARDENED.

Run the audit mechanically:

```text
python scripts/loop_auditor.py path/to/agent-config.md
python scripts/loop_auditor.py path/to/agent-config.md --json
```

Pair this reference with `react_reasoning_patterns.md` (how the loop body reasons), `hitl_defensive_architectures.md` (where humans interrupt the loop), and `four_pillar_ecosystem.md` (where loops live in the context/skills/agents/workflows structure).

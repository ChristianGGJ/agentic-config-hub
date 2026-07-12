---
title: "Loop Engineering Mechanisms — Core Agentic Design & Loop Safety"
description: "Use when implementing loop safety in Python code: wiring all six canonical exit conditions (max_iterations, no_progress, oscillation, budget. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Loop Engineering Mechanisms

<div class="page-meta" markdown>
<span class="meta-badge">:material-robot: Core Agentic Design</span>
<span class="meta-badge">:material-identifier: `loop-engineering-mechanisms`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/loop-engineering-mechanisms/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install core-agentic-design</code>
</div>


## Overview

This skill is the **runnable implementation companion** to the hub's loop-engineering
canon. The theory — the four-loop taxonomy (Self-Reflection, Evaluator-Optimizer,
Error-Mitigation, Convergence), the exit-condition definitions, the anti-runaway
design rules, and the audit checklist — is owned by the `agentic-system-architect`
skill (its loop-engineering-patterns reference). This skill owns the code layer:

- Python standard-library implementations of **all six** canonical exit conditions.
- A controller-owned iteration ledger (`LoopGuard`) that step logic cannot reset.
- Output validation gates that run **before** a loop iteration is accepted.
- Machine-readable observation messages and structured error formatters.
- Error classification and per-class recovery strategies (not uniform retry).
- A structured stop-and-report exit contract (`loop-exit-report/v1`).
- `scripts/loop_guard.py` — a deterministic reference implementation that replays
  iteration traces through the six detectors and self-tests its own logic.

**Version assumptions:** all core code is Python 3.8+ standard library only. The
optional Pydantic validation pattern targets Pydantic 2.x (third-party) and is
clearly marked as such in the reference.

## Core Capabilities

1. **Six-condition guard wiring** — drop-in `LoopGuard` class: pass counter,
   state-hash stall detector (window 2), A-B-A-B oscillation ring buffer
   (window 4), tool-call/token/wall-clock budgets, evidence-producing success
   predicate, and escalation triggers with the two-strikes rule.
2. **Validation gates** — deterministic checks (JSON structure, syntax compile,
   schema, tests) that decide whether an iteration's output is accepted, retried
   with a structured observation, or escalated.
3. **Observation engineering** — versioned, machine-readable error reports
   injected into message history so the next iteration corrects the right thing.
4. **Recovery strategy selection** — classify errors as transient / bad_input /
   wrong_tool / permission / unknown, then apply backoff-retry, reformulation,
   fallback, or escalation per class.
5. **Exit handoff contract** — every non-success exit produces a structured
   report (condition fired, evidence, counters, work remaining, recommended next
   step) instead of a bare exception.

## Decision Frameworks

### Detector calibration defaults

| Exit condition | Mechanism | Calibrated default | Tighten when | Loosen when |
|---|---|---|---|---|
| `max_iterations` | monotonic pass counter, checked before any work in the pass | 3-5 (reflection / evaluator loops), 10-20 (convergence loops) | side effects are expensive or risky | each pass is cheap and verifiably monotonic progress |
| `no_progress` | canonicalized state hash, fire on N identical consecutive hashes | window = 2 | passes are expensive (fire on first repeat is too eager; 2 is already the floor) | legitimate warm-up passes mutate nothing (rare — prefer fixing state selection) |
| `oscillation` | ring buffer of normalized action signatures, A-B-A-B test | window = 4 | agent has few tools (alternation is more meaningful) | pipelines legitimately alternate two tools (then key the signature on tool+input, never tool alone) |
| `budget` | decrementing counters checked before each consuming action | 20 tool calls per task; 3 consecutive errors; optional token and wall-clock caps | irreversible or paid actions in the loop body | long-horizon batch tasks with human checkpoints |
| `success_predicate` | machine-checkable test producing evidence, evaluated on fresh state each pass | none — written per task, before iteration 1 | never (a lax predicate is a false success) | never (if unwritable, the task is not loop-ready) |
| `escalation_trigger` | declared predicate list + automatic conversions | irreversible action, permission failure, or any other condition firing twice | high-blast-radius environments | never below the defaults |

### Validation gate selection

| Gate | Catches | Cost | Use when |
|---|---|---|---|
| JSON parse + required-keys/type check (stdlib) | malformed structure, missing fields | negligible | every structured LLM output — the minimum gate |
| `ast.parse` / `compile()` syntax gate | broken generated Python | negligible | any code-producing loop |
| Schema validator (stdlib helper or Pydantic 2.x) | wrong types, out-of-range values, bad enums | low | outputs with numeric/enum/range contracts |
| Regex contract | malformed IDs, dates, delimited formats | negligible | short string outputs with a fixed grammar |
| Test-suite run (subprocess) | behavioral regressions | high | code changes; run as the final gate, not the first |

Order gates cheapest-first and stop at the first failure: one precise error
observation beats four stacked ones.

### Error classification -> recovery strategy

| Class | Typical signals | Strategy | Calibrated defaults |
|---|---|---|---|
| `transient` | timeout, connection reset, HTTP 429/5xx, lock contention | retry with exponential backoff + jitter | base 1s, factor 2, full jitter, max 3 attempts |
| `bad_input` | HTTP 400, validation error, file-not-found on a path the agent chose | reformulate the input, then retry once | max 2 reformulations per action |
| `wrong_tool` | capability error, repeated `bad_input` after reformulating | fallback to an alternative tool or approach | 1 fallback switch, always log why |
| `permission` | HTTP 401/403, access denied, sandbox refusal | escalate immediately — retrying cannot help | 0 retries |
| `unknown` | anything unclassified | 1 conservative retry, then escalate | 1 retry |

Uniform retry is the anti-pattern this table replaces: retrying a deterministic
failure N times produces N identical failures while the budget burns.

### Budget denomination trade-offs

| Denomination | Portability | Precision | Notes |
|---|---|---|---|
| Tool calls | best | medium | default 20 per task; survives model and provider changes |
| Consecutive errors | best | high | default 3; feeds `escalation_trigger` (error cascade) |
| Tokens | medium | high | requires usage metering from the provider response; use for cost-sensitive loops |
| Wall-clock time | low | low | interactive contexts only; measure with `time.monotonic()`, never `time.time()` |
| Cost (currency) | low | high | derive from tokens x rate; keep rates in config, never hard-coded |

Denominate the primary budget in tool calls; add tokens or wall clock as a
second ceiling when the context demands it. Multiple budgets are OR-ed like
every other exit condition.

## Implementation Map

| Mechanism | Where |
|---|---|
| `LoopGuard` ledger + all six detectors, runnable convergence-loop example, exit report contract, nested-loop budgeting | `references/loop_mitigation_patterns.md` |
| Validation gates (stdlib + Pydantic), observation message format, error classifier, recovery strategies with backoff | `references/validation_and_observation.md` |
| Deterministic trace replay + detector self-test CLI | `scripts/loop_guard.py` |

## Ledger Design Rules

These rules make the detectors trustworthy. Violating any of them silently
disables a guard.

1. **The controller owns the ledger.** Step logic reports outcomes; only the
   loop controller reads and writes counters. A step that can reset its own
   retry counter will.
2. **Counters never reset mid-task.** The only legal reset is
   `consecutive_errors` after a genuinely successful action. `attempts` never
   resets within a subtask's lifetime — "trying a new approach" is not a new
   subtask.
3. **Canonicalize state before hashing.** Strip timestamps, absolute paths,
   run IDs, and other volatile trivia, then serialize with sorted keys.
   Otherwise `no_progress` never fires because noise changes every pass.
4. **Normalize action inputs.** Collapse whitespace, lowercase, and serialize
   structured inputs with sorted keys before building the signature, or
   oscillation detection is blind to trivially different spellings of the same
   action.
5. **Declare before iteration 1, OR-ed, first-fired wins.** All six conditions
   are stated before the loop starts. The first to fire terminates the loop.
   No condition defers to another.
6. **Two strikes escalate.** Any condition firing twice for the same subtask
   converts to `escalation_trigger`. Loops do not get a third attempt at the
   same wall.
7. **Nested loops consume the outer budget.** An inner loop (e.g. a retry loop
   inside a convergence loop) draws down the outer loop's tool-call and token
   budgets while keeping its own independent iteration cap. An inner loop with
   a private budget is a runaway loop with extra steps.

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| `no_progress` never fires even though the agent is visibly stalled | state hash includes volatile fields (timestamps, run IDs, temp paths) | canonicalize before hashing (rule 3); hash only task-relevant state such as the failing-test list or output text |
| Oscillation fires on the first repeated error | detector is a first-repeat check — that is `no_progress` mislabeled as `oscillation` | implement the A-B-A-B test over a window-4 ring buffer; repetition of one state belongs to `no_progress` |
| Loop burns its full iteration cap doing nothing | guard subset: only `max_iterations` implemented | wire all six conditions; stall and alternation guards fire long before the cap |
| Agent hammers a 403 three times, then gives up confused | uniform retry with no classification | classify first; `permission` class escalates with 0 retries |
| Exit surfaces as a bare `RuntimeError` with no context | no stop-and-report contract | emit a `loop-exit-report/v1` object; the exception (if any) carries the report |
| Loop reports success but the artifact is broken | success predicate is a belief ("looks done"), not evidence | predicate must produce checkable evidence (exit code, validator verdict, score) evaluated on fresh state |
| Correction loop repeats the same wrong fix each pass | error fed back as prose or not at all | inject a machine-readable observation with exact error, location, and corrective hint |
| Inner retry loop exhausts the whole task budget | inner loop given its own private budget | inner consumes outer budget; outer keeps an independent cap (rule 7) |
| Guards pass in testing, never fire in production | step code resets counters or filters what the ledger sees | move the ledger to the controller; steps only report (rule 1) |

## Hub Canon Integration

- **Exit-condition taxonomy.** This skill implements the canonical six types
  1:1 — `max_iterations`, `no_progress` (state-hash window 2), `oscillation`
  (A-B-A-B window 4), `budget`, `success_predicate`, `escalation_trigger` —
  as declared-before-iteration-1, OR-ed guards. Anything less is the "guard
  subset" anti-pattern the canon names explicitly.
- **Trace detections D1-D7.** The detectors here are the preventive twins of
  the hub's trace analysis: the oscillation ring buffer prevents what D2
  (A-B-A-B window 4) detects post-hoc; the action-signature dedup addresses D1
  (identical call >= 3 times); `consecutive_errors >= 3` is D3 (error cascade)
  enforced live; the budget counter prevents D5 (steps >= `budget.max_steps`);
  an evidence-producing success predicate prevents D6 (no convergence).
- **HITL gates R1-R6 and the 5-Phase Protocol.** A fired `escalation_trigger`
  is a hard stop in the sense of Phase 3 — HUMAN GATE: the loop freezes and
  hands a decision to a human. The `loop-exit-report/v1` object is the
  escalation object that gate rule R3 requires and doubles as the Phase 5
  SELF-REVIEW & HANDOFF artifact for loop-shaped work.
- **HARDENED gate (>= 90).** Wiring `LoopGuard` as shipped satisfies the loop
  safety checks of the hub audit rubric (iteration cap, stall detection,
  oscillation guard, budget) — the categories a configuration cannot reach
  HARDENED without. Run the flagship's auditor for the score; run this skill's
  `loop_guard.py --self-test` to prove the mechanisms themselves work.

## When NOT to Use

- **Choosing which loop pattern to use, or auditing an agent config for
  runaway risk** — that is design and audit territory: see
  `agentic-system-architect` (four-loop taxonomy, exit-condition theory,
  `loop_auditor.py` rubric).
- **Framework-native loop controls** — LangGraph `recursion_limit` and cycle
  design: see `langgraph-state-design`. CrewAI `max_iter` / `max_rpm` /
  `max_execution_time`: see `crewai-role-engineering`.
- **Designing where humans interrupt the loop** (gate placement, strictness
  classes, rollback) — see `agentic-system-architect` (HITL defensive
  architectures); this skill only produces the escalation report those gates
  consume.
- **A bounded fix protocol for a broken feature** — see `focused-fix`; it
  applies these mechanisms inside a scoped repair workflow.
- **Evaluating loop output quality over a dataset** — see
  `agentic-evals-benchmarking`; validation gates here are per-iteration
  accept/reject checks, not eval suites.

## Tools

```bash
# Detector self-test: proves max_iterations, no_progress (window 2),
# oscillation (A-B-A-B window 4), budgets, success, and escalation fire
# exactly where canon says they should -- and nowhere else.
python scripts/loop_guard.py --self-test
python scripts/loop_guard.py --self-test --json

# Replay a recorded iteration trace (JSONL, one pass per line) through the
# guards and report the first condition that fires.
python scripts/loop_guard.py --trace run_trace.jsonl
python scripts/loop_guard.py --trace run_trace.jsonl --max-iterations 5 --json
```

Exit codes: `0` = trace ended in `success_predicate` or consumed cleanly;
`1` = a non-success exit condition fired (or a self-test failed);
`2` = usage or trace-format error. Trace format is documented in `--help`.

## References

| File | Summary |
|------|---------|
| `references/loop_mitigation_patterns.md` | Stdlib implementations of all six exit conditions: canonical hashing and normalization helpers, the `LoopGuard` controller-owned ledger, a complete runnable convergence loop, the `loop-exit-report/v1` stop-and-report contract, and nested-loop budgeting |
| `references/validation_and_observation.md` | Output validation gates (stdlib and Pydantic 2.x), machine-readable observation message format, structured error formatters, and the error classification -> recovery strategy implementation with backoff defaults |

# ReAct Reasoning Patterns

ReAct (Reasoning + Acting) is the foundational control pattern for autonomous agents: instead of producing a single monolithic answer, the agent interleaves explicit reasoning steps with tool actions and grounds every subsequent decision in the observed result of the previous one. Each cycle is a **Thought -> Action -> Observation** triple. The Thought explains *why* the next action is chosen, the Action invokes a tool with concrete input, and the Observation records what the tool actually returned. The loop repeats until an exit condition fires or a final answer is produced.

The value of the pattern is not the vocabulary — it is the discipline. An agent that reasons without acting hallucinates world state; an agent that acts without reasoning selects tools poorly and burns budget. ReAct forces the two to alternate, which makes agent behavior *auditable*: every trace can be replayed, scored, and diagnosed mechanically. This reference defines the ReAct contract, the core reasoning patterns built on top of it (Reflexion, Plan-and-Execute, Tool-Use Hygiene), the canonical failure modes D1-D7 detected by `scripts/react_trace_analyzer.py`, and the prompt blocks that enforce the contract in production agents.

---

## The ReAct Contract

Every step in a ReAct loop MUST contain all three fields — Thought, Action, Observation. No exceptions, no "obvious" steps that skip the Thought, no fire-and-forget actions that skip the Observation.

The canonical trace schema (the exact input format for `react_trace_analyzer.py`):

```json
{
  "agent": "string",
  "task": "string",
  "budget": {"max_steps": 20, "max_errors": 3},
  "steps": [
    {
      "step": 1,
      "thought": "string",
      "action": {"tool": "string", "input": "string"},
      "observation": "string",
      "status": "ok|error"
    }
  ],
  "final_answer": "string or null"
}
```

Why each field is load-bearing:

- **Skipping Thought degrades tool selection.** Without a written rationale, the agent selects tools by surface pattern-matching on the task text rather than by reasoning about current state. Empirically this shows up as calling the same tool the previous step already called, calling a search tool when the answer is already in a prior observation, or picking a write tool during a read-only phase. The Thought is also the only place where exit conditions can be evaluated deliberately ("I have enough evidence; stop").
- **Skipping Observation causes hallucinated state.** If the tool result is not captured and re-read, the agent's next Thought is conditioned on what it *expected* the tool to return, not what it returned. This is the single most common source of cascading errors: a failed file write that the agent believes succeeded poisons every subsequent step.
- **Recording `status` enables error-mitigation loops.** The `ok|error` flag lets both the agent and the analyzer count consecutive failures against `budget.max_errors` and trigger escalation before an error cascade consumes the whole budget.
- **`budget` makes exit conditions explicit.** `max_steps` bounds total iterations (the `max_iterations` exit condition); `max_errors` bounds consecutive failures. A trace without a budget is an unbounded loop waiting to happen.
- **`final_answer` is the convergence signal.** A trace that ends with `final_answer: null` while the last step succeeded means the agent stopped without concluding — detectable, and fixable with a `success_predicate` exit condition.

---

## Core Patterns

### 1. Vanilla ReAct Loop

The baseline: a single loop of Thought -> Action -> Observation cycles with explicit exit conditions checked at the top of every iteration.

**Structure:**

1. Read the task and current state.
2. Check exit conditions (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger`). If any fires, stop and report.
3. Write a Thought: current state, what is missing, which tool closes the gap, why.
4. Execute exactly one Action.
5. Record the full Observation verbatim, including errors.
6. Go to step 2.

**Prompt snippet:**

```text
For every step, produce exactly:
Thought: <what I know, what is missing, which tool I will use and why>
Action: <tool>(<input>)
Observation: <verbatim tool result — never paraphrase, never invent>

Before each Thought, check exit conditions:
- Stop with a final answer when the success_predicate is met.
- Stop and escalate after max_iterations = 15 steps.
- Stop and escalate after 3 consecutive error observations.
- Stop if the last 2 actions produced no new information (no_progress).
Never emit an Action without a Thought. Never continue without reading
the full Observation.
```

**When to use:** short, well-scoped tasks (under ~15 steps) where the path to the answer is discoverable step by step: lookups, diagnostics, single-file edits, verification runs. This is the default; reach for the heavier patterns below only when the vanilla loop demonstrably fails.

### 2. Reflexion

Reflexion adds **episodic memory of past failures** on top of the vanilla loop. When an attempt fails or an exit condition fires without success, the agent writes a short structured self-critique ("what I tried, why it failed, what to do differently") and prepends that memory to the next attempt. The next episode starts smarter instead of replaying the same mistake.

**Structure:**

1. Run a vanilla ReAct episode with a fixed budget.
2. On failure or non-convergence, generate a reflection: root cause, wrong assumption, concrete rule for the next attempt ("do not call `search` with the same query twice", "the config lives in `settings.local.json`, not `settings.json`").
3. Store the reflection in an episodic memory buffer (last N reflections, N small — 3 to 5).
4. Start the next episode with the memory buffer injected into context.
5. Bound the outer loop: at most `max_attempts` episodes, then escalate (`escalation_trigger`).

**Prompt snippet:**

```text
Previous attempts and lessons (episodic memory):
{{reflections}}

You failed the last attempt. Before acting, write a Reflection:
Reflection: <root cause of the failure, the assumption that was wrong,
one concrete rule I will follow this attempt>

Then run the standard Thought -> Action -> Observation loop.
Hard limits: max_attempts = 3 total episodes. If attempt 3 fails,
stop and escalate to a human with all reflections attached.
Never retry an action that an earlier reflection marked as a dead end.
```

**When to use:** tasks with a cheap, reliable verification signal (a failing test, a validator, a compile step) where retrying is inexpensive but blind retrying loops forever. Reflexion is the antidote to the D7 reasoning loop — it forces each retry to differ from the last. Do not use it when verification is expensive or subjective; the reflection has nothing trustworthy to condition on.

### 3. Plan-and-Execute

Plan-and-Execute separates strategy from tactics: the agent first produces an **upfront plan** (an ordered list of bounded sub-steps), then executes each sub-step with a small ReAct loop, with **plan-deviation detection** between steps.

**Structure:**

1. **Plan phase:** decompose the task into 3-10 numbered sub-steps, each with its own success criterion and tool budget. No actions in this phase.
2. **Execute phase:** for each sub-step, run a bounded ReAct loop (typically max 5 steps per sub-step).
3. **Deviation check:** after each sub-step, compare actual outcome against the plan's expected outcome. If they diverge, do not improvise — return to the plan phase and re-plan the remainder, or escalate if re-planning has already happened twice.
4. Finish when all sub-steps report success (the plan itself acts as the `success_predicate`).

**Prompt snippet:**

```text
Phase A - PLAN (no tool calls allowed):
Produce a numbered plan of 3-10 sub-steps. For each: goal, tool(s),
success criterion, max 5 ReAct steps.

Phase B - EXECUTE:
Work one sub-step at a time using Thought -> Action -> Observation.
After each sub-step, emit:
Plan-Check: <sub-step N: MET | DEVIATED — expected X, got Y>
On DEVIATED: stop executing, re-plan the remaining sub-steps once.
A second deviation on the same sub-step = stop and escalate.
Never execute a sub-step that is not in the current plan.
```

**When to use:** long-horizon tasks (multi-file refactors, ecosystem scaffolding, migrations) where a vanilla loop drifts. The plan gives the trace a spine that both humans and `hitl_gate_validator.py`-style checks can audit before execution begins. Inside the 5-Phase Protocol, the plan phase maps naturally onto Phase 2 MANIFEST — see the integration section below.

### 4. Tool-Use Hygiene

Not a loop topology but a set of invariants applied to every Action in every pattern above. Most runaway traces are hygiene failures, not architecture failures.

**Rules:**

1. **Validate arguments before the call.** Check that paths exist, required fields are present, and inputs are inside the allowed scope *in the Thought*, before spending a tool call to find out.
2. **Read the whole observation before the next thought.** Not the first line, not the exit code alone — the whole result. Truncated reading is how agents miss the "warning: nothing was written" at the bottom of an apparently successful output.
3. **Never repeat an identical failed call.** Same tool + same input + previous status `error` = guaranteed same failure. Change the input, change the tool, or escalate. This single rule prevents most D1 action loops.
4. **One action per step.** Batching hides which action produced which observation and breaks trace auditability.

**Prompt snippet:**

```text
Tool-use rules (apply to every Action):
1. In the Thought, verify the arguments are valid and in-scope BEFORE
   calling the tool.
2. Read the ENTIRE Observation, including warnings and trailing output,
   before writing the next Thought.
3. If a call failed, never repeat it with identical input. State in the
   next Thought what you are changing and why.
4. Exactly one tool call per step.
```

**When to use:** always. Embed these rules in every agent spec; `loop_auditor.py` scores their presence under Category A (Loop Safety) and Category D (Boundary Control).

---

## Failure Modes and Detections

`scripts/react_trace_analyzer.py` mechanically detects seven canonical failure modes in any trace that follows the schema above. Each detection maps to a root cause and a concrete mitigation:

| ID | Detection | Severity | Failure Mode | Root Cause | Mitigation |
|----|-----------|----------|--------------|------------|------------|
| D1 | Same tool+input appears >= 3 times | CRITICAL | Action loop | Agent does not track its own action history; retries identical calls hoping for different results | Add an `oscillation` exit condition plus a dedup rule: "never repeat an identical call" (Tool-Use Hygiene rule 3) |
| D2 | Alternating A-B-A-B actions in a window of 4 | HIGH | Oscillation | Two tools each undo or invalidate the other's result; no memory of the alternation | Detect the A-B-A-B signature in the Thought; force a third option or escalate (`oscillation` exit condition) |
| D3 | Consecutive `error` statuses >= `budget.max_errors` (default 3) | HIGH | Error cascade | Agent keeps acting on a broken assumption instead of diagnosing | Add an error-mitigation loop: after 2 consecutive errors, the next step must diagnose, not retry; at `max_errors`, escalate |
| D4 | Step missing `thought` or `observation` | MEDIUM | ReAct contract violation | Prompt does not enforce the step template, or output parsing drops fields | Enforce the step template (Prompt Blocks below); reject/regenerate any step missing a field |
| D5 | `len(steps)` >= `budget.max_steps` | CRITICAL | Budget overrun | No `max_iterations` counter, or the counter is not checked before each step | Check the `budget` exit condition at the top of every iteration; hard-stop and report at the limit |
| D6 | `final_answer` null/absent while last step status is `ok` | MEDIUM | No convergence | Agent has no definition of "done", so it stops without concluding | Define a `success_predicate` exit condition and require an explicit final answer when it is met |
| D7 | Identical thought text appears >= 3 times | MEDIUM | Reasoning loop | Agent re-derives the same conclusion each cycle with no memory of having reasoned it before | Add reflection with a rubric (Reflexion pattern): each repeated thought must state what is different this time, or the loop exits via `no_progress` |

**Health scoring:** the analyzer starts at 100 and subtracts 30 per CRITICAL, 15 per HIGH, and 5 per MEDIUM finding (floor 0). Verdicts: **>= 90 HEALTHY**, **60-89 DEGRADED**, **< 60 RUNAWAY**. A RUNAWAY verdict on any production trace should trigger the agent's `escalation_trigger` path and a review of its loop-safety controls with `loop_auditor.py`.

---

## Instrumenting Traces

Detection only works if traces exist. Every production ReAct agent should log each step in the canonical JSON schema — one `steps[]` entry per cycle, appended as it happens, with `budget` recorded up front and `final_answer` written at exit. Log the observation verbatim (truncate at a fixed byte limit if needed, but note the truncation); paraphrased observations defeat D1/D2 detection because identical results no longer compare equal.

Audit a trace:

```text
python scripts/react_trace_analyzer.py trace.json --json
```

Human-readable output is the default; `--json` emits machine-readable results for CI gates and dashboards. Exit code 0 on success, 1 on error. A useful production pattern: run the analyzer on every completed trace in CI and fail the pipeline (or page the `escalation.contact`) on any RUNAWAY verdict. A sample well-formed trace ships in `assets/sample_react_trace.json`.

Minimal logging checklist:

- `agent` and `task` filled in at trace start.
- `budget.max_steps` and `budget.max_errors` set explicitly — never defaulted silently.
- Every step numbered sequentially with all four fields (`thought`, `action`, `observation`, `status`).
- `status` set to `error` on any tool failure, timeout, or invalid result — not just exceptions.
- `final_answer` set to the actual conclusion, or left `null` if the agent exited without converging (so D6 can catch it).

---

## Prompt Blocks

Ready-to-paste sections that enforce the contract in any agent spec. Use them together; each one closes a different detection class.

**Step template (closes D4):**

```text
Every step MUST use exactly this format, all three fields required:
Thought: <state assessment, gap, chosen tool, rationale>
Action: <tool>(<input>)
Observation: <verbatim result>
A step missing any field is invalid — regenerate it before proceeding.
```

**Exit-condition declaration (closes D1, D5, D6, D7):**

```text
Exit conditions (check ALL before every step, in this order):
1. success_predicate: <task-specific test for "done">. If met, emit the
   final answer and stop.
2. max_iterations: stop after <N> steps.
3. no_progress: stop if the last 2 steps produced no new information.
4. oscillation: stop if actions repeat (identical call, or A-B-A-B).
5. budget: stop when <time/token/tool-call> limit is reached.
6. escalation_trigger: on any irreversible ambiguity or after any other
   exit fires without success, stop and hand off to a human with the
   full trace attached.
```

**Observation-first rule (closes D3, hallucinated state):**

```text
Before writing any Thought, restate in one line what the LAST
Observation actually said — including whether it was an error.
Never assume an action succeeded. If the restated observation
contradicts your expectation, your next action must diagnose the
mismatch, not proceed with the original plan.
```

---

## Integration with the 5-Phase Protocol

ReAct is an execution engine, not a governance model. In the defensive HITL architecture (see `hitl_defensive_architectures.md`), **ReAct runs INSIDE Phase 4 — IMPLEMENTATION**. Phases 1-3 bound what actions are legal before a single tool call with side effects is made:

- **Phase 1 — DISCOVERY (read-only):** a ReAct loop may run here, but with a read-only tool allowlist. Any write Action is a contract violation regardless of how sound the Thought is. No writes allowed.
- **Phase 2 — MANIFEST:** the output of a Plan-and-Execute planning phase *is* the change manifest — files to create/modify, risks, rollback plan. No execution happens here.
- **Phase 3 — HUMAN GATE:** hard stop. A human approves, edits, or rejects the manifest. No implementation without approval. No ReAct loop can talk its way through this gate; it is enforced outside the model.
- **Phase 4 — IMPLEMENTATION:** the full ReAct loop executes, bounded strictly by the approved manifest. The manifest defines the `success_predicate` and the allowed action scope; the exit-condition declaration bounds the loop. **Any deviation returns to Phase 2** — a plan-deviation detection (Plan-and-Execute step 3) is precisely the trigger that sends the agent back to produce a revised manifest for re-approval.
- **Phase 5 — SELF-REVIEW & HANDOFF:** the agent audits its own diff against the manifest, runs verification, and produces a handoff report. Running `react_trace_analyzer.py` on the Phase 4 trace belongs in this phase: a HEALTHY verdict is evidence for the handoff report; a DEGRADED or RUNAWAY verdict is a finding the report must disclose.

The division of labor is deliberate: exit conditions keep the loop from running away *within* its authority; the 5-Phase Protocol keeps the loop's authority itself bounded. An agent with perfect ReAct hygiene but no phase gates can still efficiently do the wrong thing — both layers are required for production autonomy.

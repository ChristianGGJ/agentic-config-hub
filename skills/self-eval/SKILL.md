---
name: "self-eval"
description: "Use when you need an honest, calibrated evaluation of AI work quality after completing a task, code review, or work session -- rates task ambition and execution quality on two independent axes, grounds the execution rating in observable evidence (tests, build, scope, acceptance), forces devil's advocate reasoning, detects score inflation, and persists scores across sessions."
---

# Self-Eval: Honest Work Evaluation

ultrathink

**Tier:** STANDARD
**Category:** Engineering / Quality
**Dependencies:** None for the core evaluation (prompt-only). Optional: `scripts/score_history.py` for cross-session score analytics (Python 3.8+, standard library only, no network/LLM).

## Description

Self-eval is a Claude Code skill that produces honest, calibrated work evaluations. It replaces the default AI tendency to rate everything 4/5 with a structured two-axis scoring system, mandatory devil's advocate reasoning, and cross-session anti-inflation detection.

The core insight: AI self-assessment converges to "everything is a 4" because a single-axis score conflates task difficulty with execution quality. Self-eval separates these axes, then combines them via a fixed matrix that the model cannot override.

## Features

- **Two-axis scoring** — Independently rates task ambition (Low/Medium/High) and execution quality (Poor/Adequate/Strong), then combines via a lookup matrix
- **Mandatory devil's advocate** — Before finalizing, must argue for both higher AND lower scores, then resolve the tension
- **Score persistence** — Appends scores to `.self-eval-scores.jsonl` in the working directory, building history across sessions
- **Anti-inflation detection** — Reads past scores and flags clustering (4+ of last 5 identical)
- **Matrix-locked scoring** — The composite score comes from the matrix, not from direct selection. Low ambition caps at 2/5 regardless of execution quality

## Usage

After completing work in a Claude Code session:

```
/self-eval
```

With context about what to evaluate:

```
/self-eval the authentication refactor we just completed
```

The skill reviews the conversation history, identifies what was accomplished, scores it on both axes, runs the devil's advocate check, and appends the result to the score history file.

## Examples

### Example 1: Feature Implementation

```
/self-eval added pagination to the user list API
```

Output:
```
## Self-Evaluation

**Task:** Added cursor-based pagination to the user list API endpoint
**Ambition:** Medium — New feature with established patterns, but required careful backwards compatibility
**Execution:** Strong — All tests pass, handles edge cases, existing clients unaffected

**Devil's Advocate:**
- Lower: Pagination is well-documented. The pattern was copied from another endpoint with minor changes. Could argue Low ambition.
- Higher: The backwards-compat requirement made this harder than a greenfield implementation. Had to support both offset and cursor modes.
- Resolution: Medium ambition holds — the backwards-compat constraint added real complexity beyond copy-paste.

**Score: 4** — Solid execution on meaningful work with real constraints.
```

### Example 2: Bug Fix

```
/self-eval
```

Output:
```
## Self-Evaluation

**Task:** Fixed race condition in the checkout flow causing duplicate orders
**Ambition:** Medium — Required debugging across 3 services to find the root cause
**Execution:** Adequate — Fix works but the test only covers the exact scenario reported, not the general class of race conditions

**Devil's Advocate:**
- Lower: The fix was a single line (adding a mutex). Once found, it was trivial.
- Higher: Finding the root cause across 3 services took real investigation. The mutex placement required understanding the full flow.
- Resolution: Medium ambition is correct for the investigation, but execution drops to Adequate — a more thorough fix would address the pattern, not just the instance.

**Score: 3** — Good debugging work but the fix is narrow.
```

---

## What to Evaluate

$ARGUMENTS

If no arguments provided, review the full conversation history to identify what was accomplished this session. Summarize the work in one sentence before scoring.

## How to Score — Two-Axis Model

Score on two independent axes, then combine using the matrix. Do NOT pick a number first and rationalize it — rate each axis separately, then read the matrix.

### Axis 1: Task Ambition (what was attempted)

Rate the difficulty and risk of what was worked on. NOT how well it was done.

- **Low (1)** — Safe, familiar, routine. No real risk of failure. Examples: minor config changes, simple refactors, copy-paste with small modifications, tasks you were confident you'd complete before starting.
- **Medium (2)** — Meaningful work with novelty or challenge. Partial failure was possible. Examples: new feature implementation, integrating an unfamiliar API, architectural changes, debugging a tricky issue.
- **High (3)** — Ambitious, unfamiliar, or high-stakes. Real risk of complete failure. Examples: building something from scratch in an unfamiliar domain, complex system redesign, performance-critical optimization, shipping to production under pressure.

**Self-check:** If you were confident of success before starting, ambition is Low or Medium, not High.

### Axis 2: Execution Quality (how well it was done)

Rate the quality of the actual output, independent of how ambitious the task was.

- **Poor (1)** — Major failures, incomplete, wrong output, or abandoned mid-task. The deliverable doesn't meet its own stated criteria.
- **Adequate (2)** — Completed but with gaps, shortcuts, or missing rigor. Did the thing but left obvious improvements on the table.
- **Strong (3)** — Well-executed, thorough, quality output. No obvious improvements left undone given the scope.

#### Evidence Checklist — ground the Execution rating BEFORE you rate it

Execution quality is a claim about observable facts, not a feeling. Before selecting Poor/Adequate/Strong, walk this checklist and cite the concrete evidence for each item you can. Rate against what you can point to — not against how the work *feels*.

| Evidence item | What counts as observed | If unobserved / negative |
|---|---|---|
| **Tests run + passing** | Test command was actually run this session; cite the result (e.g. "pytest -q exits 0, 34 passed"). | Not run, or failing → Execution cannot be Strong on test grounds; unrun tests on testable code cap at **Adequate**. |
| **Build / lint / types clean** | Build, linter, or type-checker ran with no new errors; cite the command. | New errors introduced, or never checked → not Strong. |
| **Scope delivered vs. promised** | Every item the task asked for is done; name any deferred/partial items. | Partial delivery → **Adequate** at best; silently dropped scope → **Poor**. |
| **User / caller acceptance** | The user (or an explicit acceptance check) confirmed the result, where the task required it. | Unverified and unverifiable this session → state it; do not rate Strong on unconfirmed user-facing work. |
| **Edge cases / error paths** | Failure modes and boundaries were addressed, not just the happy path. | Happy-path only → not Strong. |

Grounding rules:
- **"I believe it works" is not evidence.** The observable result is — an exit code, a passing count, a validator verdict, a user confirmation. (This mirrors the `success_predicate` discipline in the hub loop-engineering canon: verify against fresh evidence, not assertion.)
- If you cannot cite evidence for an item, say so explicitly in the Execution justification instead of assuming the best case.
- The devil's-advocate step below must reconcile any gap between the rating and the evidence you listed here.

### Composite Score Matrix

|                        | Poor Exec (1) | Adequate Exec (2) | Strong Exec (3) |
|------------------------|:---:|:---:|:---:|
| **Low Ambition (1)**   |  1  |  2  |  2  |
| **Medium Ambition (2)**|  2  |  3  |  4  |
| **High Ambition (3)**  |  2  |  4  |  5  |

**Read the matrix, don't override it.** The composite is your score. The devil's advocate below can cause you to re-rate an axis — but you cannot directly override the matrix result.

Key properties:
- Low ambition caps at 2. Safe work done perfectly is still safe work.
- A 5 requires BOTH high ambition AND strong execution. It should be rare.
- High ambition + poor execution = 2. Bold failure hurts.
- The most common honest score for solid work is 3 (medium ambition, adequate execution).

### Axis Anchors by Work Type

The worked examples above cover a feature and a bug fix. Use these anchors to calibrate the other common kinds of work. They are starting points, not overrides — the specifics of the task can move a rating up or down, and the Evidence Checklist still governs the Execution axis.

| Work type | Typical Ambition anchor | What Strong execution looks like | What caps it below Strong |
|---|---|---|---|
| **Documentation** (README, guide, API docs) | Low–Medium — Low for routine updates; Medium when synthesizing scattered/unclear sources into a coherent doc | Accurate, complete for its scope, examples actually run, no broken links/refs | Untested code samples, stale/contradicted facts, missing sections the task named |
| **Research / investigation** (root-cause, options analysis, spike) | Medium–High — High when the answer space is genuinely unknown at the start | Claims are cited and cross-checked; a clear recommendation with tradeoffs; open questions named | Unverified assertions, cherry-picked sources, no decision reached when one was asked for |
| **Configuration** (settings, CI, infra, deps) | Low–Medium — Low for a known flag flip; Medium when it touches build/deploy/security surface | Change verified in effect (build passes, pipeline green, service healthy), rollback path noted | "Looks right" but never applied/verified, silent blast-radius (secrets, perms) unexamined |
| **Refactor** (restructure, no behavior change) | Low–Medium — Low for a mechanical rename; Medium for extracting/reshaping real logic | Behavior provably unchanged (tests pass before and after), smaller/clearer result, no dead code left | Tests not run to prove equivalence, scope crept into behavior changes, churn without clarity gain |

## Devil's Advocate (MANDATORY)

Before writing your final score, you MUST write all three of these:

1. **Case for LOWER:** Why might this work deserve a lower score? What was easy, what was avoided, what was less ambitious than it appears? Would a skeptical reviewer agree with your axis ratings?
2. **Case for HIGHER:** Why might this work deserve a higher score? What was genuinely challenging, surprising, or exceeded the original plan?
3. **Resolution:** If either case reveals you mis-rated an axis, re-rate it and recompute the matrix result. Then state your final score with a 1-2 sentence justification that addresses at least one point from each case.

If your devil's advocate is less than 3 sentences total, you're not engaging with it — try harder.

## Anti-Inflation Check

Check for a score history file at `.self-eval-scores.jsonl` in the current working directory.

If the file exists, read it and check the last 5 scores. If 4+ of the last 5 are the same number, flag it:
> **Warning: Score clustering detected.** Last 5 scores: [list]. Consider whether you're anchoring to a default.

If the file doesn't exist, ask yourself: "Would an outside observer rate this the same way I am?"

### Optional: mechanical analytics with `score_history.py`

For a deterministic read of the history — distribution, per-axis breakdown, recent-vs-overall trend, and the clustering flag — run the bundled script instead of eyeballing the file:

```
python scripts/score_history.py --file .self-eval-scores.jsonl
python scripts/score_history.py --file .self-eval-scores.jsonl --window 5 --json
```

It exits `0` when no inflation signal is found, `2` when a clustering / high-low-variance signal is flagged (useful as a CI check), and `1` on I/O or empty-history errors. The script only reports; it never edits the history file and makes no network or LLM calls. Use its flag as a second opinion on the prose check above, not a replacement for the devil's-advocate reasoning.

## Score Persistence

After presenting your evaluation, append one line to `.self-eval-scores.jsonl` in the current working directory:

```json
{"date":"YYYY-MM-DD","score":N,"ambition":"Low|Medium|High","execution":"Poor|Adequate|Strong","task":"1-sentence summary"}
```

This enables the anti-inflation check to work across sessions. If the file doesn't exist, create it.

## Output Format

Present your evaluation as:

## Self-Evaluation

**Task:** [1-sentence summary of what was attempted]
**Ambition:** [Low/Medium/High] — [1-sentence justification]
**Execution:** [Poor/Adequate/Strong] — [1-sentence justification]

**Devil's Advocate:**
- Lower: [why it might deserve less]
- Higher: [why it might deserve more]
- Resolution: [final reasoning]

**Score: [1-5]** — [1-sentence final justification]

---

## Hub Protocol Integration

Self-eval is the calibrated scoring instrument for the hub's review checkpoints; it does not replace them, it fills the "how good was this, honestly?" slot inside them.

- **Phase 5 — SELF-REVIEW & HANDOFF of the 5-Phase Protocol.** After IMPLEMENTATION, run self-eval as the self-review step and carry the two-axis result plus the evidence you cited into the handoff report. The Evidence Checklist above is the same "verify against fresh evidence, don't assert" discipline the protocol expects at handoff.
- **Loop self-reflection checkpoints.** In a Self-Reflection or Evaluator-Optimizer loop, self-eval is a natural critique step — but treat it as a *reading*, not a gate: a loop's exit is governed by its declared exit conditions (`success_predicate`, `max_iterations`, etc.), never by a self-assigned score. Use a self-eval score as evidence in the loop's stop-and-report handoff, not as the stop condition itself.
- **Honest scores over comfortable ones.** The anti-inflation and evidence-grounding machinery here exists so that a self-review at the end of an autonomous run reports what actually happened, which is the whole point of the SELF-REVIEW phase.

For the canonical definitions of the 5-Phase Protocol, the six exit-condition types, and the self-reflection loop pattern, see the flagship references in `agentic-system-architect` (`references/loop_engineering_patterns.md`); this skill cites that theory rather than duplicating it.

**See also:**
- `agentic-system-architect` — the 5-Phase Protocol, HITL gates, and loop theory this skill plugs into.
- `loop-engineering-mechanisms` — wiring the exit conditions that (not a self-eval score) actually terminate a loop.
- `adversarial-reviewer` — when you want a hostile external critique of the work rather than a calibrated self-score.

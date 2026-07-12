---
title: "Agent Self-Optimization — Prompts Optimization & Quality Rubrics"
description: "Use when automatically optimizing an agent's prompts or policy from an error, audit, or eval signal under a mandatory human gate: selecting a. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Agent Self-Optimization

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-check: Prompts & Quality</span>
<span class="meta-badge">:material-identifier: `agent-self-optimization`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agent-self-optimization/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install prompts-quality</code>
</div>


You optimize agent prompts and policies from a measured signal, then stop and hand the diff to a human. The signal comes from a deterministic audit or an eval; the optimizer proposes a candidate; a human gate accepts or rejects the change before it is committed. This is the metric-driven, human-gated **rewrite** half of the lifecycle — the piece none of the sibling skills own.

The governing rule of this skill is one sentence: **an optimization loop may propose edits to object-level prompts only; it may NEVER autonomously rewrite its own guardrails, boundaries, rubric, exit conditions, or promotion predicate.** Everything below serves that rule.

## Overview

Two tracks run in parallel throughout this skill, and every technique is stated in both:

- **FRAMEWORK TRACK** — how runtime frameworks (DSPy, TextGrad, and the OPRO/APE/PromptBreeder research algorithms) optimize prompts from a metric at dev time, with real APIs. Cataloged in `references/prompt_optimization_methods.md`.
- **STATIC TRACK** — how the same technique maps onto THIS hub: a git-versioned prompt-config library with no runtime, no vector DB, and no model calls in its shipped stdlib scripts. Here the "optimizer" is a git-versioned edit; the "reward" is a deterministic audit score or an offline eval metric; the "step" is a human-gated commit.

A self-optimizing agent is dangerous exactly where it is powerful: the same machinery that improves a prompt can, unbounded, evolve the rules that judge it (PromptBreeder's self-referential hyper-mutation, arXiv:2309.16797). The hub's answer is not "trust the optimizer" — it is the HUMAN GATE plus a frozen object/meta boundary.

**Before you optimize, you need four inputs.** If any is missing, stop and get it first (each has an owner):
- A **target config** — the object-level `.md` whose instructions/demos will be rewritten.
- A **metric** — a deterministic composite (audit score + eval pass-rate + trace penalty), defined by agentic-evals-benchmarking. Without it there is nothing to optimize against.
- A **held-out eval set** — cases the optimizer never sees, so improvement is real, not memorized (agentic-evals-benchmarking).
- **Captured failures** — the signal that motivates the rewrite (audit failures, trace hits, eval regressions, or a correction ledger). No signal means a hand edit, not an optimization.

The failure signal can come from several instruments, each owned elsewhere; this skill only consumes them: a `loop_auditor.py` verdict below the HARDENED band (agentic-system-architect), a failing eval slice (`eval_gate.py`, agentic-evals-benchmarking), a ReAct trace detection (react_trace_analyzer D1-D7, agentic-system-architect), or a recurring correction (`scripts/correction_ledger.py`). Whatever the source, it must localize to a specific object-level prompt section for the rewrite to be a targeted "gradient" rather than a blind rewrite.

## When to Use / When NOT

Use this skill when you have a **measured failure signal** (a `loop_auditor.py` verdict, an eval regression, a recurring correction) and want to turn it into a disciplined prompt rewrite rather than an ad-hoc edit.

Route elsewhere — this skill delegates, it does not re-teach:

| You need... | Go to | This skill's relationship |
|---|---|---|
| Define the metric, golden set, held-out split, overfitting guards | **agentic-evals-benchmarking** | Consumes its metric/`eval_gate.py` as the reward signal; never redefines them |
| Prompt registry, versioning, promotion gate, one-command rollback | **prompt-governance** | Emits a candidate revision *into* its registry; it owns status flips and archive |
| An autonomous propose-eval-keep/discard experiment harness over one file | **autoresearch-agent** | That IS the runnable static optimizer loop; this skill supplies the method selection |
| Loop-safety counters wired into Python (the six exit conditions) | **loop-engineering-mechanisms** | Cites the exit conditions to bound the rewrite loop; does not reimplement counters |
| Loop theory (Evaluator-Optimizer pattern, exit-condition taxonomy) | **agentic-system-architect** (`references/loop_engineering_patterns.md`) | Cites Loop Pattern #2; the governed rewrite is a named instance of it |
| Write or improve a single prompt by hand | **senior-prompt-engineer** | Hand authoring is the alternative when there is no measurable signal to optimize against |
| Memory storage schemas, embeddings, chunking | **rag-architect** / **hybrid-rag-memory** | Out of scope here entirely |

Do NOT use an optimizer when a **hand-written fix by senior-prompt-engineer is cheaper and clearer** — automatic optimization earns its cost only when you have a metric, a held-out set, and enough failure cases that manual iteration is slow. One failing case is a hand edit, not a compile.

## Optimizer Selection Ladder

Climb only as high as the signal justifies. Each rung is more powerful and more expensive; higher rungs overfit faster and need stronger held-out discipline (owned by agentic-evals-benchmarking).

| Rung | Use when | Framework-track method | Static-track action |
|---|---|---|---|
| 0. Rules suffice | The fix is a single deterministic rule ("always quote acceptance criteria") | none — it is a constraint, not an optimization | Add a line to the config or a `.claude/rules/` entry; no loop |
| 1. Few-shot bootstrapping | The instruction is fine but the model needs examples of correct behavior; you have labeled cases | `dspy.BootstrapFewShot`, `dspy.LabeledFewShot`, `dspy.KNNFewShot` | Curate demos that each pass the metric, embed a capped Pareto-covering set in the `.md` |
| 2. Instruction optimization | Wording is the problem; behavior is inconsistent across paraphrases | `dspy.COPRO`, `dspy.MIPROv2` (instruction proposer), OPRO, APE, TextGrad | Human-supervised dev session proposes a revised instruction block; audit + eval it |
| 3. Full compile | Multi-module program, joint instruction+demo search, or reflective evolution over traces | `dspy.MIPROv2` (joint), `dspy.GEPA` (reflective Pareto) | Same as rung 2 but across multiple config files; retain specialist versions on the frontier |

Reward-hacking rises with the rung: the higher you climb, the more the optimizer can satisfy the letter of the metric while missing its intent (Goodhart; arXiv:2410.06491). Above rung 1, a held-out eval slice the optimizer never saw is mandatory — see agentic-evals-benchmarking for rotating held-out subsets.

## The Two-Track Translation Table

State this mapping once; every section below reuses it. It defines the governed rewrite as a static instance of DSPy-style optimization.

| Optimizer concept (framework track) | Static-track equivalent (this hub) | Owner of that piece |
|---|---|---|
| `parameters` being optimized | Object-level prompt text + embedded few-shot demos inside a versioned `.md` | this skill |
| `optimizer.compile()` step | A git-versioned edit proposed in a dev session, then a human-gated commit | this skill |
| `trainset` / `valset` | Golden suite + captured failures (audit failures, D1-D7 trace hits, eval regressions), split into a held-out valset | agentic-evals-benchmarking |
| `metric(gold, pred)` | Deterministic composite: `loop_auditor.py` 100-pt score + eval pass-rate + trace-penalty; NEVER a model call in a shipped script | agentic-evals-benchmarking |
| Bootstrapped demos | Curated few-shot examples committed to the registry | prompt-governance |
| Archive / Pareto frontier | Git history + the prompt registry (`status: production` / `archived`) | prompt-governance |
| The optimizer role (proposer) | A human-supervised Claude dev session under the 5-Phase Protocol | this skill |
| The accept step | The Phase-3 HUMAN GATE approving the diff | agentic-system-architect (protocol) |

The load-bearing divergence from DSPy: `compile()` auto-commits the optimized program. **The hub forbids that.** The static loop splits `compile()` into (a) a *propose* step that emits a candidate `.md` + an eval-delta report, and (b) a mandatory HUMAN GATE + promotion predicate before the registry status flips candidate to production.

## The Governed Rewrite Loop

This is an explicit instance of the **Evaluator-Optimizer Loop** (Loop Pattern #2 in `skills/agentic-system-architect/references/loop_engineering_patterns.md`). Do not duplicate that reference's theory; the loop below is its concrete configuration for prompt optimization.

```text
Phase 1-2 DISCOVERY + MANIFEST
  Gather the failure signal (audit verdict, eval regression, correction ledger).
  Choose a rung on the ladder. Draft candidate as a MANIFEST line.
        |
        v
  PROPOSE (optimizer role = supervised dev session)
  Rewrite ONLY the object-level prompt section the signal localizes.
        |
        v
  AUDIT + REGRESSION EVAL (evaluator role = deterministic tools)
  loop_auditor.py score AND eval on a HELD-OUT set (owned by agentic-evals).
        |
        v
  score < threshold AND cycle < 3 ?  --yes--> REMEDIATE (back to PROPOSE)
        | no
        v
  Phase 3 HUMAN GATE  (MANDATORY, never skipped)
  A human reviews the diff + eval-delta and approves / edits / rejects.
        |
        v
  PROMOTE only if predicate holds:
    >= 90 HARDENED (loop_auditor) AND Pareto-non-regression
    (ties-or-dominates prior on EVERY eval slice; never trades one slice for another)
        |
        v
  Phase 5 SELF-REVIEW & HANDOFF  (writes the regression report; registry flip owned by prompt-governance)
```

Hard rules that make this loop safe:

1. **The HUMAN GATE is non-negotiable.** No promotion path skips Phase 3, regardless of how high the audit score is. Gate strictness scales with irreversibility, never with the optimizer's track record.
2. **Object-level only.** The loop may edit an agent/skill role prompt. It may NEVER edit the meta-level: the `loop_auditor.py` rubric, the six exit-condition definitions, the H1-H5 handoff contracts, the promotion predicate, or `context/boundaries.md`. Changing those is a separate, explicitly-flagged human governance action, never a loop step. This is the PromptBreeder guardrail (`references/prompt_optimization_methods.md`).
3. **Frozen rubric per run.** Freeze the metric before the first proposal or the score never converges (the moving-target-rubric failure). The rubric is owned by agentic-evals-benchmarking; this loop consumes it read-only.
4. **Fresh evidence each cycle.** Clear prior-version findings before scoring a new candidate, or the "gradient" points at already-fixed sections (the TextGrad `zero_grad()` discipline).
5. **Every accepted rewrite is auditable.** Phase 5 writes a regression report — the score delta, the slices each change covered, and the exit condition that ended the loop — so a later reviewer (or a rollback) can see exactly what changed and why. An optimization with no recorded evidence trail did not happen under this skill.

The score-plus-itemized-feedback contract passed back to the optimizer is the hub's H4 Audit Verdict; the accept step at the gate is the static equivalent of a LangGraph `interrupt()` resolving with a human decision (see `references/corrective_feedback_loops.md`).

## Hub Canon Integration

**Bounding the loop with the six exit conditions.** The rewrite loop is a bounded control system, guarded by the canonical taxonomy (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger` — defined in agentic-system-architect, wired in loop-engineering-mechanisms):

- `success_predicate`: `loop_auditor.py >= 90` AND Pareto-non-regression on the held-out set.
- `max_iterations`: 3 remediation cycles (reuse the existing producer -> auditor -> remediate contract).
- `no_progress`: audit score flat or declining over a window of 2 cycles = stop; more polishing will not help.
- `oscillation`: a rewrite that re-breaks a check a prior cycle fixed (window 4) = stop and escalate.
- `budget`: cap dev-session tool calls / eval runs per candidate.
- `escalation_trigger`: any of the above firing twice, or a proposed edit touching meta-level config, routes to a human immediately.

**Every generated or rewritten agent must remain >= 90 HARDENED.** An optimization that raises one metric but drops the config below the HARDENED band is a regression and must be rejected at the gate.

**Where the loop actually runs.** This skill supplies the method selection and the safety boundary; the runnable static instance of the propose-eval-keep/discard loop over one git-versioned file is **autoresearch-agent** (it edits a target file, runs an N-repeat evaluation, git-commits statistically real improvements, git-resets the rest, under declared exit conditions). Use it as the harness. This skill decides *which* optimizer method and *whether* an edit may touch a given section; autoresearch-agent executes the keep/discard mechanics. The two compose; neither re-teaches the other.

**Reward-hacking risk (the core caveat).** A deterministic reward is gameable: `loop_auditor.py` checks for the *presence* of control-plane keywords, so an optimizer can pass a loop-safety check by writing the word "oscillation" without a real guard (the presence-vs-substance gap). RLAIF-style AI feedback adds sycophancy and judge-bias on top (arXiv:2410.06491). Mitigations, all delegated:
- Held-out and rotating eval subsets so the optimizer cannot overfit a frozen set (agentic-evals-benchmarking).
- Judge-integrity / score-inflation detection on any AI corrector (self-eval).
- The HUMAN GATE as the final, ungameable check: a human reads the diff, not just the score.

## Proactive Triggers

Surface these without being asked:

- **A prompt edit is proposed with no held-out eval** — you are optimizing against nothing measurable; the change is a bet, not an improvement. Route to agentic-evals-benchmarking to define the metric first.
- **An optimizer or dev session is about to touch a rubric, exit-condition definition, promotion predicate, or `boundaries.md`** — that is meta-level self-modification. Stop and flag it as a separate human governance action.
- **The audit score rises but a specific eval slice drops** — a slice trade is a silent regression; reject at the gate. Promotion requires ties-or-dominates on every slice.
- **The same failure recurs across sessions with no ledger entry** — the correction is being re-learned from scratch. Record it (`scripts/correction_ledger.py`) so it can graduate into a rule.
- **Someone proposes auto-promoting on score alone** — no promotion path skips the HUMAN GATE, regardless of score. Say so.
- **A single failing case is being fed to a full compile** — the optimizer's cost and overfit risk are unjustified; a hand edit by senior-prompt-engineer is cheaper.
- **Embedded few-shot demos keep growing across rewrites** — prompt bloat and token debt; cap the set and keep only demos that each cover a distinct eval slice (a coverage/Pareto set).

## Output Artifacts

| When you ask for... | You get... |
|---|---|
| Optimizer selection | A rung on the selection ladder + the matching framework method and static action |
| A governed rewrite plan | The propose -> audit -> gate -> promote loop configured for your config, with exit conditions and the promotion predicate |
| A correction record | A typed ledger entry (`scripts/correction_ledger.py add`) with a trust tag |
| A recurring-correction report | Graduation candidates with provenance-stamped `boundaries.md` line suggestions (`scripts/correction_ledger.py report`) |
| Reward-hacking review | A list of where the metric is gameable and the mitigations (held-out sets, judge integrity, the human gate) mapped to their owners |

## Communication

All output follows the hub's structured standard:
- **Bottom line first** — the recommended rung or the gate verdict before the rationale.
- **What + Why + How** — every recommendation names the signal, the method, and the static action.
- **Confidence tagging** — verified / medium / assumed; framework APIs carry a version assumption and a "verify against current docs" flag where uncertain.

## References

- `references/prompt_optimization_methods.md` — FRAMEWORK TRACK catalog of real optimizer APIs (DSPy 3.x: Signature/Module/BootstrapFewShot/MIPROv2/GEPA/COPRO, `compile()`, `Evaluate`; OPRO, APE, TextGrad, PromptBreeder as algorithms), each with mechanism, driving signal, and overfitting guardrails; then the STATIC TRACK governed-rewrite mapping.
- `references/corrective_feedback_loops.md` — RLAIF vs RLHF at inference time (in-context, no weight updates), state-level correction via LangGraph `interrupt()`/`Command(resume=)`, the Correction Ledger schema, `boundaries.md` provenance fields, and the reward-hacking caveat.
- `scripts/correction_ledger.py` — deterministic, stdlib-only ledger tool: records corrections and flags recurring ones that should graduate (under a human gate) into a `boundaries.md` prohibition.

Framework APIs in the references carry a version assumption (e.g. DSPy 3.x, 2025) and a "verify against current docs" flag where the exact signature moves between releases. Treat those as starting points to confirm, never as invented members to rely on blindly.

## Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|---|---|---|
| Auto-committing the optimized prompt (DSPy `compile()` default) | Removes the human gate; a reward-hacked prompt ships silently | Split into propose + gate + promote; never flip registry status without Phase 3 |
| Letting the loop edit its own rubric / exit conditions / boundaries | Self-referential meta-mutation — the optimizer evolves the judge (PromptBreeder) | Object-level edits only; meta-level is a separate flagged human action |
| Optimizing against the training set only | Overfits the metric; Goodhart reward-hacking | Held-out valset + Pareto-non-regression, owned by agentic-evals-benchmarking |
| Trading one eval slice for another to raise the average | Silent regression on a real user segment | Promotion predicate requires ties-or-dominates on EVERY slice |
| Climbing to full compile for one failing case | Cost and overfit with no payoff | Use the selection ladder; one case is a hand edit (senior-prompt-engineer) |
| Treating the auditor's presence-check as substance | Passes the word "oscillation" without a real guard | Pair the deterministic score with a human diff review at the gate |
| Calling a model inside a shipped stdlib script to score a candidate | Breaks portability and the hub's no-model-call rule; scoring becomes non-reproducible | Keep model-execution scoring in the eval harness / CI; scripts use deterministic proxies only |
| Promoting a rewrite with no recorded evidence trail | Nothing to audit or roll back to; the change is unaccountable | Phase 5 regression report is mandatory — score delta, slices covered, exit condition |
| Rewriting the whole config when one section failed | Broad blast radius, more regressions, harder review | Localize the "gradient" to the section the signal pins; edit only that block |

## Related Skills

- **agentic-evals-benchmarking**: Owns the metric, golden set, held-out split, and overfitting guards this skill's reward signal depends on. Use it to define what "better" means before optimizing.
- **prompt-governance**: Owns the registry, versioning, promotion gate, and rollback. This skill emits candidates into it; it never manages versions itself.
- **autoresearch-agent**: The runnable static optimizer loop (propose-eval-keep/discard over one git-versioned file). Use it as the harness; this skill supplies optimizer-method selection and the object/meta safety boundary.
- **loop-engineering-mechanisms**: Wires the six exit conditions into Python. Cite it to bound the rewrite loop; do not reimplement counters here.
- **agentic-system-architect**: Owns loop theory (`references/loop_engineering_patterns.md`) and the 5-Phase Protocol / HUMAN GATE this loop is an instance of.
- **senior-prompt-engineer**: Hand-writes and improves individual prompts. The alternative to this skill when there is no measurable signal to optimize against.
- **self-eval**: Judge-integrity and score-inflation detection for any AI corrector in the loop.
- **self-improving-agent**: Promotes proven positive patterns into CLAUDE.md/rules; this skill's correction ledger is the negative-reward counterpart that nominates prohibitions.

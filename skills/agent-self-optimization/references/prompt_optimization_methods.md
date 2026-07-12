# Prompt Optimization Methods

FRAMEWORK-TRACK catalog of real automatic prompt-optimization methods, followed by the STATIC-TRACK translation onto this hub's governed rewrite. Every framework construct below is a real, published API or algorithm. Version assumptions are stated per entry; anything marked **verify against current docs** moves between releases and must be re-checked before you rely on the exact signature. Do NOT invent members.

The through-line: all of these turn a **signal** (a metric score, an execution trace, a natural-language critique) into a **rewrite** of a prompt's instructions and/or its few-shot demonstrations. They differ in what the signal is and how the rewrite is searched. The hub keeps the method and discards the auto-commit — see the static section.

## Method comparison at a glance

Read this table to pick a method; read the per-method sections for the exact API. "What it rewrites" and "driving signal" are the two axes that matter for the static translation.

| Method | What it rewrites | Driving signal | Search strategy | Package status (2025/2026) | Ladder rung |
|---|---|---|---|---|---|
| DSPy BootstrapFewShot | Few-shot demos | Metric pass/fail per demo | Teacher bootstrapping | Maintained (DSPy 3.x) | 1 |
| DSPy COPRO | Instructions | Metric score | Coordinate ascent | Maintained | 2 |
| DSPy MIPROv2 | Instructions + demos (joint) | Metric on minibatched valset | Bayesian optimization | Maintained | 2-3 |
| DSPy GEPA | Instructions (+ frontier of variants) | Score + textual feedback over traces | Reflective genetic-Pareto | Maintained | 3 |
| OPRO | Instructions | (instruction, score) trajectory | LLM-as-optimizer over sorted history | Research code, no pip | 2 |
| APE | Instructions | Execution accuracy | Induce -> score -> select (Monte-Carlo) | Research code, no pip | 2 |
| TextGrad | Any text variable (prompt) | LLM-judge critique as "textual gradient" | Textual gradient descent | Package (`pip install textgrad`) | 2 |
| PromptBreeder | Task-prompts AND mutation-prompts | Accuracy on a training batch | Self-referential evolution | No official pip | anti-pattern |

Common overfitting guardrail across all of them: score on a held-out set disjoint from what drove the rewrite, and cap the search budget. The hub delegates that discipline to agentic-evals-benchmarking; this catalog only names where each method exposes it.

Every method reduces to one of four driving-signal shapes, and each shape has a deterministic hub instrument that supplies it without a model call inside a shipped script:

| Signal shape | Framework example | Hub instrument (the static reward) |
|---|---|---|
| Scalar metric score | DSPy metric, MIPROv2 valset score | `loop_auditor.py` 100-pt score; `eval_gate.py` pass-rate |
| Execution accuracy on labeled cases | APE, OPRO scorer | Eval harness / CI pass-rate on the golden suite |
| Natural-language critique ("what to change, where") | TextGrad, GEPA feedback | `loop_auditor.py` itemized findings; react_trace_analyzer D1-D7 |
| (solution, score) history | OPRO trajectory | prompt-governance registry version history + `eval_score` |

---

## DSPy optimizers (teleprompters)

**Version assumption: DSPy 3.x, 2025. Verify against current docs** — the optimizer lineup and argument names have changed across releases (e.g. `dspy.Suggest`/`dspy.Assert` were replaced by `dspy.Refine`/`dspy.BestOfN`).

DSPy treats a program as `Module`s built from typed `Signature`s; you never hand-write the final prompt string. An optimizer is constructed with a metric and then compiles a *new* program whose prompts carry optimized instructions and bootstrapped demonstrations.

Core building blocks:
- `dspy.Signature`, `dspy.Module`, `dspy.Predict`, `dspy.ChainOfThought` — declare the typed input/output behavior; the prompt is generated, not written.
- `dspy.Evaluate(devset=, metric=)` — score a program over a dataset.
- The metric contract: `metric(gold, pred, trace=None) -> float | bool`.
- `optimizer.compile(student, trainset=, valset=) -> Module` — returns a NEW compiled program. **This auto-commit is exactly what the hub replaces with propose + human gate.**

Optimizer families (each `X.compile(...)`):

| API | Mechanism | Driving signal | Overfitting / regression guardrail |
|---|---|---|---|
| `dspy.LabeledFewShot` | Inject labeled demos verbatim, no search | Labeled examples | Trivial; cap demo count |
| `dspy.BootstrapFewShot(metric=, max_bootstrapped_demos=, max_labeled_demos=, teacher=)` | Run a teacher module over the trainset; KEEP only demos that pass the metric (self-labeled) | Metric pass/fail on each demo | Demos must pass the metric; hold a valset disjoint from trainset |
| `dspy.BootstrapFewShotWithRandomSearch(num_candidate_programs=)` | Bootstrap several demo sets, random-search the best | Metric over candidate programs | Score candidates on held-out data |
| `dspy.KNNFewShot` | Retrieve nearest labeled demos per input | Embedding similarity | Demo pool curation |
| `dspy.COPRO(metric=, breadth=, depth=)` | Coordinate-ascent INSTRUCTION refinement (no demos) | Metric score per instruction candidate | `breadth`/`depth` bound the search; validate on held-out set |
| `dspy.MIPROv2(metric=, auto='light'|'medium'|'heavy', num_trials=, minibatch_size=25, max_bootstrapped_demos=, max_labeled_demos=, valset=)` | Proposer LM drafts instruction candidates, then Bayesian optimization over the {instruction x demo-set} joint space, scored on a minibatched valset | Metric on minibatched valset | Explicit `valset`; minibatch periodic full evals; `auto` bounds trial budget |
| `dspy.SIMBA`, `dspy.BootstrapFinetune`, `dspy.Ensemble`, `dspy.BetterTogether` | Further variants (stochastic mini-batch ascent; weight finetuning; ensembling; alternating prompt+weight) | Metric | Same held-out discipline; `BootstrapFinetune` crosses into weight training (out of hub runtime scope) |

**Driving signal for the whole family:** a metric function over a labeled dataset. **The hub's static analog of that metric is a DETERMINISTIC composite (audit score + eval pass-rate + trace penalty), never a model call in a shipped script** — see the two-track table in `SKILL.md`.

**Eviction note:** MIPROv2/Bootstrap bake demos INTO the prompt; across repeated compiles these accumulate and cause prompt bloat. Cap embedded demos and keep only a coverage/Pareto set (one demo per distinct eval slice); delegate the demo curation policy to prompt-governance (registry) and slice design to agentic-evals-benchmarking.

**Choosing among the DSPy optimizers:**
- Start with `BootstrapFewShot` when the instruction is sound and you just need self-labeled examples — cheapest, least overfit-prone.
- Reach for `COPRO` when wording is the problem and there are no demos to bootstrap.
- Use `MIPROv2` when you want to search instructions AND demos jointly and can afford a valset; set `auto='light'` first and only raise the budget if the light run plateaus below threshold.
- Use `GEPA` when you have rich execution traces to reflect on and want to retain specialist variants rather than one averaged prompt; it needs a `reflection_lm` and a metric that returns feedback text, not just a scalar.
- `BootstrapFinetune` crosses into weight training — out of the hub's runtime scope (see below).

## GEPA - reflective prompt evolution (Genetic-Pareto)

**A DSPy optimizer; DSPy 3.x, 2025. Verify against current docs.** Paper: Agrawal et al., arXiv:2507.19457 (ICLR 2026 oral).

- `dspy.GEPA(metric=<GEPAFeedbackMetric>, reflection_lm=dspy.LM(model=, temperature=1.0, max_tokens=), auto='light'|'medium'|'heavy'` *(or* `max_full_evals=` */* `max_metric_calls=)`, `reflection_minibatch_size=3, candidate_selection_strategy='pareto'|'current_best', skip_perfect_score=True, use_merge=True, max_merge_invocations=5, track_stats=, log_dir=, seed=)`
- `GEPA.compile(student, *, trainset, teacher=None, valset=None) -> Module`
- Metric contract: `GEPAFeedbackMetric(gold, pred, trace, pred_name, pred_trace)` returns either a `float` or a `dspy.Prediction(score=<float>, feedback=<str>)` (feedback-carrying prediction; verify the exact type/path against current DSPy docs)

**Mechanism:** replaces numeric RL-style updates with LANGUAGE reflection over execution traces. It samples rollouts of the current candidate, collects the trace plus the metric's textual `feedback`, has a dedicated `reflection_lm` diagnose failures in natural language and propose a mutated prompt, then evaluates. It maintains a PARETO FRONTIER — a candidate is retained if it is best on at least one instance/objective — so specialist prompts are not averaged into a bland compromise; `use_merge` recombines complementary candidates.

**Driving signal:** the metric's feedback-carrying prediction (numeric score + itemized natural-language feedback). **Guardrails:** separate `valset`, `skip_perfect_score` (stop mutating a solved instance), Pareto retention instead of a single averaged winner.

GEPA is the closest published algorithm to the hub's existing producer -> auditor -> remediate audit loop: the feedback-carrying prediction maps to `loop_auditor.py`'s numeric score + itemized findings, the `reflection_lm` maps to the auditor role, and a "mutation" maps to a remediation edit. The one mandatory change vs GEPA: insert the HUMAN GATE between "propose mutation" and "accept into frontier."

**Static mapping:** the Pareto frontier maps to git history + the prompt-governance registry. Instead of forcing one linear "best" prompt, retain versions that are each best on a different eval slice or handoff contract, and let a human pick or merge. Eviction: cap the retained version set per config and archive a version (`status: archived`, rollback preserved) only when a newer one Pareto-dominates it across ALL slices; keep only mutually-non-dominated versions on the live frontier. The bounded 3-cycle audit loop is already a GEPA-lite with `max_iterations=3` — what it lacks, and what GEPA supplies, is the explicit per-slice non-regression predicate and the idea that the auditor's itemized findings ARE the optimization gradient.

## OPRO - Optimization by PROmpting

**Algorithm, not a maintained package.** Yang et al., Google DeepMind, "Large Language Models as Optimizers," arXiv:2309.03409. Reference impl: `github.com/google-deepmind/opro` (research code, no maintained pip package — **verify/reimplement**).

**Mechanism:** frames prompt search as black-box optimization where the LLM IS the optimizer. A "meta-prompt" holds the task description and an OPTIMIZATION TRAJECTORY: previously-tried instructions paired with their scores, sorted ascending. Each step the optimizer LLM reads the trajectory, infers what correlates with high scores, and proposes new candidate instructions; a scorer evaluates them; the (instruction, score) pair is appended; repeat until scores plateau or a step budget is hit.

**Driving signal:** the (instruction, score) trajectory. **Guardrails:** score on a held-out set; keep the trajectory diverse (include regressions so the proposer learns what NOT to do); cap steps; evict/summarize low-scoring middle entries to bound the meta-prompt (a token-budget exit condition).

**Static mapping:** the prompt-governance registry's version history with per-version `eval_score` IS an OPRO optimization trajectory (solution-score pairs). Feeding a dev session the sorted table of (prompt version, eval score, top failing slices) and asking for the next candidate is OPRO with the registry as the meta-prompt — the proposer is a human-supervised session, the scorer is the eval harness, and "append to trajectory" is committing the candidate's eval result. Include the worst versions too, or the proposer overfits to the last local maximum.

## APE - Automatic Prompt Engineer

**Algorithm, not a maintained package.** Zhou et al. 2022, "Large Language Models Are Human-Level Prompt Engineers," arXiv:2211.01910. Reference impl: `github.com/keirp/automatic_prompt_engineer` (research code — **verify/reimplement**).

**Mechanism:** instruction writing as program synthesis. (1) PROPOSE — give an LLM a handful of input/output demonstrations and ask it to infer the instruction that produced them (instruction induction), generating many candidates. (2) SCORE — execute each candidate on a target model over a held-out set, score by execution accuracy or log-prob of the gold output. (3) SELECT — keep the top candidate; optionally resample variations (iterative Monte-Carlo search). It is the conceptual ancestor of MIPROv2's instruction proposer.

**Driving signal:** execution accuracy on labeled examples. **Guardrails:** select on a set disjoint from the demos used to induce; filter low-scoring candidates aggressively.

**Load-bearing constraint for the hub:** APE's SCORE step requires EXECUTING candidates against a model. In the hub, instruction INDUCTION lives in a Claude dev session (offline, human-visible) while execution SCORING lives in the eval harness / CI (model calls allowed there) — NEVER in a shipped stdlib script. This is why the hub's reward signal inside portable scripts must be a deterministic proxy, not a model call.

**Static mapping:** APE's PROPOSE step maps to a dev-session candidate-generation task — from cases the current config handles well and poorly, induce a revised instruction block. The candidate `.md` drafts are ephemeral scratch artifacts (kept in the scratchpad, not committed); only the selected, human-approved candidate enters the registry, so git history is not polluted with rejected inductions. The "select best" step becomes the HUMAN GATE reviewing the eval-delta.

## TextGrad - textual gradient descent on prompts

**Package exists.** Yuksekgonul et al., arXiv:2406.07496 (2024; published in Nature 2025). `pip install textgrad` (`zou-group/textgrad`) — **verify current version and API.**

- `tg.set_backward_engine('gpt-4o', override=True)` (engine name is an example; use a current model id)
- `tg.Variable(value, role_description=, requires_grad=True)` — a prompt as an optimizable variable
- `tg.BlackboxLLM(engine)` — the forward pass
- `tg.TextLoss(evaluation_instruction)` — an LLM judge given an evaluation instruction
- `tg.TGD(parameters=[var])` — TextualGradientDescent optimizer
- `loss = loss_fn(prediction); loss.backward(); optimizer.step(); optimizer.zero_grad()`
- litellm-based engines (Bedrock/Together/Gemini/etc.)

**Mechanism:** ports PyTorch autodiff to text. `TextLoss` produces a natural-language critique; `loss.backward()` uses a backward-engine LLM to propagate that critique through the compute graph as TEXTUAL GRADIENTS (natural-language descriptions of how each variable should change); `optimizer.step()` rewrites the prompt to address the critique; `zero_grad()` clears accumulated feedback.

**Driving signal:** the judge's critique as a textual gradient (not a scalar). **Guardrail:** validation-set momentum / best-checkpoint selection reverts a step that hurts held-out performance (**verify current API**).

The hub's auditor feedback IS a textual gradient expressed as "what to change and where" — but it is deterministic-scored (which rubric item, which trace detection localizes to which prompt section) rather than judge-generated, and each step is a reviewed diff, not an auto-write. The `zero_grad()` discipline maps to the "fresh evidence each cycle" rule.

**Static mapping:** the static system is a manual, human-gated textual-gradient descent. The forward pass is running the config against an eval case; `TextLoss`/judge is `loop_auditor.py` + the evaluator; `loss.backward()` is the auditor localizing each lost rubric point to a specific prompt section ("A2 loop-safety failed -> the config lacks a `no_progress` exit condition in its loop block"); `optimizer.step()` is the remediation edit to that section; validation-momentum/revert is the regression-eval gate that rejects a step dropping any slice. This answers "what plays the optimizer": a human at the gate, driven by a deterministic gradient rather than an LLM-generated one.

## PromptBreeder - self-referential evolutionary optimization (THE ANTI-PATTERN)

**Algorithm, not a maintained package.** Fernando et al., DeepMind, "Promptbreeder: Self-Referential Self-Improvement via Prompt Evolution," arXiv:2309.16797. No official pip package (community reimplementations — **verify**).

**Mechanism:** an evolutionary algorithm over a population of task-prompts, binary-tournament selection, fitness = accuracy on a training batch. Its distinctive move is SELF-REFERENCE: the mutation operators themselves are LLM prompts ("mutation-prompts"), and a hyper-mutation operator evolves the mutation-prompts too. Nine operators span direct mutation, estimation-of-distribution, lineage-based, and crossover.

**Why it is in this catalog as a warning:** it is the most powerful and the most dangerous pattern — unbounded self-modification with the objective function itself under evolutionary pressure. It is the canonical illustration of an agent rewriting the rules that judge it. The hub's non-negotiable stance derives directly from this:

- **OBJECT-LEVEL config** = agent/skill instruction prompts. Safe to run through the governed rewrite loop with human approval.
- **META-LEVEL config** = the things that DEFINE how rewrites are judged and bounded: the `loop_auditor.py` rubric, the six exit-condition definitions, the H1-H5 handoff contracts, the promotion predicate, and `context/boundaries.md`.

The optimization loop may propose edits to object-level prompts ONLY. Meta-level config is frozen relative to the loop and can be changed only by a separate, explicitly-flagged human governance action. An agent must NEVER autonomously rewrite its own guardrails or reward function. Population culling (evicting losing candidates) operates on object-level candidates only; it never overwrites meta-level files.

## Out of the hub's runtime scope (pointer-level only)

Some optimizer families end in a WEIGHT update, not a prompt rewrite. They are named here so the boundary is explicit, but the hub never runs them — its scripts make no model calls and it ships no training pipeline:
- `dspy.BootstrapFinetune`, `dspy.BetterTogether` (the finetuning legs).
- RLHF/RLAIF training tooling — HuggingFace TRL `DPOTrainer` / `RewardTrainer` / `PPOTrainer` / `GRPOTrainer` (**verify against current TRL**). See `corrective_feedback_loops.md` for the inference-time, no-weight-update analog the hub actually uses.

When a task genuinely needs weight training, that is a model-training project outside this library; this skill's job ends at the prompt/policy text and its git-versioned, human-gated rewrite.

---

## STATIC TRACK: the governed rewrite for versioned prompt configs

The methods above optimize prompts at runtime/dev time. This hub is a git-versioned prompt-config library with no runtime, no vector DB, and no model calls in shipped stdlib scripts. The governed rewrite is the static realization, defined once as an instance of the Evaluator-Optimizer loop (Loop Pattern #2, `skills/agentic-system-architect/references/loop_engineering_patterns.md`). The role mapping lives in `SKILL.md`'s two-track table; this section states only what is specific to translating the *methods* above.

1. **Which method, when.** The selection ladder in `SKILL.md` maps rungs to methods: rung 1 = Bootstrap/Labeled/KNN few-shot; rung 2 = COPRO/MIPROv2-proposer/OPRO/APE/TextGrad instruction work; rung 3 = MIPROv2-joint/GEPA. Climb only as high as the signal justifies.

2. **`compile()` becomes propose + gate + promote.** Every method's terminal auto-commit is split: a dev/CI *propose* step emits a CANDIDATE `.md` revision plus an eval-delta report; then a mandatory HUMAN GATE and a promotion predicate (`loop_auditor.py >= 90` HARDENED AND Pareto-non-regression on a held-out set) before the registry status flips candidate -> production. The registry flip and archive are owned by prompt-governance.

3. **Where the reward lives.** APE/TextGrad/OPRO all need model execution to score. The hub confines that to the eval harness / CI (agentic-evals-benchmarking, prompt-governance's produce step), NEVER a shipped script. Inside portable scripts the reward is a deterministic proxy (`loop_auditor.py` score, `eval_gate.py` pass-rate). This is a hard constraint, not a preference.

4. **Pareto over averaging.** GEPA's frontier maps to git history + the registry: retain versions that are each best on a different eval slice / handoff contract rather than forcing one averaged "best," and let a human pick or merge. Promotion requires ties-or-dominates on EVERY slice — never trade one slice for another.

5. **Bounded and safe.** The loop is bounded by the six exit conditions (`max_iterations=3` remediation cycles; `no_progress` = score plateau over window 2; `oscillation` = a rewrite re-breaking a prior-passing check; plus `budget`, `success_predicate`, `escalation_trigger`) and is forbidden from editing meta-level config (the PromptBreeder guardrail). See `SKILL.md` -> Hub Canon Integration.

6. **Overfitting is delegated.** Held-out splits, rotating subsets, and golden-set hygiene belong to agentic-evals-benchmarking; judge-integrity / score-inflation checks on any AI corrector belong to self-eval. This skill cites them; it does not re-teach them.

Reading the version flags: every framework API above carries a version assumption (e.g. "DSPy 3.x, 2025"). Treat any signature marked **verify against current docs** as a starting point to confirm, not a guarantee — optimizer names and arguments move between releases, and research-only algorithms (OPRO, APE, PromptBreeder) have no maintained package to pin. Never invent a member to fill a gap; if the current API differs, use the current API.

### Worked example: MIPROv2 translated to a governed rewrite

Framework track (what MIPROv2 would do, illustrative — verify current API):

```python
import dspy
optimizer = dspy.MIPROv2(metric=my_metric, auto="light", valset=val_examples)
compiled = optimizer.compile(student=my_program, trainset=train_examples)
# compiled now carries optimized instructions + bootstrapped demos, AUTO-COMMITTED.
```

Static track (the same intent, governed):

1. **Signal in (Phase 1).** A `triage-agent.md` config scores 82 on `loop_auditor.py` and fails 3 of 40 held-out eval cases, all on ambiguous-priority inputs. That failure set is the "trainset"; the untouched remainder is the "valset."
2. **Propose (Phase 2, dev session = the proposer LM).** A supervised Claude session rewrites ONLY the priority-classification instruction block of `triage-agent.md` and adds two demos, each covering a distinct failing slice. It does NOT touch the loop-safety block, the rubric, or `boundaries.md`.
3. **Evaluate (deterministic).** `loop_auditor.py triage-agent.md` -> 93; `eval_gate.py` on the held-out valset -> ties-or-improves every slice, no regressions.
4. **Human gate (Phase 3).** A human reads the diff and the eval-delta report and approves.
5. **Promote.** prompt-governance flips the registry entry to `production` and archives the prior version (rollback preserved). The old version stays on the Pareto frontier only if it still wins a slice the new one lost — here it does not, so it is archived.
6. **Handoff (Phase 5).** The regression report records the score delta, the slices covered by each new demo, and the exit condition that ended the loop.

The difference from `compile()` is entirely in steps 4-5: the candidate never becomes production without a human reading the actual change. Everything MIPROv2 automates (propose, score, select) still happens; the auto-commit does not.

---

## See also

- `SKILL.md` — the optimizer selection ladder, the two-track translation table, and the governed rewrite loop this catalog feeds.
- `corrective_feedback_loops.md` — the RLAIF/RLHF corrector distinction and the correction ledger; the in-context, no-weight-update side of optimization.
- `skills/agentic-system-architect/references/loop_engineering_patterns.md` — the Evaluator-Optimizer loop (Pattern #2) and the six exit conditions that bound the rewrite. Cite; do not duplicate.
- **agentic-evals-benchmarking** — the metric, golden set, held-out split, and overfitting guards every method above depends on.
- **prompt-governance** — the registry, versioning, promotion gate, and rollback that receive the candidate.
- **autoresearch-agent** — a runnable static propose-eval-keep/discard harness for the loop.

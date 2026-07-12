# Self-Reflection & Critique Loops: A Named Catalog

Loop *shape* is covered elsewhere; this reference covers loop *identity*. It names the
published self-improvement algorithms every agentic team eventually reinvents - Reflexion,
Self-Refine, CRITIC, Constitutional AI self-critique, and the Evaluator-Optimizer workflow -
and maps each one, by name and citation, onto the machinery this hub already ships. The payoff
is diagnostic: once you can say "our audit loop is CRITIC, not Self-Refine", you know which
failure modes apply to it and which do not, and you know exactly which property is missing.

Two tracks run through every entry:

- **FRAMEWORK TRACK** - how the technique is built in a *runtime* agent framework (LangGraph,
  CrewAI, Microsoft Agent Framework, LlamaIndex, DSPy). Real constructs only, each carrying a
  version assumption and marked **verify against current docs** - these APIs move fast.
- **STATIC TRACK** - how the technique maps onto *this* hub: a git-versioned prompt-config
  library with **no runtime, no vector DB, and no model calls in its stdlib scripts**. Here
  "memory" = context packs + MANIFEST + the iteration ledger + git history; the "critic" =
  `loop_auditor.py`; the "reward signal" = the deterministic 100-point audit score; the
  "optimizer" = a human-gated edit; the "policy update" = the git commit.

This reference does **not** re-teach loop theory. The six-type exit-condition taxonomy
(`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger`), counter design, and the four canonical loop patterns live in
`loop_engineering_patterns.md` - it is the single source of truth for loop mechanics and is
cited throughout. This file adds the *named literature layer* on top of it.

---

## Framework-Track API Reference

Real constructs as of the 2025/2026 releases noted. Frameworks in this space rev quickly;
**verify every row against current docs before relying on it.** Do not treat these as frozen.

| Technique | Framework | Real constructs (verify against current docs) | Version assumption |
|---|---|---|---|
| Reflexion | LangGraph | `StateGraph`, `add_node`, `add_conditional_edges`, `MessagesState`, `compile(checkpointer=...)` - generator node + reflect node, reflect writes a critique string into a state field, conditional edge routes back until an iteration/quality bound | v1.0 (2025) |
| Reflexion | LlamaIndex | `IntrospectiveAgentWorker`, `SelfReflectionAgentWorker` (`llama-index-agent-introspective`) - agent API is migrating to `AgentWorkflow` | 2025 |
| Reflexion | Letta / MemGPT | self-editing core memory + archival blocks via memory-edit tools (`core_memory_append` / `core_memory_replace`; verify against current Letta docs) | 2025 |
| Reflexion | LangMem | episodic + procedural memory namespaces layered on the LangGraph store | 2025 |
| Self-Refine | DSPy | `dspy.Refine(module, N=, reward_fn=, threshold=)`, `dspy.BestOfN` (replaced the older `dspy.Suggest`/`dspy.Assert`) | DSPy 3.x (2025) |
| Self-Refine | LangGraph | single generator node self-looping via `add_conditional_edges` on a feedback key in the state `TypedDict` | v1.0 (2025) |
| CRITIC | LlamaIndex | `ToolInteractiveReflectionAgentWorker` driven by an `IntrospectiveAgentWorker` (docs name it the CRITIC framework) | 2025 |
| CRITIC | LangGraph | a critic node that invokes a bound tool (code exec, validator, search) then routes via `add_conditional_edges` on the tool result | v1.0 (2025) |
| CRITIC | CrewAI | a **function-based** `guardrail` that runs a real check (schema/tests), not an LLM opinion | 2025 |
| Constitutional self-critique | prompt-level | no single canonical API; NVIDIA NeMo ships a CAI recipe; in LangGraph/CrewAI it is a reviewer node/task whose instructions *are* the constitution | 2025 |
| Constitutional self-critique | DSPy | principle text carried in `reward_fn` feedback or GEPA reflective feedback (GEPA, arXiv:2507.19457) | DSPy 3.x (2025) |
| Evaluator-Optimizer | LangGraph | `StateGraph` + `add_conditional_edges` on a score field; `interrupt()` / `Command(resume=...)` + a checkpointer for the human gate | v1.0 (2025) |
| Evaluator-Optimizer | CrewAI | `Task(guardrail=..., guardrail_max_retries=3)`, `output_pydantic`, `TaskOutput`, `context=[producer_task]`, `Process.hierarchical` manager | 2025 |
| Evaluator-Optimizer | Microsoft Agent Framework | `WorkflowBuilder`, `Executor`s, `Edge`s - the writer-critic / maker-checker reflection pattern over a Pregel/BSP superstep model | orchestration patterns 1.0 (2025) |
| Evaluator-Optimizer | DSPy | `dspy.Refine` (evaluator = `reward_fn`, optimizer = re-run with feedback hints) | DSPy 3.x (2025) |

---

## The Catalog

### 1. Reflexion (Shinn et al. 2023, arXiv:2303.11366, NeurIPS 2023)

**FRAMEWORK TRACK.** Three cooperating roles with *no weight updates*: an **Actor** generates
the action/text, an **Evaluator** returns a scalar or task-feedback signal, and a
**Self-Reflection** model turns that signal into a free-form verbal reflection. The reflection
is appended to an **episodic memory buffer** (a sliding window of the last few reflections)
that is prepended to the Actor's context on the *next* trial. The "reinforcement" is entirely
linguistic and in-context; the loop repeats per trial until success or a trial cap. Reported
91% pass@1 on HumanEval.

**STATIC TRACK.** A near-perfect structural analog already exists in the hub - but incomplete.
Map the roles: Actor = the config author (human or Claude editing an agent/skill/workflow `.md`);
Evaluator = `loop_auditor.py`'s deterministic score + grade band; Self-Reflection = the
per-failed-check remediation hints plus the JSON failed-checks list; policy = the versioned
markdown config; policy update = the git-committed edit; episodic memory = git history + the
file itself. The producer -> auditor -> remediate cycle (max 3) *is* a Reflexion trial loop.

**THE GAP.** The one property that *defines* Reflexion is the one the hub lacks:
**cross-trial reflection memory.** `loop_auditor.py` is stateless - it re-scores from scratch
every run and remembers nothing about what it flagged last week or on a sibling config, so the
same error class is re-made across sessions and across authors. Closing this gap is the whole
point of the `--history` ledger and the self-improving-agent bridge (below).

### 2. Self-Refine (Madaan et al. 2023, arXiv:2303.17651)

**FRAMEWORK TRACK.** One model, three sequential roles, no training and no second model:
Generator (draft), Feedback (critiques its *own* output - genericness is the documented failure
mode), Refiner (rewrites). Feedback -> Refine iterates to a stopping criterion or a
max-iterations cap; the paper uses a scalar stop signal to avoid non-convergence. DSPy
operationalizes it as `dspy.Refine(module, N, reward_fn, threshold)`, which auto-generates
feedback after each unsuccessful attempt and stops early when `reward_fn` exceeds `threshold`
(`dspy.BestOfN` is the no-feedback sibling).

**STATIC TRACK.** This is the pattern the hub deliberately **warns against** -
`loop_engineering_patterns.md` calls it out as "reflection without a rubric" and
"self-agreement bias." The static analog of pure Self-Refine is an author critiquing their own
config with no external check; the hub replaces that with a *separate deterministic auditor* -
the Evaluator-Optimizer upgrade of Self-Refine, and the defensible choice given that CRITIC (below)
shows ungrounded self-critique is unreliable. Where Self-Refine's real lesson *does* land: the
**stopping criterion.** Its scalar stop maps to `loop_auditor`'s `--min-score` gate and the
`>=90` HARDENED threshold; its "infinite polish" failure is exactly the `no_progress` guard on
the score - a plateau at 85 across two remediation cycles must *stop*, not iterate. That guard
is described in `loop_engineering_patterns.md` but, until `--history`, was not computable by any
tool.

### 3. CRITIC (Gou et al. 2023, arXiv:2305.11738)

**FRAMEWORK TRACK.** Verify-then-correct: the LLM does **not** self-critique from its own
judgment; it invokes **external tools** (search, code interpreter, validator, classifier) to
generate a *grounded* critique of specific output aspects, then revises, iterating until checks
pass. The central finding: LLMs are unreliable self-critics - self-correction *without* external
feedback yields modest or **negative** gains; the external tool is what makes the loop work.
LlamaIndex ships this as `ToolInteractiveReflectionAgentWorker`.

**STATIC TRACK.** This is the technique the hub implements **best**, though it never names it.
`loop_auditor.py`, `hitl_gate_validator.py`, and `react_trace_analyzer.py` are tool-verified
critics: deterministic regex/rule engines, not LLM opinions - precisely CRITIC's prescription
and the antidote to Self-Refine's self-agreement bias. The "tool" grounding the critique is the
deterministic rubric. So the hub's static audit loop is closer to CRITIC than to naive
Reflexion, and that is a strength worth stating out loud.

**THE CEILING.** CRITIC's tools verify *substance* (does the code run? is the fact true?),
whereas `loop_auditor` verifies only the *presence* of control-plane keywords (does the config
contain the string "oscillation"?). A config can pass A3 by writing the word without a real
guard - the critique is grounded but shallow. A deeper critic tier that parses the declared
*value* (is `max_iterations` a sane number? is the `success_predicate` actually
machine-checkable?), or a gated LLM-judge tier for semantic quality, is the documented next
layer. Metric design for any such tier is owned by **agentic-evals-benchmarking**, not here.

### 4. Constitutional AI self-critique (Bai et al. 2022, arXiv:2212.08073)

**FRAMEWORK TRACK.** Supervised phase: the model generates a response, critiques it against a
**principle sampled from a written constitution** (~75 principles), then revises per that
critique; the critique-revision loop repeats, sampling different principles. (A later RLAIF
phase trains a preference model on AI-judged pairs - out of scope here.) The constitution is the
externalized, human-authored rubric; the critique is "which principle did this violate and how."
Less a library primitive than a prompt pattern - a critic node/task whose instructions carry the
principle set; NVIDIA NeMo ships a CAI recipe.

**STATIC TRACK.** The hub already has a *de facto* constitution, just scattered: the 5-Phase
Protocol, the six exit-condition types, the anti-pattern table, the H1-H5 handoff contracts, and
the `loop_auditor` 15-check rubric all function as principles a config is critiqued and revised
against. `loop_auditor` even samples-and-checks per principle (one regex per check) exactly as
CAI samples a principle, and emits a per-principle finding + remediation - a CAI-style critique.
The **H4 Audit Verdict** is the constitution's verdict record.

**THE GAP.** CAI derives *both* the critic and the generator from *one* canonical constitution,
so a principle change propagates to both together. The hub has no single canonical config
constitution: principles live redundantly in `loop_auditor.py`'s `RUBRIC`, in
`loop_engineering_patterns.md`, and in the templates, which can drift apart (the moving-target-rubric
failure mode). Consolidating a versioned constitution as the single source both the deterministic
critic and the authoring templates derive from is registry/versioning work owned by
**prompt-governance** - delegate it there; do not fork a competing rubric here.

### 5. Evaluator-Optimizer workflow (Anthropic, "Building Effective Agents", 2024)

**FRAMEWORK TRACK.** A canonical workflow: an **Evaluator** scores output against a *frozen*
rubric and returns score + itemized feedback; a separate **Optimizer** revises using only that
feedback; iterate until `score >= threshold` or `max_iterations`. Role separation defeats the
self-agreement bias of single-model Self-Refine. In LangGraph it is generator + evaluator nodes
with `add_conditional_edges` routing on the score and `interrupt()`/`Command` inserting a human
gate; Microsoft Agent Framework ships it as the writer-critic / maker-checker pattern over
`Executor`s and `Edge`s; CrewAI as a reviewer QA `Task` with `context=[producer_task]` plus a
`guardrail`.

**STATIC TRACK.** This is the pattern the hub is **built on**. `loop_engineering_patterns.md`
documents it as Loop Pattern #2 with its full failure-mode set (moving-target rubric, score
plateau = `no_progress`, threshold-at-100). The team layer's producer -> auditor -> remediate
(max 3 cycles) is a live instance: producer = Optimizer, `loop_auditor` = Evaluator, the **H4
Audit Verdict** = the score+feedback contract passed back, and the **Phase-3 HUMAN GATE** = the
human-in-the-loop that accepts/rejects the policy update before merge (the static equivalent of
LangGraph's `interrupt()`). Reward = the 0-100 score; threshold = `>=90` HARDENED via
`--min-score`; the rubric is frozen because `RUBRIC` is a fixed module-level data structure, so
the moving-target failure is *structurally prevented*. Role separation is stronger here than in
LLM frameworks: the evaluator is a deterministic tool, not a same-family model, so it cannot be
argued into agreement.

---

## The Load-Bearing Insight

Put the four mappings together and one sentence falls out that should govern how anyone reasons
about this hub's self-improvement loop:

> **The hub already runs a CRITIC-grounded Evaluator-Optimizer loop with a frozen rubric and a
> human-gated policy update - not a self-agreement-prone Self-Refine loop.**

Concretely: `loop_auditor.py` is a CRITIC-style *tool-verified* critic (deterministic, external
to the author), and producer -> auditor -> remediate(max 3) + the **H4 Audit Verdict** + the
**Phase-3 HUMAN GATE** already realize the Evaluator-Optimizer workflow end to end. This is a
design strength, and it is why the hub does not need - and must not adopt - an LLM that grades
its own prose against itself. The only thing the loop is missing is memory.

---

## The Cross-Session Gap and How It Is Closed

Reflexion's defining property is cross-trial reflection memory; the hub's evaluator-optimizer
loop has none. `loop_auditor.py` was **stateless**: it re-scored each file from scratch and
retained nothing, so a finding fixed on Monday and re-broken on Thursday looked brand-new both
times, and a finding that recurs across ten sibling configs was re-discovered ten times. A
single-trial evaluator-optimizer loop is not yet Reflexion.

**Closing move 1 - a versioned critique ledger (`loop_auditor.py --history`).** The auditor now
takes an optional `--history <ledger.json>`. On each run it appends a record
(`file`, `score`, `grade`, `failed_check_ids`, `timestamp`) to the JSON ledger, reads prior
records **for the same file**, and computes, deterministically and with no model call:

- **score_delta** vs the previous run for that file;
- a **`no_progress`** flag - `>=2` consecutive runs with no score increase *and* an identical
  failed-check set (the score-plateau guard `loop_engineering_patterns.md` describes, now
  *computed* rather than merely prescribed);
- an **`oscillation`** flag - a check that was failing, disappeared, then reappeared (a fix that
  re-broke a previously passing check);
- a **recurring-findings digest** - the checks that failed across `>=2` runs.

The ledger is the episodic memory buffer; the digest is the verbal reflection prepended to the
author's next trial. This keeps the whole loop inside the hub's constraints: memory = a
git-versioned JSON ledger, reward = the deterministic score, optimizer = the human/agent
remediation, human gate = Phase 3. The ledger must be **bounded** the way Reflexion bounds its
buffer to the last N reflections and the way self-improving-agent's MEMORY.md truncates at 200
lines: keep recurring-finding digests, evict one-off resolved findings, or the ledger becomes
unbounded and unread. Storage schema, chunking, and any embedding-based retrieval over a larger
memory corpus are owned by **rag-architect** and the storage sections of **hybrid-rag-memory** -
delegate there rather than growing a bespoke store in this skill.

**Closing move 2 - the self-improving-agent bridge (the highest-leverage wiring in the cluster).**
A ledger that only *reports* recurrence is diagnosis without treatment. The digest becomes a
*policy update* by routing a recurring or oscillating finding into the existing promotion
pipeline owned by **self-improving-agent**:

```text
loop_auditor --history          # a finding recurs across runs / sibling configs
        |
        v
auto-memory (MEMORY.md)          # the recurrence is recorded as a project learning
        |
   /si:review                    # flags it as a promotion candidate (recurs 2-3x)
        |
   HUMAN GATE  <----------------- mandatory: a human approves the graduation
        |
   /si:promote                   # graduates it into CLAUDE.md or .claude/rules/
        |
        v
enforced authoring rule          # the lesson is now structural; evict it from the ledger
```

That path turns a single-trial evaluator-optimizer loop into a true Reflexion episodic-memory
loop, entirely within the hub's static, git-versioned, human-gated, no-runtime model: the ledger
is episodic memory, CLAUDE.md/`.claude/rules/` is crystallized policy, `--history` is the
optimizer's signal source, and the human PR is the gated gradient step. self-improving-agent
today promotes only *positive* patterns; promoting a recurring audit *finding* into an enforced
rule is the generalization this bridge adds.

---

## The Non-Negotiable Boundary: the Loop May Not Rewrite Its Own Rubric

Every technique in this catalog proposes edits to **object-level** config - the instruction text
of an agent/skill/workflow. None of them may touch **meta-level** config: the `loop_auditor`
rubric, the six exit-condition definitions, the H1-H5 handoff contracts, the promotion
predicate, or the boundaries the config must respect. An agent rewriting its own guardrails or
its own reward function is the PromptBreeder self-referential-mutation failure - the single most
dangerous pattern in this space. The rule is absolute: **the self-improvement loop proposes
object-level edits only; any change to a guardrail or the reward rubric is a separate,
explicitly-flagged human governance action, never an autonomous step, and always subordinate to
the Phase-3 HUMAN GATE.** No audit finding, however often it recurs, may auto-edit
`boundaries.md`, a rule file, or the rubric without a human approving the graduation. A generated
agent must stay `>=90` HARDENED, and safety of the optimization loop is subordinate to the
human gate.

---

## Ownership Map (delegate, do not re-teach)

This reference is the *named-literature* layer only. Adjacent concerns belong to their owners:

| Concern | Owner skill |
|---|---|
| Loop mechanics: exit-condition taxonomy, counters, ledger detectors, the four loop patterns | `loop_engineering_patterns.md` (this skill) + **loop-engineering-mechanisms** |
| Metrics, golden sets, overfitting, LLM-as-judge integrity for any deeper critic tier | **agentic-evals-benchmarking** |
| Prompt/config registry, versioning, a single canonical constitution, promotion, rollback | **prompt-governance** |
| The memory->rules promotion engine (MEMORY.md, `/si:review`, `/si:promote`) | **self-improving-agent** |
| Autonomous experiment / optimization harness | **autoresearch-agent** |
| Memory storage schemas, chunking, embeddings, retrieval | **rag-architect** + **hybrid-rag-memory** |

Pair this file with `loop_engineering_patterns.md` (loop mechanics), `react_reasoning_patterns.md`
(how the loop body reasons), and `hitl_defensive_architectures.md` (where the human interrupts
the loop).

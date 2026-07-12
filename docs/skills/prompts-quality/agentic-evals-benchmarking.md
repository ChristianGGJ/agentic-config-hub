---
title: "Agentic Evals & Benchmarking — Prompts Optimization & Quality Rubrics"
description: "Use when building evaluation suites for agents or LLM pipelines: scoring trajectories and tool calls, measuring faithfulness and relevance with. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Agentic Evals & Benchmarking

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-check: Prompts & Quality</span>
<span class="meta-badge">:material-identifier: `agentic-evals-benchmarking`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-evals-benchmarking/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install prompts-quality</code>
</div>


This skill owns **evaluation methodology** for the hub: how to measure whether an agent
works, prove it keeps working, and fail the build when it stops working. Agent evaluation
has three layers, and most teams only build the second:

1. **Trajectory (process) evaluation** — did the agent take the right steps? Tool-call
   correctness, step efficiency, loop-health detections. This is the heart of agent
   evals and the layer this skill treats as first-class.
2. **Output (outcome) evaluation** — is the final answer good? Faithfulness, relevance,
   correctness against references.
3. **System (guardrail) evaluation** — at what cost? Tokens, tool calls, latency,
   error rates recorded per eval case and gated as budgets.

**BYOK note:** LLM-judged metrics (DeepEval, Ragas, custom judges) require an evaluator
model that *you* supply — your own API key or local model. That is a user-provided
dependency, not a paid dependency of this skill. Deterministic metrics (tool-call
matching, predicates, `scripts/eval_gate.py`) run with no LLM at all.

## Core Capabilities

- Design trajectory-level metrics: tool-call precision/recall, order matching, step
  efficiency, task-completion scoring.
- Configure DeepEval (`GEval`, `assert_test`, `evaluate`, datasets/goldens) and Ragas
  (`evaluate()`, `SingleTurnSample`/`MultiTurnSample`, agent metrics) with real,
  current APIs — see `references/deepeval_ragas_api.md`.
- Build golden datasets with size floors, edge-case ratios, and versioning rules.
- Generate synthetic test data from domain documents (entity x template matrix).
- Detect and mitigate LLM-judge bias; calibrate judges against human labels.
- Wire regression gates into CI with the deterministic `scripts/eval_gate.py`.

## Decision Frameworks

### 1. Which evaluator type for which assertion

Always exhaust the cheaper, deterministic rows before reaching for an LLM judge.

| Signal to measure | Evaluator | Cost | Deterministic | Default choice when |
|---|---|---|---|---|
| Format, schema, exit codes, predicates | Code check | Free | Yes | Always first — target >= 60% of assertions here |
| Tool-call correctness, trajectory match | Set/sequence comparison | Free | Yes | Any agent with tools (see trajectory reference) |
| Loop health (repeats, oscillation, budget) | Trace detections D1-D7 | Free | Yes | Any looping agent |
| Semantic closeness to a reference | Embedding similarity | Cheap | Mostly | Reference answers exist, wording varies |
| Faithfulness, relevance, tone, rubric quality | LLM judge | $$ | No | Only what code cannot check |
| End-user acceptability, high-stakes calls | Human review | $$$ | — | Calibration samples and launch gates |

### 2. Trajectory match strictness

| Metric | Passes when | Use when | Default |
|---|---|---|---|
| Exact match | Same tools, same order, same args | Compliance-critical, short fixed flows | Rare; brittle |
| In-order match | Expected calls appear as a subsequence | Required steps with optional extras allowed | **Recommended default** |
| Any-order match | Expected calls all present, any order | Independent lookups, parallel-safe steps | Common |
| Precision / recall / F1 | Scored, not pass/fail | Dashboards, partial credit, trend lines | F1 >= 0.9 gate |

### 3. Framework selection

| Situation | Choice |
|---|---|
| Pytest-style unit evals, custom rubric metrics (GEval), CI-first | DeepEval |
| RAG pipeline metrics, agent multi-turn samples, LangChain-native stack | Ragas |
| Zero dependencies, air-gapped CI, deterministic gates only | Stdlib scripts (this skill's `eval_gate.py` + trajectory reference code) |
| Production trace capture, dashboards, online monitoring | Not this skill — see agentic-observability-telemetry |

### 4. Calibrated threshold defaults

Starting points; re-baseline against your golden set, never against vibes.

| Metric | Gate default | Notes |
|---|---|---|
| Faithfulness | >= 0.85 | Raise to 0.95+ for regulated/medical/financial domains |
| Answer/response relevance | >= 0.80 | Below 0.7 usually means retrieval problems, not prompt problems |
| Context precision / recall | >= 0.75 | Retrieval-layer gate; fix retrieval before tuning prompts |
| Tool-call F1 | >= 0.90 | Deterministic; no excuse for flakiness |
| Task completion pass rate | >= 0.85 over the suite | Use pass@k for nondeterministic agents |
| Trace health score | >= 90 (no CRITICAL detections) | Mirrors hub trace-analyzer verdict bands |

## Golden Dataset Design (summary)

- **Size floors:** 30 cases minimum for any gate; 100-300 for stable per-metric means;
  at least 10 cases per slice (intent/topic/tool) you report separately.
- **Edge-case ratio:** 20-30% of cases must be hard: adversarial phrasing, out-of-scope
  requests (correct behavior = refuse), injection attempts, empty/oversized inputs.
- **Versioning:** JSONL in git, `dataset_version` field on every row, changelog entry
  per version, and re-baseline thresholds whenever the version bumps.
- **Leakage rule:** keep a held-out split that is never used while tuning prompts or
  agents; report it separately to detect overfitting to the eval.

Full procedure and row schema: `references/eval_methodologies.md`. A ready-to-fill row
template ships in `assets/golden-dataset-template.jsonl`.

## Synthetic Data Generation (summary)

Procedure: (1) extract entities and facts from domain documents, (2) write query
templates per intent, (3) fill the entity x template matrix, (4) dedupe and
spot-check 10% by hand, (5) label expected outputs and expected tool trajectories.
Worked templates: `assets/synthetic-data-templates.md`. Framework generators
(DeepEval `Synthesizer`, Ragas `TestsetGenerator`) are covered in
`references/deepeval_ragas_api.md`.

## Judge Bias & Calibration (summary)

LLM judges are measurement instruments and must be calibrated like one: pin
temperature to 0, anchor the rubric with examples, use a judge from a different model
family than the agent under test, and verify agreement against ~50 human-labeled
cases before trusting any gate built on the judge. The bias table (position,
verbosity, self-preference, sycophancy) with mitigations and the full calibration
procedure live in `references/eval_methodologies.md`.

## CI Regression Gate

Convert any framework's output into the gate schema and let the deterministic script
decide pass/fail:

```bash
python scripts/eval_gate.py --results results.json --threshold 0.85
python scripts/eval_gate.py --results results.json \
    --metric-threshold faithfulness=0.9 --metric-threshold tool_call_f1=0.95 --json
```

Exit code 0 when every gate passes, 1 on any failure — wire it directly into CI:

```yaml
# .github/workflows/evals.yml (excerpt)
- name: Run eval suite
  run: python run_evals.py --out results.json   # your DeepEval/Ragas/custom runner
- name: Gate on eval scores
  run: python skills/agentic-evals-benchmarking/scripts/eval_gate.py \
         --results results.json --threshold 0.85 --json
```

Suite tiers: a ~30-case smoke suite on every PR touching prompts/agent configs; the
full suite nightly; the held-out split weekly. Sample input:
`assets/sample_eval_results.json`.

## Statistical Rigor (summary)

Agents are nondeterministic; single-run scores are noise. Run each case k times
(k >= 3 for gates, k >= 5 for baselines), report pass@k or mean +/- stddev, and only
call something a regression when the change exceeds the run-to-run noise band.
Formulas and code: `references/agent_trajectory_evaluation.md` (Statistical Rigor).

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Scores swing run to run with no code change | Judge nondeterminism and/or dataset too small | Temperature 0, k >= 3 runs with median, grow dataset past the size floor |
| Faithfulness passes but users report hallucinations | Judge grades only against retrieved context; query mismatch unmeasured | Add answer relevance + correctness-vs-reference; check context recall |
| Tool-call metric reads 0 despite correct behavior | Argument normalization mismatch (whitespace, key order, aliases) | Normalize args before compare (see trajectory reference, arg accuracy) |
| CI green, production regressions anyway | Golden set stale; no edge cases; drift | Mine production failures into new goldens each sprint; enforce the 20-30% edge-case ratio |
| Task completion 100% but token spend exploding | Outcome-only evaluation; process unmeasured | Add step-efficiency and budget guardrail metrics per case |
| Scores creep upward as prompts are tuned | Overfitting to the judge/eval set | Held-out split, rotate judge family periodically, human calibration check |
| Same eval case flakes across runs | Genuine agent instability, not eval noise | Quarantine the case, file it as an agent bug — do not delete or retry-until-green |

## Hub Canon Integration

This skill provides the **dynamic evidence** that complements the hub's static safety
gates. Map every eval suite onto the canon:

- **Trace schema + detections D1-D7:** evaluate looping agents on their traces, not
  just their answers. Each canonical detection is a free, deterministic trajectory
  assertion: D1 (repeated identical call), D2 (A-B-A-B oscillation), D3 (error
  cascade), D4 (missing thought/observation), D5 (budget overrun), D6 (no
  convergence), D7 (repeated reasoning). Regression-gate the trace health score at
  >= 90 with zero CRITICAL detections. Stdlib implementations:
  `references/agent_trajectory_evaluation.md`.
- **Six exit-condition types:** `success_predicate` IS your deterministic
  task-completion metric — if you cannot write it, you cannot eval the task.
  `budget` maps to the cost/latency guardrail metrics recorded per eval case.
  `max_iterations`/`no_progress`/`oscillation` map to step-efficiency and D-series
  assertions. Every eval case for a loop agent should record which condition ended
  the run; anything other than `success_predicate` on a should-pass case is a failure.
- **>= 90 HARDENED gate:** the flagship's config audit (loop auditor, >= 90 =
  HARDENED) proves the agent is *designed* safely; this skill's suites prove it
  *behaves* safely. Ship both in CI: static config gate + dynamic eval gate. An agent
  is production-ready only when both are green.
- **5-Phase Protocol:** eval suites are the Phase 5 (SELF-REVIEW & HANDOFF) evidence
  for any agent change, and the regression suite is the standing `success_predicate`
  for future changes. Building a brand-new eval suite is itself a change: run
  DISCOVERY (read the agent, its tools, its traces) and present the eval plan at the
  HUMAN GATE before wiring gates that can block deploys.

## When NOT to Use

- **Writing or improving individual prompts**, prompt-level optimization loops — see
  senior-prompt-engineer (it keeps prompt-level eval pointers; the methodology behind
  them is owned here).
- **Prompt lifecycle in production** — versioning, registries, A/B tests, rollout and
  rollback — see prompt-governance.
- **Collecting production traces, dashboards, online monitoring** — see
  agentic-observability-telemetry. Boundary: that skill gets traces out of
  production; this skill turns them into eval datasets and gates.
- **Rating your own session's work quality** — see self-eval.
- **Autonomous improve-measure loops** that consume eval scores to mutate code or
  prompts — see autoresearch-agent (and note its overfitting guards).
- **Designing the loop exit conditions themselves** — see agentic-system-architect
  (canon) and loop-engineering-mechanisms (Python implementations).

## Ownership Boundary

This skill **owns eval methodology** hub-wide: metric definitions, judge design and
calibration, dataset construction, statistical treatment, and CI gating. Sibling
skills that mention evaluation (senior-prompt-engineer, prompt-governance,
agenthub's LLM-judge ranking) hold routing pointers or apply the methodology to
their own domain; when guidance conflicts, this skill's references are canonical
for how to measure.

## Tools

| Script | Purpose |
|---|---|
| `scripts/eval_gate.py` | Deterministic CI gate: reads an eval results JSON, applies per-metric thresholds, exits non-zero on failure. Stdlib-only, `--json`, ASCII-safe. |

## References

| File | Summary |
|---|---|
| `references/agent_trajectory_evaluation.md` | Trajectory/step-level evaluation: tool-call correctness metrics with stdlib code, step efficiency, task-completion scoring, D1-D7 eval assertions, public benchmark landscape, pass@k and variance |
| `references/deepeval_ragas_api.md` | Real current API surfaces for DeepEval (GEval, metrics, assert_test/evaluate, datasets, Synthesizer) and Ragas (evaluate(), samples, RAG + agent metrics, TestsetGenerator), with version assumptions and a cross-framework mapping table |
| `references/eval_methodologies.md` | Output-quality metric taxonomy, LLM-judge design, judge bias and calibration, golden dataset procedure, synthetic data generation, regression suite design |

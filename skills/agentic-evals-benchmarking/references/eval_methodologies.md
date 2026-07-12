# Output-Quality Evaluation Methodologies

Metric taxonomy for output (outcome) evaluation, LLM-judge design and calibration,
golden dataset construction, synthetic data generation, and regression suite design.
Trajectory/process metrics live in `agent_trajectory_evaluation.md`; framework
implementations of everything here live in `deepeval_ragas_api.md`.

**Ownership note:** this file is the hub's canonical methodology for these topics.
Sibling skills (senior-prompt-engineer, prompt-governance) keep routing pointers to
it rather than restating the procedures; when guidance conflicts, this file wins.

**BYOK:** every judged metric below needs an evaluator model you supply (API key or
local model). Code samples are provider-agnostic: they take a `call_judge(prompt)`
callable that wraps whatever provider you use. Deterministic checks need no LLM.

---

## 1. Output-Quality Metric Taxonomy

| Metric | Needs | Catches | Judged? |
|---|---|---|---|
| Faithfulness / groundedness | response + retrieved context | Hallucination: claims not supported by the context | Yes |
| Answer / response relevance | input + response | Off-topic, evasive, or partial answers | Yes (+ embeddings in some impls) |
| Correctness vs reference | response + reference answer | Plain wrong answers, even when fluent and grounded | Yes, or code check when the answer is structured |
| Context precision | input + retrieved contexts (+ reference) | Retrieval returning junk; relevant chunks ranked low | Yes |
| Context recall | retrieved contexts + reference | Retrieval missing the evidence the answer needs | Yes |
| Completeness / coverage | response + rubric or reference | Right-but-partial answers (omitted required facts) | Yes |
| Format / schema validity | response only | Broken JSON, missing fields, contract violations | **No — code check** |
| Safety / policy compliance | response (+ policy rubric) | Forbidden content, out-of-scope actions described | Yes, plus deterministic denylist first |

Composition rules:

- **Faithfulness and relevance are orthogonal.** A response can be perfectly grounded
  in the context and still not answer the question (faithful, irrelevant), or answer
  the question with fabricated facts (relevant, unfaithful). Gate on both.
- **Retrieval metrics before generation metrics.** If context precision/recall is low,
  faithfulness and relevance scores describe the wrong problem — fix retrieval first
  (this is why the SKILL.md default gates put context metrics at >= 0.75).
- **Code checks before judges.** Schema validity, required fields, forbidden strings,
  and length limits are free and deterministic; running a judge on a response that
  fails schema validation wastes judge budget on a known failure.

---

## 2. LLM-Judge Design

A judge is a measurement instrument. Design it like one:

1. **Structured output, never prose.** The judge returns JSON matching a fixed schema
   (score, findings, rationale, or claims + verdicts). Use the provider's native
   JSON/structured-output mode when available; parse and validate with code.
2. **Decompose, then aggregate.** For faithfulness-style metrics, extract atomic
   claims first, verify each claim against the context, and compute the score in
   *code* (verified / total). Single-shot "rate this 0-1" scores are noisier and
   hide which claim failed.
3. **Pin the rubric.** Give the judge explicit score anchors with a short example per
   band. Discrete bands (0, 0.25, 0.5, 0.75, 1.0) beat a continuous scale — judges
   cannot reliably distinguish 0.73 from 0.78.
4. **Temperature 0** (or the provider's most deterministic setting), and pin the judge
   model version for the life of a baseline. A judge upgrade is a dataset event:
   re-baseline before comparing new scores to old ones.
5. **Different model family than the system under test** (self-preference bias,
   section 3). Use a current frontier-tier model as the judge — judge quality bounds
   metric quality, so this is the wrong place to economize. Cheaper-tier judges are
   acceptable only after a calibration check (section 4) passes for your domain.
6. **Evidence in, provenance out.** Give the judge everything it needs (context,
   question, response) and nothing that biases it (model name, run metadata, previous
   scores).

### Provider-agnostic faithfulness judge (decompose-then-aggregate)

```python
import json

CLAIM_AUDIT_PROMPT = """You are a strict factual-consistency auditor.

Source context:
{context}

Response under audit:
{response}

Step 1: List every factual claim the response makes, as short standalone sentences.
Step 2: For each claim, answer true if the source context supports it, false if the
context contradicts it or does not contain it.

Return ONLY JSON, no other text:
{{"claims": ["<claim 1>", ...], "verdicts": [true, false, ...]}}
"""

def faithfulness(response: str, context: str, call_judge) -> float:
    """call_judge(prompt) -> str: your BYOK provider call, temperature 0,
    JSON/structured-output mode enabled if the provider supports it."""
    raw = call_judge(CLAIM_AUDIT_PROMPT.format(context=context, response=response))
    data = json.loads(raw)
    verdicts = [bool(v) for v in data.get("verdicts", [])]
    if not verdicts:
        # Zero extractable claims: conventionally scored 1.0 (nothing to be
        # unfaithful about), but flag these rows for human review -- an empty
        # claim list often means the judge failed to parse the response.
        return 1.0
    return sum(verdicts) / len(verdicts)
```

The score arithmetic stays in code; the LLM only does the language task (claim
extraction and per-claim verification). Wrap `json.loads` in retry-once-then-fail
handling; a judge that returns unparseable output should fail the eval run loudly,
not silently score 0.

For rubric metrics (tone, helpfulness, custom criteria), prefer a framework
implementation — DeepEval `GEval` with explicit `evaluation_steps` is exactly this
pattern productized (`deepeval_ragas_api.md` section 1.3).

---

## 3. Judge Bias Table

Every LLM judge exhibits these; mitigate before trusting any gate built on one.

| Bias | Symptom | Mitigation |
|---|---|---|
| Position bias | In pairwise A/B judging, the first (or last) candidate wins too often | Judge both orders and average; flag pairs where order flips the verdict |
| Verbosity / length bias | Longer responses score higher regardless of quality | Rubric line: "length is not quality; penalize padding"; report score-vs-length correlation on the suite; add a conciseness criterion |
| Self-preference bias | Judge favors outputs from its own model family | Judge from a different family than the system under test; rotate judge family periodically |
| Sycophancy / authority bias | Confident or assertive phrasing scores higher than hedged-but-correct | Decompose-then-aggregate (claims don't have tone); rubric anchors with a confident-but-wrong example scored low |
| Central tendency / score clustering | Scores pile up at 0.7-0.8; nothing fails, nothing excels | Discrete score bands with anchor examples; pairwise comparison instead of absolute scoring for close calls |
| Rubric drift | Scores shift over weeks with no system change | Freeze rubric text and judge model version per baseline; re-baseline on any change |

---

## 4. Judge Calibration Procedure

Never gate on an uncalibrated judge. One-time setup per (judge model, rubric, domain):

1. **Sample** ~50 cases stratified across your golden set's slices, including edge
   cases and known-bad outputs. Fewer than 30 tells you nothing.
2. **Human-label** each with the same rubric and the same discrete bands the judge
   uses. Two labelers on at least 20 shared cases; if the humans disagree with each
   other more than 15% of the time, fix the rubric before blaming the judge.
3. **Run the judge** on the same cases, then compute agreement:

```python
def agreement(judge: list, human: list) -> dict:
    """Percent agreement and Cohen's kappa for discrete labels/bands. Stdlib only."""
    n = len(judge)
    po = sum(1 for j, h in zip(judge, human) if j == h) / n
    labels = set(judge) | set(human)
    pe = sum((judge.count(l) / n) * (human.count(l) / n) for l in labels)
    kappa = 1.0 if pe >= 1 else (po - pe) / (1 - pe)
    return {"percent_agreement": round(po, 3), "cohens_kappa": round(kappa, 3)}
```

4. **Acceptance:** percent agreement >= 0.85 or kappa >= 0.6 (kappa matters when one
   band dominates — 90% agreement is meaningless if 90% of cases share one label).
   Below threshold: tighten the rubric anchors, switch judge model, or demote the
   metric from gate to trend-only.
5. **Recalibrate** when any of these change: judge model/version, rubric text, domain
   or dataset version, or when spot checks (re-label 10 judged cases per month)
   start disagreeing.

---

## 5. Golden Dataset Procedure

### Row schema (JSONL — template in `assets/golden-dataset-template.jsonl`)

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable unique id (`g-NNN`); never reuse after deletion |
| `dataset_version` | string | Semver of the dataset this row belongs to |
| `slice` | string | Reporting slice (intent/topic/tool); >= 10 rows per slice you report |
| `difficulty` | string | `standard` \| `edge` \| `adversarial` |
| `input` | string | The user input / task |
| `expected_output` | string or null | Reference answer (null for refusal cases: the expectation is captured by `should_pass` + rubric) |
| `expected_calls` | array | Ordered `{tool, input}` reference trajectory (agents only) |
| `optimal_steps` | int | Step count of a competent reference trajectory |
| `should_pass` | bool | false = correct behavior is refusal/escalation |
| `notes` | string | Provenance: where the case came from, why it exists |

### Sourcing (in priority order)

1. **Production failures** — every triaged production incident becomes a golden row.
   Highest value: these are the mistakes your agent actually makes.
2. **Hand-authored coverage** — one row per documented behavior, tool, and policy
   branch; written by someone who knows the domain, not the agent's code.
3. **Synthetic generation** (section 6) — volume filler for breadth, never the
   backbone. Cap synthetic rows at ~50% of the suite.

### Size floors and composition

- 30 rows minimum before gating on anything; 100-300 for stable per-metric means;
  >= 10 rows per slice reported separately.
- **20-30% edge/adversarial:** ambiguous phrasing, out-of-scope requests (correct
  behavior = refuse, `should_pass: false`), prompt-injection attempts, empty and
  oversized inputs, unicode noise, multi-intent inputs.
- **Held-out split (~20%)** never touched while tuning prompts/agents; run weekly and
  report separately. A widening gap between main-suite and held-out scores is the
  overfitting alarm.

### Versioning and maintenance

- Dataset lives in git as JSONL; every row carries `dataset_version`; bump the version
  and write a changelog line for any add/remove/edit.
- **Re-baseline thresholds on every version bump** — scores across dataset versions
  are not comparable, and a "regression" after adding hard cases is the dataset
  working as intended.
- Mine new production failures into the set each sprint; retire rows only when the
  behavior they test is retired (mark deprecated first, delete a version later).
- **Curation gate for any bulk import (synthetic or migrated):** dedupe near-identical
  inputs (normalized-string or embedding similarity), then human spot-check a random
  10% — if more than 1 in 10 sampled rows is wrong or trivial, review the whole batch.

---

## 6. Synthetic Data Generation

Procedure (worked templates in `assets/synthetic-data-templates.md`):

1. **Extract entities and facts** from domain documents: products, policies, limits,
   dates, error codes — anything a real user would ask about. Keep the source span
   for each fact; it becomes the future `retrieval_context` and the faithfulness
   ground truth.
2. **Write query templates per intent** (lookup, comparison, procedure, troubleshoot,
   out-of-scope), each with `{entity}`-style placeholders and an expected-behavior
   note.
3. **Fill the entity x template matrix.** Every (entity, template) cell is a candidate
   case. Generate variants (formal/terse/typo'd phrasing) with an LLM if desired —
   generation may use an LLM; *labeling* the expected output must trace back to the
   source document, not to model knowledge.
4. **Dedupe and spot-check 10% by hand** (curation gate, section 5).
5. **Label** `expected_output` from the source span and, for agents, author
   `expected_calls` + `optimal_steps` per row.

Known failure modes of synthetic sets:

- **Distribution mismatch:** templates produce clean, well-formed questions; real
  users don't. Counter with the typo/terse variants and by keeping production-mined
  rows the backbone.
- **Too-easy bias:** generators ask about facts stated verbatim in the source. Force
  templates that require combining two facts or handling absence ("what is the limit
  for X" where X has no documented limit — correct answer is "not specified").
- **Generator-judge collusion:** if the same model family generates questions and
  judges answers, scores inflate. Use different families, or deterministic labels.

Framework generators (`Synthesizer` in DeepEval, `TestsetGenerator` in Ragas —
`deepeval_ragas_api.md` sections 1.6 and 2.4) automate steps 1-3; the curation gate
and labeling discipline in steps 4-5 remain yours.

---

## 7. Regression Suite Design

A regression suite is a standing `success_predicate` for the system: it defines, in
executable form, what "still works" means.

### Tiers

| Tier | Size | Trigger | Gate |
|---|---|---|---|
| Smoke | ~30 cases, all slices, deterministic metrics preferred | Every PR touching prompts, tools, or agent config | Hard fail (blocks merge) |
| Full | Entire main suite | Nightly + before any release | Hard fail on gate metrics, trend on judge metrics |
| Held-out | ~20% split | Weekly | Alert on main-vs-held-out gap > noise band; never used for tuning |

### Rules

- **The gate decision is deterministic.** Whatever produces the scores (DeepEval,
  Ragas, custom judge), serialize them to the gate schema and let
  `scripts/eval_gate.py` decide pass/fail — one arbiter, framework-swappable, no
  LLM in the CI decision path.
- **Thresholds come from baselines, not aspirations.** Run the suite k >= 5 times on
  the current accepted system; set each gate at (baseline mean - 2 stddev), bounded
  below by the SKILL.md calibrated defaults. Tighten deliberately, never implicitly.
- **Judge metrics gate at the suite level, not per case.** A single judged case is
  too noisy to block a merge; gate the per-metric mean and alert on per-case
  outliers.
- **Flaky-case policy:** a case that flips across runs with no system change is
  quarantined (excluded from the gate, kept in reporting) and filed as an agent bug —
  never deleted, never retried-until-green. Quarantine list must be reviewed at each
  dataset version bump.
- **Every gate change is a reviewed change:** thresholds, dataset version, judge
  model, and rubric text live in git next to the suite; changing any of them goes
  through the same review as changing the agent.

Statistical treatment (pass@k, noise bands, minimum samples):
`agent_trajectory_evaluation.md` section 7. CI wiring example: SKILL.md.

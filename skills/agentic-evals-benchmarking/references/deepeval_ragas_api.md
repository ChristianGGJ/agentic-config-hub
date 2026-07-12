# DeepEval & Ragas: Real API Surfaces

Working API reference for the two frameworks this skill configures. **Version
assumptions:** patterns verified against the **DeepEval 3.x line** and the
**Ragas 0.2/0.3 line** (2025). Both projects move fast — where a member name is
less stable it is marked *(verify against current docs)*. Nothing here is invented;
if a name is not marked, it is a documented, stable surface as of these lines.

**BYOK:** every LLM-based metric in both frameworks needs an evaluator ("judge")
model that you provide — an API key via environment variables, or a custom model
wrapper (both shown below). Local/self-hosted judges work through the same wrappers.
Deterministic metrics (`ToolCorrectnessMetric`, `ToolCallAccuracy` in exact-match
mode) call no LLM.

---

## 1. DeepEval

```bash
pip install deepeval
```

Judge configuration: by default LLM metrics use an OpenAI judge via
`OPENAI_API_KEY`; every metric accepts `model=` — a model-id string or a custom
judge (section 1.6). Prefer a **current frontier-tier model from a different family
than the agent under test** (self-preference bias — see `eval_methodologies.md`).

### 1.1 Test cases

```python
from deepeval.test_case import LLMTestCase, LLMTestCaseParams, ToolCall

test_case = LLMTestCase(
    input="What is the refund window for EU orders?",
    actual_output="EU orders can be refunded within 30 days.",
    expected_output="30 days for EU orders.",          # optional; needed by some metrics
    retrieval_context=["Refund policy: EU orders 30 days ..."],  # RAG metrics
    tools_called=[ToolCall(name="search_policy",
                           input_parameters={"region": "EU"})],  # agent metrics
    expected_tools=[ToolCall(name="search_policy")],
)
```

`ToolCall` carries `name` plus optional `input_parameters`, `output`, `description`
*(field set beyond `name`/`input_parameters`: verify against current docs)*.

### 1.2 Metric catalog (import from `deepeval.metrics`)

| Metric | Judged? | Requires | Measures |
|---|---|---|---|
| `GEval` | LLM | your `evaluation_params` | Any custom rubric criteria |
| `AnswerRelevancyMetric` | LLM | input, actual_output | Output addresses the input |
| `FaithfulnessMetric` | LLM | + retrieval_context | Claims grounded in context |
| `ContextualPrecisionMetric` | LLM | + expected_output, retrieval_context | Relevant chunks ranked high |
| `ContextualRecallMetric` | LLM | + expected_output, retrieval_context | Context covers the reference |
| `HallucinationMetric` | LLM | + context | Contradictions vs provided context |
| `ToolCorrectnessMetric` | **No (deterministic)** | tools_called, expected_tools | Expected tools were called |
| `TaskCompletionMetric` | LLM | input, actual_output, tools_called | Goal achieved given the trajectory |

Common constructor params: `threshold=0.7`, `model="<judge-model-id>"`,
`include_reason=True`. Run one metric standalone:

```python
from deepeval.metrics import FaithfulnessMetric

metric = FaithfulnessMetric(threshold=0.85)
metric.measure(test_case)
print(metric.score, metric.reason, metric.is_successful())
```

### 1.3 GEval — custom rubric metrics

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

correctness = GEval(
    name="Correctness",
    criteria="Determine whether the actual output is factually consistent "
             "with the expected output; penalize omissions of key facts.",
    # or: evaluation_steps=["Extract claims ...", "Check each claim ...", ...]
    evaluation_params=[LLMTestCaseParams.INPUT,
                       LLMTestCaseParams.ACTUAL_OUTPUT,
                       LLMTestCaseParams.EXPECTED_OUTPUT],
    threshold=0.7,
)
```

`criteria` (free-text, DeepEval derives steps) or explicit `evaluation_steps` — prefer
explicit steps for gate metrics: they freeze the rubric so scores stay comparable
across runs (moving-target rubrics never converge).

### 1.4 Agent metrics

```python
from deepeval.metrics import ToolCorrectnessMetric, TaskCompletionMetric

tool_metric = ToolCorrectnessMetric()   # deterministic: expected_tools vs tools_called
# Stricter matching (arg-level, ordering) is configurable via constructor params
# (verify exact parameter names against current docs).

completion = TaskCompletionMetric(threshold=0.7, model="<judge-model-id>")
```

Newer DeepEval versions can also compute agentic metrics from traced components via
an `@observe` decorator instead of hand-built `LLMTestCase`s *(tracing integration:
verify against current docs)*. For strictness variants DeepEval does not expose
(in-order subsequence, per-tool F1), use the stdlib implementations in
`agent_trajectory_evaluation.md` — they need no framework.

### 1.5 Running: pytest gate vs programmatic

```python
# test_agent.py  — run with: deepeval test run test_agent.py
from deepeval import assert_test
def test_refund_answer():
    assert_test(test_case, [FaithfulnessMetric(threshold=0.85), correctness])
```

```python
# programmatic — returns results you can serialize for scripts/eval_gate.py
from deepeval import evaluate
result = evaluate(test_cases=[test_case], metrics=[correctness])
```

Serialize per-metric scores from the result object into the gate schema
(`{"results": [{"metric": ..., "score": ...}]}`) and let `scripts/eval_gate.py`
make the pass/fail decision deterministically in CI.

### 1.6 Datasets, goldens, synthesis

```python
from deepeval.dataset import EvaluationDataset, Golden

dataset = EvaluationDataset(goldens=[
    Golden(input="What is the refund window for EU orders?",
           expected_output="30 days for EU orders."),
])
for golden in dataset.goldens:                      # run your agent per golden
    dataset.add_test_case(LLMTestCase(input=golden.input,
                                      actual_output=my_agent(golden.input),
                                      expected_output=golden.expected_output))
evaluate(test_cases=dataset.test_cases, metrics=[correctness])
```

Synthetic golden generation from documents:

```python
from deepeval.synthesizer import Synthesizer
synth = Synthesizer()   # accepts model= for the generator LLM
goldens = synth.generate_goldens_from_docs(document_paths=["docs/policy.md"])
# also: generate_goldens_from_contexts(contexts=[["chunk 1", "chunk 2"], ...])
```

Post-process synthetic goldens with the curation rules in `eval_methodologies.md`
(dedupe, 10% human spot-check) — generator output is a draft, not a dataset.

### 1.7 Custom judge (BYOK / local models)

```python
from deepeval.models import DeepEvalBaseLLM

class MyJudge(DeepEvalBaseLLM):
    def __init__(self, client): self.client = client
    def load_model(self): return self.client
    def generate(self, prompt: str) -> str: ...        # call your provider
    async def a_generate(self, prompt: str) -> str: ...
    def get_model_name(self) -> str: return "my-judge"

metric = FaithfulnessMetric(threshold=0.85, model=MyJudge(client))
```

---

## 2. Ragas

```bash
pip install ragas
```

Ragas 0.2 moved from function-style metrics plus HF `Dataset` columns to
**class-based metrics plus typed samples**. The legacy 0.1 style
(`from ragas.metrics import faithfulness, answer_relevancy` + a dataset with
`question/answer/contexts/ground_truth` columns) still appears in older tutorials —
prefer the 0.2+ surface below.

### 2.1 Samples and datasets

```python
from ragas import SingleTurnSample, EvaluationDataset

sample = SingleTurnSample(
    user_input="What is the refund window for EU orders?",
    retrieved_contexts=["Refund policy: EU orders 30 days ..."],
    response="EU orders can be refunded within 30 days.",
    reference="30 days for EU orders.",     # ground truth; needed by *WithReference metrics
)
dataset = EvaluationDataset(samples=[sample])
```

### 2.2 RAG metrics and evaluate()

```python
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,                        # response grounded in retrieved_contexts
    ResponseRelevancy,                   # response addresses user_input
    LLMContextPrecisionWithReference,    # retrieved chunks relevant, ranked well
    LLMContextRecall,                    # contexts cover the reference
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

evaluator_llm = LangchainLLMWrapper(your_langchain_chat_model)   # BYOK judge
result = evaluate(
    dataset=dataset,
    metrics=[Faithfulness(), ResponseRelevancy(),
             LLMContextPrecisionWithReference(), LLMContextRecall()],
    llm=evaluator_llm,
    embeddings=LangchainEmbeddingsWrapper(your_embeddings),  # ResponseRelevancy needs it
)
df = result.to_pandas()   # per-sample scores -> serialize for scripts/eval_gate.py
```

`your_langchain_chat_model` is any LangChain chat model — pick a current
frontier-tier judge from your provider; do not hard-code deprecated model ids.
Naming note: `ResponseRelevancy` is the 0.2 name for the metric older docs call
`answer_relevancy`.

### 2.3 Agent evaluation — MultiTurnSample and agent metrics

This is the Ragas surface that matters for this skill's core: trajectory-aware
metrics over multi-turn, tool-calling interactions.

```python
from ragas import MultiTurnSample
from ragas.messages import HumanMessage, AIMessage, ToolMessage, ToolCall
from ragas.metrics import (
    ToolCallAccuracy,                 # deterministic-by-default trajectory match
    AgentGoalAccuracyWithReference,   # LLM-judged: did it achieve the stated goal?
    AgentGoalAccuracyWithoutReference,
    TopicAdherenceScore,              # stays within allowed topic domains
)

sample = MultiTurnSample(
    user_input=[
        HumanMessage(content="Book a table for two at 8pm at Nadro."),
        AIMessage(content="Checking availability.",
                  tool_calls=[ToolCall(name="check_availability",
                                       args={"restaurant": "Nadro", "time": "20:00"})]),
        ToolMessage(content="Slot available."),
        AIMessage(content="Booked your table for two at 20:00."),
    ],
    reference_tool_calls=[ToolCall(name="check_availability",
                                   args={"restaurant": "Nadro", "time": "20:00"})],
    reference="Table booked at Nadro for 2 at 20:00",   # for goal accuracy
)

scorer = ToolCallAccuracy()
score = await scorer.multi_turn_ascore(sample)          # async API

goal = AgentGoalAccuracyWithReference(llm=evaluator_llm)
goal_score = await goal.multi_turn_ascore(sample)
```

Notes:

- `ToolCallAccuracy` compares the AI messages' `tool_calls` against
  `reference_tool_calls` — exact name+args by default; argument comparison is
  configurable *(configuration attribute name: verify against current docs)*.
- `TopicAdherenceScore(llm=..., mode="precision")` needs `reference_topics` on the
  sample; use it to eval scope discipline (the eval-side view of the hub's boundary
  rules).
- Metric scoring is async (`multi_turn_ascore` / `single_turn_ascore`); batch
  `evaluate()` also accepts multi-turn samples with these metrics.

### 2.4 Synthetic test set generation

```python
from ragas.testset import TestsetGenerator

generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)
testset = generator.generate_with_langchain_docs(documents, testset_size=50)
df = testset.to_pandas()
```

*(Constructor parameter names moved between 0.1 and 0.2 — verify `llm` /
`embedding_model` against current docs.)* Same curation rule as DeepEval's
Synthesizer: generated sets are drafts; apply the golden-dataset procedure in
`eval_methodologies.md` before gating on them.

---

## 3. Cross-Framework Mapping

| Concept (this skill) | DeepEval | Ragas | Stdlib fallback |
|---|---|---|---|
| Faithfulness / grounding | `FaithfulnessMetric` | `Faithfulness` | judge pattern in `eval_methodologies.md` |
| Answer relevance | `AnswerRelevancyMetric` | `ResponseRelevancy` | — |
| Retrieval precision / recall | `ContextualPrecisionMetric` / `ContextualRecallMetric` | `LLMContextPrecisionWithReference` / `LLMContextRecall` | — |
| Custom rubric | `GEval` | general-purpose metrics (e.g. rubric/aspect-style; verify current names) | judge pattern |
| Tool-call correctness | `ToolCorrectnessMetric` | `ToolCallAccuracy` | `agent_trajectory_evaluation.md` sec 2 |
| Task completion | `TaskCompletionMetric` | `AgentGoalAccuracyWith/WithoutReference` | success predicate (sec 4) |
| Golden datasets | `EvaluationDataset` + `Golden` | `EvaluationDataset` + samples | JSONL per `eval_methodologies.md` |
| Synthetic generation | `Synthesizer` | `TestsetGenerator` | template matrix in `assets/` |
| CI pass/fail gate | `assert_test` + `deepeval test run` | serialize `evaluate()` output | `scripts/eval_gate.py` (always the final arbiter) |

Selection guidance lives in SKILL.md (Decision Framework 3). Whichever framework
produces the scores, route the final gate decision through `scripts/eval_gate.py`:
it is deterministic, dependency-free, and keeps the CI contract stable if you swap
frameworks later.

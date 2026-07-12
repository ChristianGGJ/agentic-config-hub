# Agentic & Advanced RAG Patterns

Classic RAG is a straight line: embed query -> retrieve top-k -> stuff context -> generate.
It fails predictably when the query is ambiguous, the corpus is incomplete, the answer
spans multiple documents, or retrieval quality varies per query. The patterns in this
reference add *decision-making* around retrieval. Each section covers: what the pattern
is, when to use it, how it works, and its failure modes.

Rule of thumb: **every pattern here adds latency and cost**. Adopt the cheapest pattern
that fixes your measured failure mode (see `references/rag_evaluation_framework.md`),
not the most impressive one.

---

## 1. Agentic RAG (retrieval as a tool in an agent loop)

### What it is
Instead of a fixed retrieve-then-generate pipeline, an LLM agent decides *whether*,
*what*, and *how many times* to retrieve. Retrieval becomes one or more tools
(vector search, keyword search, SQL, web search, API lookups) the agent invokes while
reasoning. The agent can reformulate queries, pick between sources, and judge whether
retrieved evidence is sufficient before answering.

### When to use
- Heterogeneous sources (vector DB + SQL + APIs + web) where source *selection* matters.
- Queries with high variance: some need zero retrieval (chitchat, general knowledge),
  some need several rounds.
- Conversational systems where follow-up questions need query rewriting against history.

### When NOT to use
- Homogeneous corpus + single-shot factual queries: a tuned classic pipeline with
  reranking is cheaper, faster, and easier to evaluate.
- Hard latency budgets (< ~2 s end-to-end): each agent decision is an extra LLM call.

### How it works (framework-agnostic loop)

```
loop (bounded):
    decide: answer directly | retrieve(source, query) | reformulate | give up
    if retrieve: run tool, append evidence to working context
    if evidence judged sufficient: generate answer with citations
```

Implementation vehicles: any tool-calling agent runtime (e.g. LangGraph cyclic graphs,
or plain tool-use loops over a provider SDK). The pattern is the loop-with-judgment,
not any specific framework API.

### Loop safety (hub canon — non-negotiable)
An agentic RAG loop is an autonomous loop and must declare exit conditions from the
six-type taxonomy before it runs: `max_iterations` (typical: 3-5 retrieval rounds),
`no_progress` (same evidence set two rounds in a row), `oscillation` (alternating
between the same two query reformulations), `budget` (token/tool-call ceiling),
`success_predicate` (evidence-sufficiency check passed), `escalation_trigger`
(fall back to "I could not find grounded evidence" + best partial answer).
See also `agentic-system-architect` (references/loop_engineering_patterns.md) for the
full taxonomy and detector implementations.

### Failure modes
| Failure | Symptom | Mitigation |
|---|---|---|
| Retrieval avoidance | Agent answers from parametric memory, hallucinating | Require citations; instruct "must retrieve for factual claims"; verify groundedness post-hoc |
| Query thrashing | Agent reformulates endlessly without converging | `oscillation` + `max_iterations` guards; log query history into the prompt so it sees its own repeats |
| Tool-choice bias | Agent always picks the same source | Route by source descriptions with explicit selection criteria; evaluate per-source recall |
| Context flooding | Each round appends full chunks until the window drowns | Summarize/compress evidence between rounds; cap evidence tokens per round |
| Cost blowup | 5x LLM calls per user query | `budget` exit condition; route simple queries to the classic pipeline first (a router in front of the agent) |

---

## 2. Self-RAG (self-reflective retrieval and generation)

### What it is
A pattern from the Self-RAG paper (Asai et al., 2023): the model critiques its own
process at each step — *should I retrieve?*, *is this passage relevant?*, *is my
answer supported by the passage?*, *is the answer useful?*. The original paper trains
a model to emit special reflection tokens; in practice most teams implement the same
control flow with prompted critique steps instead of trained tokens.

### When to use
- Groundedness matters more than latency (compliance answers, medical/legal drafting).
- Mixed query stream where many queries need no retrieval at all — the "should I
  retrieve?" gate saves cost on those.

### How it works (prompted approximation)

```
1. Gate:      LLM judges "does this query need retrieval?"  -> no: answer directly
2. Retrieve:  top-k candidates
3. Filter:    LLM grades each candidate relevant/irrelevant (drop irrelevant)
4. Generate:  answer from surviving passages
5. Verify:    LLM checks answer-passage entailment (supported / partially / not)
6. If unsupported: regenerate or re-retrieve (bounded — this is a loop; declare
   exit conditions per hub canon)
```

### Failure modes
- **Self-grading bias**: the same model that generated the answer grades it as
  supported. Mitigate with a different model for the verify step, or an NLI
  cross-check; calibrate the grader against a small labeled set.
- **Gate false negatives**: "no retrieval needed" on a query that did need it —
  monitor the gate's decision distribution; a gate that answers "no retrieval" > ~50%
  of the time on a knowledge workload is miscalibrated.
- **Latency multiplication**: 3-4 extra LLM calls per query. Grade candidates in a
  single batched call, not one call per passage.

---

## 3. CRAG (Corrective RAG)

### What it is
Corrective RAG (Yan et al., 2024) adds a lightweight *retrieval evaluator* that scores
retrieved documents and branches on the score:
- **Correct** (high confidence): refine the passages (decompose-then-recompose:
  strip irrelevant sentences) and generate.
- **Incorrect** (low confidence): discard retrieval and fall back to an alternative
  source — in the paper, web search with rewritten queries.
- **Ambiguous** (middle): combine both refined passages and fallback results.

### When to use
- Corpus is known to be *incomplete* for the query domain (fallback path earns its keep).
- You can afford a small evaluator model (the paper uses a fine-tuned lightweight
  evaluator; a prompted utility-tier LLM grader is the common substitute).

### When NOT to use
- No acceptable fallback source exists (air-gapped corpora): then CRAG degenerates to
  Self-RAG-style filtering — use that instead.

### Failure modes
- **Evaluator miscalibration**: thresholds for correct/ambiguous/incorrect are
  corpus-specific; tune on a labeled sample, re-check after corpus changes.
- **Fallback trust**: web fallback reintroduces unvetted content — treat it as
  untrusted input (indirect injection vector; see also `agentic-guardrails-security`).
- **Refinement overpruning**: sentence-level stripping can delete the qualifying
  context that made a fact true. Keep refinement conservative for legal/medical text.

---

## 4. GraphRAG (knowledge-graph-augmented retrieval)

### What it is
Instead of (or alongside) a vector index, build a knowledge graph from the corpus.
The reference implementation is Microsoft GraphRAG: LLM-extracted entities and
relations -> graph -> community detection (Leiden) -> pre-computed community
summaries at multiple levels. Two query modes:
- **Local search**: start from entities matched in the query, walk their
  neighborhoods, combine graph facts with raw text chunks.
- **Global search**: map-reduce over community summaries — answers "whole-corpus"
  questions ("what are the main themes across these filings?") that top-k chunk
  retrieval structurally cannot answer.

### When to use
- **Global/sensemaking questions** over a corpus (themes, trends, cross-document
  synthesis) — the headline use case.
- **Entity-centric corpora** with dense cross-references (contracts, org data,
  investigations, codebases): multi-hop relations are explicit edges instead of
  hoped-for chunk co-retrieval.

### When NOT to use
- Simple factual Q&A over homogeneous docs — vector + reranking wins on cost by an
  order of magnitude.
- Rapidly changing corpora: index build is LLM-intensive (every chunk passes through
  entity extraction) and incremental updates are the weak spot.

### Failure modes
| Failure | Symptom | Mitigation |
|---|---|---|
| Extraction cost blowup | Indexing bill >> query bill | Use a utility-tier model for extraction; index only entity-rich subsets; hybrid: graph for entities, vectors for the rest |
| Entity resolution errors | "Acme Corp" and "ACME Inc." become two nodes; hops silently break | Canonicalization pass + alias table; evaluate entity dedup explicitly |
| Stale graph | Answers reflect last index build | Schedule rebuilds; route freshness-sensitive queries to vector/live sources |
| Summary hallucination | Community summaries drift from sources | Keep provenance links from summaries to source chunks; spot-check with groundedness evals |

---

## 5. Multi-hop retrieval

### What it is
Answering questions whose evidence spans multiple documents connected by intermediate
facts ("Who managed the fund that acquired the company founded by X?"). One retrieval
round cannot fetch hop 2 because its query terms only exist in hop 1's results.

### Techniques (cheapest first)
1. **Query decomposition**: LLM splits the question into sub-questions, answered
   sequentially, each conditioning the next retrieval. Simple, debuggable; fails when
   decomposition requires knowledge you don't have yet.
2. **Iterative retrieve-and-read (IRCoT-style)**: interleave chain-of-thought
   reasoning with retrieval — after each reasoning step, use the newest reasoning
   sentence as the next retrieval query. Handles decompositions discovered mid-flight.
3. **Graph traversal**: if you have GraphRAG (section 4), multi-hop becomes edge
   walking — the most reliable option when the hops are entity relations.
4. **Full agentic loop** (section 1): the general case; use when hops mix source types.

### Failure modes
- **Error compounding**: a wrong hop-1 answer poisons every later hop. Retrieve top-k
  (not top-1) per hop and carry alternatives; verify intermediate answers against
  their passages before proceeding.
- **Unbounded hop count**: cap hops (`max_iterations`, typical 3) and fire
  `no_progress` when a hop retrieves an evidence set already seen.
- **Sub-question drift**: decomposed questions lose the original constraint
  (dates, jurisdictions). Re-inject the original question into every hop prompt.

---

## 6. Pattern selection table

| Measured failure | Reach for | Cost delta vs classic RAG |
|---|---|---|
| Right doc retrieved but buried below top-k | Reranking (see SKILL.md sec 4) — not an agentic pattern | +1 small model call |
| Retrieval runs when it should not (or vice versa) | Self-RAG gate | +1 LLM call on gated queries |
| Irrelevant passages pollute context | Self-RAG grading / CRAG refinement | +1-2 LLM calls |
| Corpus incomplete for some queries | CRAG with fallback source | +1 grader call, + fallback path |
| Questions span docs via entities | GraphRAG local search or graph traversal | High indexing cost, moderate query cost |
| Whole-corpus synthesis questions | GraphRAG global search | High indexing cost, high query cost |
| Multi-step questions, evidence chains | Query decomposition -> IRCoT -> agentic loop (escalate in that order) | +N LLM calls (N = hops) |
| Heterogeneous sources, high query variance | Full agentic RAG | Highest; route simple queries around it |

## 7. Evaluation notes for agentic pipelines

Classic RAG metrics (context precision/recall, faithfulness, answer relevance) still
apply, but add *trajectory-level* checks: retrieval-decision accuracy (did it retrieve
when it should have?), hops-to-answer distribution, exit-condition firing rates
(a rising `max_iterations` rate means the loop is being cut off, not converging),
and per-query cost. Log every retrieval decision with its inputs — an agentic pipeline
you cannot replay is a pipeline you cannot debug. See also `agentic-evals-benchmarking`
for trajectory evaluation methodology.

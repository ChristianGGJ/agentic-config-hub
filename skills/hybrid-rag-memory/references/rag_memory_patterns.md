# Hybrid Retrieval Over Agent Memories

Patterns for retrieving stored memories with combined lexical + dense search, fusing
the two arms with Reciprocal Rank Fusion (RRF), sizing memory entries, keeping thread
state durable, and measuring whether the memory system actually works.

Scope note: this reference covers hybrid retrieval **over memory stores** (small,
namespaced, per-tenant entries). Hybrid retrieval as part of a document-RAG pipeline —
corpus chunking, rerankers, embedding model benchmarks — is owned by the sibling skill
`rag-architect`; the fusion math is the same, the workload tuning differs.

---

## 1. When hybrid beats pure-dense (and when it does not)

Dense embeddings excel at paraphrase and concept matching but blur exact tokens; BM25
excels at exact tokens and fails on paraphrase. Memory queries are unusually heavy on
exact tokens (names, IDs, error codes), which is why hybrid is the default here.

| Query class | Pure dense | Hybrid (BM25 + dense + RRF) |
|---|---|---|
| "what are the user's UI preferences?" | Good | Equal (fusion adds nothing) |
| "what happened with ticket ABC-1234?" | Often misses | Wins — lexical arm pins the ID |
| "errors like ECONNRESET on deploy" | Partial | Wins — error codes are lexical |
| One-word queries ("proxmox") | Weak | Wins — BM25 carries short queries |
| Cross-lingual recall | Wins (multilingual embedder) | Lexical arm contributes ~nothing |

Costs of hybrid: a second index to maintain, a second query per retrieval, and a new
failure mode (noisy lexical fields dragging fusion down — index only the memory text,
see `references/vector_schema_examples.md` section 4). If offline evaluation (section 5
below) shows dense-only recall@5 >= 0.9 on your real query mix, skip hybrid.

Prefer **server-side fusion** when the backend offers it (Azure AI Search hybrid
queries, Qdrant `FusionQuery(RRF)` — schemas and query bodies in
`references/vector_schema_examples.md`). Implement client-side RRF only when the arms
live in different engines (e.g. Postgres FTS + a separate vector store).

---

## 2. Reciprocal Rank Fusion (client-side implementations)

RRF ignores raw scores (which are not comparable across BM25 and cosine space) and
fuses by rank: `score(d) = sum over arms of 1 / (k + rank_arm(d))`, with k = 60 as the
standard constant. Larger k flattens the influence of top ranks; k between 10 and 100
rarely changes top-5 materially — tune only with evaluation data.

### 2.1 Python (stdlib only)

```python
def rrf_fuse(result_lists, k=60, weights=None):
    """Fuse ranked lists of document ids. result_lists: list of lists of ids,
    each ordered best-first. weights: optional per-arm multipliers (default 1.0)."""
    weights = weights or [1.0] * len(result_lists)
    scores = {}
    for arm, ranked_ids in enumerate(result_lists):
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weights[arm] * (1.0 / (k + rank))
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

fused = rrf_fuse([dense_ids, bm25_ids])          # equal weighting (default)
top5  = [doc_id for doc_id, _ in fused[:5]]
```

Weighted RRF (`weights=[1.0, 0.5]` to soften the lexical arm) is the first knob to try
if evaluation shows one arm polluting results; keep equal weights until measured.

### 2.2 C# / .NET

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public sealed class SearchResult
{
    public string DocumentId { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
    public double Score { get; set; }
}

public static class RrfFusion
{
    private const double K = 60.0;

    public static List<SearchResult> Fuse(params List<SearchResult>[] rankedArms)
    {
        var scores = new Dictionary<string, double>();
        var docs = new Dictionary<string, SearchResult>();

        foreach (var arm in rankedArms)
        {
            for (int i = 0; i < arm.Count; i++)
            {
                var doc = arm[i];
                double contribution = 1.0 / (K + (i + 1));
                scores[doc.DocumentId] =
                    scores.TryGetValue(doc.DocumentId, out var s) ? s + contribution
                                                                  : contribution;
                docs.TryAdd(doc.DocumentId, doc);
            }
        }

        return scores
            .Select(kvp => new SearchResult
            {
                DocumentId = kvp.Key,
                Content = docs[kvp.Key].Content,
                Score = kvp.Value,
            })
            .OrderByDescending(r => r.Score)
            .ToList();
    }
}
```

Retrieve top-20 from each arm, fuse, keep top-5 for context injection. Injecting more
than ~5 memories per turn measurably degrades answer focus before it improves recall.

---

## 3. Sizing memory entries (chunking for memory vs documents)

Document chunking (200-800 token chunks, 10-20% overlap, structure-aware splits) is
`rag-architect` territory. Memory entries follow different rules because they are
*authored at write time*, not split from a corpus:

| Property | Document chunk | Memory entry |
|---|---|---|
| Size | 200-800 tokens | 50-200 tokens |
| Overlap | 10-20% | None — entries are atomic |
| Unit | Passage of a source doc | One fact / one episode summary |
| Produced by | Splitter over ingested files | Write policy (dedup + summarize) |
| Update model | Re-ingest on source change | Update-in-place by stable key |

Rules: one fact per entry (a compound entry can only be retrieved whole, dragging
irrelevant halves into context); resolve pronouns and relative dates at write time
("the user" -> the name, "yesterday" -> ISO date) because the entry will be read
without its original context; store provenance in metadata, not in the embedded text.

---

## 4. Durable thread state (checkpointer setup)

**Framing (important):** the checkpointer below persists *thread/session state* so a
service restart does not lose in-flight conversations. It is NOT long-term memory —
the long-term layer is the Store API and friends, covered in
`references/memory_apis.md`. Presenting checkpointers as "long-term memory sync" is
the exact conflation this skill exists to prevent.

As of LangGraph 1.x, `InMemorySaver` loses state on restart; production services use
the Postgres checkpointer (package `langgraph-checkpoint-postgres`):

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:password@localhost:5432/agent_state"

# Context-manager form (recommended)
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # one-time: creates checkpoint tables
    app = workflow.compile(checkpointer=checkpointer)
    app.invoke(inputs, config={"configurable": {"thread_id": "thread-42"}})
```

For pooled connections, construct with a `psycopg_pool.ConnectionPool` instead of a
conn string; an async twin `AsyncPostgresSaver` exists for async graphs. Checkpoint
rows accumulate per thread — apply the retention defaults from `SKILL.md` (delete or
archive by `thread_id` after 30-90 days idle), and record thread-to-user ownership at
creation time so user erasure can find these rows (`references/memory_apis.md`
section 6).

Microsoft Agent Framework achieves the same durability by serializing `AgentThread`
into your own database; CrewAI persists its layers to local storage — both covered in
`references/memory_apis.md`.

---

## 5. Measuring memory quality

A memory system without metrics degrades silently: retrieval gets noisier as the store
grows, and nobody notices until the agent confidently recalls the wrong thing.

### 5.1 Offline probe set (the core instrument)

Maintain a small versioned probe set (30-100 items) of `(query, expected_memory_key)`
pairs drawn from real usage — including identifier-style queries and paraphrase-style
queries in realistic proportion. After any change (embedder, fusion weights, BM25
params, eviction policy), run:

- **recall@k** (k=5): fraction of probes whose expected memory appears in the fused
  top-k. Gate: >= 0.9. This is the deterministic success_predicate for retrieval
  changes.
- **mrr** (mean reciprocal rank): sensitivity to ordering; watch for drops even when
  recall@k holds.
- **arm attribution**: for each hit, which arm(s) ranked it — if the lexical arm never
  contributes, drop hybrid; if it dominates identifier queries only, that is working
  as designed.

The probe run is pure arithmetic over retrieval results — no LLM judge required. Wire
it into CI for the memory service; failures block deploys the same way `loop_auditor`
gates agent specs (see hub canon in `SKILL.md`).

### 5.2 Online counters

| Metric | Definition | Alarm signal |
|---|---|---|
| Memory hit rate | Turns where >= 1 retrieved memory passed the relevance cut / turns that queried memory | Sustained drop = staleness or embedder drift |
| Injection utilization | Retrieved memories actually referenced in the answer (heuristic: key-entity overlap) | Persistently low = retrieving noise, tighten top-k or write policy |
| Write acceptance | Writes committed / write candidates (post-dedup) | Near-zero = dedup too aggressive; near-one = dedup broken |
| Store growth vs hit rate | Entries per namespace over time against hit rate | Growth with flat hits = transcript anti-pattern returning |

Cross-session fact retention — "does the agent still know X next week?" — is tested by
replaying the probe set on a schedule, not by trusting the write path. For richer
LLM-judged evaluation harnesses, route to the `agentic-evals-benchmarking` sibling;
this skill's metrics are deliberately deterministic.

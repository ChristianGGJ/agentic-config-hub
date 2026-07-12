---
name: "hybrid-rag-memory"
description: "Use when designing agent memory: short-term thread state vs long-term stores, vector DB schemas (pgvector/Qdrant/Azure AI Search), hybrid BM25+dense retrieval over memories, and cross-session persistence in LangGraph, CrewAI, or Microsoft Agent Framework."
---

# Skill: hybrid-rag-memory

## Overview

This skill designs **memory and persistence** for agentic systems: what an agent
remembers, where it is stored, how it is retrieved, and when it is forgotten. It covers
the memory taxonomy (short-term vs long-term; semantic/episodic/procedural), the real
framework memory APIs (LangGraph checkpointers vs Store, CrewAI memory, Microsoft Agent
Framework threads and context providers), concrete vector database schemas, and hybrid
lexical+dense retrieval over stored memories.

**Ownership boundary:** this skill owns MEMORY and PERSISTENCE. Document-RAG pipeline
design — corpus chunking, embedding model selection, reranking, ingestion — is owned by
the sibling skill `rag-architect`. Both skills use RRF-style hybrid fusion; the version
here is specialized to memory workloads (small atomic entries, per-tenant namespaces),
and each side stays self-contained.

## Memory Taxonomy (read this first)

The single most common design error is conflating session state with long-term memory.
They have different scopes, backends, and lifecycles:

| Layer | Scope | Typical backend | Lifecycle | Framework surface |
|---|---|---|---|---|
| **Short-term (thread)** | One conversation/run | Checkpointer tables (Postgres/SQLite) or in-process | Lives with the thread; replayable; discard or archive when the thread ends | LangGraph checkpointer; MAF `AgentThread`; CrewAI short-term memory |
| **Long-term (store)** | Cross-thread, cross-session | Vector store / KV store with namespaces | Survives restarts and threads; needs write policy + eviction | LangGraph Store API; CrewAI long-term memory; MAF context providers |
| **Entity** | Facts keyed to a person/org/thing | Structured rows or namespaced KV | Updated in place; superseded facts overwritten or versioned | CrewAI entity memory; custom namespaces elsewhere |

Within long-term memory, distinguish content types — they demand different schemas:

- **Semantic memory** — facts and preferences ("user prefers dark mode", "deploys go
  through staging"). Small atomic entries, embedded for similarity search, deduplicated.
- **Episodic memory** — records of what happened ("on run 41 the migration failed with
  X"). Append-only, timestamped, queried by recency + similarity, aggressively evicted.
- **Procedural memory** — learned rules of behavior ("always run lint before commit").
  Few, high-value, usually promoted into system prompts or instructions rather than
  retrieved per-query.

**Lifecycle rule of thumb:** thread state is *checkpointed* (automatic, every step);
long-term memory is *curated* (explicit writes, dedup, eviction). If a write happens on
every message with no curation policy, you are building a transcript, not a memory.

## Core Capabilities

1. **Memory architecture design** — choose layers, backends, and namespaces for a given
   multi-agent system and tenancy model.
2. **Vector schema authoring** — pgvector DDL, Azure AI Search index JSON, Qdrant
   collection configs, with index-type and parameter defaults
   (see `references/vector_schema_examples.md`).
3. **Framework memory wiring** — LangGraph checkpointer + Store, CrewAI memory
   configuration, MAF thread serialization and context providers
   (see `references/memory_apis.md`).
4. **Hybrid retrieval over memories** — BM25 + dense fusion with RRF, and the decision
   rule for when hybrid beats pure-dense (see `references/rag_memory_patterns.md`).
5. **Write/eviction policy design** — what to store, when to summarize, how to
   deduplicate, TTL and deletion procedures (including user-data erasure).
6. **Memory lifecycle & learning** — the eviction/consolidation policy that fights
   context noise, and procedural memory (self-authored skill/tool registries)
   (see the *Memory Lifecycle & Learning* section below).

## Decision Frameworks

### Backend selection

| Situation | Default choice | Why | Reconsider when |
|---|---|---|---|
| Already running Postgres | **pgvector** (+ `tsvector` for lexical) | One database for state, memory, and search; transactional writes | > ~10M vectors per tenant or heavy ANN QPS — move vectors to a dedicated engine |
| Azure-native stack / MAF | **Azure AI Search** | Managed hybrid (BM25 + vector + RRF) out of the box | Cost-sensitive small deployments — pgvector is cheaper |
| Dedicated vector workload, self-hosted | **Qdrant** | Named dense+sparse vectors per point, server-side RRF fusion, payload filters | Team has no ops capacity — prefer managed |
| Prototype / single process | LangGraph `InMemoryStore` or SQLite | Zero infrastructure | Anything multi-instance or restart-sensitive |

### Hybrid vs pure-dense retrieval

| Signal in your memory queries | Verdict |
|---|---|
| Exact identifiers: ticket IDs, SKUs, error codes, usernames, version strings | **Hybrid required** — embeddings blur exact tokens |
| Domain jargon or codenames unlikely to be in the embedding model's training data | **Hybrid required** |
| Purely conceptual recall ("what does the user like?") | Pure dense is fine; hybrid adds latency for little gain |
| Short queries (1-3 words) | Hybrid — BM25 carries short queries better |
| Multilingual memories with a strong multilingual embedder | Dense-first; add lexical only if IDs appear |

Calibrated defaults: RRF constant k=60; retrieve top-20 from each retriever, fuse, keep
top-5 for context injection; equal weighting unless offline evaluation says otherwise.

### Memory write policy

| Policy | When to use | Cost profile |
|---|---|---|
| **Hot-path write** (agent writes memory during the turn) | Explicit user statements ("remember that..."), critical corrections | Adds latency + tokens to every turn; keep to 0-1 writes/turn |
| **Background reflection** (batch job summarizes threads into memories) | Preference inference, episodic summaries, dedup passes | Deferred cost; run per-thread-close or on a schedule with a hard budget |
| **Write-through entity update** | Structured facts with a natural key (user profile fields) | Cheap; overwrite in place, keep `updated_at` |

Always: deduplicate before write (reject new entry if cosine similarity to an existing
memory in the same namespace exceeds ~0.9 — tune per embedder), summarize episodic runs
instead of storing transcripts, and record provenance (`source_thread_id`, timestamp).

### Eviction and retention defaults

| Memory type | Default retention | Eviction trigger |
|---|---|---|
| Thread checkpoints | 30-90 days after last activity | Archive or delete by `thread_id` |
| Episodic memories | Keep last N=100 per namespace + summaries of the rest | Count cap, then summarize-and-delete |
| Semantic memories | Indefinite while referenced | Superseded-fact overwrite; staleness review when hit rate ~ 0 |
| User-requested erasure | Immediate | Delete by user namespace across ALL layers (checkpoints included) — see `references/memory_apis.md` |

## Memory Lifecycle & Learning

Storage is only half of memory design; the other half is the LIFECYCLE — how memory is
aged, consolidated, evicted, and grown into new capability. The load-bearing thesis is
that **more memory is not better**: past a point, extra context becomes *noise* that
degrades retrieval precision (context rot / lost-in-the-middle), so a memory system is
defined as much by what it drops as by what it keeps. Two references (and one tool) cover
this layer without repeating the storage/taxonomy content above: `references/memory_eviction_and_consolidation.md`
gives the two-track eviction picture (real framework levers — LangGraph/LangMem store TTL
and `refresh_on_read`, Mem0 fused/temporal scoring, MemGPT/Letta paging + sleep-time
compute, LlamaIndex `token_flush_size`/block `priority`, rerank-before-inject — and their
git-native static analogs) plus a concrete 8-rule eviction policy and a composite
keep/evict score; `references/procedural_memory_skill_registries.md` frames the hub's own
`skills/` directory as a governed, Voyager-style procedural-memory registry where adding a
skill = registering a capability, but human-gated, audited, and versioned. The deterministic
tool `scripts/memory_evictor.py` plans eviction over a JSONL store on the age/recency/
frequency/pinned axes (semantic relevance is a runtime concern, delegated to `rag-architect`).
Safety rule: an eviction/consolidation pass never autonomously drops a pinned safety rule or
a crystallized boundary — those are removed only through the Phase-3 HUMAN GATE.

## Framework Surfaces (summary)

Full runnable examples live in `references/memory_apis.md`. The one-line map:

- **LangGraph** (as of LangGraph 1.x): checkpointer (`InMemorySaver` / `SqliteSaver` /
  `PostgresSaver`) = thread state; Store API (`BaseStore` / `InMemoryStore` /
  `PostgresStore` with namespaced `put`/`get`/`search` and optional semantic index) =
  long-term memory. Compile with BOTH: `graph.compile(checkpointer=..., store=...)`.
- **CrewAI** (as of CrewAI 0.1xx, 2025): `Crew(memory=True)` enables short-term +
  long-term + entity memory; stock backends are ChromaDB (RAG layers) and SQLite
  (long-term) — Qdrant is NOT a stock CrewAI memory backend. Custom paths via
  `LongTermMemory(storage=LTMSQLiteStorage(db_path=...))`; embedder via `embedder={...}`.
- **Microsoft Agent Framework** (public preview, 2025): conversation state lives in
  `AgentThread` (serialize/deserialize for persistence); long-term memory is injected
  via context providers (`AIContextProvider`) and custom chat-message stores. The old
  Semantic Kernel `IMemoryStore` is legacy and must not be used with MAF.

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| "Long-term memory" vanishes when a new conversation starts | Memories were written to the checkpointer (thread-scoped), not a store | Move cross-session facts to the Store layer; checkpointer keeps only thread state |
| Memory retrieval returns near-duplicates of the same fact | No dedup on write | Add similarity-threshold dedup + periodic merge pass |
| Agent recalls another user's data | Namespace/filter missing on the read path | Enforce tenant namespace in EVERY query (store namespace tuple, Qdrant payload filter, AI Search `$filter`); add a cross-tenant test |
| Exact ID lookups fail ("ticket ABC-1234 not found" though stored) | Pure-dense retrieval blurring identifiers | Add lexical arm + RRF fusion (see decision table above) |
| Memory store grows unbounded; retrieval gets slower and noisier | Transcript-as-memory anti-pattern, no eviction | Adopt write policy (summarize + dedup) and eviction defaults |
| State lost on service restart | In-memory saver/store in production | `PostgresSaver` + `PostgresStore` (or managed equivalents); call `.setup()` once |
| Fusion returns worse results than dense alone | Lexical arm indexes noisy fields (whole transcripts) | Index only the memory `text` field lexically; tune BM25 k1/b (see `references/vector_schema_examples.md`) |
| Background reflection job loops forever re-summarizing | No budget/exit condition on the curation loop | Apply the six exit conditions (below) to the reflection loop |

## Hub Canon Integration

Memory work plugs into the hub's safety canon at two points: the **curation loop** and
the **persistence gates**.

**Exit conditions for memory loops.** Any memory-maintenance loop (retrieval-retry,
background reflection, dedup/merge) must declare all six canonical exit conditions
before iteration 1:

| Exit condition | Memory-loop instantiation (calibrated default) |
|---|---|
| `max_iterations` | Retrieval reformulation: max 2 retries. Reflection pass: max 1 summarize-write cycle per thread |
| `no_progress` | Same query (normalized) returning the same empty/identical result set twice -> stop retrying, answer without memory |
| `oscillation` | Write-delete-write on the same memory key over window 4 (A-B-A-B) -> freeze the key, escalate; guards promote/demote churn |
| `budget` | Hard cap on embedding calls + tokens per reflection run (e.g. 50 embedding calls / 20k tokens); counters never reset mid-run |
| `success_predicate` | Declared before the loop: e.g. "top-1 retrieved memory passes the grounding check against the user turn" — report the evidence on exit |
| `escalation_trigger` | Cross-tenant read attempt, or any user-data erasure request -> stop, surface to a human |

**5-Phase Protocol mapping.** Memory infrastructure changes are consequential:
- *Phase 1 DISCOVERY (read-only):* inventory existing schemas, collections, namespaces,
  and row counts before proposing anything.
- *Phase 2 MANIFEST:* list tables/collections to create or migrate, the rollback plan
  (schema migrations down-scripts; collection snapshots), and declared exit conditions.
- *Phase 3 HUMAN GATE:* dropping a collection, altering an index (rebuild cost), and
  deleting user data are Class 3 IRREVERSIBLE or Class 2 COSTLY — per gate rules R1/R2
  they must be gated and must define rollback. Never auto-run destructive migrations.
- *Phase 4 IMPLEMENTATION:* apply strictly per manifest; new namespaces before new
  writes.
- *Phase 5 SELF-REVIEW:* verify with evidence — row counts, a cross-tenant negative
  test, and a memory hit-rate probe (see `references/rag_memory_patterns.md` section 5).

**HARDENED gate.** Agents that own memory writes (curator/reflection agents) go through
the same `loop_auditor.py` >= 90 (HARDENED) gate as any other agent: their spec must
declare the six exit conditions above, gate destructive memory operations, and emit a
structured handoff (memories written, deduped, evicted, evidence of success_predicate).

## When NOT to Use

- **Designing the document-RAG pipeline** (corpus chunking strategy, embedding model
  choice, reranker selection, ingestion): use `rag-architect`. This skill covers
  chunking only for *memory entries*.
- **Wiring LangGraph graphs, state schemas, reducers, or interrupts**: use
  `langgraph-state-design`. This skill only covers its checkpointer/Store memory
  surfaces.
- **CrewAI role/task design**: use `crewai-role-engineering`; here only the memory
  config.
- **MAF enterprise hosting, DI, and telemetry**: use `ms-agent-framework-enterprise`.
- **Token/cost reduction for LLM calls** (caching, routing): use `llm-cost-optimizer`
  and `multi-llm-routing`.
- **Measuring memory/retrieval quality with eval frameworks**: use
  `agentic-evals-benchmarking`; this skill defines the memory-specific metrics only.

## References

| File | Summary |
|------|---------|
| `references/memory_apis.md` | Real framework memory APIs: LangGraph checkpointer vs Store (semantic search config, namespacing), CrewAI memory configuration, MAF AgentThread + context providers; write policies, multi-tenancy, retention/erasure |
| `references/vector_schema_examples.md` | Concrete schemas: pgvector DDL with HNSW/IVFFlat tuning, Azure AI Search index JSON, Qdrant collection config with sparse+dense vectors; BM25 parameter guidance |
| `references/rag_memory_patterns.md` | Hybrid retrieval over memories: RRF implementations (Python + C#), when hybrid beats pure-dense, memory-vs-document chunking, durable checkpointer setup, memory quality evaluation |
| `references/memory_eviction_and_consolidation.md` | The context-noise thesis and eviction/consolidation LIFECYCLE: real framework levers (store TTL/`refresh_on_read`, Mem0 fused/temporal scoring, MemGPT/Letta paging + sleep-time compute, LlamaIndex `token_flush_size`/block priority, rerank-before-inject) and their git-native static analogs; a concrete 8-rule eviction policy and composite keep/evict score |
| `references/procedural_memory_skill_registries.md` | Procedural memory (self-authored skill/tool libraries): the Voyager propose->verify->register->retrieve loop and its static analog — the hub's `skills/` directory as a governed, human-gated, audited, versioned capability registry; description-as-retrieval-index and skill-retrieval hygiene |

**Tools**

| Script | Summary |
|------|---------|
| `scripts/memory_evictor.py` | Deterministic eviction planner over a JSONL memory store (stdlib only, `--json`): composite TTL + recency + frequency policy with pinned-item protection; emits the kept set and an evicted report with reasons. Covers the age/recency/frequency/pinned axes only — semantic relevance is delegated to `rag-architect`. Run `python scripts/memory_evictor.py --help`. |

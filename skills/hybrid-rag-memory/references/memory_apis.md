# Framework Memory APIs: LangGraph, CrewAI, Microsoft Agent Framework

Real API surfaces for wiring short-term and long-term memory in the three frameworks
this hub targets. Version assumptions are stated per section; anything uncertain is
explicitly marked **verify against current docs**. The taxonomy these APIs implement is
defined in `SKILL.md` (Memory Taxonomy).

---

## 1. LangGraph — checkpointer (thread state) vs Store (long-term memory)

*As of LangGraph 1.x (APIs stable since langgraph 0.2). Checkpointer backends ship as
separate packages: `langgraph-checkpoint-sqlite`, `langgraph-checkpoint-postgres`.*

LangGraph has TWO persistence layers and they are not interchangeable:

| | Checkpointer | Store |
|---|---|---|
| Persists | Full graph state, per `thread_id`, every super-step | Arbitrary JSON documents in hierarchical namespaces |
| Scope | One thread (conversation/run) | Cross-thread, cross-session |
| Use for | Resume, replay, time travel, interrupts | User facts, preferences, episodic summaries |
| Classes | `InMemorySaver`, `SqliteSaver`, `PostgresSaver` | `InMemoryStore`, `PostgresStore` (both implement `BaseStore`) |

### 1.1 Checkpointer (short-term / durability)

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:password@localhost:5432/agent_state"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # one-time: creates checkpoint tables
    app = workflow.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "thread-42"}}
    app.invoke({"messages": [("user", "hi")]}, config)
    # Re-invoking with the same thread_id resumes the conversation.
```

`InMemorySaver` (importable from `langgraph.checkpoint.memory`; older docs call it
`MemorySaver`, which remains an alias) is for tests only. `SqliteSaver` suits
single-instance deployments. There is an async twin, `AsyncPostgresSaver`.

**This layer is NOT long-term memory.** A new `thread_id` starts blank regardless of
which checkpointer you use.

### 1.2 Store API (long-term memory)

`BaseStore` documents live under a **namespace tuple** and a **key**; values are dicts.

```python
from langgraph.store.memory import InMemoryStore

def embed(texts: list[str]) -> list[list[float]]:
    # call your embedding provider here; return one vector per input text
    ...

store = InMemoryStore(
    index={"embed": embed, "dims": 1536, "fields": ["text"]}  # enables semantic search
)

namespace = ("memories", "user-123")            # tenant isolation via namespace
store.put(namespace, "pref-editor", {"text": "Prefers vim keybindings."})
store.put(namespace, "fact-tz",     {"text": "Works in Europe/Madrid timezone."})

item = store.get(namespace, "pref-editor")       # exact key lookup -> Item or None
hits = store.search(namespace, query="what editor setup does the user like?", limit=3)
for h in hits:
    print(h.key, h.score, h.value["text"])       # SearchItem: .key, .value, .score

store.delete(namespace, "fact-tz")               # erasure
```

Production backend (requires the `pgvector` extension when a semantic `index` is
configured):

```python
from langgraph.store.postgres import PostgresStore

with PostgresStore.from_conn_string(DB_URI, index={"embed": embed, "dims": 1536}) as store:
    store.setup()  # one-time table creation
    app = workflow.compile(checkpointer=checkpointer, store=store)  # BOTH layers
```

Inside a node, LangGraph injects the compiled store when you declare the parameter:

```python
from langgraph.store.base import BaseStore

def recall_node(state: State, *, store: BaseStore):
    user_ns = ("memories", state["user_id"])
    hits = store.search(user_ns, query=state["messages"][-1].content, limit=3)
    memories = "\n".join(h.value["text"] for h in hits)
    return {"recalled": memories}
```

A `get_store()` accessor also exists in `langgraph.config` in recent releases —
**verify against current LangGraph docs** before relying on it; the injected-parameter
pattern above is the stable form. `store.list_namespaces(prefix=("memories",))`
enumerates tenants (useful for audits and erasure sweeps).

---

## 2. CrewAI memory

*As of CrewAI 0.1xx (2025). Stock backends: ChromaDB for the RAG-style layers
(short-term, entity) and SQLite for long-term. Qdrant is NOT a stock CrewAI memory
backend — integrate external engines via `ExternalMemory` or custom storage classes.*

### 2.1 Turning memory on

```python
from crewai import Agent, Crew, Process, Task

crew = Crew(
    agents=[...],
    tasks=[...],
    process=Process.sequential,
    memory=True,  # enables short-term + long-term + entity memory
    embedder={
        "provider": "openai",
        "config": {"model": "text-embedding-3-small"},
    },
)
```

`memory=True` activates three layers: short-term (recent context, ChromaDB), long-term
(task learnings persisted across runs, SQLite), and entity memory (people/orgs/things,
ChromaDB). Storage location defaults to a platform data dir; override with the
`CREWAI_STORAGE_DIR` environment variable.

### 2.2 Custom storage paths

```python
from crewai.memory import LongTermMemory
from crewai.memory.storage.ltm_sqlite_storage import LTMSQLiteStorage

crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,
    long_term_memory=LongTermMemory(
        storage=LTMSQLiteStorage(db_path="./memory/agent_ltm.db")
    ),
)
```

`ShortTermMemory` and `EntityMemory` accept a `storage=RAGStorage(...)` argument for
custom paths/embedders — **verify the `RAGStorage` constructor signature against
current CrewAI docs**, it has shifted between minor versions.

### 2.3 External memory and resets

- `ExternalMemory` plugs a third-party memory service (e.g. a Mem0-backed provider)
  into a crew via the `external_memory=` parameter — **verify the current import path
  and provider config shape against CrewAI docs** before use.
- Reset accumulated memories with the CLI: `crewai reset-memories --all` (flags exist
  for individual layers; run `crewai reset-memories --help`).

---

## 3. Microsoft Agent Framework memory

*As of Microsoft Agent Framework public preview (2025), package `Microsoft.Agents.AI`
(.NET) / `agent-framework` (Python). MAF supersedes Semantic Kernel Agents and AutoGen.*

**Do not use `IMemoryStore` or `ISemanticTextMemory`** — those are legacy Semantic
Kernel memory abstractions and are not part of the Agent Framework surface.

### 3.1 Short-term: AgentThread

Conversation state is owned by `AgentThread`, not by a hand-rolled message list:

```csharp
AIAgent agent = chatClient.CreateAIAgent(
    instructions: "You are a support assistant.",
    name: "SupportAgent");

AgentThread thread = agent.GetNewThread();
AgentRunResponse first  = await agent.RunAsync("My printer is broken.", thread);
AgentRunResponse second = await agent.RunAsync("What did I just say?", thread);
// 'thread' carries the conversation; the second call sees the first turn.
```

Persist a thread across process restarts by serializing it — the documented pattern is
JSON round-tripping on the thread object (`thread.Serialize()` returning a
`JsonElement`, restored via `agent.DeserializeThread(...)`). **Verify exact member
names against current MAF docs** — the framework is in preview and serialization
signatures have evolved. Store the serialized JSON in your own database keyed by
conversation id; this is the MAF equivalent of a LangGraph checkpoint row.

### 3.2 Long-term: context providers and message stores

MAF injects long-term memory through **context providers**: components that run before
and after each agent invocation, contributing instructions/messages into the request
and extracting memories from the exchange. The base class is `AIContextProvider`, with
a pre-invocation hook (return extra context: instructions, messages) and a
post-invocation hook (observe the request/response to write memories). Providers are
attached via the agent's options (a context-provider factory on
`ChatClientAgentOptions`). **Verify the exact class and option names against current
MAF docs** — preview surface.

The memory flow to implement with a context provider:

```text
before run:  query your vector store (user namespace) -> inject top-k memories
             as additional instructions/context
after run:   extract candidate facts from the turn -> dedup -> store.put(...)
```

For custom persistence of the conversation history itself (rather than in-thread
storage), MAF exposes a chat-message store hook (`ChatMessageStoreFactory` on the
agent options) so messages can live in your database — **verify against current MAF
docs**.

The Python package mirrors these concepts (`ChatAgent`, `get_new_thread()`, thread
serialization, context providers) — same verify caveat applies.

Backends: pair MAF with pgvector or Azure AI Search using the schemas in
`references/vector_schema_examples.md`; MAF does not mandate a store.

---

## 4. Memory write policies

What separates a memory system from a transcript dump is the write policy.

### 4.1 Decision rules — should this be stored?

Store when ALL of: (a) useful beyond the current thread, (b) stated or observed fact —
not speculation, (c) not already stored (dedup check), (d) permitted (no secrets,
no data the tenant policy excludes). Otherwise skip the write.

### 4.2 Summarize-then-write (episodic)

Never store raw transcripts as episodic memory. On thread close, produce a bounded
summary (target 100-200 tokens: goal, outcome, notable failures, decisions) and store
that single entry with `source_thread_id` and timestamp.

### 4.3 Dedup-before-write (semantic)

```python
def write_memory(store, namespace, key, text):
    near = store.search(namespace, query=text, limit=1)
    if near and near[0].score is not None and near[0].score > 0.9:
        # Same fact already known: update instead of duplicating
        store.put(namespace, near[0].key, {"text": text, "updated": now_iso()})
        return "updated"
    store.put(namespace, key, {"text": text, "created": now_iso()})
    return "created"
```

The 0.9 threshold is a starting point — calibrate per embedding model against a small
labeled set of duplicate/non-duplicate pairs.

### 4.4 Loop safety

Reflection/curation jobs are loops and MUST declare the hub's six exit conditions
(`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger`) before iteration 1 — see the Hub Canon Integration table in
`SKILL.md` for the memory-specific defaults (e.g. write-delete-write on one key over a
window of 4 is oscillation: freeze the key and escalate).

---

## 5. Multi-tenant partitioning (proving isolation)

One bullet ("partition by user") is not a design. The isolation key must appear in
**every** read and write path, enforced by structure rather than discipline:

```python
# LangGraph Store: tenant is part of the namespace tuple — reads cannot cross it
ns = ("tenant", tenant_id, "memories", user_id)
store.put(ns, key, value)
store.search(ns, query=q, limit=5)
```

```python
# Qdrant: tenant as an indexed payload field + mandatory filter on every query
from qdrant_client import QdrantClient, models

client.query_points(
    collection_name="agent_memory",
    query=dense_vector,
    query_filter=models.Filter(must=[
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
    ]),
    limit=5,
)
```

For Azure AI Search, add a filterable `tenant_id` field and pass
`$filter=tenant_id eq '...'` with every query (schema in
`references/vector_schema_examples.md`).

**Test it:** every memory deployment ships one negative test — write as tenant A, query
as tenant B, assert zero hits. A cross-tenant hit is an `escalation_trigger`, not a bug
to file quietly.

---

## 6. Retention, TTL, and user erasure

- **TTL:** store `created`/`updated` timestamps on every entry. Qdrant and pgvector
  have no automatic TTL for this use case — run a scheduled sweep that deletes entries
  older than the retention window (SQL `DELETE WHERE updated_at < ...`; Qdrant
  `delete` with a datetime range filter on an indexed payload field).
- **Count caps (episodic):** keep the newest N per namespace; before deleting the
  overflow, roll it into one summary entry.
- **User erasure (GDPR-style):** deletion must cover ALL layers, in this order:
  1. Long-term store: delete the user's namespace(s)
     (`store.list_namespaces(prefix=...)` then delete keys; or engine-level delete by
     `user_id` filter).
  2. Checkpoints: delete rows for every `thread_id` belonging to the user (thread
     ownership must be recorded at thread creation for this to be possible — design
     requirement, not an afterthought).
  3. Lexical indexes / replicas: confirm the same documents are removed from any
     secondary index (e.g. the Azure AI Search index alongside pgvector).
  Log the erasure as an auditable event (who, when, which namespaces) WITHOUT logging
  the deleted content. Erasure is irreversible: per hub gate rule R1 it requires the
  HUMAN GATE before execution.

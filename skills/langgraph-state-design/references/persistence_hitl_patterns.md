# LangGraph Persistence, Time Travel, HITL, and Streaming

Checkpointers, thread scoping, state history and forking, modern `interrupt()` gates,
long-term memory via the Store API, and streaming modes. **As of LangGraph 1.x
(Python)**; renames from the 0.2 line are noted inline. Schema/wiring patterns live in
`state_design_patterns.md`.

---

## 1. Checkpointers

A checkpointer persists a snapshot of the state after every superstep, keyed by
`thread_id`. It is what makes resume, time travel, and `interrupt()` possible — a graph
compiled without one has none of those capabilities.

```python
# Dev / tests only -- lost on process exit.
# 1.x docs name: InMemorySaver; the 0.2 line called it MemorySaver (both import today).
from langgraph.checkpoint.memory import InMemorySaver
graph = builder.compile(checkpointer=InMemorySaver())
```

```python
# Single-writer durable: pip install langgraph-checkpoint-sqlite
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke(inputs, config)
# Async variant: langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver
```

```python
# Production multi-process: pip install langgraph-checkpoint-postgres
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@host:5432/db"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()             # one-time: creates the checkpoint tables
    graph = builder.compile(checkpointer=checkpointer)
    ...
# Async variant: langgraph.checkpoint.postgres.aio.AsyncPostgresSaver
```

Note: `from_conn_string` returns a **context manager** in current releases of both
packages — hold it open for the graph's lifetime (in servers, enter it at startup).
A parent graph's checkpointer propagates automatically into attached subgraphs.

---

## 2. Threads: Scoping Runs with `thread_id`

Every checkpointed invocation carries a `thread_id` in `config["configurable"]`. Same
`thread_id` = same conversation: state accumulates and the graph resumes where it left
off. New `thread_id` = blank state.

```python
config = {"configurable": {"thread_id": "user-42-session-7"}}
graph.invoke({"messages": [("user", "Start the migration plan.")]}, config)
# Later -- same thread resumes with full state:
graph.invoke({"messages": [("user", "Now execute step 1.")]}, config)
```

Design rules: derive `thread_id` from (user, session), never share one across users
(cross-tenant state leak); a checkpointer is **thread-scoped session state, not
long-term memory** — cross-session facts belong in the Store (section 6).

---

## 3. Inspecting State: `get_state` and `get_state_history`

```python
snapshot = graph.get_state(config)   # StateSnapshot for the thread's latest checkpoint
snapshot.values                      # the state dict
snapshot.next                        # tuple of node names about to run (empty = done)
snapshot.tasks                       # pending tasks; interrupted ones carry .interrupts
snapshot.config                      # includes this snapshot's checkpoint_id

history = list(graph.get_state_history(config))   # newest first, one per superstep
```

`get_state_history` is the audit trail: which node ran, what the state was, in what
order. Use it in Phase 5 SELF-REVIEW handoffs to reconstruct what the graph actually did.

---

## 4. Time Travel: Replay, Fork, and `update_state`

**Replay / fork from a past checkpoint** — invoke with the snapshot's own config (it
contains `checkpoint_id`). Execution resumes *from that point*, creating a new branch of
history rather than overwriting the old one:

```python
past = list(graph.get_state_history(config))[3]   # pick an earlier superstep
graph.invoke(None, past.config)                   # None input = resume, don't restart
```

**Edit state before resuming** — `update_state` writes a new checkpoint as if the named
node had produced the update (reducers apply):

```python
graph.update_state(config, {"plan": human_edited_plan}, as_node="architect")
graph.invoke(None, config)
```

This pair is the rollback mechanism the hub's gate rule R2 asks for on reversible-in-
software actions: reset to the pre-mistake checkpoint, patch the state, re-run. It does
**not** undo external side effects (emails, deploys) — those still need real rollback
plans or gates (section 5).

---

## 5. Human-in-the-Loop

### 5.1 Modern pattern: `interrupt()` + `Command(resume=...)` — use this

`interrupt(payload)` inside a node pauses the graph, persists a checkpoint, and surfaces
the payload to the caller. Resuming with `Command(resume=value)` re-runs the node, and
this time `interrupt()` **returns** `value`. Requires a checkpointer.

```python
from langgraph.types import interrupt, Command

def approval_gate(state: State):
    # Phase 3 HUMAN GATE: no side effects in this node, only the question.
    decision = interrupt({
        "question": "Approve this manifest for implementation?",
        "manifest": state["manifest"],
    })
    if decision == "approve":
        return {"approved": True}
    return {"approved": False, "feedback": decision}   # rejection reason as free text

# --- caller side ---
config = {"configurable": {"thread_id": "run-9"}}
result = graph.invoke({"manifest": plan}, config)
# Paused: the interrupt payload is surfaced under the "__interrupt__" key
print(result["__interrupt__"])

# Hours later (durable checkpointer!), the human answers:
graph.invoke(Command(resume="approve"), config)
```

**The replay caveat (top HITL bug):** on resume, the node re-executes *from its start* up
to the `interrupt()` call. Any side effect placed before the interrupt runs **twice**.
Keep gate nodes side-effect free: gate node asks, downstream node acts.

Common gate shapes, all the same primitive:

- **Approve/reject** (above) — route on the resume value with a conditional edge.
- **Edit state:** `revised = interrupt({"draft": state["draft"]})` then
  `return {"draft": revised}` — human-corrected value flows on.
- **Review a tool call before execution:** interrupt with the tool name + args in the
  payload; execute only after resume, honoring an edited-args resume value.

Multiple pending interrupts (e.g. parallel branches) can be resumed together by mapping
interrupt ids to values in a single `Command(resume={...})` — exact mapping shape:
verify against current docs for your minor version.

### 5.2 Legacy pattern: static `interrupt_before` / `interrupt_after`

```python
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["deploy"])
graph.invoke(inputs, config)          # halts BEFORE 'deploy' runs
graph.get_state(config).next          # ('deploy',)
graph.update_state(config, {...})     # optional human edits
graph.invoke(None, config)            # None = proceed
```

| | `interrupt()` (dynamic) | `interrupt_before/after` (static) |
|---|---|---|
| Placement | Anywhere in node logic, conditional on state | Node boundary only, always fires |
| Payload to human | Explicit, structured, you design it | None — human must inspect state |
| Resume carries a value | Yes: `Command(resume=...)` | No: resume is `invoke(None, config)` |
| Use for | All new designs; conditional gates (only interrupt when action is Class 2/3) | Debugger-style stepping; pre-0.2.31 codebases |

### 5.3 Gate placement (hub canon cross-map)

- Class 1 REVERSIBLE nodes: no gate.
- Class 2 COSTLY: checkpoint gate — one `interrupt()` after the manifest/batch node.
- Class 3 IRREVERSIBLE: pre-execution approval gate — `interrupt()` in a side-effect-free
  node immediately upstream of the acting node (gate rule R1); pair with a rollback note
  (R2) and an escalation route (R3) so a rejection has somewhere to go.

---

## 6. Long-Term Memory: the Store API

Checkpointers are per-thread. The **Store** is the cross-thread layer: namespaced
key-value documents, optionally semantically indexed, injected into any node.

```python
from langgraph.store.memory import InMemoryStore     # durable: langgraph.store.postgres
import uuid
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

store = InMemoryStore()          # optional semantic search: InMemoryStore(index={...})
graph = builder.compile(checkpointer=checkpointer, store=store)

def remember(state: State, config: RunnableConfig, *, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    ns = ("memories", user_id)                       # namespace tuple = tenant isolation
    store.put(ns, str(uuid.uuid4()), {"fact": "prefers async APIs"})
    return {}

def recall(state: State, config: RunnableConfig, *, store: BaseStore):
    ns = ("memories", config["configurable"]["user_id"])
    items = store.search(ns, limit=5)    # query="..." needs an index configured
    return {"context": [i.value for i in items]}
```

Boundary: what to write, when to summarize, and vector-backend selection are owned by
the sibling skill `hybrid-rag-memory`. This skill owns the mechanics: `compile(store=)`,
node injection, and the namespace-per-tenant rule.

---

## 7. Streaming Modes

`graph.stream(inputs, config, stream_mode=...)` — pick per consumer:

| Mode | Yields | Use for |
|---|---|---|
| `"values"` | Full state after each superstep | Debug dashboards, state inspection |
| `"updates"` | Only the delta each node returned | Progress logs; cheapest to render |
| `"messages"` | `(message_chunk, metadata)` LLM tokens from inside nodes | Token-by-token UI streaming |
| `"custom"` | Whatever nodes emit via a stream writer | Tool progress ("fetched 3/10 pages") |
| `"debug"` | Detailed execution events | Tracing without an APM |

```python
for chunk in graph.stream(inputs, config, stream_mode="updates"):
    print(chunk)                          # {"node_name": {...delta...}}

# Multiple modes: yields (mode, payload) tuples
for mode, payload in graph.stream(inputs, config, stream_mode=["updates", "messages"]):
    ...

# Custom events from inside a node:
from langgraph.config import get_stream_writer
def scrape(state: State):
    writer = get_stream_writer()
    writer({"progress": "fetched 3/10 pages"})
    return {...}
```

`graph.astream_events(inputs, config, version="v2")` is the lower-level LangChain event
stream (per-runnable start/stream/end events) — reach for it only when `stream_mode`
granularity is not enough. When a run hits an `interrupt()`, stream consumers see the
`"__interrupt__"` payload as the final chunk before the pause — surface it to the human
instead of treating the stream's end as completion.

---

## 8. Operational Checklist

- [ ] Durable checkpointer (`SqliteSaver`/`PostgresSaver`) before any `interrupt()` gate.
- [ ] `PostgresSaver.setup()` executed once per database.
- [ ] `thread_id` derivation documented and tenant-safe; never reused across users.
- [ ] Gate nodes contain zero side effects (replay caveat, section 5.1).
- [ ] Every Class 3 IRREVERSIBLE node is downstream of an `interrupt()` gate (R1) with a
      rollback note (R2).
- [ ] Schema changes are additive-with-defaults, or old threads are migrated via
      `update_state` / retired (checkpoint drift).
- [ ] Store namespaces include the tenant key as the first tuple element.

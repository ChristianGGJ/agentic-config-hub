---
title: "Skill: langgraph-state-design — MCP Servers & RAG Architectures"
description: "Use when designing LangGraph StateGraphs: typed state schemas and reducers, conditional edge routing, Command/Send handoffs, checkpointers and time. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: langgraph-state-design

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `langgraph-state-design`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/langgraph-state-design/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


**API version assumption:** everything in this skill targets **LangGraph 1.x (Python)**,
which is source-compatible with the late 0.2 line except where a rename is noted inline
(e.g. `MemorySaver` -> `InMemorySaver`, `input`/`output` -> `input_schema`/`output_schema`).
Members marked "verify against current docs" are patterns whose exact signature has moved
between minor versions.

## Overview

LangGraph's differentiator is the **cyclic StateGraph**: unlike DAG pipelines, edges may
loop back, which is what makes evaluator-optimizer loops, supervisor delegation, and
retry-until-green flows expressible — and also what makes runaway recursion the number one
production failure. This skill does one thing: it designs the *state layer* of a LangGraph
system — schemas, reducers, edges, persistence, human gates, and cycle bounds — so that
every cycle in the graph terminates by design, not by luck.

## Core Capabilities

1. **State schema design** — TypedDict/Pydantic schemas, reducers (`add_messages`,
   `operator.add`, custom), input/output schemas, private inter-node channels.
2. **Graph wiring** — `add_node` / `add_edge` / `add_conditional_edges(source, router,
   path_map)`, `START`/`END`, compile-time validation.
3. **Dynamic control flow** — `Command(goto=..., update=...)` handoffs, `Send` map-reduce
   fan-out, supervisor and swarm topologies, subgraphs.
4. **Persistence** — checkpointers (`InMemorySaver`, `SqliteSaver`, `PostgresSaver`),
   `thread_id` scoping, `get_state_history`, `update_state`, checkpoint replay/forking.
5. **Human-in-the-loop** — modern `interrupt()` + `Command(resume=...)` gates; legacy
   static `interrupt_before`/`interrupt_after` for contrast.
6. **Cycle safety** — `recursion_limit`, `GraphRecursionError`, `RemainingSteps`, and
   state-carried counters mapped to the hub's six exit-condition types.

## Decision Frameworks

### State schema: TypedDict vs Pydantic vs dataclass

| Option | Validation | Overhead | Default when |
|---|---|---|---|
| `TypedDict` (+ `Annotated` reducers) | None at runtime | Lowest | **Default.** Internal graphs where nodes are trusted producers |
| Pydantic `BaseModel` | Full runtime validation on node output | Per-superstep validation cost | Untrusted/LLM-shaped updates crossing the state boundary; API-facing graphs |
| `dataclass` | None | Low | You need defaults + methods but not validation |

Calibrated default: TypedDict for speed, promote individual graphs to Pydantic only after
a state-corruption incident or when inputs arrive from outside your process.

### Checkpointer selection

| Checkpointer | Package | Survives restart | Concurrency | Use for |
|---|---|---|---|---|
| `InMemorySaver` (alias `MemorySaver` pre-1.0 name) | `langgraph` | No | Single process | Tests, notebooks, demos — never production |
| `SqliteSaver` / `AsyncSqliteSaver` | `langgraph-checkpoint-sqlite` | Yes | Single writer | Local tools, single-user apps, CLIs |
| `PostgresSaver` / `AsyncPostgresSaver` | `langgraph-checkpoint-postgres` | Yes | Multi-process | **Production default** for anything multi-user |

Rule: any graph containing an `interrupt()` gate needs a durable checkpointer, because the
human may answer hours later, after the process restarted.

### Routing mechanism

| Mechanism | Decides | Also mutates state | Default when |
|---|---|---|---|
| `add_conditional_edges(source, router, path_map)` | Next node from a fixed map | No | **Default.** Routing logic is separable from node logic; keeps topology visible/renderable |
| `Command(goto=..., update=...)` returned by a node | Next node | Yes, atomically | Handoffs where the decision and the state update belong together (supervisor/worker, swarm) |
| `Send("node", payload)` from a router | N parallel instances of a node, each with its own payload | Payload is per-branch state | Map-reduce fan-out over a runtime-sized list |
| Static `add_edge` | Nothing (unconditional) | No | Every hop that never varies — prefer it; fewer routers = fewer loops |

### Topology selection

| Topology | Shape | Pick when | Cost |
|---|---|---|---|
| Single graph, conditional edges | One schema, routers | <= ~6 nodes, one concern | Lowest |
| Supervisor | Central router node + workers returning `Command(goto="supervisor")` | Heterogeneous workers, central budget/priority control | +1 LLM call per hop |
| Swarm / network handoff | Peers hand off directly via `Command(goto=peer)` | Expert-to-expert flows where a hub adds latency | Harder to bound; every peer needs guards |
| Hierarchical subgraphs | Parent graph invokes compiled child graphs | Schema would exceed ~10 unrelated keys, or teams own subsystems | State mapping at every boundary |

Worked supervisor example: `references/state_design_patterns.md` section 4.

### Thread-scoped vs cross-thread memory

| Need | Mechanism | Not |
|---|---|---|
| Conversation/session state, resume, time travel | Checkpointer + `thread_id` | A long-term memory system |
| Facts that persist across threads/users/sessions | Store API (`InMemoryStore`, `PostgresStore`) via `compile(store=...)` | The checkpointer — it is per-thread by design |

Deeper memory-system design (write policies, taxonomies, vector backends) is owned by the
sibling skill `hybrid-rag-memory`; this skill owns only the LangGraph-native surfaces.

## Cycle Safety (LangGraph mechanics -> hub exit-condition canon)

`recursion_limit` (config key, default **25 supersteps**) is LangGraph's only built-in
loop guard. When exceeded, the run raises `langgraph.errors.GraphRecursionError`:

```python
from langgraph.errors import GraphRecursionError

try:
    result = graph.invoke(inputs, config={"recursion_limit": 50,
                                          "configurable": {"thread_id": "t-1"}})
except GraphRecursionError:
    # This is an incident report, not a control system. Escalate with state attached.
    snapshot = graph.get_state({"configurable": {"thread_id": "t-1"}})
    ...
```

Relying on `recursion_limit` alone is the hub's **guard subset anti-pattern**: the graph
burns 25 supersteps stalled or oscillating, then dies with an exception instead of a
report. Map every cycle to all six canonical exit-condition types:

| Hub exit condition | LangGraph implementation |
|---|---|
| `max_iterations` | Counter field in state (`attempts: int`), incremented by the loop-entry node; router checks `attempts >= cap` and routes to a report/END branch. `recursion_limit` stays as the backstop, never the primary guard |
| `no_progress` | Hash the relevant state slice (e.g. failing-test list) into `state["last_hash"]`; router fires when unchanged for window 2 |
| `oscillation` | Ring buffer of the last 4 routing decisions in state; fire on A-B-A-B (window 4, matches hub trace detection D2) |
| `budget` | Accumulate token usage (`response.usage_metadata`) and tool-call counts into state via an `operator.add` reducer; router refuses the next hop over budget |
| `success_predicate` | The router's primary branch: a machine-checkable check (exit code, validator verdict) routes to `END` with the evidence written into state |
| `escalation_trigger` | Route to a dedicated node that calls `interrupt()` (an Escalation Gate); catching `GraphRecursionError` in the caller also converts the crash into an escalation report. Any other condition firing twice -> this one |

`langgraph.managed.RemainingSteps` (annotate a state field with it) exposes the remaining
superstep budget inside nodes so a router can end gracefully *before* the limit raises —
use it to turn the backstop into a clean `budget` exit ("verify against current docs" for
the exact import path on your minor version).

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| `InvalidUpdateError: Can receive only one value per step` | Parallel branches (fan-out or `Send`) write the same key that has **no reducer** | Annotate the key: `Annotated[list, operator.add]` or a custom reducer; keys written concurrently must always declare how they merge |
| Message history silently truncated to one message | A plain `messages: list` field — the last writer overwrote it | Use `Annotated[list[AnyMessage], add_messages]` |
| Context window blowout, cost climbing per turn (**state bloat**) | `add_messages` grows unboundedly; large artifacts (file bodies, raw HTML) stored in state | Add a trim/summarize node (emit `RemoveMessage` ids via `add_messages`); store artifact *references* (paths, URIs) in state, not payloads |
| Node crashes with `KeyError` on resume of an old thread (**checkpoint drift**) | Schema changed between deploys; old checkpoints lack the new key | Make schema changes additive with defaults (`total=False` / Pydantic defaults); for breaking changes migrate via `update_state` or start new `thread_id`s |
| `GraphRecursionError` at 25 supersteps | A router that can never reach `END` — the infinite router loop | Wire the six-condition table above; verify every cycle has at least one edge to `END` reachable from every router branch |
| Duplicate side effects after a human resumes a gate | Code **before** `interrupt()` in the node re-executes on resume | Put side effects after the interrupt, or in a separate downstream node; keep pre-interrupt code idempotent |
| Subgraph output never appears in parent state | Parent/child schemas share no keys and no mapping was written | Shared-schema: attach compiled subgraph directly with `add_node`; different-schema: wrap in a parent node that maps keys both ways |
| Interrupt never pauses anything | Graph compiled without a checkpointer | `interrupt()` requires `compile(checkpointer=...)`; no checkpointer, no pause |

## Hub Canon Integration

- **5-Phase Protocol as a graph shape:** Phase 1 DISCOVERY = read-only nodes that only
  append findings to state; Phase 2 MANIFEST = a node that writes the change manifest into
  state; Phase 3 HUMAN GATE = an `interrupt()` node presenting that manifest (hard stop —
  gate rule R1/B1); Phase 4 IMPLEMENTATION = side-effecting nodes downstream of the gate;
  Phase 5 SELF-REVIEW & HANDOFF = a terminal node that emits the handoff report before
  `END`.
- **Gate strictness classes -> interrupt placement** (cross-map to the hub's HITL canon in
  `agentic-system-architect`): Class 1 REVERSIBLE nodes run gate-free; Class 2 COSTLY work
  gets a checkpoint gate — `interrupt()` after the manifest/batch boundary (or legacy
  `interrupt_after` for post-hoc review); Class 3 IRREVERSIBLE actions get a pre-execution
  approval gate — `interrupt()` immediately upstream of the side-effecting call, in a node
  that performs no side effects itself.
- **Exit conditions:** declare all six types (table above) in the graph design *before*
  wiring nodes, exactly as the canon requires them declared before iteration 1. OR-ed:
  first to fire routes out of the cycle.
- **Trace detections:** D2 (oscillation, window 4) and D3 (error cascade, 3 consecutive)
  are implementable as state-carried counters checked in routers; a node that counts
  consecutive tool errors and routes to escalation at 3 satisfies D3 inside the graph.
- **HARDENED gate (>= 90):** a LangGraph design scores HARDENED only when every cycle
  declares the six conditions, every irreversible node sits behind an `interrupt()` gate
  with a rollback note, and the graph ends in a handoff-report node. `recursion_limit`
  alone caps the Loop Safety category at the `max_iterations` points and fails A2/A3.

## When NOT to Use

- **Framework-agnostic ecosystem architecture, exit-condition taxonomy, gate design** —
  see `agentic-system-architect` (this skill implements its canon in LangGraph terms).
- **Role/crew design on CrewAI** (role/goal/backstory, Flows) — see
  `crewai-role-engineering`.
- **.NET agents on Microsoft Agent Framework** — see `microsoft-agent-framework`.
- **Loop-guard code outside any framework** (plain-Python ledgers/detectors) — see
  `loop-engineering-mechanisms`.
- **Long-term memory architecture** (vector schemas, write policies, hybrid retrieval) —
  see `hybrid-rag-memory`; this skill stops at `compile(store=...)`.
- **Framework-neutral workflow scaffolds and handoff contracts** — see
  `agent-workflow-designer`.

## References

| File | Summary |
|------|---------|
| `references/state_design_patterns.md` | Schemas and reducers, `add_conditional_edges` wiring, `Command` handoffs, worked supervisor topology, `Send` map-reduce, subgraphs, private/input/output schemas, node `RetryPolicy` |
| `references/persistence_hitl_patterns.md` | Checkpointer setup (SQLite/Postgres), `thread_id` config, `get_state_history` / `update_state` / checkpoint replay and forking, modern `interrupt()` + `Command(resume=...)` gates vs legacy `interrupt_before`, Store API, streaming modes |

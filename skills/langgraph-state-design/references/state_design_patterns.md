# LangGraph State & Graph Design Patterns

State schemas, reducers, edge wiring, dynamic routing (`Command`, `Send`), topologies,
subgraphs, and node retry policies. **As of LangGraph 1.x (Python)**; renames from the
0.2 line are noted inline. Persistence, HITL, and streaming live in
`persistence_hitl_patterns.md`.

---

## 1. State Schemas and Reducers

Every key in the state schema is a *channel*. A channel without a reducer is
**overwritten** by the last node that returns it; a channel with a reducer **merges**
updates. When two parallel branches write the same reducer-less key in one superstep,
LangGraph raises `InvalidUpdateError` — reducers are mandatory for concurrently written
keys, not a style choice.

```python
import operator
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages   # also importable from langgraph.graph.message

def merge_max(left: int, right: int) -> int:
    """Custom reducer: keep the maximum seen so far."""
    return max(left, right)

class AgentState(TypedDict):
    # add_messages: appends, dedupes by message id, honors RemoveMessage
    messages: Annotated[list[AnyMessage], add_messages]
    # operator.add: list concatenation -- safe under parallel fan-in
    findings: Annotated[list[str], operator.add]
    # custom reducer
    worst_severity: Annotated[int, merge_max]
    # no reducer: last write wins; must never be written by parallel branches
    current_phase: str
```

Rules:

- Nodes return **only the keys they changed**, never the whole state.
- Any key written by parallel branches (fan-out, `Send`) needs a reducer.
- Trim message bloat with `RemoveMessage`: `add_messages` treats a
  `RemoveMessage(id=msg.id)` in the update as a deletion instruction.

```python
from langchain_core.messages import RemoveMessage

def trim_history(state: AgentState):
    stale = state["messages"][:-10]                    # keep the last 10
    return {"messages": [RemoveMessage(id=m.id) for m in stale]}
```

Pydantic alternative — `StateGraph` also accepts a `BaseModel` subclass as the schema:
same channels (fields keep `Annotated[..., reducer]` and may declare defaults), plus
runtime validation of each node's returned update, so corruption surfaces at the node
boundary instead of three nodes later.

---

## 2. Wiring: Nodes, Edges, and Conditional Edges

The complete, compiling loop skeleton. The router is a plain function; the wiring call
that actually puts it in the graph is `add_conditional_edges(source, router, path_map)`.

```python
from typing import Literal, TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    attempts: int
    tests_passing: bool

def write_code(state: State):
    ...                                   # LLM call, patch generation
    return {"attempts": state["attempts"] + 1}

def run_tests(state: State):
    passed = ...                          # execute the suite, read exit code
    return {"tests_passing": passed}

def escalate_node(state: State):
    # escalation_trigger exit: emit a stop-and-report payload, never loop on
    return {"messages": [("ai", f"Escalating after {state['attempts']} attempts; "
                                "tests still failing. Human review needed.")]}

MAX_ATTEMPTS = 5

def route_after_tests(state: State) -> Literal["write_code", "escalate", "__end__"]:
    if state["tests_passing"]:            # success_predicate -> done
        return "__end__"
    if state["attempts"] >= MAX_ATTEMPTS: # max_iterations -> escalate, never loop on
        return "escalate"
    return "write_code"                   # the cycle: this edge points BACKWARD

builder = StateGraph(State)
builder.add_node("write_code", write_code)
builder.add_node("run_tests", run_tests)
builder.add_node("escalate", escalate_node)

builder.add_edge(START, "write_code")
builder.add_edge("write_code", "run_tests")
builder.add_conditional_edges(
    "run_tests",                          # source node
    route_after_tests,                    # router: reads state, returns a key
    {"write_code": "write_code",          # path_map: router output -> node name
     "escalate": "escalate",
     "__end__": END},
)
builder.add_edge("escalate", END)

graph = builder.compile()
```

Notes:

- `path_map` may be a dict (router output -> node) or a list of node names when the
  router already returns node names verbatim. Always provide it: it makes the topology
  statically known for rendering and validation.
- Routers must be **cheap and deterministic where possible**. When an LLM must route,
  bind it to a structured schema whose `next` field is a `Literal` of the declared
  branches (`init_chat_model(...).with_structured_output(Decision)`) so the output is
  always a `path_map` key — section 4 shows the full pattern. Routing does not need a
  frontier-tier model; use a fast tier.

---

## 3. Dynamic Routing with `Command`

A node may return `langgraph.types.Command` to **update state and choose the next node
atomically** — the idiom for handoffs. Annotate the return type so compilation knows the
possible destinations (no `add_edge` needed from that node).

```python
from langgraph.types import Command
from typing import Literal

def worker(state: State) -> Command[Literal["supervisor"]]:
    result = do_work(state)
    return Command(
        update={"findings": [result]},   # merged via the channel's reducer
        goto="supervisor",
    )
```

From inside a subgraph, `Command(goto="parent_node", graph=Command.PARENT)` routes in the
parent graph — the primitive behind swarm-style peer handoffs.

Selection guidance between `Command` and conditional edges: the routing-mechanism table
in `SKILL.md`.

---

## 4. Worked Topology: Supervisor with `Command` Handoffs

Central supervisor decides; workers do one job and hand control back. Every hop passes
through one router, so budget/iteration guards live in exactly one place.

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

class SupState(TypedDict):
    messages: Annotated[list, add_messages]
    hops: int                                  # max_iterations guard

class SupervisorDecision(BaseModel):
    next: Literal["researcher", "writer", "FINISH"] = Field(
        description="Which worker acts next, or FINISH when the goal is met.")

sup_llm = init_chat_model("<provider>:<capable-tier-model>").with_structured_output(
    SupervisorDecision)

MAX_HOPS = 10

def supervisor(state: SupState) -> Command[Literal["researcher", "writer", "__end__"]]:
    if state["hops"] >= MAX_HOPS:              # hub max_iterations, checked BEFORE the LLM
        return Command(goto="__end__",
                       update={"messages": [("ai", "Hop budget exhausted; stopping with partial results.")]})
    decision = sup_llm.invoke(state["messages"])
    if decision.next == "FINISH":              # success_predicate branch
        return Command(goto="__end__")
    return Command(goto=decision.next, update={"hops": state["hops"] + 1})

def researcher(state: SupState) -> Command[Literal["supervisor"]]:
    answer = ...                               # research work
    return Command(goto="supervisor", update={"messages": [("ai", answer)]})

def writer(state: SupState) -> Command[Literal["supervisor"]]:
    draft = ...
    return Command(goto="supervisor", update={"messages": [("ai", draft)]})

builder = StateGraph(SupState)
builder.add_node("supervisor", supervisor)
builder.add_node("researcher", researcher)
builder.add_node("writer", writer)
builder.add_edge(START, "supervisor")
graph = builder.compile()

# hops has no reducer/default: seed it at invoke time or the first read KeyErrors
graph.invoke({"messages": [("user", goal)], "hops": 0},
             {"configurable": {"thread_id": "run-1"}})
```

Swarm variant: drop the supervisor; each worker returns `Command[Literal[<peers>,
"__end__"]]` and decides its own handoff. Cheaper per hop, but every worker must then
carry its own hop/budget guard — prefer supervisor until hub latency measurably hurts.

---

## 5. `Send` API: Map-Reduce Fan-Out

`Send(node, payload)` launches one instance of `node` per payload **in parallel within
one superstep**, each seeing only its payload as state. Return a list of `Send` objects
from a conditional-edge router. Fan-in happens through reducers on the shared state.

```python
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

class OverallState(TypedDict):
    documents: list[str]
    summaries: Annotated[list[str], operator.add]   # reducer = the fan-in

class WorkerState(TypedDict):        # per-branch state: just the payload
    document: str

def plan(state: OverallState):
    return {}                        # discovery/validation before fan-out

def fan_out(state: OverallState):
    # Bound the fan-out: unbounded Send lists are a budget exit condition waiting to fire
    return [Send("summarize", {"document": d}) for d in state["documents"][:50]]

def summarize(state: WorkerState):
    summary = ...                    # one LLM call per document
    return {"summaries": [summary]}  # merged into OverallState by operator.add

def reduce_all(state: OverallState):
    return {}                        # runs once, after ALL branches complete

builder = StateGraph(OverallState)
builder.add_node("plan", plan)
builder.add_node("summarize", summarize)
builder.add_node("reduce", reduce_all)
builder.add_edge(START, "plan")
builder.add_conditional_edges("plan", fan_out, ["summarize"])
builder.add_edge("summarize", "reduce")   # implicit join: waits for every branch
builder.add_edge("reduce", END)
graph = builder.compile()
```

Rules: the fan-in key **must** have a reducer; cap the fan-out size explicitly (branch
count times per-branch tokens is your `budget`); the worker's schema can differ from the
graph schema — it receives exactly the `Send` payload.

---

## 6. Subgraphs

Two attachment patterns, chosen by schema relationship:

**Shared keys — attach the compiled subgraph directly as a node.** State flows through
the shared keys automatically; the parent's checkpointer propagates into the subgraph.

```python
child_builder = StateGraph(ChildState)      # ChildState shares keys with ParentState
...
child_graph = child_builder.compile()
parent_builder.add_node("qa_loop", child_graph)
```

**Different schemas — invoke the subgraph inside a wrapper node and map keys by hand.**

```python
class QAState(TypedDict):
    code: str
    errors: list[str]
    is_valid: bool

qa_graph = qa_builder.compile()

def qa_validation_node(parent_state: ParentState):
    child_out = qa_graph.invoke({
        "code": parent_state["generated_code"], "errors": [], "is_valid": False,
    })
    return {"generated_code": child_out["code"],
            "validation_passed": child_out["is_valid"]}
```

Use subgraphs when one schema would accumulate 10+ unrelated keys, or when a child loop
(e.g. an evaluator-optimizer cycle) deserves its own recursion budget: the wrapper node
can pass `config={"recursion_limit": N}` to the child `invoke`, giving the inner loop an
independent cap while its work still counts against the parent's superstep budget — the
hub's nested-loop rule.

---

## 7. Input/Output Schemas and Private Channels

Constrain what callers send and what they get back; keep working keys internal:

```python
class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class OverallState(InputState, OutputState):
    scratchpad: str                  # internal only: never returned to the caller

# LangGraph 1.x names; the 0.2 line called these `input=` / `output=`
builder = StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
```

**Private inter-node channels:** a node may type-hint a schema that is not the graph
schema; keys appearing only in such node schemas become channels visible to the nodes
that declare them, invisible in graph input/output. Use for handoff payloads two adjacent
nodes share (e.g. a raw tool dump the next node compresses) without polluting the public
state.

```python
class PrivateHandoff(TypedDict):
    raw_tool_output: str

def producer(state: OverallState):
    return {"raw_tool_output": ...}          # written to the private channel

def consumer(state: PrivateHandoff):         # reads ONLY the private channel
    return {"scratchpad": compress(state["raw_tool_output"])}
```

---

## 8. Node Retry Policies and Error Handling

Give flaky-by-nature nodes (network tools, test runs) a bounded retry policy at
`add_node` time instead of hand-rolling try/except loops:

```python
from langgraph.types import RetryPolicy

builder.add_node(
    "call_search_api",
    call_search_api,
    retry_policy=RetryPolicy(          # 0.2 line used `retry=`; 1.x uses `retry_policy=`
        max_attempts=3,                # aligns with hub budget.max_errors default
        initial_interval=0.5,
        backoff_factor=2.0,
        jitter=True,
        # retry_on=<exception class or predicate> -- default retries transient errors;
        # exact default predicate: verify against current docs for your minor version
    ),
)
```

Beyond transient retries, follow the hub Error-Mitigation pattern *in the graph*: catch
inside the node, classify (transient / bad input / wrong tool / permission), write the
classification into state, and let a conditional edge choose retry-with-reformulation,
fallback node, or the escalation gate. Blind retry of deterministic failures is the
anti-pattern `RetryPolicy` will happily execute for you — classify before you retry.

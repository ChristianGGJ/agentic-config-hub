# LangGraph Advanced State Design Patterns

This guide defines the advanced design patterns for stateful multi-agent systems using LangGraph (Python/TypeScript).

---

## 1. State Reducers & State Overwrite Prevention

In LangGraph, the global state is defined as a schema where fields can either be completely overwritten by nodes or merged using *reducers*.

### Overwrite vs. Merge (Python):
```python
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# 1. Base Message List Reducer (avoids list loss)
class AgentState(TypedDict):
    # add_messages appends new messages while deduplicating by ID
    messages: Annotated[list[BaseMessage], add_messages]
    
    # Simple strings/flags without Annotated get overwritten by the latest node output
    current_phase: str
    is_approved: bool
```

### Key Practices:
* **Deduplication**: Always use `add_messages` (or custom append reducers) for array fields (e.g. lists of files, errors, or feedback).
* **State Isolation**: When returning updates from a node, return only the *keys* that changed. Do not return the entire state object.

---

## 2. Advanced Conditional Edges & Structured Routers

Conditional edges decide the next node based on the current state. To prevent routing errors, use structured routing outputs instead of raw text parsing.

### Code Pattern (Structured Router edge):
```python
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 1. Define the routing schema
class RouteDecision(BaseModel):
    next_node: Literal["write_code", "escalate", "finish"] = Field(
        description="The next node to execute based on validation results."
    )
    rationale: str = Field(description="Brief explanation for the routing decision.")

# 2. Bind model to output schema
llm = ChatOpenAI(model="gpt-4o-mini").with_structured_output(RouteDecision)

# 3. Router Edge function
def router_edge(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1].content
    
    prompt = ChatPromptTemplate.from_template(
        "Analyze the validation result and decide the next node.\nResult: {result}"
    )
    
    decision: RouteDecision = llm.invoke(prompt.format(result=last_message))
    return decision.next_node
```

---

## 3. Human-in-the-Loop & Time-Travel Interrupts

To prevent agents from executing irreversible actions (e.g., git commits, database updates) without approval, use interrupts.

### Code Pattern (Interrupt & Resume):
```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

# 1. Initialize Graph & State
workflow = StateGraph(AgentState)

# 2. Add Nodes
workflow.add_node("architect", architect_node)
workflow.add_node("scaffold", scaffold_node) # Irreversible action

# 3. Set up transitions
workflow.add_edge(START, "architect")
workflow.add_edge("architect", "scaffold")
workflow.add_edge("scaffold", END)

# 4. Compile with Checkpointer & Interrupt
memory = MemorySaver()
app = workflow.compile(
    checkpointer=memory,
    # Pause execution BEFORE starting the scaffold node
    interrupt_before=["scaffold"]
)

# --- Runtime Execution ---
# thread_id identifies the conversation state checkpoint
config = {"configurable": {"thread_id": "user-session-123"}}

# Launch graph: it will run START -> architect and pause BEFORE scaffold
events = app.stream({"messages": [("user", "Build the database connection.")]}, config)

# Resume execution after human approval
# app.invoke(None, config)
```

---

## 4. Hierarchical Subgraphs

Decompose large, complex graphs into smaller, modular subgraphs. This avoids single state schemas containing dozens of unrelated keys.

### Code Pattern (Parent-Child States):
```python
# 1. Define Child Graph (QA Validation Loop)
class QAState(TypedDict):
    code: str
    errors: list[str]
    is_valid: bool

qa_builder = StateGraph(QAState)
qa_builder.add_node("run_tests", run_tests_node)
qa_builder.add_node("fix_errors", fix_errors_node)
# ... compile qa_graph

# 2. Parent Node invokes Child Graph
def qa_validation_node(parent_state: AgentState) -> dict:
    # Extract sub-state
    child_input = {
        "code": parent_state["generated_code"],
        "errors": [],
        "is_valid": False
    }
    
    # Run the compiled child subgraph synchronously
    child_output = qa_graph.invoke(child_input)
    
    # Map output back to Parent State keys
    return {
        "generated_code": child_output["code"],
        "validation_passed": child_output["is_valid"]
    }
```

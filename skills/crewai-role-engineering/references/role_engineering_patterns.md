# CrewAI Advanced Role Engineering & Collaboration Patterns

This guide defines the advanced design patterns for structuring multi-agent teams, task synchronization, and memory configurations using CrewAI.

---

## 1. Persona Formulations & Anti-Overlap Rubric

To prevent agents from duplicating efforts or entering execution deadlocks, enforce strict boundaries in roles, goals, and backstories.

### Structuring Agent Personas (Python):
```python
from crewai import Agent

# Good Practice: Bounded, non-overlapping domains
product_owner = Agent(
    role="Software Product Owner",
    goal="Translate raw business requirements into precise User Stories.",
    backstory="You are a veteran PM. Your job is exclusively to define 'what' needs to be built and 'why', writing acceptance criteria. You never write code.",
    verbose=True,
    allow_delegation=False
)

developer = Agent(
    role="Senior Backend Developer",
    goal="Design database schemas and write functional API code.",
    backstory="You are a C# engineer. Your job is to draft database entities and controller implementations. You only look at acceptance criteria; you do not decide product scope.",
    verbose=True,
    allow_delegation=False
)
```

### Anti-Overlap Guidelines:
* **No Code in Backstories**: Never write generic descriptions like "You are a helpful AI assistant." Be explicit about the role constraints.
* **Disable Delegation by Default**: Set `allow_delegation=False` on worker agents. Only set it to `True` for managers or supervisors.

---

## 2. Hierarchical Orchestration & Intermediate QA Validation

When a workflow requires dynamic task assignment or intermediate quality reviews, use hierarchical processes managed by a Manager agent.

### Code Pattern (Hierarchical Crew):
```python
from crewai import Crew, Process, Task
from langchain_openai import ChatOpenAI

# 1. Define tasks with expected outputs
requirements_task = Task(
    description="Review the business brief and list acceptance criteria.",
    expected_output="A markdown document detailing 5 acceptance criteria.",
    agent=product_owner # Explicitly assigned
)

coding_task = Task(
    description="Write C# controller code passing the acceptance criteria.",
    expected_output="C# class file containing the controllers.",
    agent=developer
)

# 2. Initialize the Crew with a Manager LLM
crew = Crew(
    agents=[product_owner, developer],
    tasks=[requirements_task, coding_task],
    process=Process.hierarchical, # Orchestrated by manager LLM
    manager_llm=ChatOpenAI(model="gpt-4o-mini"),
    verbose=True
)

result = crew.kickoff()
```

---

## 3. Persistent Memory Sync & Call Caching

CrewAI utilizes three memory subsystems to allow agents to accumulate knowledge across runs without bloating the context window.

### Code Pattern (Memory & Cache Setup):
```python
crew = Crew(
    agents=[product_owner, developer],
    tasks=[requirements_task, coding_task],
    memory=True, # Enables memory sync
    # Custom memory configurations can be mapped internally
    verbose=True,
    cache=True # Caches tool calls to reduce cost and latency
)
```

### Memory Tiers:
1. **Short-Term Memory**: Shared context during execution, utilizing RAG to pull previous outputs.
2. **Long-Term Memory**: SQLite-backed history persisting across distinct runs.
3. **Entity Memory**: Semantic store extracting and linking key terms (e.g. metadata, user settings).

---

## 4. Asynchronous Execution & Callbacks

For tasks that are independent, run them in parallel to save time, and merge them using a final collector task.

### Code Pattern (Async Tasks):
```python
research_market_task = Task(
    description="Search the web for competitor pricing models.",
    expected_output="CSV table listing competitor prices.",
    agent=product_owner,
    async_execution=True # Runs in parallel
)

user_feedback_task = Task(
    description="Extract key feature requests from user survey logs.",
    expected_output="Bullet list of top 3 desired features.",
    agent=product_owner,
    async_execution=True # Runs in parallel
)

# Collector task (wait for both async tasks to complete)
report_task = Task(
    description="Consolidate research findings and feedback logs into a product roadmap.",
    expected_output="Markdown document outlining the roadmap.",
    agent=product_owner,
    context=[research_market_task, user_feedback_task] # Dependent context
)
```

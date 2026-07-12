# CrewAI Tools, Task Parametrization, and Structured Outputs

LLM assignment, custom tools, kickoff inputs, typed outputs, guardrails,
async execution, and callbacks/usage metrics.

**Version assumption:** CrewAI 0.100+ (2025/2026). Version-sensitive members
are marked "verify against current docs".

---

## 1. LLM Assignment and Per-Agent Tiering

Current CrewAI binds models through its native `LLM` class (LiteLLM-backed
`provider/model` strings). The `ChatOpenAI`/LangChain import seen in older
tutorials is the legacy pattern — do not use it in new code.

```python
from crewai import Agent, LLM

# Model IDs below are current-generation examples (2025/2026 families).
# Verify exact IDs against your provider docs; define them once, centrally.
FRONTIER = LLM(model="anthropic/claude-sonnet-4-5", temperature=0.2)
UTILITY  = LLM(model="openai/gpt-5-mini", temperature=0.0)

reviewer = Agent(
    role="QA Reviewer",
    goal="...",
    backstory="...",
    llm=FRONTIER,      # reasoning-heavy role: frontier/balanced tier
)

formatter = Agent(
    role="Report Formatter",
    goal="...",
    backstory="...",
    llm=UTILITY,       # mechanical transformation: utility tier
)
```

Notes:

- `LLM(...)` also accepts `max_tokens`, `api_key`, `base_url`, and other
  LiteLLM passthrough params (verify the full set against current docs).
- Local/BYO endpoints work through the same class (e.g. Ollama provider
  strings) — the hub is provider-agnostic; never hard-require a paid vendor.
- Which tier is right per role is a strategy question owned by the
  `multi-llm-routing` sibling skill; the table in SKILL.md gives the CrewAI
  defaults (frontier for manager/review, utility for extract/format).

---

## 2. Custom Tools

Agents without tools can only talk. Two real APIs exist in `crewai.tools`:

### `@tool` decorator — quick functional tools

```python
from crewai.tools import tool

@tool("Search internal docs")
def search_docs(query: str) -> str:
    """Search the internal documentation index and return the top 3 matching
    passages with their doc IDs. Input: a plain-language search query."""
    # deterministic implementation here (DB/index lookup, file scan, ...)
    return _index.search(query, k=3)
```

The function name, type hints, and docstring become the tool schema the LLM
sees — write the docstring as an instruction ("Input: ..."), not a comment.

### `BaseTool` subclass — typed args, the fix for hallucinated arguments

```python
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

class TicketLookupInput(BaseModel):
    ticket_id: str = Field(
        ...,
        description="Ticket key in PROJECT-123 format. Never a URL, never a title.",
    )

class TicketLookupTool(BaseTool):
    name: str = "ticket_lookup"
    description: str = (
        "Fetch status, assignee, and summary for one ticket by its key. "
        "Example call: ticket_id='PAY-421'."
    )
    args_schema: Type[BaseModel] = TicketLookupInput

    def _run(self, ticket_id: str) -> str:
        record = _tracker.get(ticket_id)
        if record is None:
            return "ERROR: no ticket with key %s. Check the key format." % ticket_id
        return record.summary_line()

developer = Agent(
    role="Senior Backend Developer",
    goal="...",
    backstory="...",
    tools=[TicketLookupTool(), search_docs],   # instances / decorated funcs
)
```

Design rules that prevent hallucinated tool args:

1. **Typed `args_schema` with per-field descriptions** — the single highest
   -leverage fix; the model sees the field docs at call time.
2. **One example invocation in the description** — anchors the format.
3. **Return actionable error strings, never raise for expectable misses** —
   "ERROR: no ticket with key X. Check the key format." lets the agent
   self-correct within its loop; an exception burns an error-mitigation cycle.
4. Tools can also be attached per-`Task` via `Task(tools=[...])`, which
   overrides the agent's tool set for that task — use this to deny a
   general-purpose agent dangerous tools on specific tasks.
5. Tool-result caching can be tuned with a `cache_function` on the tool
   (return `False` to skip caching a result) — verify against current docs.

---

## 3. Kickoff Inputs and `{placeholder}` Interpolation

Task `description`/`expected_output` and agent `role`/`goal`/`backstory`
support `{placeholder}` interpolation filled from `kickoff(inputs=...)`:

```python
research = Task(
    description="Research {topic} for the {audience} audience. "
                "Focus on developments since {since_year}.",
    expected_output="A markdown brief with 5 cited findings about {topic}.",
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[research])

result = crew.kickoff(inputs={
    "topic": "vector database pricing",
    "audience": "engineering leadership",
    "since_year": "2024",
})
```

- Every `{name}` must have a matching key in `inputs`, or kickoff raises —
  audit placeholders whenever you edit descriptions.
- **Batching:** `kickoff_for_each(inputs=[{...}, {...}])` runs the crew once
  per dict and returns a list of results. Async variants exist:
  `kickoff_async(...)` and `kickoff_for_each_async(...)`.

```python
results = crew.kickoff_for_each(inputs=[
    {"topic": "vector databases", "audience": "eng", "since_year": "2024"},
    {"topic": "reranker models",  "audience": "eng", "since_year": "2024"},
])
```

Cost warning: `kickoff_for_each` multiplies the full crew cost by N inputs.
Check `crew.usage_metrics` on a single run first, then budget N accordingly
(hub `budget` exit-condition thinking applied at the batch level).

---

## 4. Structured Outputs

Typed handoffs stop downstream agents from parsing prose. Three mechanisms on
`Task`:

```python
from pydantic import BaseModel
from typing import List

class AcceptanceCriteria(BaseModel):
    story: str
    criteria: List[str]        # each entry "AC-n: ..."

requirements = Task(
    description="Write the user story and acceptance criteria for {feature}.",
    expected_output="One story plus 3-7 numbered acceptance criteria.",
    agent=product_owner,
    output_pydantic=AcceptanceCriteria,   # validated model instance
)

audit_log = Task(
    description="Summarize decisions made in this run.",
    expected_output="A dated markdown changelog entry.",
    agent=product_owner,
    output_file="output/decisions.md",    # write artifact to disk
)
```

Access after the run:

```python
result = crew.kickoff(inputs={"feature": "billing exports"})

result.raw          # final task's raw text
result.pydantic     # model instance when the final task set output_pydantic
result.json_dict    # dict when the final task set output_json
result.tasks_output # list of TaskOutput for every task
result.token_usage  # token accounting for the run

ac = result.tasks_output[0].pydantic     # per-task typed access
```

Selection guidance is in SKILL.md (Decision Frameworks: Output typing). Key
rules: `output_pydantic` for task-to-task handoffs, `output_file` for large
artifacts (keeps context lean), and never rely on "return JSON" instructions
in prose when a typed field exists.

---

## 5. Task Guardrails (success predicates at the handoff)

A `guardrail` callable validates the task output *before* it is finalized and
handed on. Return `(True, validated_output)` to accept or `(False, "specific
fixable feedback")` to send the agent back for a bounded retry:

```python
from crewai import Task
from crewai.tasks.task_output import TaskOutput   # verify import path

def at_least_three_criteria(output: TaskOutput):
    model = output.pydantic
    if model is None:
        return (False, "Output did not validate against AcceptanceCriteria.")
    if len(model.criteria) < 3:
        return (False,
                "Only %d acceptance criteria; write at least 3, numbered AC-n."
                % len(model.criteria))
    bad = [c for c in model.criteria if not c.startswith("AC-")]
    if bad:
        return (False, "These criteria lack AC-n numbering: %r" % bad)
    return (True, output)

requirements = Task(
    description="Write the user story and acceptance criteria for {feature}.",
    expected_output="One story plus 3-7 numbered acceptance criteria.",
    agent=product_owner,
    output_pydantic=AcceptanceCriteria,
    guardrail=at_least_three_criteria,
    max_retries=2,          # bounded retry on guardrail failure
)
```

Hub-canon reading: the guardrail is the task's **success_predicate** — a
machine check with evidence — and `max_retries` is its `max_iterations`.
Exhausting retries fails the task run; treat that as the escalation event
(surface it, do not swallow it). Newer releases also accept a plain string
guardrail evaluated by an LLM ("no-code guardrails") — deterministic
callables are preferred in this hub; verify string support against current
docs before using it.

Guardrail quality rules:

- Feedback must be *actionable* ("write at least 3, numbered AC-n"), because
  it is injected into the retry prompt. "Invalid output" produces retry
  storms.
- Keep `max_retries` at 2-3. A guardrail failing 3 times is a persona or
  task-description defect, not a retry deficit.
- Validate structure with `output_pydantic` first; guardrails then check
  *semantics* (counts, ID formats, cross-references), not JSON shape.

---

## 6. Async Execution and Context Chaining

Independent tasks can run in parallel and merge through `context`:

```python
market = Task(
    description="Collect competitor pricing for {product}.",
    expected_output="Markdown table: competitor, plan, monthly price.",
    agent=researcher,
    async_execution=True,
)

feedback = Task(
    description="Extract the top feature requests from the survey export.",
    expected_output="Bullet list of the top 3 requested features.",
    agent=researcher,
    async_execution=True,
)

roadmap = Task(
    description="Merge the pricing research and feature requests into a roadmap.",
    expected_output="A one-page roadmap with priorities and rationale.",
    agent=product_owner,
    context=[market, feedback],   # waits for both; receives their outputs
)
```

Rules: only tasks with no mutual data dependency may set
`async_execution=True`; the collector task lists them in `context`. Passing
*every* prior task in `context` is the context-bloat failure mode — pass only
what the task consumes.

---

## 7. Callbacks and Usage Metrics

Two callback hooks exist, plus post-run accounting:

```python
def on_task_done(output):            # TaskOutput
    print("[task] %s -> %d chars by %s"
          % (output.description[:48], len(output.raw), output.agent))

def on_step(step):
    # Step object shape varies by version (tool invocations, agent actions);
    # use getattr defensively and verify fields against current docs.
    tool = getattr(step, "tool", None)
    if tool:
        print("[step] tool=%s" % tool)

crew = Crew(
    agents=[researcher, product_owner],
    tasks=[market, feedback, roadmap],
    task_callback=on_task_done,   # fires after each task completes
    step_callback=on_step,        # fires on each agent step (also per-Agent)
)

result = crew.kickoff()
print(crew.usage_metrics)
# UsageMetrics: total_tokens, prompt_tokens, completion_tokens,
# successful_requests (field names - verify against current docs)
```

Uses in this hub:

- `task_callback` — audit log per handoff; append TaskOutput summaries to a
  run ledger for the SELF-REVIEW phase.
- `step_callback` — the attachment point for the runaway-prevention ledger
  (budget / no_progress / oscillation) shown in
  `role_engineering_patterns.md` section 6.
- `crew.usage_metrics` — per-run `budget` evidence; log it every kickoff and
  alert on step changes.
- Per-task `callback=` also exists on `Task` for task-specific side effects
  (e.g., posting one task's output to a channel).

For exporting these signals to real telemetry (OTel, LangSmith-class tools),
see the `agentic-observability-telemetry` sibling skill; this reference stays
inside CrewAI's own surface.

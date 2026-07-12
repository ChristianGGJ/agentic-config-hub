# CrewAI Flows and the YAML Project Pattern

Crews vs Flows decision guidance, Flow anatomy (`@start`/`@listen`/`@router`,
typed state), crews inside flows, and the documented recommended project
structure (`agents.yaml`/`tasks.yaml` + `@CrewBase`).

**Version assumption:** CrewAI 0.100+ (2025/2026). Version-sensitive members
are marked "verify against current docs".

---

## 1. Crews vs Flows: What Each One Is

- A **Crew** is a team of LLM agents working through a task list. Control flow
  inside a crew is *emergent*: the process type, personas, and (in
  hierarchical mode) a manager LLM decide what happens next.
- A **Flow** is an event-driven Python state machine. Control flow is
  *deterministic*: decorated methods fire when their trigger fires, state is a
  typed object you own, and branching is plain Python you can unit-test.
- The current recommended architecture for production systems is
  **crews inside flows**: Flows own routing, state, budgets, and gates;
  crews own the collaborative LLM work inside individual flow steps.

| Signal in your requirements | Use |
|---|---|
| "The agents should figure out the steps" | Crew alone |
| "If X then A else B", retries with caps, mixing DB/API calls with LLM work | Flow (with crews inside for LLM-heavy steps) |
| Auditable exit conditions, headless HITL gates, per-step budget checks | Flow — these are deterministic-code concerns, not persona concerns |
| Cyclic graphs with checkpoint/resume and per-node state reducers | Neither — see the `langgraph-state-design` sibling skill |

Rule of thumb (matches the SKILL.md decision table): start with a plain
sequential crew; the moment a branch, a bounded loop, or a non-LLM step
appears, wrap it in a Flow rather than contorting personas to fake control
flow.

---

## 2. Flow Anatomy

Flows live in `crewai.flow.flow` (newer releases also re-export from
`crewai.flow` — verify against current docs):

```python
from crewai.flow.flow import Flow, start, listen, router
```

- `@start()` — marks an entry-point method; runs when `kickoff()` is called.
- `@listen(step)` — runs when `step` completes; receives `step`'s return
  value as its argument. Accepts the method object or its name as a string.
- `@router(step)` — runs when `step` completes and **returns a string
  label**; methods decorated `@listen("label")` fire for that branch.
- `or_(a, b)` / `and_(a, b)` — combinators for `@listen`: fire when any
  (`or_`) or all (`and_`) of the listed steps have completed.

State comes in two forms:

- **Unstructured:** `class MyFlow(Flow):` — `self.state` behaves like a dict
  with an auto-generated `id` key. Fine for prototypes.
- **Structured (preferred in this hub):** `class MyFlow(Flow[MyState])` with
  a Pydantic `BaseModel` — typed, validated, self-documenting, and the
  natural place to keep exit-condition counters.

`flow.kickoff()` runs the flow and returns the final method's output;
`kickoff(inputs={...})` initializes matching state fields. `flow.plot("name")`
writes an HTML visualization of the method graph — useful evidence for
design reviews.

## 3. Worked Example: Bounded Loop, Gate, and Escalation in a Flow

The example below shows the hub-canonical use of a Flow: the retry loop,
budget, success predicate, and escalation path are **deterministic Python
declared before iteration 1** — not persona instructions.

```python
from pydantic import BaseModel
from crewai.flow.flow import Flow, start, listen, router


class ReleaseState(BaseModel):
    version: str = ""
    notes: str = ""
    attempts: int = 0
    contract_met: bool = False


def notes_contract(text: str) -> bool:
    """Deterministic success_predicate for the drafting step."""
    return ("## Changes" in text) and ("## Breaking changes" in text)


class ReleaseNotesFlow(Flow[ReleaseState]):

    MAX_ATTEMPTS = 3          # hub: max_iterations, declared before iteration 1

    @start()
    def draft_notes(self):
        # Crew-inside-flow: the LLM team runs inside one bounded flow step.
        while self.state.attempts < self.MAX_ATTEMPTS:
            self.state.attempts += 1
            result = NotesCrew().crew().kickoff(
                inputs={"version": self.state.version}
            )
            if notes_contract(result.raw):     # hub: success_predicate
                self.state.notes = result.raw
                self.state.contract_met = True
                return
        self.state.contract_met = False        # exhausted -> escalation path

    @router(draft_notes)
    def gate(self):
        return "review" if self.state.contract_met else "escalate"

    @listen("review")
    def human_gate(self):
        # Headless HITL: persist the draft and enqueue it for human approval.
        # Publishing happens in a separate, human-triggered process - the
        # flow never performs the irreversible action itself.
        save_for_approval(self.state.version, self.state.notes)
        return "queued for human approval"

    @listen("escalate")
    def escalate(self):
        # hub: escalation_trigger -- structured stop-and-report, not a crash.
        return (
            "[exit-condition] escalation_trigger: notes failed the contract "
            "%d times for version %s; last draft preserved in state."
            % (self.state.attempts, self.state.version)
        )


flow = ReleaseNotesFlow()
outcome = flow.kickoff(inputs={"version": "2.3.0"})
```

Why this shape is canon-compliant:

- `MAX_ATTEMPTS` and `notes_contract` are visible, testable, and declared
  up front — an auditor can verify them without running anything.
- The irreversible action (publish) sits **behind** the human gate, outside
  the flow (5-Phase Protocol Phase 3: HUMAN GATE before consequential work).
- The escalation branch produces an evidence-bearing report instead of a
  bare exception.
- Inside `NotesCrew`, per-agent `max_iter`/`max_rpm`/`max_execution_time`
  still apply (see `role_engineering_patterns.md` section 6) — the flow
  bounds the outer loop, the crew bounds the inner ones. Hub nesting rule:
  the inner crew consumes the outer flow's budget; the flow keeps its own
  independent cap.

**State persistence:** `@persist()` (from `crewai.flow.persistence`) can be
applied at class or method level to checkpoint flow state (SQLite-backed by
default), enabling resumption — verify the decorator surface and restore
semantics against current docs before depending on it for HITL waits.

---

## 4. The YAML Project Pattern (`@CrewBase`)

The documented recommended structure for team-maintained crews separates
prompts (YAML, iterated by non-engineers) from wiring and bounds (Python,
owned by engineers and auditable by `scripts/crewai_runaway_auditor.py`).

Scaffold and run with the CLI:

```bash
crewai create crew research_crew    # generates the layout below
crewai run                          # runs main.py's kickoff
```

Generated layout (trimmed to what matters):

```
research_crew/
└── src/research_crew/
    ├── config/
    │   ├── agents.yaml       # personas: role / goal / backstory
    │   └── tasks.yaml        # task contracts
    ├── crew.py               # @CrewBase wiring: tools, bounds, process
    └── main.py               # kickoff(inputs={...}) entry point
```

### config/agents.yaml — personas only

```yaml
researcher:
  role: >
    {topic} Senior Researcher
  goal: >
    Find and rank the 5 most relevant {topic} developments since {since_year}.
  backstory: >
    You report only findings you can cite with a source. When sources
    conflict, you present both and say so instead of silently picking one.
```

### config/tasks.yaml — task contracts

```yaml
research_task:
  description: >
    Research {topic}. Focus on developments since {since_year}.
  expected_output: >
    A markdown brief with exactly 5 findings, each with a one-line citation.
  agent: researcher
```

The `agent:` key names the `@agent` method in `crew.py`. `{placeholders}`
interpolate from `kickoff(inputs={...})` exactly as in inline Python (see
`crewai_tools_tasks_outputs.md` section 3). Additional constructor fields
(e.g. `llm`, `output_file`) can also be set in YAML — verify the supported
key set against current docs.

### crew.py — wiring, tools, and bounds stay in Python

```python
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class ResearchCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher"],   # persona from YAML
            tools=[search_docs],                       # wiring in Python
            max_iter=10,                               # bounds in Python,
            max_execution_time=600,                    # visible to the
            max_rpm=20,                                # runaway auditor
            allow_delegation=False,
        )

    @task
    def research_task(self) -> Task:
        return Task(config=self.tasks_config["research_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,     # collected from @agent methods
            tasks=self.tasks,       # collected from @task methods, in order
            process=Process.sequential,
            verbose=True,
        )
```

`@CrewBase` collects `@agent`/`@task` methods into `self.agents` /
`self.tasks`; task order follows method definition order. `@before_kickoff`
and `@after_kickoff` hooks (also in `crewai.project`) run around each
kickoff for input mutation and output post-processing — verify signatures
against current docs.

### main.py

```python
from research_crew.crew import ResearchCrew

def run():
    ResearchCrew().crew().kickoff(inputs={
        "topic": "vector database pricing",
        "since_year": "2024",
    })
```

### Division-of-ownership rule (hub-calibrated)

| Concern | Lives in | Why |
|---|---|---|
| role / goal / backstory | `agents.yaml` | Prompt iteration without code review noise |
| description / expected_output | `tasks.yaml` | Contract wording iterated alongside personas |
| tools, llm tiering, `output_pydantic`, guardrails | `crew.py` | Typed objects; cannot be expressed cleanly in YAML |
| `max_iter`, `max_rpm`, `max_execution_time`, `allow_delegation`, `human_input` | `crew.py` | Runaway-prevention bounds must be auditable in source — the static auditor reads Python, and a YAML edit must never be able to silently remove a guard |

Note on auditing: `crewai_runaway_auditor.py` reports constructors that use
`config=` and omit explicit bounds as *unverifiable*, not as passes — keep
the bounds in Python so the audit stays meaningful.

---

## 5. Choosing at a Glance

1. One linear deliverable, trusted defaults — sequential Crew, inline Python.
2. Same, but maintained by a team / CI-deployed — YAML `@CrewBase` project.
3. Branching, bounded loops, non-LLM steps, headless HITL, budget checks —
   Flow with crews inside (section 3 pattern).
4. Full cyclic state machines with checkpoint/resume — `langgraph-state-design`
   sibling skill; do not force Flows to be a general graph runtime.

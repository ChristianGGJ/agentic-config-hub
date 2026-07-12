# CrewAI Role Engineering Patterns

Persona formulations, delegation rules, hierarchical orchestration, memory
configuration, HITL gates, and runaway prevention for CrewAI teams.

**Version assumption:** CrewAI 0.100+ (2025/2026). Version-sensitive members
are marked "verify against current docs".

**Boundary note:** framework-agnostic persona/system-prompt craft is owned by
the sibling skill `agent-designer`; this reference covers only how personas
map onto CrewAI's constructor surface and how CrewAI executes them.

---

## 1. Persona Engineering: Backstories That Change Behavior

CrewAI injects `role`, `goal`, and `backstory` into the agent's system prompt.
They are not documentation — they are executable configuration. Each sentence
should do one of four jobs; delete any sentence that does none:

| Pattern | What it does | Example clause |
|---|---|---|
| **Constraint clause** | Fences scope; prevents overlap and delegation loops | "You never write code. You only produce acceptance criteria." |
| **Method anchor** | Fixes *how* the agent works, making output reproducible | "You always start from the acceptance criteria and cite each one by ID in your output." |
| **Escalation instruction** | Converts uncertainty into a report instead of a guess | "If requirements are ambiguous or data is missing, you state exactly what is missing instead of estimating." |
| **Format anchor** | Stabilizes tone and structure across runs | "You write terse, numbered findings. No preamble, no apologies." |

Anti-pattern — **biography fluff**: "You spent 10 years at a top tech company
and are passionate about quality" spends tokens without bounding behavior.
Expertise framing is useful only when it changes vocabulary or assumptions
("You are a PostgreSQL specialist; you assume PostgreSQL 15+ semantics").

### Worked personas (anti-overlap pair)

```python
from crewai import Agent

product_owner = Agent(
    role="Software Product Owner",
    goal="Translate the business brief into numbered user stories with "
         "testable acceptance criteria.",
    backstory=(
        "You define WHAT must be built and WHY. You write user stories and "
        "acceptance criteria only - you never write code and never choose "
        "implementation technology. Each acceptance criterion you write is "
        "independently testable and numbered AC-1, AC-2, ... If the brief "
        "is ambiguous, you list the open questions instead of inventing scope."
    ),
    allow_delegation=False,
    max_iter=6,
    verbose=True,
)

developer = Agent(
    role="Senior Backend Developer",
    goal="Implement API endpoints that satisfy every numbered acceptance "
         "criterion you are given.",
    backstory=(
        "You implement exactly the acceptance criteria handed to you, citing "
        "each AC-n your code satisfies. You never re-scope requirements and "
        "never invent endpoints that no criterion asks for. If a criterion "
        "cannot be implemented as written, you report why instead of "
        "silently changing it."
    ),
    allow_delegation=False,
    max_iter=10,
    verbose=True,
)
```

Why this pair works: each backstory contains a constraint clause excluding the
other's territory, a method anchor (numbered ACs, cited ACs) that makes the
handoff machine-checkable, and an escalation instruction replacing guessing.

### Goal scoping

- `goal` is **agent-level and stable** across tasks; the per-run specifics
  belong in `Task.description` (with `{placeholders}` for parametrization).
- A good goal names one deliverable and its quality bar: "Produce X that
  satisfies Y." Goals with "and" usually indicate an agent that should be two
  agents (hub atomicity rule).
- Do not restate the goal in the backstory; the backstory explains method and
  boundaries, the goal names the target.

### Anti-overlap rubric

Before shipping a crew, check every agent pair:

1. Could both agents plausibly claim the same task? If yes, add mutually
   exclusive constraint clauses.
2. Do any two goals name the same deliverable? Merge or split.
3. Does any backstory instruct behavior that another agent's task requires?
   (e.g., reviewer allowed to "fix" code it reviews) — reviewers report,
   workers fix.

---

## 2. Delegation Rules

`allow_delegation=True` gives the agent two extra internal tools: **Delegate
work to coworker** and **Ask question to coworker**. That is the entire
mechanism — delegation is tool use, so everything known about tool misuse
applies (wrong target, vague instructions, loops).

- Default is `False` in current releases (early versions defaulted to `True`).
  Set it explicitly on every agent.
- Enable it only for supervisor/manager/QA roles whose *job* is routing work.
- Never enable it on two agents with overlapping personas — that is the
  classic delegation ping-pong loop (each decides the other is better suited).
- A delegating agent still consumes its own `max_iter`; each delegation round
  trip costs iterations on both sides. Budget accordingly.

---

## 3. Hierarchical Orchestration and Manager Configuration

Use `Process.hierarchical` when task assignment must be decided at runtime or
outputs need managerial review before acceptance. Current LLM binding uses the
native `LLM` class (LiteLLM-backed provider/model strings) — **not** the
legacy LangChain `ChatOpenAI` pattern from pre-1.0 tutorials:

```python
from crewai import Agent, Crew, LLM, Process, Task

# Model IDs are current-generation examples - verify exact IDs against your
# provider's docs; prefer configuring them in one place for easy rotation.
manager_llm = LLM(model="anthropic/claude-sonnet-4-5", temperature=0.1)

requirements_task = Task(
    description="Review the business brief and produce acceptance criteria.",
    expected_output="A markdown list of numbered, testable acceptance criteria.",
    agent=product_owner,
)

coding_task = Task(
    description="Implement the API endpoints satisfying the acceptance criteria.",
    expected_output="Python source for the endpoints, citing each AC-n satisfied.",
    agent=developer,
    context=[requirements_task],
)

crew = Crew(
    agents=[product_owner, developer],       # the manager is NOT listed here
    tasks=[requirements_task, coding_task],
    process=Process.hierarchical,
    manager_llm=manager_llm,
    verbose=True,
)
result = crew.kickoff()
```

### `manager_llm` vs `manager_agent`

```python
manager = Agent(
    role="Delivery Manager",
    goal="Route tasks to the right specialist and accept work only when it "
         "meets its expected_output contract.",
    backstory=(
        "You coordinate specialists. You NEVER execute work yourself - you "
        "delegate, review the result against the task's expected output, and "
        "either accept it or return it once with specific corrections."
    ),
    allow_delegation=True,
    max_iter=15,
)

crew = Crew(
    agents=[product_owner, developer],
    tasks=[requirements_task, coding_task],
    process=Process.hierarchical,
    manager_agent=manager,                    # custom manager persona
)
```

| Choose | When |
|---|---|
| `manager_llm` | Stock manager prompt is fine; you only pick the model. Fastest setup, opaque behavior. |
| `manager_agent` | You need manager rules: "never execute work yourself", domain-specific acceptance criteria, bounded review rounds ("return work at most once"). |

Manager pitfalls: (1) putting the manager in `agents=[...]` — it must be
passed only via `manager_agent`; (2) a utility-tier manager model — routing
and review are frontier-tier work; (3) unbounded review cycles — write "at
most one correction round per task" into the manager backstory.

### Planning mode

`Crew(planning=True, planning_llm=LLM(...))` prepends a planning step whose
output is injected into every task — useful for sequential crews that benefit
from a shared plan without paying the hierarchical manager tax. It is a plan
annotation, not dynamic routing.

---

## 4. Memory Configuration

`Crew(memory=True)` enables CrewAI's memory subsystems (short-term RAG memory
for the current run, long-term SQLite-backed memory across runs, and entity
memory). Configure the embedder explicitly rather than inheriting defaults:

```python
crew = Crew(
    agents=[product_owner, developer],
    tasks=[requirements_task, coding_task],
    memory=True,
    embedder={
        "provider": "openai",   # also: "ollama", "google", others per docs
        "config": {"model": "text-embedding-3-small"},
    },
    cache=True,                 # cache tool results within/between executions
)
```

Operational facts that matter in production:

- **Persistence location** is controlled by the `CREWAI_STORAGE_DIR`
  environment variable (verify against current docs); otherwise a platform
  default data dir is used. Pin it in deployments so memory survives image
  rebuilds intentionally, not accidentally.
- **Resetting:** stale long-term memory causes agents to confidently repeat
  outdated facts across runs. Reset from the CLI:

  ```bash
  crewai reset-memories --all      # see reset-memories --help for per-tier flags
  ```

- **External memory:** newer releases support supplying an external memory
  implementation (e.g., `ExternalMemory` backed by a provider such as Mem0)
  instead of the built-in stores — verify the current class name and wiring
  against docs before depending on it. For hub designs that need real
  long-term memory architecture, see the `hybrid-rag-memory` sibling skill.
- Do not enable `memory=True` reflexively: for stateless one-shot crews it
  adds embedding cost and a contamination channel between runs.

---

## 5. Human-in-the-Loop Gates

`Task(human_input=True)` is CrewAI's native HITL mechanism: after the agent
produces the task output, execution pauses, the human provides feedback, and
the agent revises before the output is finalized.

```python
deploy_plan = Task(
    description="Produce the production deployment plan for {service}.",
    expected_output="Ordered deployment steps with rollback plan per step.",
    agent=devops_engineer,
    human_input=True,   # hard stop: human reviews before this output stands
)
```

Placement rules (aligned with hub gate canon):

- Gate every task whose output drives an **irreversible** action downstream
  (deploy, delete, publish, send, migrate) — the gate must sit *upstream* of
  the irreversible consumer.
- Gate the **plan/manifest task** in plan-then-execute crews (5-Phase
  Protocol Phase 3: no implementation before an approved manifest).
- Do not gate every task: gates cost human latency; over-gating trains humans
  to rubber-stamp.

Production caveat: the built-in mechanism collects input on the console
(blocking). In services, host the crew inside a Flow and implement the gate as
a Flow step awaiting your own approval channel; console `human_input` is a
development-time gate.

---

## 6. Runaway Prevention Implementation

Native bounds (set on every agent — see SKILL.md for the calibrated-defaults
table and the full six-type mapping):

```python
worker = Agent(
    role="Report Writer",
    goal="...",
    backstory="...",
    max_iter=8,               # hub: max_iterations
    max_rpm=20,               # hub: budget (rate)
    max_execution_time=300,   # hub: budget (wall-clock seconds)
    allow_delegation=False,
)
```

Remember: hitting `max_iter` forces a best-effort final answer rather than
raising — pair it with a task guardrail so a forced, contract-missing answer
is caught (`success_predicate`), and treat a guardrail that exhausts
`max_retries` as the escalation event.

### Callback ledger for `no_progress` and `oscillation`

CrewAI has no native stall or oscillation detector. Implement both as a
crew-level `step_callback` ledger (hub canon: `no_progress` window 2,
`oscillation` A-B-A-B window 4):

```python
import hashlib
from collections import deque

class StepLedger:
    """Controller-owned counters; step logic cannot reset them (hub canon)."""

    def __init__(self, budget_calls=40):
        self.calls = 0
        self.budget = budget_calls
        self.actions = deque(maxlen=4)   # oscillation window
        self.state_hashes = deque(maxlen=2)  # no_progress window

    def _fire(self, condition, evidence):
        # Raising from a callback aborts the run with a traceback - a blunt
        # but effective tripwire. Verify propagation behavior on your
        # installed version; alternatively set a flag your Flow checks.
        raise RuntimeError(
            "[exit-condition] %s fired; evidence=%r" % (condition, evidence)
        )

    def __call__(self, step):
        # Attribute names on the step object vary by version (AgentAction /
        # tool invocation records) - verify against current docs.
        self.calls += 1
        if self.calls > self.budget:
            self._fire("budget", self.calls)

        tool = getattr(step, "tool", None)
        tool_input = getattr(step, "tool_input", None)
        sig = "%r|%r" % (tool, tool_input)
        self.actions.append(sig)
        a = list(self.actions)
        if len(a) == 4 and a[0] == a[2] and a[1] == a[3] and a[0] != a[1]:
            self._fire("oscillation", a)

        text = getattr(step, "text", "") or getattr(step, "output", "") or sig
        h = hashlib.sha256(str(text).encode("utf-8", "replace")).hexdigest()
        self.state_hashes.append(h)
        s = list(self.state_hashes)
        if len(s) == 2 and s[0] == s[1]:
            self._fire("no_progress", s)

ledger = StepLedger(budget_calls=40)
crew = Crew(
    agents=[worker],
    tasks=[task],
    step_callback=ledger,     # fires on every agent step
)
```

Post-hoc budget accounting comes free after any kickoff:

```python
result = crew.kickoff()
print(crew.usage_metrics)   # prompt/completion/total tokens, request count
```

Log `usage_metrics` per run and alert on deviation — a crew whose token usage
doubles without a task change is looping somewhere.

### Declaration discipline

Hub canon requires exit conditions to be **declared before iteration 1**. For
crews, that means the agent spec / crew module states, in one visible place:
each agent's `max_iter`/`max_rpm`/`max_execution_time`, the ledger budget, the
guarded tasks (guardrails as success predicates), and the gated tasks
(`human_input` as escalation). Run `scripts/crewai_runaway_auditor.py` to
verify the source matches the declaration.

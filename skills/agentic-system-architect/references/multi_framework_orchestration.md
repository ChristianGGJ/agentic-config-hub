# Multi-Framework Orchestration & Microservices Guide

This guide establishes the framework allocation strategy and API-First architectural design principles for building hybrid, multi-agent systems.

---

## 1. Framework Selection Matrix

When designing an agentic system, select the runtime framework based on the specific capabilities required by each component:

### 1. CrewAI (Role-Playing & Collaborative Processes)
* **Best for**: Scenarios where the final output relies on sequential or hierarchical collaboration between distinct personas (role-playing).
* **Ideal Tasks**:
  * **User Story (US) Generation**: Composing stories through collaborative review (Product Manager + Senior Dev + QA).
  * **Market & Content Research**: Searcher, Consolidator, and Writer agents cooperating sequentially to publish technical briefs.
* **Core Advantage**: Quick setup of sequential/hierarchical pipelines via descriptive `Role`, `Goal`, and `Backstory` properties without verbose control flow code.

### 2. LangGraph (Loop Engineering & Rigorous State Machines)
* **Best for**: Non-linear execution paths, cyclic state transitions, self-correcting code loops, and strict human-in-the-loop gating.
* **Ideal Tasks**:
  * **Defensive Code Review & Refactoring**: Nodes that write code, compile, and run unit tests, looping back to repair code (injecting stdout errors) until tests pass.
  * **Stateful File Processing**: Pipeline stages that clean, extract, and reload state if downstream errors occur.
* **Core Advantage**: Directed Acyclic Graphs (DAGs) and cyclic graphs that give developers control over execution states, thread memory, checkpoints, and manual approval gates.

### 3. Microsoft Agent Framework (Enterprise Backend & Native Binding)
* **Best for**: High-throughput applications running in typed core backends (C#/.NET) requiring native library access, database bindings, and enterprise dependency injection.
* **Ideal Tasks**:
  * **Infrastructure Automation**: Reading internal databases, triggering message queues, or executing system command line utilities.
  * **Native SDK Integration**: Consuming shared data types and internal APIs via clean DI patterns.
* **Core Advantage**: Modular, high-performance runtime utilizing `ChatClientAgent` and `Microsoft.Extensions.AI` abstractions.

---

## 2. API-First Agential Microservices Architecture

To prevent library clashes and optimize compute, decouple dynamic frameworks into isolated services consumed by the core backend.

```text
 ┌────────────────────────────────────────────────────────┐
 │            BACKEND / APLICACIÓN PRINCIPAL              │
 └──────────────────────────┬─────────────────────────────┘
                            │ (Llamadas HTTP / gRPC)
         ┌──────────────────┴──────────────────┐
         ▼                                     ▼
 ┌───────────────┐                     ┌───────────────┐
 │ API LangGraph │                     │  API CrewAI   │
 │ (Python/TS)   │                     │   (Python)    │
 ├───────────────┤                     ├───────────────┤
 │ Tareas: Loops │                     │ Tareas: Roles │
 │ de Código y   │                     │ Creativos y   │
 │ Auto-corrección                     │ Planificación │
 └───────────────┘                     └───────────────┘
```

### Architectural Requirements:
1. **Isolation**: Package LangGraph and CrewAI runtimes into microservices using FastAPI (Python) or Express (TypeScript).
2. **API Contract**: The main application communicates with these microservices via standard HTTP REST endpoints or gRPC.
3. **LLM Tiering**:
   - **Reasoning Tier**: Use highly capable models (e.g. `claude-3-5-sonnet`, `o1`, `o3`) for critical decision-making nodes, code repair, and loop evaluations.
   - **Utility Tier**: Use faster, cost-efficient models (e.g. `gpt-4o-mini`, `ollama/llama3`) for repetitive extraction tasks, summarizing, and formatting.

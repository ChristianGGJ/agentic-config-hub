---
name: "agent-designer"
description: "Use when the user asks to design a single agent's persona, system prompt, or tool schemas, or to architect multi-agent systems — selecting architecture patterns (supervisor, swarm, hierarchical, pipeline), defining agent roles and communication protocols, and planning agent evaluation. Not for workflow orchestration (see agent-workflow-designer) or ecosystem governance and HITL hardening (see agentic-system-architect)."
---

# Agent Designer - Multi-Agent System Architecture

**Tier:** POWERFUL  
**Category:** Engineering  
**Tags:** AI agents, architecture, system design, orchestration, multi-agent systems

## Overview

Agent Designer is a comprehensive toolkit for designing individual agents (persona, system prompt, tools) and architecting multi-agent systems. It provides structured approaches to agent architecture patterns, persona and system-prompt authoring, tool design principles, communication strategies, and performance evaluation frameworks for building robust, scalable AI agent systems.

## When NOT to Use This Skill

- **Workflow orchestration** — sequencing multi-step workflows, wiring step handoffs, scaffolding workflow configs -> use **agent-workflow-designer**. This skill designs the agents; that one sequences them.
- **Ecosystem governance** — four-pillar ecosystem design (context/skills/agents/workflows), loop-safety hardening and auditing, HITL approval gates, the 5-Phase Protocol -> use **agentic-system-architect**. This skill designs an agent's persona, prompt, and tools; that one hardens it for autonomy and governs the ecosystem it lives in.

This skill owns: single-agent persona/system-prompt/tool design (see `references/agent_prompt_design.md`) and multi-agent architecture pattern selection.

## Core Capabilities

### 0. Research and Discovery (Query Engineering)

Before designing an agent, the designer must research and synthesize capabilities using a strict methodology:

#### 3-Layer Query Strategy
1. **State of the Art:** Search for current industry best practices and canonical design patterns for the specific technical problem.
2. **Tooling Identification:** Track down which APIs, SDKs, or CLI tools are most efficient for the agent to interact with its environment.
3. **Failure Case Detection:** Proactively search for the most common errors made by humans or AI when performing the specific task, using these as preventative bounds.

#### Strict Noise Filtering & Capability Synthesis
- **Prioritize Official Documentation:** Rely strictly on technical docs (e.g., MSDN, LangGraph docs, corporate GitHubs).
- **Capability Synthesis:** Extract only real, operational capabilities (action verbs and technical flows). Discard generic marketing noise, ambiguous adjectives, and commercial promises.

### 1. Agent Architecture Patterns

#### Single Agent Pattern
- **Use Case:** Simple, focused tasks with clear boundaries
- **Pros:** Minimal complexity, easy debugging, predictable behavior
- **Cons:** Limited scalability, single point of failure
- **Implementation:** Direct user-agent interaction with comprehensive tool access

#### Supervisor Pattern
- **Use Case:** Hierarchical task decomposition with centralized control
- **Architecture:** One supervisor agent coordinating multiple specialist agents
- **Pros:** Clear command structure, centralized decision making
- **Cons:** Supervisor bottleneck, complex coordination logic
- **Implementation:** Supervisor receives tasks, delegates to specialists, aggregates results

#### Swarm Pattern
- **Use Case:** Distributed problem solving with peer-to-peer collaboration
- **Architecture:** Multiple autonomous agents with shared objectives
- **Pros:** High parallelism, fault tolerance, emergent intelligence
- **Cons:** Complex coordination, potential conflicts, harder to predict
- **Implementation:** Agent discovery, consensus mechanisms, distributed task allocation

#### Hierarchical Pattern
- **Use Case:** Complex systems with multiple organizational layers
- **Architecture:** Tree structure with managers and workers at different levels
- **Pros:** Natural organizational mapping, clear responsibilities
- **Cons:** Communication overhead, potential bottlenecks at each level
- **Implementation:** Multi-level delegation with feedback loops

#### Pipeline Pattern
- **Use Case:** Sequential processing with specialized stages
- **Architecture:** Agents arranged in processing pipeline
- **Pros:** Clear data flow, specialized optimization per stage
- **Cons:** Sequential bottlenecks, rigid processing order
- **Implementation:** Message queues between stages, state handoffs

### 2. Agent Role Definition

#### Role Specification Framework

Every agent role is specified across these five engineering fields. **None is optional — `Constraints` in particular is the hard rail that prevents hallucination, controls cost, and bounds autonomy; it is software configuration, never narrative.**

- **Identity:** Name, purpose statement, core competencies.
- **Responsibilities:** Primary tasks, decision boundaries, success criteria.
- **Capabilities:** Required tools, knowledge domains, processing limits.
- **Interfaces:** Input/output formats, communication protocols.
- **Constraints:** Security boundaries, resource limits (token / time / tool-call budgets), and operational guidelines — enforced as explicit config, not left to the model's discretion.

#### CrewAI-Native Profile Mapping (Role / Goal / Backstory)

Frameworks such as CrewAI model an agent as a `Role` / `Goal` / `Backstory` triple. Map the specification above onto that triple **additively** — the triple is a presentation layer over the engineering fields, it does not replace them:

- **Role:** Canonical position (derived from Identity + Responsibilities).
- **Goal:** The measurable objective that defines task success (from Responsibilities).
- **Backstory:** The identity narrative that shapes tone and technical rigor. **Backstory tunes behavior only** — security boundaries, resource limits, and tool allowlists stay in `Constraints` as explicit config, never encoded as story.

#### Common Agent Archetypes

Five co-equal archetypes, each with a distinct technical purpose. They classify into three functional taxonomy classes — **Orchestrator, Executor, Evaluator** — but the two infrastructure archetypes (Interface, Monitor) are **not** subclasses of Executor or Evaluator; their purpose is orthogonal and must not be collapsed into them.

**Coordinator Agent** — *Orchestrator class*
- Orchestrates multi-agent workflows
- Makes high-level decisions and resource allocation
- Monitors system-level progress; handles escalations and conflict resolution

**Specialist Agent** — *Executor class*
- Deep expertise in a specific domain (code, data, research)
- Optimized tools and knowledge for specialized tasks
- High-quality output within a narrow scope; clear handoff for out-of-scope requests

**Evaluator / Critic Agent** — *Evaluator class*
- Audits and verifies the work of other agents against hard acceptance criteria
- Runs strict QA checklists; issues PASS / FAIL verdicts
- Never produces the artifact it audits (producer/critic separation)

**Interface Agent** — *Infrastructure*
- Handles external interactions (users, APIs, systems)
- Protocol translation and format conversion
- Authentication and authorization management

**Monitor Agent** — *Infrastructure*
- System health monitoring and alerting
- Performance metrics collection and analysis
- Anomaly detection, compliance and audit-trail maintenance

**Taxonomy note (identity-crisis guard):** classify every agent by its primary function — *Orchestrator* (divides subtasks, coordinates flow), *Executor* (actuates tools, produces output), *Evaluator* (audits others via strict checklists). This prevents role confusion, but never force Interface (protocol / auth infra) or Monitor (observability infra) into an Executor or Evaluator box — they are infrastructure roles carrying their own responsibilities.

**Persona and system-prompt authoring:** turning an archetype into a deployable agent means writing its system prompt. Use the three-layer method (Role Definition -> Boundaries -> Output Contract) in `references/agent_prompt_design.md`, which includes one complete worked system prompt per archetype above.

### 3. Tool Design Principles

#### Schema Design
- **Input Validation:** Strong typing, required vs optional parameters
- **Output Consistency:** Standardized response formats, error handling
- **Documentation:** Clear descriptions, usage examples, edge cases
- **Versioning:** Backward compatibility, migration paths

#### Error Handling Patterns
- **Graceful Degradation:** Partial functionality when dependencies fail
- **Retry Logic:** Exponential backoff, circuit breakers, max attempts
- **Error Propagation:** Structured error responses, error classification
- **Recovery Strategies:** Fallback methods, alternative approaches

#### Idempotency Requirements
- **Safe Operations:** Read operations with no side effects
- **Idempotent Writes:** Same operation can be safely repeated
- **State Management:** Version tracking, conflict resolution
- **Atomicity:** All-or-nothing operation completion

### 4. Communication Patterns

#### Message Passing
- **Asynchronous Messaging:** Decoupled agents, message queues
- **Message Format:** Structured payloads with metadata
- **Delivery Guarantees:** At-least-once, exactly-once semantics
- **Routing:** Direct messaging, publish-subscribe, broadcast

#### Shared State
- **State Stores:** Centralized data repositories
- **Consistency Models:** Strong, eventual, weak consistency
- **Access Patterns:** Read-heavy, write-heavy, mixed workloads
- **Conflict Resolution:** Last-writer-wins, merge strategies

#### Event-Driven Architecture
- **Event Sourcing:** Immutable event logs, state reconstruction
- **Event Types:** Domain events, system events, integration events
- **Event Processing:** Real-time, batch, stream processing
- **Event Schema:** Versioned event formats, backward compatibility

Concrete message envelope schema, a full handoff payload example, and delivery-guarantee selection rules (at-most-once vs at-least-once vs exactly-once): see `references/communication_protocols.md`.

### 5. Guardrails and Safety

#### Input Validation
- **Schema Enforcement:** Required fields, type checking, format validation
- **Content Filtering:** Harmful content detection, PII scrubbing
- **Rate Limiting:** Request throttling, resource quotas
- **Authentication:** Identity verification, authorization checks

#### Output Filtering
- **Content Moderation:** Harmful content removal, quality checks
- **Consistency Validation:** Logic checks, constraint verification
- **Formatting:** Standardized output formats, clean presentation
- **Audit Logging:** Decision trails, compliance records

#### Human-in-the-Loop
- **Approval Workflows:** Critical decision checkpoints
- **Escalation Triggers:** Confidence thresholds, risk assessment
- **Override Mechanisms:** Human judgment precedence
- **Feedback Loops:** Human corrections improve system behavior

The canonical gate taxonomy (Pre-Execution Approval, Checkpoint, Escalation, Override/Abort), irreversibility classification, and the 5-Phase Protocol are owned by **agentic-system-architect** — use that skill when designing gates for irreversible actions. This section covers only per-agent guardrail concerns.

#### Loop Safety (Exit Conditions)

Any agent that iterates (retry, refine, re-plan) must declare exit conditions in its prompt and spec. The six canonical types:

| Exit condition | Terminates when |
|----------------|-----------------|
| `max_iterations` | The loop counter reaches a hard ceiling |
| `no_progress` | N consecutive iterations produce no state change |
| `oscillation` | The agent alternates between the same states/actions (A-B-A-B) |
| `budget` | Tokens, time, tool calls, or cost are exhausted |
| `success_predicate` | A machine-checkable success condition holds |
| `escalation_trigger` | A defined condition transfers control to a human |

Rule of thumb: `success_predicate` alone is never enough — pair it with a bounding condition (`max_iterations` or `budget`). The full taxonomy, counter design, loop pattern catalog, and the >= 90 HARDENED audit gate are owned by **agentic-system-architect**; harden any agent there before it runs autonomously.

### 6. Evaluation Frameworks

#### Task Completion Metrics
- **Success Rate:** Percentage of tasks completed successfully
- **Partial Completion:** Progress measurement for complex tasks
- **Task Classification:** Success criteria by task type
- **Failure Analysis:** Root cause identification and categorization

#### Quality Assessment
- **Output Quality:** Accuracy, relevance, completeness measures
- **Consistency:** Response variability across similar inputs
- **Coherence:** Logical flow and internal consistency
- **User Satisfaction:** Feedback scores, usage patterns

#### Cost Analysis
- **Token Usage:** Input/output token consumption per task
- **API Costs:** External service usage and charges
- **Compute Resources:** CPU, memory, storage utilization
- **Time-to-Value:** Cost per successful task completion

#### Latency Distribution
- **Response Time:** End-to-end task completion time
- **Processing Stages:** Bottleneck identification per stage
- **Queue Times:** Wait times in processing pipelines
- **Resource Contention:** Impact of concurrent operations

### 7. Orchestration Strategies

#### Centralized Orchestration
- **Workflow Engine:** Central coordinator manages all agents
- **State Management:** Centralized workflow state tracking
- **Decision Logic:** Complex routing and branching rules
- **Monitoring:** Comprehensive visibility into all operations

#### Decentralized Orchestration
- **Peer-to-Peer:** Agents coordinate directly with each other
- **Service Discovery:** Dynamic agent registration and lookup
- **Consensus Protocols:** Distributed decision making
- **Fault Tolerance:** No single point of failure

#### Hybrid Approaches
- **Domain Boundaries:** Centralized within domains, federated across
- **Hierarchical Coordination:** Multiple orchestration levels
- **Context-Dependent:** Strategy selection based on task type
- **Load Balancing:** Distribute coordination responsibility

Orchestration at ecosystem scale — gating, sequencing, and governance across many agents — is owned by **agentic-system-architect**; plain workflow scaffolding by **agent-workflow-designer**. This section informs which topology an individual agent is designed to live in.

### 8. Memory Patterns

#### Short-Term Memory
- **Context Windows:** Working memory for current tasks
- **Session State:** Temporary data for ongoing interactions
- **Cache Management:** Performance optimization strategies
- **Memory Pressure:** Handling capacity constraints

#### Long-Term Memory
- **Persistent Storage:** Durable data across sessions
- **Knowledge Base:** Accumulated domain knowledge
- **Experience Replay:** Learning from past interactions
- **Memory Consolidation:** Transferring from short to long-term

#### Shared Memory
- **Collaborative Knowledge:** Shared learning across agents
- **Synchronization:** Consistency maintenance strategies
- **Access Control:** Permission-based memory access
- **Memory Partitioning:** Isolation between agent groups

### 9. Scaling Considerations

#### Horizontal Scaling
- **Agent Replication:** Multiple instances of same agent type
- **Load Distribution:** Request routing across agent instances
- **Resource Pooling:** Shared compute and storage resources
- **Geographic Distribution:** Multi-region deployments

#### Vertical Scaling
- **Capability Enhancement:** More powerful individual agents
- **Tool Expansion:** Broader tool access per agent
- **Context Expansion:** Larger working memory capacity
- **Processing Power:** Higher throughput per agent

#### Performance Optimization
- **Caching Strategies:** Response caching, tool result caching
- **Parallel Processing:** Concurrent task execution
- **Resource Optimization:** Efficient resource utilization
- **Bottleneck Elimination:** Systematic performance tuning

### 10. Failure Handling

#### Retry Mechanisms
- **Exponential Backoff:** Increasing delays between retries
- **Jitter:** Random delay variation to prevent thundering herd
- **Maximum Attempts:** Bounded retry behavior
- **Retry Conditions:** Transient vs permanent failure classification

#### Fallback Strategies
- **Graceful Degradation:** Reduced functionality when systems fail
- **Alternative Approaches:** Different methods for same goals
- **Default Responses:** Safe fallback behaviors
- **User Communication:** Clear failure messaging

#### Circuit Breakers
- **Failure Detection:** Monitoring failure rates and response times
- **State Management:** Open, closed, half-open circuit states
- **Recovery Testing:** Gradual return to normal operation
- **Cascading Failure Prevention:** Protecting upstream systems

## Implementation Guidelines

### Architecture Decision Process
0. **Ecosystem Consistency Analysis (Anti-Redundancy):** **MANDATORY**. Before proposing any new agent, you must read the current `agents/` folder of the repository. Ask: "Does this new agent propose skills that an existing agent already has, or does it truly cover an operational gap?" Do not proceed if redundant.
1. **Requirements Analysis:** Understand system goals, constraints, scale
2. **Pattern Selection:** Choose appropriate architecture pattern
3. **Agent Design:** Define roles, responsibilities, interfaces
4. **Tool Architecture:** Design tool schemas and error handling
5. **Communication Design:** Select message patterns and protocols
6. **Safety Implementation:** Build guardrails and validation
7. **Evaluation Planning:** Define success metrics and monitoring
8. **Deployment Strategy:** Plan scaling and failure handling

### Quality Assurance
- **Testing Strategy:** Unit, integration, and system testing approaches
- **Monitoring:** Real-time system health and performance tracking
- **Documentation:** Architecture documentation and runbooks
- **Security Review:** Threat modeling and security assessments

### Continuous Improvement
- **Performance Monitoring:** Ongoing system performance analysis
- **User Feedback:** Incorporating user experience improvements
- **A/B Testing:** Controlled experiments for system improvements
- **Knowledge Base Updates:** Continuous learning and adaptation

This skill provides the foundation for designing robust, scalable multi-agent systems that can handle complex tasks while maintaining safety, reliability, and performance at scale.
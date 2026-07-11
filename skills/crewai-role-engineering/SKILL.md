---
name: "crewai-role-engineering"
version: "1.0.0"
description: "Design sequential and hierarchical multi-agent teams using CrewAI, optimizing backstories, goals, task scopes, memory sync, and manager coordination"
type: "skill"
---

# Skill: crewai-role-engineering

This skill teaches the agent how to engineer distinct agent personas and task allocations within a collaborative CrewAI team.

## Capability

**This skill does exactly one thing:** authors precise agent parameters (`role`, `goal`, `backstory`), configures sequential/hierarchical task delegations, and sets up short/long-term/entity memory synchronization.

## Core Principles

### 1. Agent Psychology & Alignment
* **Role**: Clear, bounded job titles (e.g. `Senior Code Auditor`) that establish clear domains.
* **Goal**: Actionable, measurable mission statements.
* **Backstory**: Explains the perspective, expertise, and constraints of the agent to shape its thinking and tone. Prevents responsibility overlap.

### 2. Task Allocation & Delegation
* **Tasks**: Define atomic inputs, descriptions, and expected outputs per task.
* **Delegation**: Set `allow_delegation=True` only for supervisor/manager roles. Keep worker agents focused on their specific tasks with `allow_delegation=False` to prevent chaotic messaging.
* **Manager Agent**: Use hierarchical execution when task dependencies require dynamic routing and review.

### 3. Memory Architectures
* **Short-Term Memory**: Holds active conversation context during the execution of a single Crew.
* **Long-Term Memory**: Persists learnings and feedback across historical runs.
* **Entity Memory**: Identifies and links key concepts (e.g., product names, user preferences) across different tasks.

## References

| File | Summary |
|------|---------|
| `references/role_engineering_patterns.md` | Persona formulations, hierarchical crews, memory synch configurations, and asynchronous task execution patterns |


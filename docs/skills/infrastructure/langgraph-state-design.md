---
title: "Skill: langgraph-state-design — MCP Servers & RAG Architectures"
description: "Design stateful multi-agent directed graphs using LangGraph, focusing on state schemas, nodes, conditional edges, checkpointers, and. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
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


This skill teaches the agent how to plan and design robust, non-linear multi-agent state machines using LangGraph (Python/TypeScript).

## Capability

**This skill does exactly one thing:** structures multi-agent system state schemas, maps node execution behaviors (state mutators), defines conditional edge logic, and integrates checkpointers for state persistence and human-in-the-loop approval gates.

## Core Principles

### 1. Global State Management
* Define a typed state schema (typically a Python `TypedDict` or TypeScript `interface`).
* State fields must flow cleanly across nodes. Use reducers (e.g. `operator.add` or list appends) to merge list inputs (like message histories) instead of overwriting them.

### 2. Nodes and Conditional Edges
* **Nodes**: Nodes are pure or state-mutating functions that receive the current state, run execution logic (LLM calls or tool invocation), and return an updated slice of the state.
* **Conditional Edges**: Decision-routing functions that analyze the state (e.g. looking for exit conditions or validation failures) and return the name of the next node to execute.

### 3. Checkpointing & Human Gateways
* **Checkpointers**: Enable memory persistence (MemorySaver) to allow time-travel debugging, rollbacks, and session resumes.
* **Interrupts**: Configure `interrupt_before` or `interrupt_after` on specific nodes to pause execution, allowing human review and state modification before resuming the graph.

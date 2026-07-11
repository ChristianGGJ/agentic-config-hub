---
name: "agentic-observability-telemetry"
version: "1.0.0"
description: "Establish tracing, logging, and performance metrics across LangGraph (LangSmith), CrewAI (AgentOps), and Microsoft Agent Framework (OpenTelemetry/ILogger)"
type: "skill"
---

# Skill: agentic-observability-telemetry

This skill teaches the agent how to configure complete observability, trace mapping, and latency/token telemetry across different multi-agent runtimes.

## Capability

**This skill does exactly one thing:** structures OpenTelemetry setups, configures tracing backends (LangSmith, AgentOps), and integrates structured logging (ILogger/JSON logs) to capture cost, latency, and agent decision paths.

## Core Principles

### 1. LangGraph Tracing (LangSmith)
* Set up standard telemetry environment variables (`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`).
* Export run IDs and trace logs to trace exact node routing execution, conditional edge results, and state updates.

### 2. CrewAI Tracing (AgentOps)
* Integrate `agentops` SDK at initialization.
* Instrument agent goals, backstories, and tools to identify slow worker personas and excessive delegation loops.

### 3. Microsoft Agent Framework Telemetry (.NET)
* Use the built-in .NET `ActivitySource` in `Microsoft.Agents.AI` and `Microsoft.Extensions.AI`.
* Configure OpenTelemetry exporters (Console, Jaeger, or Azure Application Insights) to log:
  - Token consumption (Prompt vs. Completion tokens).
  - Native `AIFunction` tool execution times and parameter values.
  - LLM response latencies.

## References

| File | Summary |
|------|---------|
| `references/telemetry_instrumentation.md` | Environment tracer configurations, LangSmith metadata mappings, AgentOps session trackers, and C# OpenTelemetry setups |


---
title: "Agentic Observability & Telemetry — MCP Servers & RAG Architectures"
description: "Use when instrumenting agentic systems for observability: OpenTelemetry tracing of the chat client itself, structured logging with correlation IDs. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Agentic Observability & Telemetry

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `agentic-observability-telemetry`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-observability-telemetry/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


Instrument multi-agent runtimes so every run answers three questions: **what did it
cost** (tokens, latency, dollars), **what path did it take** (nodes, tool calls,
delegations), and **why did it stop** (which exit condition fired). The third question
is the one generic APM misses and the one this skill makes first-class.

## When to Use / When NOT

- **Use** when adding tracing/logging/metrics to a LangGraph, CrewAI, or Microsoft
  Agent Framework system, or when you need loop-level telemetry to debug runaway or
  stalling agents.
- **NOT** for guardrail/PII-in-traces policy design -> `agentic-guardrails-security`
  (this skill only notes redaction hooks). **NOT** for evaluation scoring ->
  `agentic-evals-benchmarking`. **NOT** for cost *optimization* decisions ->
  `llm-cost-optimizer` (this skill measures cost; it does not route to reduce it).

## Decision Frameworks

**What to instrument first (by signal-to-effort):**

| Priority | Instrument | Why first |
|----------|-----------|-----------|
| 1 | The chat client (token usage + latency per call) | Cheapest to add, highest diagnostic value; every agent makes model calls |
| 2 | Tool/function execution (name, args, duration, error) | Tool failures and slow tools are the top latency cause |
| 3 | Agent-loop events (iteration, delegation, exit condition) | The hub-canon layer; turns "it hung" into "no_progress fired at iter 4" |
| 4 | End-to-end run trace (span tree) | Ties it together; needed for multi-agent path analysis |

**Backend selection:**

| Backend | Choose when | Note |
|---------|-------------|------|
| OpenTelemetry (OTLP) -> Jaeger/Tempo/App Insights | Vendor-neutral, self-hosted or cloud, .NET-first | The portable default; MAF and M.E.AI emit OTel natively |
| LangSmith | LangGraph/LangChain stack, want run trees + eval hooks in one place | Tightest LangGraph integration |
| AgentOps | CrewAI stack, want session/cost dashboards with minimal setup | Session-oriented view of crews |

Rule: emit **OpenTelemetry** as the substrate; layer a vendor backend only for its
UX. Never hand-roll spans when the framework ships native instrumentation.

**Sampling & cost:** trace 100% in dev; in production, head-sample routine traffic
(e.g. 5-10%) but **tail-sample all errors and all runs that fired a non-success exit
condition** — those are the ones you need. Telemetry that doubles latency or leaks PII
is a liability; see redaction below.

## 1. Instrument the chat client (.NET, Microsoft Agent Framework / M.E.AI)

The audit's key fix: instrument the **client**, not just the exporter pipeline. As of
`Microsoft.Extensions.AI` current releases (verify against your package version):

```csharp
using Microsoft.Extensions.AI;
using OpenTelemetry.Trace;

// OTel pipeline
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource("Experimental.Microsoft.Extensions.AI")   // GenAI source (enable experimental switch)
    .AddOtlpExporter()
    .Build();

// Instrument the chat client itself
IChatClient client = baseChatClient
    .AsBuilder()
    .UseOpenTelemetry(configure: o => o.EnableSensitiveData = false)  // opt-in for prompt/response capture
    .Build();
```

This emits GenAI semantic-convention spans (model, token counts, finish reason) around
every call. `EnableSensitiveData` is off by default — turn it on only in dev, never
where prompts may carry PII.

## 2. Structured logging with correlation IDs

Traces show the tree; logs carry the detail. Correlate them by stamping the trace/run
id on every log line.

**.NET (ILogger + JSON):**

```csharp
using (logger.BeginScope(new Dictionary<string, object> {
        ["run_id"] = runId, ["agent"] = agentName })) {
    logger.LogInformation("tool {Tool} completed in {Ms}ms", toolName, elapsedMs);
}
// Configure a JSON console formatter (or Serilog) so scopes serialize as fields.
```

**Python (stdlib logging, JSON-ish):**

```python
import logging, json
class JsonFormatter(logging.Formatter):
    def format(self, r):
        return json.dumps({"level": r.levelname, "msg": r.getMessage(),
                           "run_id": getattr(r, "run_id", None), "agent": getattr(r, "agent", None)})
# attach run_id via logging.LoggerAdapter(logger, {"run_id": run_id, "agent": name})
```

## 3. LangGraph -> LangSmith

Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY`; every graph run becomes a run
tree showing node routing, conditional-edge results, and state deltas. Tag runs with a
stable `run_id` (config `{"metadata": {"run_id": ...}}`) so they join your logs.
LangSmith also hosts eval datasets — but scoring belongs to
`agentic-evals-benchmarking`; here it is only a trace/telemetry sink.

## 4. CrewAI -> AgentOps

Initialize `agentops` before building the crew; it captures per-agent sessions, tool
calls, token spend, and delegation events — the fastest way to spot a slow persona or a
delegation loop. Pair with the crew's own `max_iter`/`max_rpm` (see
`crewai-role-engineering`) so telemetry and controls agree.

## 5. Hub-canon agent-loop telemetry (the differentiator)

Generic APM tells you a request was slow; it cannot tell you an agent *stalled*. Emit
these as first-class span attributes / metrics on the agent-loop span:

| Attribute / metric | Meaning | Debugging use |
|--------------------|---------|---------------|
| `agent.iteration` | Current loop iteration number | See how close to `max_iterations` a run ran |
| `agent.delegation_depth` | Nesting depth of sub-agent calls | Catch runaway delegation trees |
| `agent.oscillation_detected` (bool/count) | A-B-A-B action/tier repetition seen | Explains thrash without reading logs |
| `agent.budget_consumed` | Tool calls / tokens / seconds against the declared budget | Cost attribution + early-warning |
| `agent.exit_condition` | Which of the 6 canon types ended the loop | The headline: WHY it stopped |
| `agent.exit_detail` | Human-readable reason | Context for the exit |

`agent.exit_condition` takes exactly one of the six canonical values —
`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger` — so dashboards can chart stop-reason distribution across runs.
See `references/agent_loop_telemetry.md` for the emit pattern and a stdlib helper, and
`agentic-system-architect/references/loop_engineering_patterns.md` for the taxonomy
itself.

## Failure Modes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Spans show latency but no token counts | Exporter instrumented, client not | Wrap the client with `UseOpenTelemetry` (section 1) |
| Logs and traces cannot be correlated | No shared id | Stamp `run_id` on scope + trace metadata (section 2/3) |
| "Agent hung" with no explanation | No loop telemetry | Emit `agent.exit_condition` + `agent.iteration` (section 5) |
| Telemetry doubled latency / leaked prompts | 100% capture + sensitive data on | Sample (tail-keep errors), set `EnableSensitiveData=false`, redact |
| Trace volume/cost exploding | No sampling policy | Head-sample routine traffic, tail-sample errors and non-success exits |

## Hub Canon Integration

- The six exit-condition types are the controlled vocabulary for `agent.exit_condition`
  — never invent a seventh; unknown stops map to `escalation_trigger` with detail.
- Telemetry is the evidence layer for the flagship loop controls and for
  `react_trace_analyzer.py` (D1-D7): emit traces in a shape the analyzer can read so
  runaway detection runs on real production runs, not just tests.
- PII in traces routes to `agentic-guardrails-security` for redaction policy.

## References

| File | Summary |
|------|---------|
| `references/telemetry_instrumentation.md` | Backend setup: LangSmith env, AgentOps session trackers, C# OpenTelemetry exporter and client instrumentation |
| `references/agent_loop_telemetry.md` | Hub-canon loop telemetry: span attributes, the 6-value exit-condition dimension, and a stdlib emit helper |

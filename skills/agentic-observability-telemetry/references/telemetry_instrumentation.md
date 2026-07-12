# Telemetry Instrumentation

Backend setup and instrumentation patterns for the agentic-observability-telemetry
skill: chat-client instrumentation (the piece generic APM misses), the metrics layer,
trace-context propagation, and SLO/alert design. Loop-level telemetry (iterations,
exit conditions) lives in `agent_loop_telemetry.md`.

> Framework APIs assume current releases (2025/2026); verify against your package
> versions. **Instrument the client, not only the exporter** — an exporter pipeline with
> no client instrumentation produces spans without token counts or model metadata.

## 1. Instrument the chat client FIRST (.NET, MAF / M.E.AI)

The exporter pipeline (section 4) only ships spans that something produced. The spans
that carry model, token, and finish-reason data come from wrapping the `IChatClient`:

```csharp
using Microsoft.Extensions.AI;

// Wrap the client so every call emits GenAI-semantic-convention spans + metrics.
IChatClient client = baseChatClient
    .AsBuilder()
    .UseOpenTelemetry(configure: o => o.EnableSensitiveData = false) // prompts/responses OFF by default
    .Build();
// The agent built on this client is now instrumented end to end:
var agent = new ChatClientAgent(client, instructions);
```

`EnableSensitiveData = true` captures prompt/response text — dev only, never where
prompts may carry PII (route redaction policy to `agentic-guardrails-security`). Enabling
the experimental GenAI source switch may be required to emit the spans; check your
`Microsoft.Extensions.AI` version's opt-in flag.

## 2. Structured logging with correlation IDs

Traces show the tree; logs carry detail. Join them with a shared id.

```csharp
using (logger.BeginScope(new Dictionary<string, object> {
        ["run_id"] = runId, ["agent"] = agentName })) {
    logger.LogInformation("tool {Tool} finished in {Ms}ms", toolName, elapsedMs);
}
// Configure a JSON console formatter (or Serilog) so scope fields serialize as structured data.
```

Python: attach `run_id` via `logging.LoggerAdapter(logger, {"run_id": run_id})` and a
JSON formatter, so every line joins the trace by `run_id`.

## 3. The metrics layer (not just traces)

Traces answer "what happened in this run"; metrics answer "what is the trend". Emit
histograms/counters via a Meter (OTel metrics), separate from spans:

| Instrument | Type | Why |
|-----------|------|-----|
| `gen_ai.client.token.usage` | histogram | Token distribution per model/operation (cost trend) |
| `gen_ai.client.operation.duration` | histogram | Latency percentiles per model/tool |
| `agent.tool.errors` | counter | Tool failure rate by tool name |
| `agent.exit_condition` | counter (tagged) | Stop-reason distribution (see `agent_loop_telemetry.md`) |

```csharp
var meter = new Meter("AgenticConfigHub.Metrics");
var toolDuration = meter.CreateHistogram<double>("agent.tool.duration", "ms");
// record: toolDuration.Record(elapsedMs, new KeyValuePair<string,object?>("tool", name));
// pipeline: builder.Services.AddOpenTelemetry().WithMetrics(m => m.AddMeter("AgenticConfigHub.Metrics").AddOtlpExporter());
```

MAF/M.E.AI emit the `gen_ai.*` GenAI semantic-convention metrics automatically once the
client is instrumented (section 1) — add your own Meter only for app-specific signals.

## 4. Exporter pipeline (.NET)

```csharp
builder.Services.AddOpenTelemetry()
    .WithTracing(t => t
        .AddSource("Experimental.Microsoft.Extensions.AI")   // GenAI client spans (section 1)
        .AddSource("Microsoft.Agents.AI")                    // agent/workflow spans
        .AddSource("AgenticConfigHub.Telemetry")             // your custom ActivitySource
        .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("AgentBackend"))
        .AddOtlpExporter(o => o.Endpoint = new Uri("http://localhost:4317")))
    .WithMetrics(m => m
        .AddMeter("AgenticConfigHub.Metrics")
        .AddOtlpExporter());
```

## 5. Trace-context propagation across services / subprocesses

A multi-agent system that spans processes loses its trace tree unless context is
propagated. Use W3C Trace Context (`traceparent`):

- **In-process / async**: the ambient `Activity.Current` (C#) or OTel context (Python)
  flows automatically.
- **Across HTTP/gRPC**: OTel auto-instrumentation injects/extracts `traceparent` headers
  — enable the HTTP client/server instrumentation.
- **Across a queue or a spawned subprocess** (e.g. LangGraph subprocess runtimes): pass
  `traceparent` explicitly in the message/env and re-establish context on the other side,
  or the child run becomes an orphan trace. This is the #1 cause of "half the run is
  missing from the trace".

## 6. LangGraph -> LangSmith / CrewAI -> AgentOps

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=...            # set LANGCHAIN_PROJECT to group runs
```

```python
# LangGraph: tag runs so they join your logs/metrics by run_id
config = {"configurable": {"thread_id": "session-456"}, "metadata": {"run_id": run_id}}
# app.invoke(inputs, config)

# CrewAI: init AgentOps before building the crew; end the session to flush.
import agentops
agentops.init(default_tags=["prod"])    # api key via env
# ... build & kickoff crew ...
agentops.end_session("Success")
```

These are trace/metric sinks; evaluation scoring belongs to `agentic-evals-benchmarking`.

## 7. SLO & alert design

A dashboard is not an alert. Define SLOs and alert on their breach:

| SLO / signal | Example objective | Alert threshold |
|--------------|-------------------|-----------------|
| Run success rate | >= 99% end in `success_predicate` | page if < 97% over 1h |
| p95 run latency | <= target seconds | warn if p95 > 1.5x baseline over 30m |
| Non-success exit rate | `no_progress`+`oscillation`+`budget` share | warn if > 2x baseline over 1h |
| Cost per run p95 | <= budget | warn on sustained breach |
| Tool error rate | <= 1% per tool | page on spike |

Tail-sample every alerting-relevant trace (all errors, all non-`success_predicate`
exits) so an alert always has an inspectable trace behind it. Head-sample routine
success traffic to control cost.

## 8. Sampling & PII

- Dev: trace 100%, `EnableSensitiveData` on. Production: head-sample routine traffic
  (5-10%), **tail-keep all errors and non-success exits**.
- Never enable sensitive-data capture where prompts carry PII; redaction policy is owned
  by `agentic-guardrails-security`. Telemetry that leaks prompts is a bigger liability
  than the observability it buys.

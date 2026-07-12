# Microsoft Agent Framework: Observability, Resilience, and Hosting

Built-in OpenTelemetry, middleware composition, retry/timeout policies, streaming
endpoints, and testing patterns for MAF agents in ASP.NET Core.

**Version assumption:** Microsoft Agent Framework 1.x (`Microsoft.Agents.AI`) on
`Microsoft.Extensions.AI` (M.E.AI) 9.x, OpenTelemetry .NET 1.9+, Polly 8.x,
.NET 8/9/10. Members marked "verify" must be confirmed against current docs before
shipping — the OTel GenAI semantic conventions are still marked
development/experimental and attribute names have shifted between releases.

**Scope note:** this file owns wiring MAF's *built-in* telemetry and resilience
into a .NET host. Stack-wide dashboard/alerting strategy belongs to the sibling
skill `agentic-observability-telemetry`; the HITL approval primitive itself is
owned by `microsoft-agent-framework` (reference section 7) — here we only expose
it over HTTP.

---

## 1. Observability: Built-In First, Hand-Rolled Never (as the base layer)

M.E.AI ships OpenTelemetry instrumentation as a chat-client middleware. **Use it.**
A hand-rolled `ActivitySource` around your agent calls produces spans with no token
counts, no model attributes, and no compatibility with GenAI-aware trace backends.
The rule: built-in `UseOpenTelemetry` is the base layer, always on; your own
`ActivitySource` only *wraps* it with business context (order id, tenant, feature).

### 1.1 Instrument the chat client (the step everyone forgets)

Configuring an OTel exporter does nothing if the chat client itself is not
instrumented — you get HTTP spans and zero LLM spans. Instrumentation lives in the
`ChatClientBuilder` pipeline:

```csharp
builder.Services.AddChatClient(sp => /* provider client, see integration reference sec. 1.1 */)
    .UseLogging()
    .UseOpenTelemetry(
        sourceName: "Contoso.Agents",
        configure: o => o.EnableSensitiveData = false);   // prompts/completions OFF by default
```

- `sourceName` controls the `ActivitySource`/`Meter` name the spans and metrics are
  emitted under. If omitted, M.E.AI uses its own default experimental source name
  (historically `"Experimental.Microsoft.Extensions.AI"` — verify against your
  installed version); passing your own name is more stable across upgrades.
- `EnableSensitiveData = true` records prompt and completion content on spans.
  Enable only in dev/eval environments — in production it copies customer data and
  any leaked secrets into your trace backend.
- Agent-level spans (one span per agent run, wrapping the model-call spans): MAF
  provides an agent OTel decorator via the agent builder pattern
  (`agent.AsBuilder().UseOpenTelemetry(sourceName)` — verify exact extension name
  and package). Turn it on in production so trace trees read
  *agent run -> model call(s) -> tool call(s)*.

### 1.2 Register the host-side OTel pipeline

```csharp
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService("contoso-agent-api"))
    .WithTracing(t => t
        .AddSource("Contoso.Agents")            // must match sourceName above
        .AddAspNetCoreInstrumentation())
    .WithMetrics(m => m
        .AddMeter("Contoso.Agents"))
    .UseOtlpExporter();                          // OTLP to your collector/backend
```

If you did not pass a `sourceName`, you must `AddSource`/`AddMeter` the library's
default experimental names instead — another reason to name your own.

### 1.3 What the built-in layer emits (GenAI semantic conventions)

Span and metric names follow the OpenTelemetry GenAI semantic conventions. The
conventions are still marked development — treat this table as the shape, and
verify current attribute names before building dashboards on them:

| Signal | Name / attribute | Meaning |
|--------|------------------|---------|
| Span | `chat {model}` | One model invocation |
| Attr | `gen_ai.operation.name` | `chat`, `execute_tool`, agent-run operations |
| Attr | `gen_ai.system` (newer semconv revisions: `gen_ai.provider.name` — verify) | Provider id |
| Attr | `gen_ai.request.model` / `gen_ai.response.model` | Requested vs actual model |
| Attr | `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | Token counts per call |
| Attr | `gen_ai.response.finish_reasons` | stop / tool_calls / length ... |
| Metric | `gen_ai.client.token.usage` (histogram) | Token usage by direction |
| Metric | `gen_ai.client.operation.duration` (histogram) | Model-call latency |

Hub-canon payoff: with these spans exported, the flagship trace detections D1-D7
(error cascades, repeated identical tool calls, runaway loops) become trace-backend
queries over `gen_ai.*` attributes — e.g. "sessions where `execute_tool` spans with
identical names+arguments repeat > 3x" — instead of log archaeology.

### 1.4 Supplementary business spans (the only hand-rolled part)

```csharp
private static readonly ActivitySource Source = new("Contoso.Agents.Business");

using Activity? activity = Source.StartActivity("support.answer_ticket");
activity?.SetTag("ticket.id", ticketId);
activity?.SetTag("tenant.id", tenantId);          // ids only — never prompt content
AgentRunResponse response = await agent.RunAsync(message, thread, cancellationToken: ct);
activity?.SetTag("agent.exit_condition", "success_predicate");   // hub canon: name what fired
```

Add `"Contoso.Agents.Business"` to `AddSource(...)`. The business span becomes the
parent of the built-in agent/model spans automatically via `Activity.Current`.

---

## 2. Usage Accounting (the real API)

There is no `response.Metadata["Usage"]` and no `ChatResponseUsage` type. The run
surface is:

```csharp
AgentRunResponse response = await agent.RunAsync(message, thread, cancellationToken: ct);

UsageDetails? usage = response.Usage;      // null if the provider does not report usage
long? input  = usage?.InputTokenCount;
long? output = usage?.OutputTokenCount;
long? total  = usage?.TotalTokenCount;
```

Streaming: individual `AgentRunResponseUpdate` items do not each carry usage.
Aggregate the updates into a full response and read usage from that (MAF ships a
`ToAgentRunResponseAsync()` aggregation extension for update streams — verify exact
name; M.E.AI's equivalent for raw chat streams is `ToChatResponseAsync()`).

Feed usage into a per-session ledger — this is the enforcement point for the hub
`budget` exit condition (see section 3.3).

---

## 3. Middleware Pipeline Composition

`ChatClientBuilder` composes `DelegatingChatClient` middleware. **First added =
outermost.** A sane production order (verify current ordering guidance in the
M.E.AI docs — some components document required relative positions):

```csharp
builder.Services.AddChatClient(sp => /* provider client */)
    .UseLogging()                    // outermost: sees final requests/responses
    .UseOpenTelemetry(sourceName: "Contoso.Agents")
    .UseDistributedCache(sp.GetRequiredService<IDistributedCache>())
    .Use((inner, sp) => new BudgetEnforcingChatClient(inner,
        sp.GetRequiredService<SessionBudgetLedger>()));
// .UseFunctionInvocation()  <- only for pipelines you invoke directly as
//    IChatClient. ChatClientAgent performs function invocation for its own runs;
//    adding it here too creates two invocation loops.
```

| Middleware | What it does | Enterprise note |
|------------|--------------|-----------------|
| `UseLogging()` | `ILogger` request/response logging | Structured JSON when the host logger is JSON-configured; content logged at Trace level only |
| `UseOpenTelemetry(...)` | GenAI spans + token metrics | Section 1; always on |
| `UseDistributedCache(...)` | Caches responses for identical requests | Wins on repeated deterministic calls (classification, extraction); useless for open chat. Cache key derives from messages+options — verify keying/TTL behavior for your version |
| `UseFunctionInvocation()` | Runs the tool-call loop | Raw `IChatClient` pipelines only (see comment above). The invoking client exposes a per-request iteration cap (`FunctionInvokingChatClient` — verify exact property, e.g. maximum-iterations setting): that cap is your `max_iterations` guard at the model-call layer |
| Custom `DelegatingChatClient` | Anything cross-cutting | Budget/ledger enforcement below |

### 3.3 A budget-and-progress middleware (hub exit conditions in the pipeline)

One compact `DelegatingChatClient` gives three of the six canon exit conditions
(`budget`, `no_progress`, `oscillation`) enforcement teeth at the layer every
model call passes through:

```csharp
using Microsoft.Extensions.AI;

public sealed class BudgetExceededException(string condition, string evidence)
    : Exception($"Exit condition '{condition}' fired: {evidence}")
{
    public string Condition { get; } = condition;
    public string Evidence { get; } = evidence;
}

public sealed class SessionBudgetLedger
{
    private long _totalTokens;
    private int _toolCalls;
    private readonly List<string> _callSignatures = [];   // name+normalized args
    public long MaxTokens { get; init; } = 100_000;
    public int MaxToolCalls { get; init; } = 20;          // hub default budget

    public void Record(UsageDetails? usage)
        => Interlocked.Add(ref _totalTokens, usage?.TotalTokenCount ?? 0);

    public void RecordToolCall(string name, string normalizedArgs)
    {
        _toolCalls++;
        _callSignatures.Add($"{name}({normalizedArgs})");
    }

    public void AssertWithinBudget()
    {
        if (_totalTokens > MaxTokens || _toolCalls > MaxToolCalls)
            throw new BudgetExceededException("budget",
                $"{_totalTokens} tokens, {_toolCalls} tool calls");
        var s = _callSignatures;
        if (s.Count >= 2 && s[^1] == s[^2])                        // window-2 stall
            throw new BudgetExceededException("no_progress", s[^1]);
        if (s.Count >= 4 && s[^1] == s[^3] && s[^2] == s[^4]       // A-B-A-B window-4
                         && s[^1] != s[^2])
            throw new BudgetExceededException("oscillation", $"{s[^2]} <-> {s[^1]}");
    }
}

public sealed class BudgetEnforcingChatClient(IChatClient inner, SessionBudgetLedger ledger)
    : DelegatingChatClient(inner)
{
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        ledger.AssertWithinBudget();
        ChatResponse response = await base.GetResponseAsync(messages, options, cancellationToken);
        ledger.Record(response.Usage);
        foreach (FunctionCallContent call in response.Messages
                     .SelectMany(m => m.Contents).OfType<FunctionCallContent>())
            ledger.RecordToolCall(call.Name, NormalizeArgs(call.Arguments));
        return response;
    }

    private static string NormalizeArgs(IDictionary<string, object?>? args)
        => args is null ? "" : string.Join(",",
               args.OrderBy(kv => kv.Key, StringComparer.Ordinal)
                   .Select(kv => $"{kv.Key}={kv.Value}"));
}
```

Ledger rules (canon): the ledger is controller-owned per session, counters never
reset mid-task, and arguments are normalized (key-ordered) before signature
comparison. The endpoint catches `BudgetExceededException` and returns a
stop-and-report payload naming the condition and evidence — never a bare 500.
Remaining conditions: `max_iterations` = function-invocation cap + outer pass cap
(SKILL.md), `success_predicate` = typed output validation, `escalation_trigger` =
approval-required tools (section 5.3).

---

## 4. Resilience

### 4.1 What is safe to retry

| Failure | Retry? | Why |
|---------|--------|-----|
| 429 rate limit, 5xx, transport timeout on the **model call** | Yes, with backoff + jitter | Transient, idempotent at the HTTP layer |
| Model returned unusable output (bad JSON, refused) | Once, with a corrective message — via app logic, not Polly | It is a *semantic* failure; blind replay re-rolls the dice at full cost |
| A whole **agent run** that already executed tools | NO blanket retry | Replays non-idempotent tool calls: duplicate emails, double writes |
| A failing **write tool** | Never automatically | Gate it (rule R1) or make it idempotent; retrying irreversible ops is the canonical enterprise agent disaster |

Retry at the narrowest layer that is idempotent. Note the provider SDKs
(Azure/OpenAI clients) already retry transient failures internally with their own
policies — configure or disable one layer so you do not stack retries into a storm
(client retry options: verify your SDK's `RetryPolicy`/`MaxRetries` surface).

### 4.2 Polly v8 pipeline around the model boundary

```csharp
using Polly;
using Polly.Retry;

ResiliencePipeline<AgentRunResponse> pipeline = new ResiliencePipelineBuilder<AgentRunResponse>()
    .AddRetry(new RetryStrategyOptions<AgentRunResponse>
    {
        ShouldHandle = new PredicateBuilder<AgentRunResponse>()
            .Handle<HttpRequestException>()
            .Handle<TaskCanceledException>(ex => !ct.IsCancellationRequested), // timeout, not user abort
        MaxRetryAttempts = 3,
        Delay = TimeSpan.FromSeconds(1),
        BackoffType = DelayBackoffType.Exponential,
        UseJitter = true,
    })
    .AddTimeout(TimeSpan.FromSeconds(90))     // wall-clock slice of the hub 'budget'
    .Build();

AgentRunResponse response = await pipeline.ExecuteAsync(
    async token => await agent.RunAsync(message, thread, cancellationToken: token), ct);
```

Caveat: this wraps the whole run, so it is only safe when the agent's tools are
read-only (the default posture from the integration reference). For agents with
write tools, move the retry inside — around the `IChatClient` HTTP layer — and
leave run-level failures to surface.

Add a circuit breaker (`.AddCircuitBreaker(new CircuitBreakerStrategyOptions<...>
{ FailureRatio = 0.5, MinimumThroughput = 10, BreakDuration = TimeSpan.FromSeconds(30) })`)
when a provider outage should fail fast instead of queueing 90-second timeouts.
If you route the provider SDK through your own `HttpClient`, prefer
`Microsoft.Extensions.Http.Resilience` (`AddStandardResilienceHandler()`) at the
handler level (SDK transport injection surface: verify for your SDK version).

The `CancellationToken` is not resilience decoration — it is the hub Override/Abort
gate. Every endpoint, `RunAsync`, tool method, and EF query takes and honors `ct`.

---

## 5. Hosting: Minimal-API and Streaming Endpoints

### 5.1 Non-streaming endpoint

See the integration reference (sections 1.2 and 6) for the request/response
endpoint with thread persistence. Pattern: resolve keyed agent, load thread, run,
save thread, return DTO with `response.Text` + usage.

### 5.2 SSE streaming with `RunStreamingAsync`

The portable implementation writes `text/event-stream` frames directly (on
.NET 10+ the built-in typed SSE results can replace the manual loop — verify):

```csharp
app.MapPost("/agents/support/sessions/{sessionId}/stream", async (
    string sessionId,
    ChatRequestDto request,
    [FromKeyedServices("support")] AIAgent agent,
    IDistributedCache cache,
    HttpContext http,
    CancellationToken ct) =>
{
    http.Response.Headers.ContentType = "text/event-stream";
    http.Response.Headers.CacheControl = "no-cache";

    AgentThread thread = await ThreadStore.LoadOrCreateAsync(agent, cache, sessionId, ct);

    try
    {
        await foreach (AgentRunResponseUpdate update in
            agent.RunStreamingAsync(request.Message, thread, cancellationToken: ct))
        {
            if (string.IsNullOrEmpty(update.Text)) continue;
            await http.Response.WriteAsync(
                $"data: {JsonSerializer.Serialize(new { text = update.Text })}\n\n", ct);
            await http.Response.Body.FlushAsync(ct);
        }
        await http.Response.WriteAsync("data: {\"done\":true}\n\n", ct);
    }
    catch (BudgetExceededException ex)   // stop-and-report, mid-stream
    {
        await http.Response.WriteAsync(
            $"data: {JsonSerializer.Serialize(new { error = ex.Condition, evidence = ex.Evidence })}\n\n",
            CancellationToken.None);
    }

    await ThreadStore.SaveAsync(cache, sessionId, thread,
        new DistributedCacheEntryOptions { SlidingExpiration = TimeSpan.FromMinutes(30) }, ct);
});
```

Rules: flush after every event; client disconnect surfaces as cancellation on `ct`
— let it propagate into the run so the model call actually stops billing; save the
thread even on partial completion so the conversation is resumable.

### 5.3 Escalation over HTTP: the pending-approval status

When a tool is wrapped in the framework's approval primitive (owned by sibling
`microsoft-agent-framework`, reference section 7), a run that hits the gate comes
back with approval-request content instead of a final answer. The enterprise
surface for that is a *status*, not a blocked thread:

1. Run the agent; detect function-approval request content in `response.Messages`
   (content type name: verify — `FunctionApprovalRequestContent` in current docs).
2. Persist the thread, return `202 Accepted` with
   `{ status: "pending_approval", approvals: [{ id, toolName, arguments }] }`.
3. A separate authorized endpoint (`POST .../approvals/{id}`) appends the matching
   approval response content to the thread and re-runs the agent to completion.

This is hub Phase 3 (HUMAN GATE) and `escalation_trigger` made concrete: the gate
fires **before** the tool executes, the approver sees the exact arguments, and the
approval action is authenticated and audit-logged like any other business mutation.

---

## 6. Testing with a Scripted Fake `IChatClient`

No network, no key, deterministic. The fake replays a scripted sequence of
`ChatResponse` objects and records what it was asked:

```csharp
using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;

public sealed class ScriptedChatClient(params ChatResponse[] script) : IChatClient
{
    private readonly Queue<ChatResponse> _script = new(script);
    public List<IReadOnlyList<ChatMessage>> Calls { get; } = [];

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Calls.Add(messages.ToList());
        return Task.FromResult(_script.Dequeue());
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ChatResponse response = await GetResponseAsync(messages, options, cancellationToken);
        foreach (ChatMessage m in response.Messages)
            yield return new ChatResponseUpdate { Role = m.Role, Contents = m.Contents };
    }

    public object? GetService(Type serviceType, object? serviceKey = null)
        => serviceType.IsInstanceOfType(this) ? this : null;
    public void Dispose() { }
}
```

### 6.1 Testing the full tool loop

Script a tool call, then a final answer; `ChatClientAgent` executes the real tool
in between — proving schema generation, DI wiring, and DTO serialization together:

```csharp
[Fact]
public async Task Agent_calls_order_tool_and_answers()
{
    var toolCallTurn = new ChatResponse(new ChatMessage(ChatRole.Assistant,
        [new FunctionCallContent("call-1", nameof(CustomerTools.GetRecentOrders),
            new Dictionary<string, object?> { ["customerId"] = 42 })]));
    var finalTurn = new ChatResponse(new ChatMessage(ChatRole.Assistant,
        "Customer 42 has 2 recent orders."))
        { Usage = new UsageDetails { InputTokenCount = 120, OutputTokenCount = 15 } };

    var fake = new ScriptedChatClient(toolCallTurn, finalTurn);
    var tools = new CustomerTools(CreateInMemoryDbFactory(), NullLogger<CustomerTools>.Instance);

    var agent = new ChatClientAgent(fake, new ChatClientAgentOptions
    {
        Instructions = "Answer using tools.",
        ChatOptions = new ChatOptions { Tools = [AIFunctionFactory.Create(tools.GetRecentOrders)] },
    });

    AgentRunResponse response = await agent.RunAsync("What did customer 42 order?");

    Assert.Contains("2 recent orders", response.Text);
    Assert.Equal(2, fake.Calls.Count);                       // tool round + final round
    Assert.Contains(fake.Calls[1].SelectMany(m => m.Contents)
        .OfType<FunctionResultContent>(), r => r.CallId == "call-1");
}
```

For the `IDbContextFactory<T>` in tests, use the EF Core in-memory or SQLite
in-memory provider behind a tiny factory stub.

### 6.2 What to test at each layer

| Layer | Test | Fake needed |
|-------|------|-------------|
| Tool method | Call it directly; assert DTO shape, row caps, error contract on failure | DB factory only — no agent, no chat client |
| Tool exposure | `AIFunctionFactory.Create(...)` then inspect the generated schema for leaked parameters | None |
| Agent loop | Scripted tool-call/final-answer sequence (above) | `ScriptedChatClient` |
| Budget middleware | Script N tool-call turns; assert `BudgetExceededException` names the right condition | `ScriptedChatClient` + ledger |
| Endpoint | `WebApplicationFactory`, replace `IChatClient` registration with the fake | Full host |

Never point tests at a live model to assert business logic: nondeterminism turns
every assertion into a flake. Live-model runs belong to evals — see sibling skill
`agentic-evals-benchmarking`.

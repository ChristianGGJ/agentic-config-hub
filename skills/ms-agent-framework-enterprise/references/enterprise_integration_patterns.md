# Microsoft Agent Framework: Enterprise Integration Patterns

Dependency injection, tool design, and data-access patterns for hosting Microsoft
Agent Framework agents inside ASP.NET Core / .NET applications.

**Version assumption:** Microsoft Agent Framework 1.x (`Microsoft.Agents.AI`) on
`Microsoft.Extensions.AI` 9.x, EF Core 8/9, .NET 8/9. Where a member name is marked
"verify", confirm it against current docs before shipping — do not guess.

**Scope note:** this file owns the *enterprise integration* slice. Agent
construction fundamentals, Workflows, and migration guidance are owned by the
sibling skill `microsoft-agent-framework` and are deliberately not re-taught here.

---

## 1. DI Registration and Lifetimes

### 1.1 The chat client: one singleton per provider/deployment

Register `IChatClient` once, with the middleware pipeline composed at registration
time. `AddChatClient` returns a `ChatClientBuilder` so the pipeline reads top-down.

```csharp
// Program.cs
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOptions<AgentSettings>()
    .BindConfiguration("Agents")
    .ValidateDataAnnotations()
    .ValidateOnStart();

builder.Services.AddChatClient(sp =>
    {
        var settings = sp.GetRequiredService<IOptions<AgentSettings>>().Value;
        // Keyless auth: managed identity / developer credential chain. No API key
        // in config for production. For OpenAI-direct, substitute:
        //   new OpenAIClient(key).GetChatClient(model).AsIChatClient()
        return new AzureOpenAIClient(new Uri(settings.Endpoint), new DefaultAzureCredential())
            .GetChatClient(settings.Deployment)   // deployment/model name from config, never hard-coded
            .AsIChatClient();                     // current name; AsChatClient was the preview name
    })
    .UseLogging()
    .UseOpenTelemetry(sourceName: "Contoso.Agents",
                      configure: o => o.EnableSensitiveData = false);
// Note: ChatClientAgent handles function invocation for its own runs. Add
// .UseFunctionInvocation() only for pipelines you call directly as IChatClient.
// Middleware order is significant (first added = outermost); verify current
// ordering guidance in the M.E.AI docs.
```

### 1.2 Multiple agents: keyed singletons

Agents are stateless and thread-safe — conversation state travels in the
`AgentThread`, not in the agent — so singleton is the correct default. Keyed
services (built into `Microsoft.Extensions.DependencyInjection` since .NET 8) give
each named agent its own registration:

```csharp
using Microsoft.Agents.AI;

builder.Services.AddSingleton<CustomerTools>();   // deps must be singleton-safe (sec. 2.3)

builder.Services.AddKeyedSingleton<AIAgent>("support", (sp, _) =>
{
    var chatClient = sp.GetRequiredService<IChatClient>();
    var tools = sp.GetRequiredService<CustomerTools>();

    return new ChatClientAgent(chatClient, new ChatClientAgentOptions
    {
        Name = "SupportAgent",
        Instructions = """
            You are a customer support agent for Contoso.
            Use tools for every factual claim about customer data.
            If a request requires modifying data, stop and state what approval is needed.
            """,
        ChatOptions = new ChatOptions
        {
            Tools =
            [
                AIFunctionFactory.Create(tools.GetRecentOrders),
                AIFunctionFactory.Create(tools.GetOpenInvoices),
            ],
        },
    });
});

builder.Services.AddKeyedSingleton<AIAgent>("triage", (sp, _) =>
    sp.GetRequiredService<IChatClient>()
      .CreateAIAgent(instructions: "Classify the request and answer with a category.",
                     name: "TriageAgent"));
```

Consumption — endpoints and services resolve by key:

```csharp
app.MapPost("/agents/support/chat", async (
    ChatRequestDto request,
    [FromKeyedServices("support")] AIAgent agent,
    CancellationToken ct) =>
{
    AgentRunResponse response = await agent.RunAsync(request.Message, cancellationToken: ct);
    return Results.Ok(new ChatReplyDto(response.Text,
                                       response.Usage?.InputTokenCount,
                                       response.Usage?.OutputTokenCount));
});
```

`Microsoft.Agents.AI.Hosting` ships registration helpers (e.g. an `AddAIAgent`
extension) intended for exactly this scenario — prefer it if it is in your
dependency set, and verify its current signature against the docs. The keyed
pattern above is the framework-independent floor that always works.

### 1.3 Lifetime decision table

| Component | Lifetime | Why |
|-----------|----------|-----|
| `IChatClient` | Singleton | HTTP resources + composed middleware pipeline |
| `AIAgent` / `ChatClientAgent` | Keyed singleton | Stateless; safe under concurrency |
| `AgentThread` | Per conversation | The only stateful piece; never a singleton field |
| Tool classes | Singleton (with factory deps) | Captured by the agent at build time |
| `DbContext` | Per tool invocation | Created inside the tool via factory; never captured |
| Scoped agent variant | Scoped | Only when tools/instructions differ per request or tenant |

---

## 2. Business Services as AIFunction Tools

### 2.1 Class-based tool with DTO mapping and a structured error contract

Tools are ordinary C# methods. `AIFunctionFactory.Create(method)` reads the
`[Description]` attributes and parameter types to generate the JSON schema the
model sees. `CancellationToken` parameters are wired automatically and hidden from
the model.

```csharp
using System.ComponentModel;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;

public sealed record OrderDto(int Id, decimal Total, string Status, string PlacedOn);

public sealed class CustomerTools
{
    private readonly IDbContextFactory<CrmDbContext> _dbFactory;
    private readonly ILogger<CustomerTools> _logger;

    public CustomerTools(IDbContextFactory<CrmDbContext> dbFactory, ILogger<CustomerTools> logger)
    {
        _dbFactory = dbFactory;
        _logger = logger;
    }

    [Description("Gets the five most recent orders for a customer. Returns JSON.")]
    public async Task<string> GetRecentOrders(
        [Description("The unique integer id of the customer.")] int customerId,
        CancellationToken ct = default)
    {
        try
        {
            await using var db = await _dbFactory.CreateDbContextAsync(ct);

            List<OrderDto> orders = await db.Orders
                .AsNoTracking()
                .Where(o => o.CustomerId == customerId)
                .OrderByDescending(o => o.PlacedAt)
                .Take(5)
                .Select(o => new OrderDto(o.Id, o.Total, o.Status.ToString(),
                                          o.PlacedAt.ToString("yyyy-MM-dd")))
                .ToListAsync(ct);

            return JsonSerializer.Serialize(orders);
        }
        catch (Exception ex)
        {
            // Log the real exception locally; give the model a stable, non-leaky contract.
            _logger.LogError(ex, "GetRecentOrders failed for customer {Id}", customerId);
            return JsonSerializer.Serialize(new
            {
                error = "order_lookup_failed",
                retryable = ex is DbUpdateException or TimeoutException,
                message = "Order lookup failed. Do not retry with the same id more than once.",
            });
        }
    }
}
```

Rules baked into this pattern:

- **Never throw across the tool boundary.** An unhandled exception either crashes
  the run or feeds the raw stack trace (connection strings, table names) to the
  model. Return a structured error object with an `error` code and a `retryable`
  hint instead.
- **Never serialize entities.** The DTO is the tool's *output contract* — an
  allowlist. If a field is not needed for the agent's decision, it does not exist.
- **Cap everything**: `Take(N)` on rows, truncate long strings, format dates as
  short strings. Every byte returned is paid for again on every subsequent turn of
  the conversation.

### 2.2 Sizing the tool schema

The model only sees the method signature and descriptions. Keep parameters
primitive (`int`, `string`, `bool`, enums-as-strings) or a single small record.
A parameter the model cannot reliably produce (GUID composites, base64 blobs,
nested graphs) is a hallucination invitation — resolve those inside the tool from
ambient context (claims, session) instead.

### 2.3 Singleton-safe dependencies (the capture rule)

Tool instances are captured by the agent when `ChatOptions.Tools` is built. In a
singleton agent, that means the tool object lives forever. Its constructor may
therefore only take:

| Safe to inject | Why |
|----------------|-----|
| `IDbContextFactory<T>` | Creates a fresh context per call |
| `IHttpContextAccessor` | Resolves ambient request context at call time |
| `IServiceScopeFactory` | Lets the tool open a true DI scope per invocation |
| `ILogger<T>`, `IOptionsMonitor<T>`, `HttpClient` via `IHttpClientFactory` | Singleton-safe by design |

| NOT safe | Failure |
|----------|---------|
| `DbContext` (scoped) | Disposed after the first request; `ObjectDisposedException` later, or a permanently-captured connection |
| Any scoped unit-of-work/domain service | Same disposal/staleness class of bug |

When a tool genuinely needs several scoped services, open a scope explicitly:

```csharp
public sealed class FulfillmentTools
{
    private readonly IServiceScopeFactory _scopeFactory;
    public FulfillmentTools(IServiceScopeFactory scopeFactory) => _scopeFactory = scopeFactory;

    [Description("Checks fulfillment eligibility for an order.")]
    public async Task<string> CheckEligibility(int orderId, CancellationToken ct = default)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var checker = scope.ServiceProvider.GetRequiredService<IEligibilityService>();
        var result = await checker.EvaluateAsync(orderId, ct);
        return JsonSerializer.Serialize(new { result.Eligible, result.Reason });
    }
}
```

---

## 3. EF Core / Relational Data Strategies for Tools

### 3.1 Projection over entity graphs — always

```csharp
// BAD: entity graph. Circular navigation references break serialization, lazy
// loading fires N+1 queries, and the model receives every column including the
// ones that are confidential.
var customer = await db.Customers.Include(c => c.Orders).FirstAsync(c => c.Id == id, ct);
return JsonSerializer.Serialize(customer);

// GOOD: projection is the query. EF translates Select into SQL that fetches only
// the projected columns; the DTO doubles as the exposure allowlist.
var summary = await db.Customers
    .AsNoTracking()
    .Where(c => c.Id == id)
    .Select(c => new
    {
        c.Id,
        c.Name,
        RecentOrders = c.Orders
            .OrderByDescending(o => o.PlacedAt)
            .Take(3)
            .Select(o => new { o.Id, o.Total, Status = o.Status.ToString() }),
    })
    .SingleOrDefaultAsync(ct);
return JsonSerializer.Serialize(summary);
```

### 3.2 Read-only context strategy

Agent tools are read-heavy and adversarial-input-adjacent. Give them the least
capable data surface that works:

| Level | Mechanism |
|-------|-----------|
| Query level (minimum) | `AsNoTracking()` on every tool query |
| Context level | A dedicated `ReadOnlyCrmDbContext` whose `SaveChanges`/`SaveChangesAsync` overrides throw, registered via its own `AddDbContextFactory` |
| Connection level | Read-only connection string / read replica; `ApplicationIntent=ReadOnly` on SQL Server availability groups |
| Account level (strongest) | A DB principal for the agent app with SELECT-only grants on the specific views/tables tools query |

```csharp
public sealed class ReadOnlyCrmDbContext : CrmDbContext
{
    public ReadOnlyCrmDbContext(DbContextOptions<CrmDbContext> options) : base(options) { }

    public override int SaveChanges()
        => throw new InvalidOperationException("Agent tool context is read-only.");
    public override Task<int> SaveChangesAsync(CancellationToken ct = default)
        => throw new InvalidOperationException("Agent tool context is read-only.");
}
```

Write operations belong in explicitly-designed write tools that are classified as
COSTLY/IRREVERSIBLE and gated per hub rule R1 (approval-required function pattern
— see the observability/hosting reference, and `agentic-system-architect` for the
gate canon itself).

### 3.3 Token budgeting for query results

| Rule | Default |
|------|---------|
| Max rows per tool response | 5-20 (paginate; give the model a `page` parameter) |
| Max chars per string field | 200-500, truncate with an ellipsis marker |
| Money/date formatting | Pre-format to short strings; do not ship raw ticks/decimals with 10 digits |
| Aggregates over raw rows | If the question is "how many / how much", compute in SQL (`Count`, `Sum`) and return one number, not the rows |

A useful invariant: a single tool response should stay under ~1-2K tokens. If a
legitimate answer cannot fit, the tool's contract is wrong — split it or aggregate.

---

## 4. Configuration and Secrets

### 4.1 Typed options with validation

```csharp
public sealed class AgentSettings
{
    [Required, Url] public string Endpoint { get; set; } = "";
    [Required] public string Deployment { get; set; } = "";   // model/deployment name — config, never hard-coded
    [Range(1, 100)] public int MaxToolCallsPerTask { get; set; } = 20;   // hub 'budget' default
    [Range(1, 10)] public int MaxAgentPasses { get; set; } = 3;          // hub 'max_iterations' default
}

builder.Services.AddOptions<AgentSettings>()
    .BindConfiguration("Agents")
    .ValidateDataAnnotations()
    .ValidateOnStart();   // fail at boot, not on the first customer request
```

### 4.2 Secret sources per environment

- **Local dev:** `dotnet user-secrets set "Agents:ApiKey" "..."` — keeps keys out
  of `appsettings.json` and out of git. The user-secrets provider is wired
  automatically for Development in the default host builder.
- **Production:** a managed secret vault exposed through a configuration provider
  (Azure Key Vault, AWS Secrets Manager, HashiCorp Vault — the pattern is
  identical: secrets appear as configuration keys; code never changes).
- **Prefer keyless entirely:** with Azure OpenAI / Foundry, authenticate with
  `DefaultAzureCredential` (managed identity in production, developer credential
  locally) and grant the identity the inference RBAC role. No secret exists, so no
  secret can leak. This is the recommended production posture.

Never: keys in `appsettings.json`, keys in agent instructions, keys passed through
tool parameters, keys echoed into telemetry (see `EnableSensitiveData` in the
observability reference).

---

## 5. Tenant Boundary Enforcement in Tools

The model must never be the tenancy mechanism. Tenant identity comes from the
authenticated request (claims), is resolved *inside* the tool, and is applied as a
SQL filter the model cannot influence. Note the tool takes **no tenant parameter**
— a model-supplied tenant id would be a confused-deputy vulnerability.

```csharp
public sealed class TenantScopedTools
{
    private readonly IDbContextFactory<CrmDbContext> _dbFactory;
    private readonly IHttpContextAccessor _http;

    public TenantScopedTools(IDbContextFactory<CrmDbContext> dbFactory, IHttpContextAccessor http)
    {
        _dbFactory = dbFactory;
        _http = http;
    }

    [Description("Lists the signed-in customer's open invoices.")]
    public async Task<string> GetOpenInvoices(CancellationToken ct = default)
    {
        // Fail CLOSED: no claim, no query.
        string? tenantId = _http.HttpContext?.User.FindFirst("tenant_id")?.Value;
        if (string.IsNullOrEmpty(tenantId))
            return JsonSerializer.Serialize(new { error = "unauthenticated", message = "No tenant context." });

        await using var db = await _dbFactory.CreateDbContextAsync(ct);
        var invoices = await db.Invoices
            .AsNoTracking()
            .Where(i => i.TenantId == tenantId && i.Status == InvoiceStatus.Open)
            .Take(10)
            .Select(i => new { i.Id, i.Amount, Due = i.DueDate.ToString("yyyy-MM-dd") })
            .ToListAsync(ct);

        return JsonSerializer.Serialize(invoices);
    }
}
```

Defense in depth: pair the claims filter with EF Core global query filters
(`modelBuilder.Entity<Invoice>().HasQueryFilter(i => i.TenantId == _tenantProvider.TenantId)`)
and/or database row-level security, so a forgotten `Where` clause in one tool does
not become a cross-tenant leak.

Threads are tenant state too: never resume an `AgentThread` for a session id the
current principal does not own.

---

## 6. Multi-Turn State in a Web App

Agents are stateless; HTTP is stateless; the `AgentThread` bridges them.

```csharp
// Per-conversation continuity across requests on a single node or a web farm:
// serialize the thread into IDistributedCache keyed by the session id.
app.MapPost("/agents/support/sessions/{sessionId}/chat", async (
    string sessionId,
    ChatRequestDto request,
    [FromKeyedServices("support")] AIAgent agent,
    IDistributedCache cache,
    CancellationToken ct) =>
{
    // Rehydrate or start a thread. Serialization surface: MAF supports
    // serializing thread state to JSON and rehydrating it via the agent
    // (thread.Serialize() / agent.DeserializeThread(...)) — verify the exact
    // member names against current docs.
    AgentThread thread = await ThreadStore.LoadOrCreateAsync(agent, cache, sessionId, ct);

    AgentRunResponse response = await agent.RunAsync(request.Message, thread, cancellationToken: ct);

    await ThreadStore.SaveAsync(cache, sessionId, thread,
        new DistributedCacheEntryOptions { SlidingExpiration = TimeSpan.FromMinutes(30) }, ct);

    return Results.Ok(new ChatReplyDto(response.Text,
                                       response.Usage?.InputTokenCount,
                                       response.Usage?.OutputTokenCount));
});
```

Operational rules:

- **TTL every stored thread** (sliding 30-60 min for chat UX). Unexpired threads
  are unbounded token liabilities: the whole history rides into every future call.
- **Truncate or summarize** long threads before they exceed your per-request token
  budget; the `budget` exit condition applies to conversation length, not just
  loops.
- **Authorize the session id** against the principal on every request (sec. 5).

For cross-session semantic memory (facts that outlive a thread), route to the
sibling skill `hybrid-rag-memory` — a serialized thread is transcript state, not a
memory system.

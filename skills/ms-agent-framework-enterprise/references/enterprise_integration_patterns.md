# Microsoft Agent Framework Enterprise Integration Patterns

This guide defines the advanced design patterns for integrating Microsoft Agent Framework 1.0 within production-grade C# / .NET 9 applications.

---

## 1. Advanced Dependency Injection & Agent Scoping

In enterprise applications, register agents and model abstractions within the standard Microsoft dependency container (`IServiceCollection`) to allow seamless sharing of state and database connections.

### Setup in `Program.cs` (C#):
```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using OpenAI;

var builder = WebApplication.CreateBuilder(args);

// 1. Register the unified Chat Client (e.g. OpenAI or Azure OpenAI)
builder.Services.AddSingleton<IChatClient>(sp =>
{
    var openAiClient = new OpenAIClient(builder.Configuration["OpenAI:ApiKey"]);
    return openAiClient.AsChatClient("gpt-4o");
});

// 2. Register local tools/services (scoped per HTTP request)
builder.Services.AddScoped<DatabaseService>();
builder.Services.AddScoped<EnterpriseTools>();

// 3. Register a named ChatClientAgent using Factory DI
builder.Services.AddScoped<ChatClientAgent>(sp =>
{
    var chatClient = sp.GetRequiredService<IChatClient>();
    var tools = sp.GetRequiredService<EnterpriseTools>();

    // Expose local tools as AIFunctions
    var functions = new[]
    {
        AIFunctionFactory.Create(tools.QueryCustomerRecords, "QueryCustomerRecords")
    };

    return new ChatClientAgent(chatClient, instructions: "You are a customer service assistant.")
    {
        Name = "CustomerServiceAgent",
        Arguments = new ChatOptions { Tools = functions }
    };
});
```

---

## 2. Robust Class-Based Tools (`AIFunction`) & Error Handling

Enterprise tools must handle internal database exceptions gracefully to prevent crashes in the LLM runtime.

### C# Class-Based Tool Pattern:
```csharp
using System.ComponentModel;
using System.Text.Json;
using Microsoft.Extensions.Logging;

public class EnterpriseTools
{
    private readonly DatabaseService _db;
    private readonly ILogger<EnterpriseTools> _logger;

    public EnterpriseTools(DatabaseService db, ILogger<EnterpriseTools> logger)
    {
        _db = db;
        _logger = logger;
    }

    [Description("Retrieves clean transaction history for a specific customer ID.")]
    public async Task<string> QueryCustomerRecords(
        [Description("The unique integer ID of the customer.")] int customerId)
    {
        try
        {
            var records = await _db.GetTransactionsAsync(customerId);
            
            // Map to lightweight DTOs to optimize token usage
            var dtos = records.Select(r => new { r.Id, r.Amount, r.Status, Date = r.CreatedDate.ToString("yyyy-MM-dd") });
            return JsonSerializer.Serialize(dtos);
        }
        catch (Exception ex)
        {
            // Log locally and return a machine-readable error explanation to the LLM
            _logger.LogError(ex, "Failed querying customer records for customer {Id}", customerId);
            return JsonSerializer.Serialize(new { error = "Database query failed.", details = "Invalid customer ID or timeout." });
        }
    }
}
```

---

## 3. Relational Data Context Optimization

Never dump entire relational database objects (containing back-references, navigation properties, or bloated text fields) into the context window. Use narrow DTO projection.

### Context Projection Pattern:
```csharp
// BAD: Serializing EF Core Entities directly (bloats context and causes circular reference errors)
// var json = JsonSerializer.Serialize(customerEntity);

// GOOD: Projecting only the fields the agent needs to make decisions
var cleanDto = new
{
    customerEntity.Id,
    customerEntity.Name,
    RecentOrders = customerEntity.Orders
        .OrderByDescending(o => o.OrderDate)
        .Take(3)
        .Select(o => new { o.Id, o.Total, o.Status })
};
var json = JsonSerializer.Serialize(cleanDto);
```

---

## 4. Observability and Telemetry Instrumentations

Microsoft Agent Framework 1.0 supports OpenTelemetry out of the box using .NET `ActivitySource` instrumentation.

### Logging Token and Latency Telemetry:
```csharp
using System.Diagnostics;

private static readonly ActivitySource AgentActivitySource = new("AgenticConfigHub.Telemetry");

public async Task<string> RunAgentSessionAsync(ChatClientAgent agent, string prompt)
{
    using Activity? activity = AgentActivitySource.StartActivity("AgentSession");
    
    var startTime = Stopwatch.GetTimestamp();
    var response = await agent.SendAsync(prompt);
    var elapsed = Stopwatch.GetElapsedTime(startTime);

    // Track tokens if available in response metadata
    if (response.Metadata.TryGetValue("Usage", out var usageObj) && usageObj is ChatResponseUsage usage)
    {
        activity?.SetTag("tokens.input", usage.InputTokens);
        activity?.SetTag("tokens.output", usage.OutputTokens);
        activity?.SetTag("tokens.total", usage.TotalTokens);
    }
    
    activity?.SetTag("duration.ms", elapsed.TotalMilliseconds);
    return response.Text;
}
```

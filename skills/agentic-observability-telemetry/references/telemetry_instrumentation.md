# Agentic Observability & Telemetry Instrumentation

This guide defines the advanced design patterns for tracing execution flow, tool latencies, and token costs across LangGraph, CrewAI, and Microsoft Agent Framework.

---

## 1. LangGraph Tracing (LangSmith Setup)

LangSmith allows visual debugging of state mutations and conditional edge executions. Ensure environment configurations are passed to all subprocess runtimes.

### Environment Instrumentation:
```bash
# Set in deployment environment
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_API_KEY="ls__your_api_key_here"
export LANGCHAIN_PROJECT="enterprise-agentic-prod"
```

### Metadata Tracing (Python):
```python
from langgraph.graph import StateGraph
from langchain_core.runnables import RunnableConfig

# Pass configuration containing metadata keys at kickoff
config = RunnableConfig(
    configurable={
        "thread_id": "session-456",
        "user_id": "customer-99"
    },
    metadata={
        "environment": "production",
        "version": "1.1.0"
    }
)

# Run the compiled graph with tracing context
# result = app.invoke({"state_key": "input"}, config)
```

---

## 2. CrewAI Tracing (AgentOps Setup)

AgentOps tracks multi-agent collaborative team execution, identifying redundant tool calls and agent loops.

### Tracing Instrumentation (Python):
```python
import agentops
from crewai import Crew

# Initialize AgentOps before initializing any agents or crews
agentops.init(
    api_key="ao__your_api_key_here",
    default_tags=["sprint-12", "crew-refactoring"]
)

# Initialize and kickoff your Crew
# crew = Crew(agents=[...], tasks=[...])
# crew.kickoff()

# End the session to flush metrics
agentops.end_session("Success")
```

---

## 3. Microsoft Agent Framework & OpenTelemetry (.NET 9)

In corporate C# backends, direct telemetry exports to OpenTelemetry (Jaeger, Zipkin, or Azure Monitor).

### Telemetry Pipeline Configuration (C#):
```csharp
using OpenTelemetry;
using OpenTelemetry.Trace;
using OpenTelemetry.Resources;

var builder = WebApplication.CreateBuilder(args);

// Configure OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing => tracing
        .AddSource("AgenticConfigHub.Telemetry") // Bind custom ActivitySource
        .AddSource("Microsoft.Agents.AI")        // Bind Microsoft Agent SDK
        .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("AgentBackend"))
        .AddConsoleExporter()                    // Console logging for dev
        .AddOtlpExporter(opt =>                  // OTLP collector for production (Jaeger/AppInsights)
        {
            opt.Endpoint = new Uri("http://localhost:4317");
        })
    );
```

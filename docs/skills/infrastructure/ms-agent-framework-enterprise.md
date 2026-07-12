---
title: "Skill: ms-agent-framework-enterprise — MCP Servers & RAG Architectures"
description: "Use when integrating Microsoft Agent Framework agents into enterprise ASP.NET Core/.NET applications: DI lifetimes and keyed agent registration. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: ms-agent-framework-enterprise

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `ms-agent-framework-enterprise`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/ms-agent-framework-enterprise/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


## Overview

This skill covers the **integration layer** between Microsoft Agent Framework and
production .NET applications: how agents, chat clients, and tools live inside an
ASP.NET Core service container without leaking scoped resources, overexposing data,
or losing observability.

**Version assumption:** Microsoft Agent Framework 1.x (`Microsoft.Agents.AI`) on
`Microsoft.Extensions.AI` (M.E.AI) 9.x abstractions, .NET 8/9. Verify member names
against current docs before shipping; the framework moved fast between preview and 1.0.

**Scope boundary:** framework fundamentals — agent construction options, Workflows
(`WorkflowBuilder`), AgentThread mechanics, SK/AutoGen migration — are owned by the
sibling skill **microsoft-agent-framework**. This skill assumes you already know how
to build a `ChatClientAgent` and teaches how to *host* it in an enterprise app.

## Core Capabilities

1. **DI registration and lifetime design** — `IServiceCollection` patterns, keyed
   services for multiple named agents, singleton-vs-scoped decision rules.
2. **Business services as tools** — class-based `AIFunction` tools via
   `AIFunctionFactory.Create`, DTO mapping, structured error contracts.
3. **Relational data strategy** — EF Core access from tools: `IDbContextFactory`,
   read-only no-tracking queries, projection over entity graphs, row/field caps.
4. **Configuration and secrets** — `IOptions<T>`, user-secrets in dev, managed
   secret vault plus keyless (managed identity) auth in production.
5. **Observability, built-in first** — `ChatClientBuilder.UseOpenTelemetry` and
   GenAI semantic conventions; hand-rolled `ActivitySource` only as a supplement.
6. **Resilience** — Polly-style retry/timeout/circuit-breaker around model calls;
   what is safe to retry and what never is.
7. **Hosting** — minimal-API agent endpoints, SSE streaming via `RunStreamingAsync`,
   cancellation as the universal abort gate.
8. **Testing** — unit-testing tools and agents against a scripted fake `IChatClient`.

## The Invocation Contract (real API, memorize this)

Everything in this skill builds on the actual run surface. Legacy hub samples and
old blog posts show APIs that do not exist — use this table to purge them:

| Ghost API (do NOT write)                        | Real API (MAF 1.x)                                          |
|-------------------------------------------------|-------------------------------------------------------------|
| `agent.SendAsync(prompt)`                        | `await agent.RunAsync(prompt, thread)` -> `AgentRunResponse` |
| `response.Metadata["Usage"]` / `ChatResponseUsage` | `response.Usage` -> `UsageDetails` (`InputTokenCount`, `OutputTokenCount`, `TotalTokenCount`) |
| `new ChatClientAgent(...) { Arguments = new ChatOptions {...} }` | `new ChatClientAgent(chatClient, new ChatClientAgentOptions { Name, Instructions, ChatOptions = new() { Tools = [...] } })` or `chatClient.CreateAIAgent(...)` |
| `openAiClient.AsChatClient("model")`             | `openAiClient.GetChatClient(deployment).AsIChatClient()`     |
| manual `List<ChatMessage>` history               | `AgentThread thread = agent.GetNewThread();` then `RunAsync(msg, thread)` |

```csharp
AIAgent agent = serviceProvider.GetRequiredKeyedService<AIAgent>("support");
AgentThread thread = agent.GetNewThread();

AgentRunResponse response = await agent.RunAsync(userMessage, thread, cancellationToken: ct);
string text = response.Text;
long? inputTokens = response.Usage?.InputTokenCount;
long? outputTokens = response.Usage?.OutputTokenCount;
```

## Decision Frameworks

### 1. Component lifetimes (the single most common enterprise MAF bug class)

`AIAgent`/`ChatClientAgent` is stateless and thread-safe: conversation state lives
in the `AgentThread` you pass to `RunAsync`, not in the agent. That makes agents
singleton-friendly — and makes captured scoped dependencies the failure mode.

| Component                  | Lifetime            | Rationale |
|----------------------------|---------------------|-----------|
| `IChatClient` (per deployment) | Singleton       | Owns HTTP resources; pipeline (telemetry, logging, cache) composed once |
| `AIAgent` / `ChatClientAgent`  | Singleton (keyed) | Stateless; per-conversation state travels in `AgentThread` |
| `AgentThread`              | Per conversation    | The state carrier; never share across users or store in a singleton field |
| Tool classes               | Singleton IF all deps are singleton-safe | Tools are captured by the agent at construction; see rule below |
| `DbContext`                | Never captured      | Resolve per tool invocation via `IDbContextFactory<T>` |

**Capture rule:** any tool instance registered into a singleton agent's
`ChatOptions.Tools` may only depend on singleton-safe services:
`IDbContextFactory<T>`, `IHttpContextAccessor`, `IServiceScopeFactory`,
`ILogger<T>`, `IOptionsMonitor<T>`. Injecting a scoped `DbContext` directly
compiles fine and dies at runtime (see Failure Modes).

**Default:** singleton agent + factory-based tools. Choose scoped agents only when
per-request tool sets or per-request instructions genuinely differ.

### 2. Tool data-access strategy

| Strategy                          | Use when                                  | Cost |
|-----------------------------------|-------------------------------------------|------|
| `IDbContextFactory<T>` per call (default) | Read-mostly tools, singleton agents | One context per invocation; trivial |
| `IServiceScopeFactory` scope per call | Tool needs several scoped services (UoW, domain services) | More ceremony; correct disposal required |
| Scoped agent + scoped tools       | Per-request agent variants, tenant-specific tool sets | Rebuilds agent every request; loses singleton wins |
| Dedicated read-only context (separate connection string / replica) | Reporting-style tools on hot OLTP databases | Extra infra; strongest isolation |

### 3. Conversation-state placement

| Placement                              | Use when                          | Trade-off |
|----------------------------------------|-----------------------------------|-----------|
| In-process `AgentThread` per request   | Stateless Q&A, single-turn tools  | Simplest; no continuity |
| Serialized thread in `IDistributedCache` keyed by session id | Multi-turn chat on a web farm | Serialization round-trip per turn; set TTL. Thread serialization API: verify exact members (`thread.Serialize()` / `agent.DeserializeThread(...)`) against current docs |
| Full history in your own store + replay | Audit/compliance requirements     | You own truncation and token budgeting |

Long-term memory (cross-session facts, vector recall) is out of scope here — see
sibling skill **hybrid-rag-memory**.

### 4. Observability approach

| Layer                                   | Mechanism                                    | Default |
|-----------------------------------------|----------------------------------------------|---------|
| Model calls (spans, token metrics)      | `ChatClientBuilder.UseOpenTelemetry` (GenAI semantic conventions) | ALWAYS ON — this is the built-in, standards-based layer; never hand-roll it |
| Agent runs                              | Agent-level OTel decorator (`agent.AsBuilder().UseOpenTelemetry(...)` — verify exact builder name) | On in production |
| Business operations around the agent    | Your own `ActivitySource` spans              | Supplement only, wrapping — never replacing — built-in spans |
| Sensitive prompt/completion content     | `EnableSensitiveData` opt-in on the OTel client | OFF by default; enable only in dev/eval |

### 5. Secrets and auth by environment

| Environment | Secret source                          | Model endpoint auth |
|-------------|----------------------------------------|---------------------|
| Local dev   | `dotnet user-secrets` (never appsettings.json) | API key from user-secrets |
| CI          | Pipeline secret store -> env vars      | Short-lived key or federated credential |
| Production  | Managed secret vault via configuration provider | **Keyless**: managed identity / `DefaultAzureCredential` where the provider supports it; API key in vault otherwise |

## Failure Modes

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `ObjectDisposedException: Cannot access a disposed context` when a tool runs | Singleton agent captured a scoped `DbContext` at startup | Inject `IDbContextFactory<T>`; create/dispose a context inside the tool method |
| User B sees user A's conversation | `AgentThread` cached in a singleton field or static | One thread per conversation, keyed by session/user id; threads are state, agents are not |
| Token spend balloons; tool results dominate the context | Tool serializes EF entities (navigation properties, circular graphs, blob columns) | Project to purpose-built DTOs with `Select`, cap rows (`Take(N)`), cap string lengths |
| Model echoes internal ids, margins, PII it was never asked about | Tool DTO overexposure — DTO mirrors the table instead of the task | Allowlist fields per tool; treat every tool return value as user-visible output |
| Traces show HTTP spans but no LLM/agent spans | OTel exporter configured, but the chat client itself was never instrumented | Add `.UseOpenTelemetry(...)` to the `ChatClientBuilder` pipeline and register the source name with your tracer provider |
| Compile errors on `SendAsync` / `Metadata["Usage"]` | Code generated from pre-1.0 samples with invented APIs | Rewrite to `RunAsync` / `AgentRunResponse.Usage` (see contract table above) |
| Tools declared but never invoked when calling a raw `IChatClient` | Custom pipeline missing function invocation (`ChatClientAgent` adds it for you; a hand-built pipeline does not) | Add `.UseFunctionInvocation()` when composing a raw client pipeline; verify ordering guidance in current M.E.AI docs |
| Retry storm after provider rate limiting; duplicated side effects | Blanket retry wraps the whole agent run, replaying non-idempotent tool calls | Retry only transport-level transient failures; make write-tools idempotent or gate them (R1) instead of retrying them |

## Hub Canon Integration

Enterprise hosting is where the hub's loop-safety canon becomes enforceable code.
An agent endpoint that cannot answer "which of the six exit conditions fired?" is
not production-ready, and agents shipped behind these endpoints must score
**>= 90 (HARDENED)** on the flagship `loop_auditor.py` rubric with all six
conditions declared before iteration 1.

| Exit condition (canon)  | Enterprise .NET mechanism |
|-------------------------|---------------------------|
| `max_iterations`        | Cap tool-invocation rounds per request on the function-invoking layer (M.E.AI exposes a per-request iteration cap on `FunctionInvokingChatClient` — verify exact property name); cap outer agent passes in controller code (default 3-5) |
| `no_progress`           | Hash each round's tool-call ledger entry (name + normalized args); identical hash across a window of 2 -> stop and report |
| `oscillation`           | A-B-A-B detection over the last 4 ledger entries (ring buffer in a `DelegatingChatClient`) |
| `budget`                | Accumulate `AgentRunResponse.Usage` into a per-session ledger; enforce token and tool-call ceilings (default 20 tool calls/task); wall-clock via `CancellationTokenSource` or a resilience timeout |
| `success_predicate`     | Deserialize the final answer into a typed DTO and validate business invariants before returning 200 — never grep the text for "done" |
| `escalation_trigger`    | Approval-required tool pattern for irreversible functions (MAF ships a function-approval wrapper — verify exact type name); endpoint returns a pending-approval status instead of executing |

- **5-Phase Protocol:** tool registration is a Phase 1/2 concern (classify each
  tool's irreversibility, manifest it); the HUMAN GATE (Phase 3) maps to
  approval-required functions firing *before* the tool executes, never after.
- **Gate rules:** R1 — every irreversible tool sits behind an approval gate in code,
  not behind "the model will ask first". R2 — each irreversible tool documents a
  rollback (or `none:justified:`). R3 — the hosting config names a reachable
  escalation contact. `CancellationToken` propagation through every endpoint, agent
  run, and tool call is the Override/Abort gate: if a tool ignores the token, the
  architecture has a state a human cannot stop.
- **Trace detections D1-D7:** with GenAI-convention spans exported, detections like
  error cascades and repeated identical tool calls become trace-backend queries
  over `gen_ai.*` attributes instead of log archaeology.

## When NOT to Use

- **Agent construction, Workflows, AgentThread fundamentals, SK/AutoGen migration**
  -> `microsoft-agent-framework` (framework fundamentals live there).
- **Stack-wide tracing/dashboards/alerting strategy** -> `agentic-observability-telemetry`
  (this skill covers only wiring MAF's built-in OTel into a .NET host).
- **Token cost reduction strategy (caching tiers, routing, batching)** -> `llm-cost-optimizer`.
- **Cross-session memory and retrieval** -> `hybrid-rag-memory`.
- **Designing the gates/exit conditions themselves** -> `agentic-system-architect`
  (this skill only implements the canon in .NET hosting terms).
- **Python-first stacks** -> `langgraph-state-design` or `crewai-role-engineering`.

## References

| File | Contents |
|------|----------|
| `references/enterprise_integration_patterns.md` | DI registration and keyed agents, lifetime rules, class-based AIFunction tools with DTO mapping, EF Core strategies (factory contexts, projection, read-only), IOptions/secrets, tenant-boundary enforcement, multi-turn state |
| `references/observability_resilience_hosting.md` | Built-in OpenTelemetry (GenAI semantic conventions), correct usage accounting, middleware pipeline (function invocation, cache, logging, custom ledger), Polly-style resilience, minimal-API and SSE streaming endpoints, testing with a fake IChatClient |

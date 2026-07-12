---
title: "Skill: microsoft-agent-framework — MCP Servers & RAG Architectures"
description: "Use when translating agentic-config-hub skills, agents, or workflows into Microsoft Agent Framework C# code (ChatClientAgent, AIFunction tools. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: microsoft-agent-framework

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `microsoft-agent-framework`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/microsoft-agent-framework/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


## Overview

This is a **knowledge and mapping skill**. It defines the canonical rules for translating this hub's four-pillar configurations (context, skills, agents, workflows) into Microsoft Agent Framework (MAF) C# implementations, and it teaches the real API surface so that generated code compiles and preserves the hub's safety canon. It ships one deterministic script (`scripts/legacy_construct_scanner.py`) that detects legacy Semantic Kernel / AutoGen constructs and known-invented API names in migrated code. It does **not** generate C# code via a CLI — translation is performed by the agent following the mapping rules in `references/`.

**Version assumption:** all API surfaces below are stated as of **Microsoft Agent Framework 1.x** (`Microsoft.Agents.AI`, `Microsoft.Agents.AI.Workflows`) built on **Microsoft.Extensions.AI** (M.E.AI), targeting .NET 8+. MAF unifies the former Semantic Kernel Agents and AutoGen efforts. Anything marked *verify against current docs* is a pattern whose exact member name shifted during the 2025-2026 preview cycle — confirm before shipping.

## Core Capabilities

1. **Config-to-code mapping** — hub skills to `AIFunction` tools, hub agents to `ChatClientAgent`, hub workflows to `Microsoft.Agents.AI.Workflows` graphs (see `references/agent_framework_mapping.md`).
2. **Orchestration pattern selection** — sequential, concurrent, group-chat, handoff, and custom executor graphs, with calibrated defaults (see `references/workflows_orchestration.md`).
3. **Safety-canon preservation** — every exit condition, gate, and boundary declared in a hub config must survive translation into an enforceable MAF construct (mapping table below).
4. **Legacy migration** — Semantic Kernel `ChatCompletionAgent`/plugins and AutoGen group chats to the unified framework (migration table in the mapping reference).
5. **Legacy/invented construct detection** — deterministic scan of C# and Python sources for banned constructs.

## The Real API Surface (quick reference)

| Hub concept | MAF construct | Namespace / package |
|---|---|---|
| Skill script (CLI tool) | `AIFunction` via `AIFunctionFactory.Create(...)` + `[Description]` | `Microsoft.Extensions.AI` |
| Agent (persona + tools + boundaries) | `ChatClientAgent` over an `IChatClient` | `Microsoft.Agents.AI` |
| Agent invocation | `RunAsync` / `RunStreamingAsync` returning `AgentRunResponse` (`.Text`, `.Messages`, `.Usage`) | `Microsoft.Agents.AI` |
| Conversation state | `AgentThread` from `agent.GetNewThread()`, passed to each run | `Microsoft.Agents.AI` |
| Token accounting | `AgentRunResponse.Usage` (`UsageDetails`: `InputTokenCount`, `OutputTokenCount`, `TotalTokenCount`) | `Microsoft.Extensions.AI` |
| Workflow (sequencing + gates) | Graph of executors + edges via `WorkflowBuilder`; agent-level patterns via `AgentWorkflowBuilder` | `Microsoft.Agents.AI.Workflows` |
| HITL gate on a tool | `ApprovalRequiredAIFunction` wrapping the `AIFunction` | `Microsoft.Agents.AI` |
| Structured output | `ChatOptions.ResponseFormat = ChatResponseFormat.ForJsonSchema(...)` | `Microsoft.Extensions.AI` |

APIs that do **not** exist and must never appear in generated code: `agent.SendAsync(...)`, `Arguments = new ChatOptions {...}` as a `ChatClientAgent` initializer, `ChatResponseUsage`, `response.Metadata["Usage"]`. The scanner flags all of these.

## Decision Frameworks

### 1. Agent construction path

| Path | Use when | Notes |
|---|---|---|
| `chatClient.CreateAIAgent(instructions:, name:, tools:)` | Default. Single agent, default chat settings suffice | Extension method on `IChatClient`; shortest correct form |
| `new ChatClientAgent(chatClient, new ChatClientAgentOptions { Name, Instructions, ChatOptions = new() { Tools = [...] } })` | You need `ChatOptions` control: temperature, response format, tool mode | The canonical explicit form; hub agent specs with output contracts map here |
| Provider-hosted agent (e.g. Azure AI Foundry persistent agents) | Server-side thread/tool state is required | Different client (`PersistentAgentsClient` + MAF Azure extensions); *verify against current docs* |

**Default:** `CreateAIAgent` for prototypes; `ChatClientAgentOptions` for anything translated from a hub agent spec (specs always declare an output contract, which needs `ChatOptions`).

### 2. Orchestration pattern (never hand-roll message-forwarding loops)

| Pattern | Use when | Cost/latency | Calibrated default |
|---|---|---|---|
| Single agent + tools | One role, cohesive toolset | 1x | Up to ~10 tools; beyond that, split roles |
| Sequential | Fixed pipeline of specialists | Sum of stages | 2-5 stages; each stage's output contract validated before the next |
| Concurrent (fan-out/fan-in) | Independent subtasks, one aggregator | Max of branches | Cap fan-out at 5; aggregator must handle partial failure |
| Group chat | Genuinely deliberative tasks (critique, negotiation) | High (N agents x rounds) | Cap rounds at 3-5; require a manager with a hard round limit |
| Handoff | Routing by domain/intent, user-facing triage | ~1x after routing | Every handoff target must be able to hand back |
| Custom executor graph | Cycles, gates, counters — any hub Convergence Loop | Varies | **Mandatory** when the workflow contains loops or irreversible steps: only a custom graph can host the ledger guard and gate executors |

### 3. Conversation state

| Need | Construct |
|---|---|
| One-shot call | `agent.RunAsync(prompt)` — no thread; each call is independent |
| Multi-turn, in-process | `var thread = agent.GetNewThread();` reuse across `RunAsync(msg, thread)` |
| Resume across processes | Serialize/deserialize the thread (JSON round-trip; *verify exact members against current docs*) |
| Cross-session long-term memory | Out of scope — see also **hybrid-rag-memory** |

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| `CS1061: 'ChatClientAgent' does not contain a definition for 'SendAsync'` | Code written against an invented or legacy API | Use `RunAsync` / `RunStreamingAsync`; run the legacy scanner over the source |
| Agent answers in prose but never calls its tools | Tools never reached the agent (e.g. set on an unrelated `ChatOptions`) | Pass `tools:` to `CreateAIAgent` or `ChatClientAgentOptions.ChatOptions.Tools`; `ChatClientAgent` enables automatic function invocation on the underlying client |
| Every turn forgets the previous turn | `RunAsync` called without a thread (stateless by design) | Create one `AgentThread` via `GetNewThread()` and pass it to every run |
| `response.Usage` is null | Provider/deployment does not report usage, or streaming updates were not aggregated | Check provider support; aggregate streaming updates into a full response before reading usage |
| Tool loop burns dozens of calls in one run | No iteration cap on the function-invocation loop | Cap function-calling iterations on the client pipeline (M.E.AI `FunctionInvokingChatClient` max-iterations setting; *verify property name*) and enforce a tool-call budget in the orchestration ledger |
| Workflow starts but never completes | A produced message type has no edge/handler, or no terminal condition | Every message type an executor emits must have a consuming edge; declare an explicit terminal executor |
| Human gate never triggers | Gate implemented as output-text sniffing (`if (text.Contains("y/n"))`) | Wrap the gated tool in `ApprovalRequiredAIFunction` so the gate fires on the tool **call**, not on text |
| JSON output intermittently unparseable | Prompt-only JSON enforcement | Set `ChatOptions.ResponseFormat = ChatResponseFormat.ForJsonSchema(...)` |

## Hub Canon Integration

### Exit-condition taxonomy -> MAF constructs

All six types (canon: `agentic-system-architect/references/loop_engineering_patterns.md`) must be declared before iteration 1 and OR-ed. MAF gives you primitives for two of them; the other four are ledger logic you implement in a guard executor:

| Exit condition | MAF construct | Calibrated default |
|---|---|---|
| `max_iterations` | In-run tool loop: max function-calling iterations on the client pipeline (*verify property name*). Workflow cycles: pass counter in a ledger guard executor on the loop edge | 3-5 passes; 20 steps for convergence loops |
| `no_progress` | No built-in — ledger executor hashes canonicalized state each pass, fires on unchanged window | Window 2 |
| `oscillation` | No built-in — ring buffer of action signatures in the ledger executor, A-B-A-B compare | Window 4 |
| `budget` | Accumulate `response.Usage.TotalTokenCount` and tool-call counts across runs; `CancellationTokenSource` with timeout for wall clock | 20 tool calls; 3 consecutive errors |
| `success_predicate` | Conditional edge predicate routing to the terminal executor; the predicate evaluates the typed message payload (fresh evidence) | Written per task, before iteration 1 |
| `escalation_trigger` | `ApprovalRequiredAIFunction` for gated tools; workflow request/response port for mid-graph human input; two-strikes rule in the ledger | Escalate on irreversible ops, auth failures, and any condition firing twice |

### 5-Phase Protocol mapping

| Phase | MAF implementation |
|---|---|
| 1 DISCOVERY (read-only) | Agent constructed with a read-only tool allowlist — only non-mutating `AIFunction`s registered |
| 2 MANIFEST | Manifest emitted as structured output (`ForJsonSchema`) and passed as a typed workflow message |
| 3 HUMAN GATE | Every irreversible tool wrapped in `ApprovalRequiredAIFunction`; for durable gates, checkpoint the workflow before the gated step |
| 4 IMPLEMENTATION | Write-capable tools enabled; ledger guard executor enforces the declared exit conditions |
| 5 SELF-REVIEW & HANDOFF | Terminal reviewer executor emits the handoff report as the workflow output |

### HARDENED gate

Translation does not launder safety: the **hub-side agent spec must score >= 90 (HARDENED) on `loop_auditor.py` before translation**, and the C# translation must preserve every declared control. Post-translation checklist: (1) each declared exit condition appears as enforceable code, not prose; (2) every irreversible tool is approval-wrapped (gate rule R1); (3) counters live in the orchestrating ledger, never in step logic; (4) non-success exits produce a structured stop-and-report message. Runtime traces for detection D1-D7 analysis come from workflow events and OTel spans — see also **agentic-observability-telemetry**.

## Legacy-Construct Detection

`scripts/legacy_construct_scanner.py` deterministically scans `.cs` and `.py` sources for banned legacy Semantic Kernel / AutoGen constructs and known-invented MAF API names.

```bash
python scripts/legacy_construct_scanner.py path/to/src            # human-readable report
python scripts/legacy_construct_scanner.py path/to/src --json     # machine-readable
python scripts/legacy_construct_scanner.py path/to/src --strict   # warnings also fail
```

| Aspect | Contract |
|---|---|
| Inputs | A file or directory path; `--ext` to override scanned extensions (default `.cs,.py`) |
| Outputs | Findings as `file:line [SEVERITY] pattern - guidance`; `--json` emits a JSON report |
| Exit codes | 0 = clean (warnings allowed unless `--strict`); 1 = banned constructs found; 2 = path error |

Note: the scanner targets **code**. Scanning markdown that legitimately documents legacy names (like this skill's migration table) will produce expected hits — that is why `.md` is not scanned by default.

## When NOT to Use

- **Enterprise DI, hosting, lifetimes, data/DTO mapping, telemetry pipelines** -> see also **ms-agent-framework-enterprise** (owns `IServiceCollection` registration, tool classes with injected services, and observability; this skill owns construction, invocation, and orchestration mapping).
- **Choosing between MAF, LangGraph, and CrewAI** -> see also **agentic-system-architect** (framework selection) and the framework siblings **langgraph-state-design** / **crewai-role-engineering**.
- **Exit-condition theory and loop auditing** -> see also **agentic-system-architect**; Python loop implementations -> **loop-engineering-mechanisms**.
- **Cross-session memory design** -> see also **hybrid-rag-memory**.

## Model Selection Note

Never hard-code model IDs in generated code. Read the model/deployment name from configuration, and choose by tier: a utility-tier model for routing/extraction executors, a standard-tier model for worker agents, a frontier-tier model only for planner/judge roles. Model families rotate faster than code ships.

## References

| File | Contents |
|---|---|
| `references/agent_framework_mapping.md` | Provider setup (`IChatClient`), skill -> `AIFunction`, agent -> `ChatClientAgent`, invocation and usage, `AgentThread`, structured outputs, HITL approvals, SK/AutoGen migration table |
| `references/workflows_orchestration.md` | `Microsoft.Agents.AI.Workflows`: executors, edges, `WorkflowBuilder`, agent-level patterns (sequential/concurrent/group-chat/handoff), guarded loops with the six exit conditions, checkpointing, hub workflow-schema mapping (R1-R6) |

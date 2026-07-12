# Microsoft Agent Framework C# Mapping Reference

Canonical rules for translating this hub's four-pillar configs into Microsoft Agent Framework code.

**Version assumption:** Microsoft Agent Framework 1.x (`Microsoft.Agents.AI` + `Microsoft.Agents.AI.Workflows`) on Microsoft.Extensions.AI (M.E.AI), .NET 8+. Where an exact member name is uncertain it is marked *verify against current docs* — never guess a member name into generated code; run `scripts/legacy_construct_scanner.py` over the output.

---

## 1. Provider Setup — Acquiring an `IChatClient`

Everything in MAF sits on the M.E.AI `IChatClient` abstraction. Acquire it from the provider SDK, then adapt.

```csharp
using Microsoft.Extensions.AI;
using OpenAI;

// OpenAI (model name from configuration -- never hard-code model IDs)
IChatClient chatClient = new OpenAIClient(config["OpenAI:ApiKey"])
    .GetChatClient(config["OpenAI:Model"])
    .AsIChatClient();
```

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;

// Azure OpenAI with keyless auth (preferred in enterprise contexts)
IChatClient chatClient = new AzureOpenAIClient(
        new Uri(config["AzureOpenAI:Endpoint"]),
        new DefaultAzureCredential())
    .GetChatClient(config["AzureOpenAI:Deployment"])
    .AsIChatClient();
```

Rules:

- `AsIChatClient()` is the current adapter name. `AsChatClient()` is the **outdated preview name** — the scanner flags it.
- Azure AI Foundry also exposes server-side persistent agents through its own client (`PersistentAgentsClient` with MAF Azure extension methods to obtain an `AIAgent`); use it only when server-side thread/tool state is a requirement. *Verify the current extension names against docs.*
- DI registration, client pipeline middleware, and telemetry wiring are owned by **ms-agent-framework-enterprise** — do not duplicate them here.

---

## 2. Hub Skill -> `AIFunction` Tool

Every hub skill whose `scripts/` expose a deterministic CLI maps to a C# method wrapped as an `AIFunction`. The method's and parameters' `[Description]` attributes become the tool schema the model sees.

```csharp
using System.ComponentModel;
using System.Diagnostics;
using Microsoft.Extensions.AI;

public sealed class RepositoryTools
{
    private readonly string _repoRoot;
    public RepositoryTools(string repoRoot) => _repoRoot = repoRoot;

    [Description("Audits an agent configuration against the loop-safety rubric and returns the JSON score report.")]
    public async Task<string> AuditAgentAsync(
        [Description("Relative path to the agent markdown file, e.g. agents/cs-prompt-engineer.md")] string agentPath)
    {
        var scriptPath = Path.Combine(_repoRoot, "skills", "agentic-system-architect", "scripts", "loop_auditor.py");
        var startInfo = new ProcessStartInfo
        {
            FileName = "python",
            Arguments = $"\"{scriptPath}\" \"{Path.Combine(_repoRoot, agentPath)}\" --json",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        using var process = Process.Start(startInfo);
        if (process is null)
            return """{"error": "failed to start auditor process"}""";
        string output = await process.StandardOutput.ReadToEndAsync();
        await process.WaitForExitAsync();
        return output;
    }
}

// Wrap as a tool. Name/description default from the method and [Description] attributes.
AIFunction auditTool = AIFunctionFactory.Create(new RepositoryTools(repoRoot).AuditAgentAsync);
```

Mapping rules:

1. One skill script = one `AIFunction`. Keep the tool atomic; do not bundle several scripts behind one tool with a mode switch.
2. Tools return strings (JSON preferred). On failure, return a structured error payload — never throw across the LLM boundary.
3. The hub script's `--json` output is the tool's return value verbatim; the model parses it.
4. Tool classes with injected services (databases, loggers) belong to **ms-agent-framework-enterprise**; this reference stays at the plain-class level deliberately.

---

## 3. Hub Agent -> `ChatClientAgent`

A hub agent spec (persona, skills, tool allowlist, boundaries, output contract) maps to a `ChatClientAgent`.

```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// Path A -- concise: extension method on IChatClient
AIAgent architect = chatClient.CreateAIAgent(
    instructions: architectSystemPrompt,   // the agent spec's persona + boundaries, verbatim
    name: "SystemArchitect",
    tools: [auditTool]);

// Path B -- explicit: options object, needed when the spec declares an output contract
AIAgent architect2 = new ChatClientAgent(chatClient, new ChatClientAgentOptions
{
    Name = "SystemArchitect",
    Instructions = architectSystemPrompt,
    ChatOptions = new ChatOptions
    {
        Tools = [auditTool],
        // Temperature, ResponseFormat, ToolMode etc. go here
    }
});
```

Mapping rules:

1. **Instructions:** inject the hub agent's markdown persona, boundaries, and declared exit conditions verbatim. Exit conditions must ALSO be enforced in code (section 4 and the workflows reference) — prompt text alone is not a control.
2. **Tools:** only the spec's tool allowlist. A DISCOVERY-phase agent gets exclusively read-only functions.
3. **Name:** matches the hub agent id for traceability.
4. `ChatClientAgent` enables automatic function invocation on the underlying client — you do not hand-roll the tool-call loop.
5. **Never write** `Arguments = new ChatOptions {...}` or a settable `Name` object-initializer on `ChatClientAgent` — these members do not exist (a known invented-API failure the scanner flags).

---

## 4. Invocation — `RunAsync`, Streaming, and Usage

```csharp
using Microsoft.Agents.AI;

// Non-streaming
AgentRunResponse response = await architect.RunAsync("Design the ecosystem for project X.");
Console.WriteLine(response.Text);            // aggregated assistant text
// response.Messages -- full message list (tool calls, tool results, assistant turns)

// Token accounting for the hub 'budget' exit condition
long total = response.Usage?.TotalTokenCount ?? 0;
long input = response.Usage?.InputTokenCount ?? 0;
long output = response.Usage?.OutputTokenCount ?? 0;
```

```csharp
// Streaming
await foreach (AgentRunResponseUpdate update in architect.RunStreamingAsync(prompt, thread))
{
    Console.Write(update);   // update renders its text delta
}
// Aggregate updates into a full response (with usage) via the ToAgentRunResponseAsync
// extension over the update stream -- verify exact extension name against current docs.
```

Budget ledger pattern (hub canon `budget`, default 20 tool calls / token ceiling):

```csharp
long tokensUsed = 0;
int passes = 0;
while (true)
{
    passes++;
    if (passes > maxIterations) { /* fire max_iterations: stop + report */ break; }

    AgentRunResponse r = await worker.RunAsync(nextInstruction, thread);
    tokensUsed += r.Usage?.TotalTokenCount ?? 0;
    if (tokensUsed > tokenBudget) { /* fire budget: stop + report */ break; }

    if (SuccessPredicate(r)) { /* fire success_predicate with evidence */ break; }
}
```

Prefer implementing multi-step loops as guarded workflow graphs (see `workflows_orchestration.md`) — the inline loop above is acceptable only for a single-agent Convergence Loop with all six exit conditions declared.

**Never write** `agent.SendAsync(...)`, `response.Metadata["Usage"]`, or the type `ChatResponseUsage` — none exist. Usage lives on `AgentRunResponse.Usage` as an M.E.AI `UsageDetails`.

---

## 5. Conversation State — `AgentThread`

`RunAsync` without a thread is stateless. Multi-turn conversations use the framework's thread abstraction, not a hand-managed `List<ChatMessage>`:

```csharp
AgentThread thread = architect.GetNewThread();

AgentRunResponse r1 = await architect.RunAsync("Draft the manifest.", thread);
AgentRunResponse r2 = await architect.RunAsync("Now list the irreversible steps.", thread); // r2 sees r1
```

Rules:

1. One thread per conversation; one agent can serve many threads concurrently (the agent object is stateless with respect to conversations).
2. Do not share one thread across different agents unless the design explicitly wants a shared transcript.
3. Threads can be serialized to JSON and rehydrated later for durable sessions (*verify exact serialize/deserialize member names against current docs*). For cross-session semantic memory, route to the **hybrid-rag-memory** skill — threads are transcript state, not long-term memory.

---

## 6. Structured Outputs

Hub skills and agents that declare structured output contracts map to schema-enforced responses, not prompt-only JSON pleading:

```csharp
using System.Text.Json;
using Microsoft.Extensions.AI;

JsonElement schema = AIJsonUtilities.CreateJsonSchema(typeof(ManifestReport));

var agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
{
    Name = "ManifestWriter",
    Instructions = "Produce the Phase 2 change manifest.",
    ChatOptions = new ChatOptions
    {
        ResponseFormat = ChatResponseFormat.ForJsonSchema(schema, schemaName: "manifest_report")
    }
});

AgentRunResponse response = await agent.RunAsync(taskDescription);
ManifestReport report = JsonSerializer.Deserialize<ManifestReport>(response.Text)!;
```

MAF also offers typed-run conveniences that deserialize for you (*verify the current generic RunAsync/deserialization helper against docs*); the `ForJsonSchema` + explicit deserialize path above is the stable baseline. Validate the deserialized object before acting on it — schema conformance is not semantic correctness.

---

## 7. HITL — Function Approval, Not Text Sniffing

The hub's HUMAN GATE (Phase 3; gate rule R1) fires on the **tool call**, using the framework's approval primitive — never on matching "y/n" strings in model output.

```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

AIFunction scaffold = AIFunctionFactory.Create(tools.ScaffoldEcosystemAsync);

// Wrap: the agent may REQUEST this tool, but invocation requires an explicit human decision.
AITool gatedScaffold = new ApprovalRequiredAIFunction(scaffold);

AIAgent implementer = chatClient.CreateAIAgent(
    instructions: implementerPrompt,
    name: "Implementer",
    tools: [gatedScaffold]);

AgentThread thread = implementer.GetNewThread();
AgentRunResponse response = await implementer.RunAsync(taskDescription, thread);

// The run pauses with approval requests instead of executing the tool.
// Surface each request to a human, then resume with the decision.
// Approval requests appear as function-approval content in the response
// (request content exposes the function call; create the matching approval
// response with approved: true/false and send it back on the same thread).
// Verify the exact request/response content type names against current docs.
```

Rules:

1. Every hub workflow step marked `irreversible: true` translates to an approval-wrapped tool (R1). No exceptions — including "the model promised it was safe".
2. The human decision and its evidence go into the handoff report (R3 escalation object stays honest).
3. For durable gates that survive process restarts, combine approval with workflow checkpointing (see `workflows_orchestration.md` section 6).

---

## 8. Migration Table — Semantic Kernel / AutoGen -> MAF

Legacy constructs are banned in this hub's generated code (Non-Goals). Migrate, do not wrap:

| Legacy construct | MAF replacement |
|---|---|
| SK `Kernel` + `IChatCompletionService` | `IChatClient` (M.E.AI) |
| SK `ChatCompletionAgent` (`Microsoft.SemanticKernel.Agents`) | `ChatClientAgent` (`Microsoft.Agents.AI`) |
| SK plugin methods `[KernelFunction]` | `AIFunctionFactory.Create` + `[Description]` |
| SK `KernelArguments` / `PromptExecutionSettings` | `ChatOptions` (via `ChatClientAgentOptions` or run options) |
| SK `ChatHistory` | `AgentThread` |
| SK `AgentGroupChat` | Workflows group-chat orchestration (`Microsoft.Agents.AI.Workflows`) |
| SK memory (`ISemanticTextMemory`, `IMemoryStore`) | Not part of MAF core — thread state via `AgentThread`; semantic memory via the **hybrid-rag-memory** skill's patterns |
| AutoGen `AssistantAgent` | `ChatClientAgent` |
| AutoGen `UserProxyAgent` (human input) | `ApprovalRequiredAIFunction` / workflow request-response port |
| AutoGen `RoundRobinGroupChat` | Workflows group-chat with round-robin manager |
| AutoGen `SelectorGroupChat` | Handoff orchestration or a custom router executor |
| AutoGen `register_function` / `FunctionTool` | `AIFunctionFactory.Create` |
| AutoGen `max_turns` / termination conditions | Workflow loop guards implementing the hub's six exit conditions |

Migration procedure: (1) run `scripts/legacy_construct_scanner.py` to inventory legacy constructs; (2) replace bottom-up — clients first, then tools, then agents, then orchestration; (3) re-run the scanner until clean; (4) re-audit the hub-side agent spec with `loop_auditor.py` (>= 90 HARDENED) before deploying the translation.

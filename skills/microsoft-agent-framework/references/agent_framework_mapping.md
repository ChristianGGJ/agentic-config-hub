# Microsoft Agent Framework 1.0 C# Mapping Reference

This document defines the canonical mapping guidelines for translating the repository's 4-pillar config schemas into Microsoft Agent Framework 1.0 (unifying AutoGen and Semantic Kernel) using `Microsoft.Agents.AI` and `Microsoft.Extensions.AI`.

---

## 1. Skill to AIFunction Mapping

Every atomic skill (`skills/<name>/`) containing a CLI python tool (`scripts/<script>.py`) maps to a C# method representing an `AIFunction`.

### Mapping Rules:
1. **Tool Definition**: Implement a C# class with methods containing clear parameter descriptions.
2. **Abstractions**: Wrap the method into an `AIFunction` using `AIFunctionFactory.Create()`.
3. **Execution**: The C# method spawns the corresponding Python process, passes inputs, and captures stdout (JSON/string).

### Example Mapping:
```csharp
using System.Diagnostics;
using System.ComponentModel;
using Microsoft.Extensions.AI;

namespace AgenticConfigHub.AgentFramework.Tools;

public class RepositoryTools
{
    private readonly string _repoRoot;

    public RepositoryTools(string repoRoot)
    {
        _repoRoot = repoRoot;
    }

    [Description("Audits an agent configuration against safety rubrics and returns a validation score.")]
    public async Task<string> AuditAgent(
        [Description("The relative path to the agent markdown file (e.g., agents/cs-prompt-engineer.md)")] string agentPath)
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
        if (process == null) return "{\"error\": \"Failed to start auditor process.\"}";

        string output = await process.StandardOutput.ReadToEndAsync();
        await process.WaitForExitAsync();

        return output;
    }
}
```

---

## 2. Agent to ChatClientAgent Mapping

Every flat agent configuration (`agents/cs-*.md`) maps to a C# `ChatClientAgent` utilizing `Microsoft.Extensions.AI` abstractions.

### Mapping Rules:
1. **Class**: Instantiate `ChatClientAgent` from `Microsoft.Agents.AI`.
2. **ChatClient**: Supply an `IChatClient` (e.g. Azure OpenAI, OpenAI client).
3. **Instructions**: Inject the agent's markdown instructions verbatim.
4. **Tools**: Register the mapped `AIFunction` objects inside the agent's chat completion options or client.

### Example Mapping:
```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using AgenticConfigHub.AgentFramework.Tools;

namespace AgenticConfigHub.AgentFramework.Personas;

public static class AgentPersonas
{
    public static ChatClientAgent CreateSystemArchitect(IChatClient chatClient, RepositoryTools tools)
    {
        // 1. Wrap the C# tool method as an AIFunction
        AIFunction auditTool = AIFunctionFactory.Create(tools.AuditAgent, "AuditAgent");

        // 2. Initialize the ChatClientAgent with instructions and tools
        return new ChatClientAgent(chatClient, instructions: @"You are a Universal Agentic System Architect.
                                 Your role is bound to designing four-pillar ecosystems.
                                 Always enforce loop-safety exit conditions.")
        {
            Name = "SystemArchitect",
            // Pass the tools to the agent's default completion options
            Arguments = new ChatOptions
            {
                Tools = new[] { auditTool }
            }
        };
    }
}
```

---

## 3. Workflow to Agent Collaboration Mapping

Multi-agent workflows (`workflows/*.md`) map to Agent-to-Agent (A2A) orchestration patterns managed via custom loop structures or state machines.

### Mapping Rules:
1. **Handoffs & Loops**: Managed programmatically by forwarding messages between `ChatClientAgent` instances.
2. **Human-in-the-Loop Gates**: Explicitly intercept message handoffs before executing any tool representing an irreversible action.

### Example Mapping:
```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

public async Task RunWorkflowAsync(ChatClientAgent architect, ChatClientAgent engineer, string prompt)
{
    // Initialize session history
    List<ChatMessage> conversationHistory = new() { new ChatMessage(ChatRole.User, prompt) };

    // Step 1: Architect plans the design
    var architectResponse = await architect.SendAsync(conversationHistory);
    Console.WriteLine($"[Architect]: {architectResponse}");
    conversationHistory.Add(new ChatMessage(ChatRole.Assistant, architectResponse.Text));

    // HUMAN GATE: Before triggering any C# tools mapped to scaffolding
    if (architectResponse.Text.Contains("[scaffold]"))
    {
        Console.Write("[HUMAN GATE] Approve scaffolding operation? (y/n): ");
        var approved = Console.ReadLine();
        if (approved?.ToLower() != "y")
        {
            Console.WriteLine("[Escalation] Scaffolding aborted by human gate.");
            return;
        }
    }

    // Step 2: Pass instructions to the Prompt Engineer
    var engineerResponse = await engineer.SendAsync(conversationHistory);
    Console.WriteLine($"[PromptEngineer]: {engineerResponse}");
}
```

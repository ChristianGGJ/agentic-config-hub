# Microsoft.Agents.AI.Workflows — Orchestration Reference

How to translate hub workflows (sequencing, gates, loops, exit conditions) into Microsoft Agent Framework workflow graphs instead of hand-rolled message-forwarding loops.

**Version assumption:** Microsoft Agent Framework 1.x, package `Microsoft.Agents.AI.Workflows`, on .NET 8+. The workflows surface stabilized late in the 2025 preview cycle and some member names shifted between previews; every member marked *verify against current docs* must be confirmed before generated code ships. Run `scripts/legacy_construct_scanner.py` over any translated source.

---

## 1. Execution Model

A workflow is a typed dataflow graph:

- **Executors** are the nodes. Each executor receives a typed message, does work (call an agent, run a tool, evaluate a guard), and either forwards messages or yields workflow output.
- **Edges** connect executors. An edge can be unconditional, conditional (a predicate over the message), fan-out (one source, several targets), or fan-in (several sources, one aggregating target).
- Execution proceeds in **supersteps**: all executors with pending messages run, their emitted messages are delivered, and the next superstep begins. The run completes when the graph goes idle (no pending messages) — there is no implicit "final node"; you decide which executor(s) yield output.
- **Typing is the contract:** an executor only receives messages of the type its handler declares. A message type nobody consumes is silently dropped — the number-one cause of "workflow never completes".

This maps directly onto hub canon: hub workflow *steps* become executors, `depends_on` becomes edges, validation gates become conditional edges, and loop guards become a ledger executor on a cycle.

---

## 2. Custom Executors

Derive from the executor base and implement a typed message handler. As of MAF 1.x the convenient base is `ReflectingExecutor<TSelf>` with `IMessageHandler<TInput>` (forwarding via context) or `IMessageHandler<TInput, TOutput>` (returning the output message):

```csharp
using Microsoft.Agents.AI.Workflows;

internal sealed class SpecValidator()
    : ReflectingExecutor<SpecValidator>("SpecValidator"), IMessageHandler<DraftSpec, ValidationResult>
{
    public async ValueTask<ValidationResult> HandleAsync(DraftSpec message, IWorkflowContext context)
    {
        // Deterministic validation -- no LLM call needed here.
        var errors = Validate(message);
        return new ValidationResult(message, errors);
    }
}
```

`IWorkflowContext` is the executor's I/O surface:

- `context.SendMessageAsync(message)` — forward a message along matching edges (use when one input produces several or conditional messages).
- `context.YieldOutputAsync(result)` — emit a workflow-level output; observers see it as a `WorkflowOutputEvent`. (Earlier previews completed workflows with a `WorkflowCompletedEvent`; current builds run-until-idle and use yielded outputs — *verify against current docs*.)

An executor that wraps an agent simply calls it:

```csharp
internal sealed class WorkerExecutor(AIAgent worker)
    : ReflectingExecutor<WorkerExecutor>("Worker"), IMessageHandler<WorkOrder, WorkResult>
{
    public async ValueTask<WorkResult> HandleAsync(WorkOrder order, IWorkflowContext context)
    {
        AgentRunResponse response = await worker.RunAsync(order.Instruction);
        return new WorkResult(order, response.Text, response.Usage?.TotalTokenCount ?? 0);
    }
}
```

Note the executor returns **usage alongside the result** — the ledger guard (section 5) needs it for the `budget` exit condition.

---

## 3. Building and Running a Workflow

```csharp
using Microsoft.Agents.AI.Workflows;

var worker = new WorkerExecutor(workerAgent);
var validator = new SpecValidator();

var workflow = new WorkflowBuilder(worker)          // constructor takes the START executor
    .AddEdge(worker, validator)                     // unconditional edge
    .WithOutputFrom(validator)                      // which executor's yields are workflow output
    .Build();
```

Conditional edges route by predicate over the message:

```csharp
builder.AddEdge(validator, fixer,    condition: msg => msg is ValidationResult r && r.Errors.Count > 0);
builder.AddEdge(validator, reporter, condition: msg => msg is ValidationResult r && r.Errors.Count == 0);
```

Fan-out / fan-in for concurrent branches (*verify exact member names — `AddFanOutEdge` / `AddFanInEdge` in current builds*):

```csharp
builder.AddFanOutEdge(splitter, targets: [reviewerA, reviewerB, reviewerC]);
builder.AddFanInEdge(aggregator, sources: [reviewerA, reviewerB, reviewerC]);
```

Run in-process and observe events as a stream:

```csharp
await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new WorkOrder(task));

await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    switch (evt)
    {
        case WorkflowOutputEvent output:
            Console.WriteLine($"OUTPUT: {output.Data}");
            break;
        // AgentRunUpdateEvent surfaces streaming agent deltas inside the workflow;
        // SuperStepCompletedEvent marks superstep boundaries (checkpointing hook).
    }
}
```

A non-streaming `InProcessExecution.RunAsync(workflow, input)` variant returns the accumulated run/events (*verify the result-access members against current docs*).

**Rule:** the event stream is your D1-D7 trace source. Persist workflow events (plus OTel spans — see also **agentic-observability-telemetry**) so runaway detection has evidence to analyze.

---

## 4. Agent-Level Patterns — `AgentWorkflowBuilder`

For the standard multi-agent shapes you do not wire executors by hand; `AgentWorkflowBuilder` builds the graph from `AIAgent` instances directly.

| Pattern | Entry point | Use when | Guardrail default |
|---|---|---|---|
| Sequential | `AgentWorkflowBuilder.BuildSequential(agent1, agent2, ...)` | Fixed pipeline of specialists; each output feeds the next | 2-5 stages; validate output contracts between stages |
| Concurrent | `AgentWorkflowBuilder.BuildConcurrent(agent1, agent2, ...)` | Independent perspectives on the same input, then aggregate | Cap fan-out at 5; aggregation must tolerate a failed branch |
| Group chat | Group-chat builder with a chat manager (round-robin or custom selection; *verify builder/manager type names against current docs*) | Genuinely deliberative work: critique, negotiation, consensus | Hard round cap 3-5 enforced by the manager, never by prompt text |
| Handoff | Handoff builder from a triage agent with declared handoff targets (*verify builder member names against current docs*) | Intent routing, user-facing triage | Every target can hand back to triage; no dead-end specialists |

```csharp
using Microsoft.Agents.AI.Workflows;

// Sequential pipeline: researcher -> writer -> reviewer
var workflow = AgentWorkflowBuilder.BuildSequential(researcher, writer, reviewer);

await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Summarize the incident.");
```

Inputs to agent workflows are chat-shaped (a string or `List<ChatMessage>`); agent responses flow along the graph as chat messages.

**Hub mapping rules:**

1. A hub workflow whose steps are all `type: action` with linear `depends_on` translates to `BuildSequential`.
2. Independent steps sharing one downstream aggregator translate to `BuildConcurrent`.
3. Steps with `type: gate` or `irreversible: true`, and any loop, force the **custom executor graph** path (sections 5-6) — the prebuilt patterns have no slot for a ledger guard or an approval gate, so translating a gated hub workflow to `BuildSequential` silently deletes its safety controls. That is a translation failure, not a simplification.

---

## 5. Guarded Loops — the Six Exit Conditions as a Ledger Executor

Cycles are legal in the graph: add an edge from the guard back to the worker. The guard executor owns the ledger — counters never live inside worker steps (canon: Counter Design, `loop_engineering_patterns.md`).

```csharp
public sealed record StopReport(
    string ConditionFired,      // which of the six types
    string Evidence,            // why it fired (hashes, counts, budget numbers)
    string WorkCompleted,
    string WorkRemaining,
    string RecommendedNextStep);

internal sealed class LoopLedger
{
    public int Passes;
    public long TokensUsed;
    public int ToolCalls;
    public int ConsecutiveErrors;
    public readonly Queue<string> StateHashes = new();     // window 2: no_progress
    public readonly Queue<string> ActionSignatures = new(); // window 4: oscillation A-B-A-B
}

internal sealed class LedgerGuard(LoopLedger ledger, LoopLimits limits)
    : ReflectingExecutor<LedgerGuard>("LedgerGuard"), IMessageHandler<WorkResult>
{
    public async ValueTask HandleAsync(WorkResult result, IWorkflowContext context)
    {
        ledger.Passes++;
        ledger.TokensUsed += result.TokensUsed;

        // 1. success_predicate -- declared before iteration 1, evaluated on fresh evidence
        if (limits.SuccessPredicate(result))
        {
            await context.YieldOutputAsync(result); return;
        }
        // 2. max_iterations (default 3-5 fix passes; 20 for convergence loops)
        if (ledger.Passes >= limits.MaxIterations)
        {
            await context.YieldOutputAsync(Stop("max_iterations", $"passes={ledger.Passes}", result)); return;
        }
        // 3. budget -- tokens and tool calls (default: 20 tool calls / declared token ceiling)
        if (ledger.TokensUsed > limits.TokenBudget || ledger.ToolCalls > limits.ToolCallBudget)
        {
            await context.YieldOutputAsync(Stop("budget", $"tokens={ledger.TokensUsed} toolCalls={ledger.ToolCalls}", result)); return;
        }
        // 4. no_progress -- canonicalized state hash unchanged over window 2
        string hash = Sha256(Canonicalize(result));
        ledger.StateHashes.Enqueue(hash);
        if (ledger.StateHashes.Count > 2) ledger.StateHashes.Dequeue();
        if (ledger.StateHashes.Count == 2 && ledger.StateHashes.All(h => h == hash))
        {
            await context.YieldOutputAsync(Stop("no_progress", $"state hash {hash[..8]} unchanged over window 2", result)); return;
        }
        // 5. oscillation -- A-B-A-B over action-signature window 4
        ledger.ActionSignatures.Enqueue(result.ActionSignature);
        if (ledger.ActionSignatures.Count > 4) ledger.ActionSignatures.Dequeue();
        var w = ledger.ActionSignatures.ToArray();
        if (w.Length == 4 && w[0] == w[2] && w[1] == w[3] && w[0] != w[1])
        {
            await context.YieldOutputAsync(Stop("oscillation", $"A-B-A-B: {w[0]} / {w[1]}", result)); return;
        }
        // 6. escalation_trigger -- two-strikes rule and error classes
        if (ledger.ConsecutiveErrors >= 2)
        {
            await context.YieldOutputAsync(Stop("escalation_trigger", "same failure twice -- human decision required", result)); return;
        }

        // No condition fired: loop back to the worker (edge LedgerGuard -> Worker exists in the graph).
        await context.SendMessageAsync(new WorkOrder(NextInstruction(result)));
    }
}
```

Wiring the cycle:

```csharp
var workflow = new WorkflowBuilder(worker)
    .AddEdge(worker, guard)
    .AddEdge(guard, worker)        // the loop edge -- legal because the guard bounds it
    .WithOutputFrom(guard)
    .Build();
```

Rules (all six are canon, non-negotiable):

1. All six conditions are declared **before iteration 1** and OR-ed — any one firing stops the loop. A max-iterations-only loop fails the hub audit.
2. Non-success exits yield a **structured `StopReport`**, never a bare exception: condition fired, evidence, work remaining, recommended next step (this is the Phase 5 handoff contract).
3. The guard also honors wall-clock limits: pass a `CancellationToken` from a `CancellationTokenSource` with timeout into the run.
4. `escalation_trigger` converts repeated firings into a human decision (two-strikes rule) — see section 6 for the human-input mechanics.

---

## 6. Human Gates and Checkpointing

### Request/response ports (mid-graph human input)

For a HUMAN GATE **inside** the graph (Phase 3; checkpoint gates), workflows expose a request/response mechanism: the workflow emits a typed request event, pauses that path, and resumes when the host supplies the response. In current builds this is an input-port/request-info pattern — the workflow surfaces a request event on the run's event stream and the host answers via the run handle (*the port/event/response type names moved during previews — verify `InputPort` / request-info event / send-response members against current docs*).

Host-side shape:

```csharp
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    if (IsHumanInputRequest(evt))            // request event carries the question payload
    {
        var decision = AskHuman(evt);        // real UI, ticket, or CLI prompt
        await SendResponseAsync(run, decision); // resume the paused path
    }
}
```

For gates on a **specific tool call** (gate rule R1: every `irreversible: true` step), prefer `ApprovalRequiredAIFunction` on the tool itself — see `agent_framework_mapping.md` section 7. Port-based gates guard *graph position*; approval-wrapped functions guard *actions*. R1 requires the action guard; use ports for judgment checkpoints (manifest review, plan approval).

### Checkpointing (durable gates and time travel)

Long-running or gated workflows checkpoint at superstep boundaries so a human gate can span process restarts:

```csharp
CheckpointManager checkpointManager = CheckpointManager.Default;   // in-memory; JSON-store variants exist

Checkpointed<StreamingRun> checkpointed =
    await InProcessExecution.StreamAsync(workflow, input, checkpointManager);

// SuperStepCompletedEvent exposes the checkpoint info; persist the latest one.
// Resume later: restore the checkpoint on a rehydrated run and continue.
// (*verify CheckpointManager/Checkpointed/restore member names against current docs*)
```

Rules:

1. Checkpoint **before** every gated step, so a rejected approval can roll back to the pre-gate state (R2 rollback discipline).
2. The checkpoint plus the pending approval request is the durable HUMAN GATE: process death does not skip the gate.
3. Checkpoints are workflow state, not long-term memory — cross-session semantic memory routes to **hybrid-rag-memory**.

---

## 7. Hub Workflow Schema -> Workflow Graph (R1-R6 Preservation)

| Hub workflow field | Workflow construct | Rule preserved |
|---|---|---|
| `id` | Executor id string (constructor argument) | Traceability in events/spans |
| `type: action` | Worker executor (agent or tool call) | R4: failure handling declared on the executor |
| `type: gate` | Approval-wrapped tool or request/response port + pre-gate checkpoint | R1: irreversible steps gated |
| `type: validation` | Deterministic validator executor + conditional edges | Success evidence, not self-report |
| `irreversible: true` | `ApprovalRequiredAIFunction` on the acting tool; checkpoint before | R1 (CRITICAL), R2 rollback |
| `depends_on` | Edges (fan-in when several dependencies) | R5: dependency graph valid — the builder makes dangling references a compile/build-time failure |
| `on_fail: retry` | Loop edge through the ledger guard (bounded) | R4 + six exit conditions |
| `on_fail: escalate` | Route to escalation executor yielding a `StopReport` | R3: escalation object required |
| Final step | Self-review executor as the output-yielding terminal | R6: end with self-review |

Translation checklist (run after generating any workflow code):

1. Every message type emitted has a consuming edge — no silently dropped types.
2. Every cycle passes through exactly one ledger guard; counters live only there.
3. Every `irreversible: true` step is approval-gated AND checkpointed.
4. Non-success paths yield `StopReport`, and the terminal executor emits the Phase 5 handoff report.
5. `legacy_construct_scanner.py` is clean over the generated source, and the hub-side spec scored >= 90 (HARDENED) on `loop_auditor.py` before translation.

---

## 8. Workflow Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Run goes idle with no output | Output executor never received a message, or nobody calls `YieldOutputAsync` | Trace the message types edge by edge; declare `WithOutputFrom` on the real terminal |
| One branch's work vanishes | Emitted message type has no consuming edge | Add the edge or change the emitted type; typed drop is silent by design |
| Loop runs exactly once then stops | Loop edge missing (`guard -> worker`) or guard forwards the wrong type | Wire the back edge; guard must emit the worker's input type |
| Loop never stops | Guard checks conditions but `SendMessageAsync` runs before the checks, or ledger resets each pass | Checks first, forward last; ledger object lives outside the executor's per-message scope |
| Concurrent branches starve the aggregator | Fan-in waits for all branches, one branch failed silently | Aggregate with per-branch timeout/partial-failure policy |
| Approval gate skipped after restart | Gate state lived only in memory | Checkpoint before the gate; restore + re-present the pending request on resume |
| Duplicate side effects after resume | Non-idempotent action executor replayed from checkpoint | Make action executors idempotent or record action completion in the ledger before the side effect |

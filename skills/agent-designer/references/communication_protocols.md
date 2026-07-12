# Agent Communication Protocols

## Overview

SKILL.md section 4 names the communication patterns (message passing, shared state, event-driven). This reference makes them concrete: a message envelope schema every inter-agent message should carry, a complete handoff payload example, and decision guidance for delivery guarantees. The schemas are transport-agnostic — they apply whether messages travel over a queue (SQS, RabbitMQ, Kafka), a shared filesystem board, an HTTP call, or an in-process function call between framework nodes.

---

## Message Envelope Schema

Every inter-agent message is an envelope (routing + bookkeeping metadata) wrapping a payload (the domain content). Agents and middleware read the envelope; only the recipient interprets the payload.

```json
{
  "envelope": {
    "message_id": "uuid — unique per message; the idempotency key",
    "correlation_id": "uuid — constant across one task's entire message chain",
    "causation_id": "message_id of the message this one responds to, or null",
    "sender": "agent identifier, e.g. 'sql-reviewer'",
    "recipient": "agent identifier, or a topic name for pub-sub",
    "type": "request | response | event | handoff | error",
    "schema": "payload schema name + version, e.g. 'review-request/1.2'",
    "created_at": "ISO-8601 UTC timestamp",
    "expires_at": "ISO-8601 UTC timestamp or null — after this, drop, don't process",
    "priority": "high | normal | low",
    "attempt": 1
  },
  "payload": { }
}
```

Field rules:

- **message_id** is generated once by the sender and never changes across retries; consumers use it for deduplication. **attempt** increments on each redelivery of the same message_id.
- **correlation_id** is minted when a task enters the system and copied into every subsequent message for that task — it is what makes multi-agent traces reconstructable. Never mint a new one mid-task.
- **causation_id** gives you the reply chain; correlation_id gives you the task tree. You need both to debug fan-out flows.
- **schema** versions the payload independently of the envelope. Additive payload changes bump the minor version; breaking changes bump the major version and require consumers to opt in.
- **expires_at** prevents zombie work: a request whose answer no longer matters (user cancelled, workflow moved on) must not consume agent budget. Expired messages are acknowledged and logged, not processed.
- **type: error** is a first-class message, not an exception blob — it carries a structured payload (failed message_id, error class, retryable flag) so coordinators can route failures.

---

## Handoff Payload Example

A handoff transfers ownership of in-progress work from one agent to another (specialist to specialist, or agent to human via escalation). The receiving agent must be able to continue **without reading the sender's transcript** — pass artifacts and structured state, never raw conversation history.

```json
{
  "envelope": {
    "message_id": "9f8f2c1e-6f0a-4b3d-9d2e-1a7b8c9d0e1f",
    "correlation_id": "task-20260711-0042",
    "causation_id": "5d4c3b2a-1e0f-4a9b-8c7d-6e5f4a3b2c1d",
    "sender": "code-fixer",
    "recipient": "test-writer",
    "type": "handoff",
    "schema": "work-handoff/1.0",
    "created_at": "2026-07-11T14:32:08Z",
    "expires_at": null,
    "priority": "normal",
    "attempt": 1
  },
  "payload": {
    "objective": "Add regression tests for the auth token-refresh fix",
    "context_summary": "Token refresh raced with logout; fix serializes refresh behind a per-session lock in auth/service.ts",
    "work_completed": [
      "Root cause confirmed: concurrent refresh + logout on shared session state",
      "Fix implemented in auth/service.ts (commit abc1234)",
      "Existing suite passes: 41/41"
    ],
    "artifacts": [
      {"kind": "commit", "ref": "abc1234", "description": "the fix"},
      {"kind": "file", "ref": "auth/service.ts", "description": "changed file"},
      {"kind": "report", "ref": "reports/root-cause-0042.md", "description": "diagnosis"}
    ],
    "acceptance_criteria": [
      "A test reproduces the original race and fails on the pre-fix commit",
      "Full suite remains green"
    ],
    "constraints": [
      "Do not modify auth/service.ts — tests only",
      "Test files under tests/auth/ only"
    ],
    "open_issues": [
      "Logout path has no timeout; flagged, out of scope for this task"
    ],
    "budget_remaining": {"tool_calls": 30, "deadline": "2026-07-11T16:00:00Z"}
  }
}
```

Handoff validation rules (enforce at the receiving edge — reject, do not repair):

1. `objective` and `acceptance_criteria` are non-empty — work without a done-condition is not accepted.
2. Every `artifacts[].ref` resolves (file exists, commit exists) before work starts.
3. `budget_remaining` is present — a handoff without a budget silently inherits an unbounded one.
4. If any rule fails, return a `type: error` message citing the failed rule; the sender fixes the handoff. This mirrors the hub principle that malformed contracts stop at the gate rather than propagating.

---

## Delivery Guarantees — Decision Guidance

Three guarantee levels exist; pick per message type, not per system.

| Guarantee | Semantics | Cost | Use for |
|-----------|-----------|------|---------|
| At-most-once | Fire and forget; loss possible, duplicates impossible | Cheapest | Telemetry, progress pings, log events — anything a fresher message will supersede |
| At-least-once | Redelivered until acknowledged; loss ~impossible, duplicates WILL happen | Requires consumer dedup/idempotency | Default for task requests, results, handoffs |
| Exactly-once | Each message processed exactly one time | Most expensive; only real within transactional systems | Almost never required end-to-end — see below |

Decision rules:

1. **Default to at-least-once + idempotent consumers.** True end-to-end exactly-once across heterogeneous agents is effectively unachievable; the practical equivalent is at-least-once delivery plus consumers that deduplicate on `envelope.message_id` (keep a processed-ids store with a TTL beyond the maximum redelivery window).
2. **Choose at-most-once only when a lost message costs nothing** — the next scheduled message carries the same information (heartbeats, metrics, progress updates).
3. **Reach for transactional exactly-once only inside a single system boundary** (e.g., a workflow engine or broker that supports transactions natively), and only for messages whose duplicate processing has irreversible effects AND whose processing cannot be made idempotent. If the action is irreversible, it should be behind a human approval gate anyway — see the agentic-system-architect skill's HITL reference; a gate plus idempotency almost always removes the exactly-once requirement.
4. **Make handlers idempotent by design**: key side effects on `message_id` (or a payload-level idempotency key), make writes upserts, and make retried actions converge to the same state. An idempotent consumer turns the duplicates question from a correctness problem into a cost problem.
5. **Ordering is a separate promise.** At-least-once says nothing about order; if step B must observe step A's effect, encode the dependency in the payload (causation_id, explicit precondition) rather than assuming queue order.

Failure-path defaults:

- Redelivery: exponential backoff with jitter, bounded attempts (see SKILL.md section 10 retry defaults), then dead-letter.
- Dead-letter queue: mandatory for at-least-once systems — a message that fails max attempts goes to the DLQ with its envelope intact, and the coordinator or a human triages it. Silent drop after retries is data loss with extra steps.
- Poison messages (fail deterministically every attempt): route to DLQ on first non-retryable error class; do not burn the full retry budget.

---

## See Also

- SKILL.md section 4 — pattern-level overview (message passing, shared state, event-driven)
- `agent_prompt_design.md` — output contracts, the per-agent half of the messaging contract
- **agentic-system-architect** skill — HITL gates for irreversible actions and the canonical workflow schema that sequences gated steps
- **agent-workflow-designer** skill — step sequencing and handoff scaffolding at workflow level

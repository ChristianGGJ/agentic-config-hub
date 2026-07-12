# MCP Protocol Basics

What actually moves over the wire when a client talks to your MCP server, and how
clients find and launch the server in the first place. Understanding this layer is
what separates "my tool sometimes disappears" debugging sessions from deliberate
server design.

> **Version assumption:** This document describes the MCP specification revisions
> `2025-03-26` and `2025-06-18`. The protocol is versioned by date string and
> negotiated at initialize time; verify details against the current spec at
> modelcontextprotocol.io before relying on revision-specific behavior.

## 1. JSON-RPC 2.0 Framing

MCP messages are JSON-RPC 2.0. Three message shapes exist:

**Request** (expects a response; `id` must be string or number, never null):

```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": { "name": "list_items", "arguments": { "status": "active" } } }
```

**Response** (exactly one of `result` or `error`):

```json
{ "jsonrpc": "2.0", "id": 1,
  "result": { "content": [ { "type": "text", "text": "..." } ] } }
```

```json
{ "jsonrpc": "2.0", "id": 1,
  "error": { "code": -32602, "message": "Unknown tool: list_itmes" } }
```

**Notification** (no `id`, no response expected):

```json
{ "jsonrpc": "2.0", "method": "notifications/tools/list_changed" }
```

Notes:

- Requests flow in both directions. Servers can call the client too (e.g.
  `sampling/createMessage`, `roots/list`) if the client declared the capability.
- JSON-RPC batching was permitted in the `2025-03-26` revision and **removed in
  `2025-06-18`** — do not build on batch support.
- On stdio transport, messages are newline-delimited: one JSON object per line,
  no embedded literal newlines (see the transports reference).

## 2. Lifecycle: initialize -> operate -> shutdown

Every session begins with a three-step handshake:

1. **Client -> server:** `initialize` request containing the client's
   `protocolVersion`, `capabilities`, and `clientInfo` (name/version).
2. **Server -> client:** response with the negotiated `protocolVersion`, the
   server's `capabilities`, `serverInfo`, and optional `instructions` (a hint
   string the client may inject into the model's context).
3. **Client -> server:** `notifications/initialized` notification. Only after this
   is normal operation allowed.

```json
{ "jsonrpc": "2.0", "id": 0, "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": { "roots": { "listChanged": true }, "sampling": {} },
    "clientInfo": { "name": "claude-code", "version": "2.x" }
  } }
```

Version negotiation: if the server supports the requested version, it echoes it;
otherwise it responds with the latest version it supports, and the client
disconnects if it cannot accept that. On Streamable HTTP, the client also sends an
`MCP-Protocol-Version` header on every subsequent request (required since
`2025-06-18`).

Shutdown has no dedicated protocol message: on stdio the client closes the
server's stdin and terminates the subprocess; on HTTP the client may send an HTTP
`DELETE` to the MCP endpoint to end the session.

## 3. Capability Negotiation

Capabilities declared at initialize are contracts: a party MUST NOT use a feature
the other side did not declare.

| Direction | Capability | Meaning |
|-----------|-----------|---------|
| Server | `tools` (+ `listChanged`) | Server exposes tools; will notify on list changes |
| Server | `resources` (+ `subscribe`, `listChanged`) | Readable resources; per-resource update subscriptions |
| Server | `prompts` (+ `listChanged`) | User-invokable prompt templates |
| Server | `logging` | Server emits `notifications/message` log entries |
| Server | `completions` | Argument autocompletion for prompts/resources |
| Client | `roots` | Client can tell the server which directories are in scope |
| Client | `sampling` | Server may request LLM completions through the client |
| Client | `elicitation` | Server may request structured user input mid-call (`2025-06-18`) |

Practical consequence for server builders: only declare `listChanged` if you
actually send the notification, and never assume `sampling` exists — check the
client capabilities captured at initialize.

## 4. Server Primitives: Tools, Resources, Prompts

The three server-side primitives differ in **who controls invocation**:

| Primitive | Controlled by | Wire methods | Use for |
|-----------|--------------|--------------|---------|
| **Tools** | The model | `tools/list`, `tools/call` | Actions and side effects (query API, create ticket) |
| **Resources** | The application/client | `resources/list`, `resources/templates/list`, `resources/read`, `resources/subscribe` | Read-only context (files, records, config) addressed by URI |
| **Prompts** | The user | `prompts/list`, `prompts/get` | Reusable interaction templates (slash-command style) |

A server that only wraps a REST API usually starts with tools alone — that is
fine. Add resources when clients should be able to attach data as context
*without* a model round-trip (e.g. `billing://invoices/2026-01` read directly
into the conversation), and prompts when you want curated, parameterized entry
points users pick from a menu.

Resource specifics worth knowing:

- Static resources have fixed URIs; dynamic ones are advertised via **URI
  templates** (RFC 6570, e.g. `users://{userId}/profile`) under
  `resources/templates/list`.
- `resources/read` returns `contents` with either `text` or base64 `blob`, plus
  `mimeType`.
- List endpoints (`tools/list`, `resources/list`, `prompts/list`) are paginated
  with an opaque `cursor` / `nextCursor` pair — clients loop until `nextCursor`
  is absent.

## 5. The Two Error Layers (do not mix them)

This is the single most common error-handling design mistake in MCP servers.

**Layer 1 — JSON-RPC protocol errors.** Returned as the `error` member. Reserved
for *protocol-level* failures the model should never see as tool output:

| Code | Meaning |
|------|---------|
| -32700 | Parse error (malformed JSON) |
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params (includes "unknown tool name") |
| -32603 | Internal error |

**Layer 2 — tool execution errors.** A *domain* failure (upstream 4xx/5xx,
validation failure, business rule violation) is a **successful JSON-RPC response**
whose result carries `isError: true`:

```json
{ "jsonrpc": "2.0", "id": 7,
  "result": {
    "isError": true,
    "content": [ { "type": "text",
      "text": "{\"code\": \"upstream_error\", \"message\": \"Invoice not found\", \"details\": \"404 from /invoices/inv_42\"}" } ]
  } }
```

Why the split matters: `isError: true` results are shown to the **model**, which
can read the structured error and self-correct (retry with a fixed argument,
choose another tool). Protocol errors are handled by the **client plumbing** and
typically surface as opaque failures. If you throw a protocol error for "invoice
not found", you rob the agent of its recovery loop. SDKs handle this for you when
you return (rather than crash on) domain failures — in the TypeScript SDK, an
exception thrown inside a tool handler is converted to an `isError` result, but
you get better agent behavior by returning structured error payloads explicitly.

## 6. Tool Annotations and Output Schema

Since spec `2025-03-26`, tool definitions may carry `annotations` — behavioral
*hints* clients use for confirmation UX and safety policy:

```json
{ "name": "delete_invoice",
  "description": "Permanently delete an invoice by ID.",
  "inputSchema": { "type": "object", "properties": { "invoice_id": { "type": "string" } },
                   "required": ["invoice_id"] },
  "annotations": {
    "title": "Delete Invoice",
    "readOnlyHint": false,
    "destructiveHint": true,
    "idempotentHint": false,
    "openWorldHint": false
  } }
```

- `readOnlyHint` — tool does not modify state.
- `destructiveHint` — updates may be destructive (only meaningful when not read-only).
- `idempotentHint` — repeat calls with same args have no additional effect.
- `openWorldHint` — tool interacts with an open external domain (e.g. web search).

Annotations are hints, not security guarantees — clients MUST NOT treat them as
trusted for authorization decisions, but well-behaved clients (Claude Code among
them) use them to decide when to ask the human for confirmation. Set them
honestly; they complement (not replace) this skill's "explicit confirmation
input" pattern for destructive tools.

Since `2025-06-18`, tools may also declare an `outputSchema` (JSON Schema for the
result), and return machine-readable `structuredContent` alongside the human/model
readable `content` blocks. If you declare `outputSchema`, clients validate
`structuredContent` against it — declare it only when your handler actually emits
it.

## 7. Client Registration: How Servers Get Discovered and Launched

There is no network discovery in stdio MCP — clients launch servers from local
config. Each client has its own file format; the common shape is a `mcpServers`
map of name -> launch spec.

**Claude Code — project scope (`.mcp.json` at the repo root, committed for the
team):**

```json
{
  "mcpServers": {
    "billing-mcp": {
      "command": "npx",
      "args": ["-y", "@acme/billing-mcp"],
      "env": { "API_BASE": "https://api.acme.dev", "API_TOKEN": "${BILLING_TOKEN}" }
    },
    "billing-mcp-remote": {
      "type": "http",
      "url": "https://mcp.acme.dev/mcp",
      "headers": { "Authorization": "Bearer ${BILLING_TOKEN}" }
    }
  }
}
```

- `command`/`args`/`env` define a **stdio** launch: the client spawns the process
  and pipes JSON-RPC through stdin/stdout.
- `type: "http"` + `url` registers a **Streamable HTTP** endpoint instead
  (`type: "sse"` exists for legacy servers).
- `${VAR}` expands from the user's environment — this is the supported way to keep
  secrets out of the committed file.
- The `claude mcp add` CLI writes these entries for you and manages three scopes:
  `local` (per-user, per-project), `project` (`.mcp.json`, shared), `user`
  (all projects). Users must approve project-scoped servers before first launch.

**Claude Desktop (`claude_desktop_config.json`):** same `mcpServers` stdio shape;
note Desktop launches servers with a minimal environment, so pass required
variables explicitly in `env` rather than assuming the login shell's exports.

**Other clients:** VS Code uses `.vscode/mcp.json` with a `servers` key; most
other MCP hosts follow the `mcpServers` convention. Field names vary slightly —
verify against the target client's docs; do not assume Claude's schema is
universal.

Design consequence: your server's *README registration snippet is part of its
contract*. Ship a copy-pasteable block for at least Claude Code and Claude
Desktop, document every required `env` variable, and prefer a runner users
already have (`npx`, `uvx`) so registration needs no install step.

## 8. Session Lifecycle Notifications You Should Support

- `notifications/tools/list_changed` — send after dynamically adding/removing/
  disabling tools (requires `tools.listChanged` capability).
- `notifications/resources/updated` — send to subscribers after a subscribed
  resource changes.
- `ping` — either side may send; reply promptly, clients use it for liveness.
- `notifications/cancelled` — the client may cancel an in-flight request; long
  running tool handlers should honor cancellation instead of finishing anyway.
- Progress: requests may carry a `progressToken`; servers report
  `notifications/progress` (with `progress`, optional `total`, `message`) for
  long operations so clients can render progress instead of timing out.

## Related References

- Transport mechanics and selection: `mcp-transports.md`
- Working server code: `typescript-server-template.md`, `python-server-template.md`
- Manifest quality gates: `validation-checklist.md`

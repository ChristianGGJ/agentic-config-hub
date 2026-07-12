# MCP Transports: stdio vs Streamable HTTP

Transport choice decides how you package, deploy, authenticate, and scale the
server. Tool contracts stay identical across transports — pick the transport for
operational reasons, never redesign tools around it.

> **Version assumption:** Reflects MCP spec revisions `2025-03-26` (which
> introduced Streamable HTTP and deprecated HTTP+SSE) and `2025-06-18`. Verify
> transport details against the current spec before depending on
> revision-specific behavior.

## 1. stdio

The client launches your server as a **subprocess** and speaks JSON-RPC over its
stdin/stdout.

Mechanics:

- Messages are newline-delimited JSON: one complete JSON-RPC message per line;
  messages MUST NOT contain embedded literal newlines.
- `stdout` is **reserved for protocol messages**. Anything else on stdout —
  a stray `print()`, a library banner, a progress bar — corrupts the stream and
  the client drops the connection. Log to `stderr` (clients may capture and
  surface it) or to a file. This is the number one cause of "server connects then
  immediately dies".
- Lifetime is the client session: client closes stdin, process exits. There is
  no shared state between two clients — each gets its own process.
- Credentials arrive via the `env` block of the client registration (see
  `mcp-protocol-basics.md` section 7); nothing listens on the network.

Packaging and deployment for stdio:

| Runtime | Ship as | Registration command |
|---------|---------|----------------------|
| TypeScript | npm package with a `bin` entry (shebang `#!/usr/bin/env node`) | `npx -y @acme/billing-mcp` |
| Python | PyPI package with a `[project.scripts]` console script | `uvx acme-billing-mcp` (or `pipx run`) |
| Anything | Container image | `docker run -i --rm acme/billing-mcp` (`-i` keeps stdin open; never `-it` — the TTY breaks framing) |

Build notes: mark the built entry file executable; for npm set `"type": "module"`
or compile to a target Node supports directly; pin dependency versions so
`npx -y` resolves reproducibly.

## 2. Streamable HTTP

The server is an **independent web service** exposing a single MCP endpoint
(conventionally `/mcp`) that supports:

- `POST` — client sends JSON-RPC messages; server answers with either a single
  `application/json` response or a `text/event-stream` (SSE) response when it
  wants to stream notifications/progress before the final result.
- `GET` — client opens a long-lived SSE stream for unsolicited server -> client
  messages (list-changed notifications, server-initiated requests).
- `DELETE` — client terminates its session.

Session and version headers:

- Stateful servers issue an `Mcp-Session-Id` header on the initialize response;
  clients echo it on every subsequent request. Stateless deployments skip
  session IDs entirely (each request self-contained) — simpler to scale, but no
  server-initiated messages or subscriptions.
- Since `2025-06-18`, clients send `MCP-Protocol-Version` on every request after
  initialize.
- Resumability: SSE events may carry `id`s; clients reconnect with
  `Last-Event-ID` to replay missed messages. Optional but valuable behind flaky
  networks.

Security requirements (not optional):

- Validate the `Origin` header and bind local dev servers to `127.0.0.1`, not
  `0.0.0.0` — otherwise any web page the user visits can attempt DNS-rebinding
  attacks against the local server.
- Authentication: MCP over HTTP uses **OAuth 2.1** — the server acts as a
  resource server, publishes protected-resource metadata (RFC 9728) so clients
  can discover the authorization server, and validates bearer tokens on every
  request. Since `2025-06-18`, tokens must be audience-bound to this server
  (RFC 8707 resource indicators) — reject tokens minted for other services. For
  internal deployments a static bearer token or mTLS at the gateway is a common
  pragmatic substitute; document whichever you choose. Note this is *client
  auth to your MCP server* — a different layer from the upstream API
  credentials your tools use.

Packaging and deployment for Streamable HTTP: an ordinary web service. Container
image + your platform of choice; horizontal scaling requires either stateless
mode or session affinity keyed on `Mcp-Session-Id`.

## 3. Legacy HTTP+SSE (deprecated)

The `2024-11-05` revision used two endpoints (`GET /sse` to open a stream plus a
per-session `POST /messages`). It was **deprecated in `2025-03-26`** in favor of
Streamable HTTP. Do not build new servers on it. If you must serve old clients,
SDKs document a backwards-compatibility mode; treat it as a sunset path and note
the timeline in your server README. In client configs it appears as
`type: "sse"` — support requests for that from consumers are your signal to help
them migrate, not to keep shipping SSE features.

## 4. Selection Criteria

| Question | stdio | Streamable HTTP |
|----------|-------|-----------------|
| Who runs it? | Each user's machine, spawned by the client | You run it as a service |
| Consumers | One client per process | Many clients, many users |
| Secrets | User's local env vars | Central credentials + per-user OAuth |
| Latency | Zero network hops | Network + TLS |
| Updates | Users re-install / `npx` picks up new version | You deploy once, everyone updated |
| Auth burden | None (inherits local trust) | OAuth 2.1 / gateway auth to implement |
| Scaling | N/A (one process per session) | Standard web-service scaling |
| Audit/central logging | Hard (distributed) | Easy (one choke point) |

Rules of thumb:

- **Default to stdio** for developer tools, anything wrapping locally-configured
  credentials, and anything installed from a registry into individual machines.
- **Choose Streamable HTTP** when the server fronts shared infrastructure (one
  database, one internal API), when secrets must not live on user machines, when
  non-technical users cannot install runtimes, or when you need central upgrade,
  audit, or rate-limit control.
- **Undecided? Ship stdio first.** The tool contract is transport-independent;
  official SDKs let you bind the same server object to either transport, so
  promoting a stdio server to HTTP later is a deployment change, not a rewrite.

## 5. Transport-Related Pitfalls

1. Writing logs to stdout on stdio (kills the connection — use stderr).
2. Running `docker run -t` for a stdio server (TTY mangles line framing).
3. Binding a local HTTP server to `0.0.0.0` without Origin validation.
4. Implementing session state, then deploying multiple replicas without
   affinity — sessions randomly 404 (`Mcp-Session-Id` not found).
5. Building new servers on legacy SSE because an old tutorial showed it.
6. Baking upstream API keys into an HTTP server image instead of injecting at
   deploy time — and conversely, expecting env-var secrets to exist when a
   client (e.g. Claude Desktop) launches your stdio server with a minimal
   environment: declare them in the registration `env` block.

## Related References

- Wire protocol and client registration: `mcp-protocol-basics.md`
- Server code for both transports: `typescript-server-template.md`,
  `python-server-template.md`

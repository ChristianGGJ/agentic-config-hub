# TypeScript MCP Server Template

Built on the **official `@modelcontextprotocol/sdk`** package.

> **Version assumption:** `@modelcontextprotocol/sdk` **v1.x** (verified against
> the 1.12+ API surface, mid-2025). `registerTool` / `registerResource` /
> `registerPrompt` are the current registration methods; earlier 1.x releases
> used the overloaded `server.tool()` / `server.resource()` / `server.prompt()`
> forms, which remain available. There is no `server.run()` in this SDK — you
> bind a transport with `server.connect(transport)`. If you see
> `new FastMCP(...)` with `addTool`/`start`, that is the separate community
> `fastmcp` npm package, not the official SDK — do not mix the two APIs.
> Verify against current SDK docs when upgrading.

## Project Setup

```json
// package.json (relevant fields)
{
  "name": "@acme/billing-mcp",
  "version": "0.1.0",
  "type": "module",
  "bin": { "billing-mcp": "dist/server.js" },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.0",
    "zod": "^3.24.0"
  }
}
```

Input schemas are declared as **zod raw shapes**; the SDK converts them to JSON
Schema for `tools/list` and validates incoming arguments before your handler
runs.

## Full stdio Server

```ts
#!/usr/bin/env node
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE = process.env.API_BASE ?? "https://api.acme.dev";
const API_TOKEN = process.env.API_TOKEN; // never hardcode; injected by client config

const server = new McpServer({ name: "billing-mcp", version: "0.1.0" });

// --- Tool: read-only ---------------------------------------------------
server.registerTool(
  "list_invoices",
  {
    title: "List Invoices",
    description: "List invoices, optionally filtered by status.",
    inputSchema: {
      status: z.enum(["draft", "open", "paid", "void"]).optional()
        .describe("Filter by invoice status"),
      limit: z.number().int().min(1).max(100).default(20)
        .describe("Maximum invoices to return"),
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  async ({ status, limit }) => {
    const url = new URL("/invoices", API_BASE);
    if (status) url.searchParams.set("status", status);
    url.searchParams.set("limit", String(limit));

    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
    });

    if (!resp.ok) {
      // Domain failure -> isError result the MODEL can read and recover from
      // (NOT a JSON-RPC protocol error; see mcp-protocol-basics.md section 5)
      return {
        isError: true,
        content: [{
          type: "text",
          text: JSON.stringify({
            code: "upstream_error",
            message: `Invoice API returned ${resp.status}`,
            details: await resp.text(),
          }),
        }],
      };
    }

    return {
      content: [{ type: "text", text: JSON.stringify(await resp.json()) }],
    };
  }
);

// --- Tool: destructive, with annotations + confirmation input ----------
server.registerTool(
  "void_invoice",
  {
    title: "Void Invoice",
    description: "Void an invoice permanently. Irreversible.",
    inputSchema: {
      invoice_id: z.string().describe("Invoice ID, e.g. inv_42"),
      confirm: z.literal(true)
        .describe("Must be true; explicit confirmation of a destructive action"),
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ invoice_id }) => {
    const resp = await fetch(new URL(`/invoices/${invoice_id}/void`, API_BASE), {
      method: "POST",
      headers: { Authorization: `Bearer ${API_TOKEN}` },
    });
    if (!resp.ok) {
      return {
        isError: true,
        content: [{ type: "text", text: JSON.stringify({
          code: "void_failed", message: `Upstream ${resp.status}` }) }],
      };
    }
    return { content: [{ type: "text", text: `Invoice ${invoice_id} voided.` }] };
  }
);

// --- Resource: static + templated ---------------------------------------
server.registerResource(
  "billing-config",
  "billing://config",
  {
    title: "Billing Configuration",
    description: "Current billing environment settings",
    mimeType: "application/json",
  },
  async (uri) => ({
    contents: [{ uri: uri.href, text: JSON.stringify({ apiBase: API_BASE }) }],
  })
);

server.registerResource(
  "invoice",
  new ResourceTemplate("billing://invoices/{invoiceId}", { list: undefined }),
  { title: "Invoice", description: "A single invoice by ID" },
  async (uri, { invoiceId }) => {
    const resp = await fetch(new URL(`/invoices/${invoiceId}`, API_BASE), {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
    });
    return {
      contents: [{
        uri: uri.href,
        mimeType: "application/json",
        text: await resp.text(),
      }],
    };
  }
);

// --- Prompt: user-invokable template ------------------------------------
server.registerPrompt(
  "audit-invoice",
  {
    title: "Audit Invoice",
    description: "Review an invoice for anomalies",
    argsSchema: { invoice_id: z.string() },
  },
  ({ invoice_id }) => ({
    messages: [{
      role: "user",
      content: {
        type: "text",
        text: `Audit invoice ${invoice_id} for duplicate line items, ` +
              `unusual amounts, and tax inconsistencies. Use the list_invoices ` +
              `tool and the billing://invoices/${invoice_id} resource.`,
      },
    }],
  })
);

// --- Bind transport ------------------------------------------------------
// stdio rule: NEVER console.log() in a stdio server -- stdout is the wire.
// Use console.error() for diagnostics.
const transport = new StdioServerTransport();
await server.connect(transport);
console.error("billing-mcp connected over stdio");
```

## Structured Output (optional, spec 2025-06-18)

Declare `outputSchema` only when the handler returns `structuredContent`:

```ts
server.registerTool(
  "get_invoice_total",
  {
    description: "Get the total amount for an invoice.",
    inputSchema: { invoice_id: z.string() },
    outputSchema: { total_cents: z.number().int(), currency: z.string() },
  },
  async ({ invoice_id }) => {
    const data = { total_cents: 12050, currency: "EUR" }; // fetch in real code
    return {
      structuredContent: data,
      content: [{ type: "text", text: JSON.stringify(data) }],
    };
  }
);
```

## Streamable HTTP Variant

Same server object, different binding. Sketch (stateless mode; see the SDK's
Express examples for stateful sessions with `sessionIdGenerator` — verify
against current SDK docs, this surface has evolved across 1.x):

```ts
import express from "express";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

const app = express();
app.use(express.json());

app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined, // stateless: no session tracking
  });
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(3000, "127.0.0.1"); // bind localhost in dev; validate Origin in prod
```

See `mcp-transports.md` for selection criteria, session headers, and the OAuth
2.1 requirements that apply to HTTP deployments.

## Test It

```bash
npx @modelcontextprotocol/inspector node dist/server.js
```

The Inspector opens a browser UI to list tools/resources/prompts, invoke them
with arbitrary arguments, and watch the raw JSON-RPC exchange.

## Register It (Claude Code `.mcp.json`)

```json
{
  "mcpServers": {
    "billing-mcp": {
      "command": "npx",
      "args": ["-y", "@acme/billing-mcp"],
      "env": { "API_BASE": "https://api.acme.dev", "API_TOKEN": "${BILLING_TOKEN}" }
    }
  }
}
```

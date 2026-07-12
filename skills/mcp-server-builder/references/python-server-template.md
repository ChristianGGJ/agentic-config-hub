# Python MCP Server Template

Built on **FastMCP**, which generates tool schemas from Python type hints and
docstrings.

> **Version assumption:** the standalone `fastmcp` package **v2.x** (2025). The
> official `mcp` SDK ships a compatible 1.x FastMCP under
> `from mcp.server.fastmcp import FastMCP` — decorators below work on both, but
> run/transport options differ slightly (`fastmcp` 2.x: `transport="http"`;
> official SDK: `transport="streamable-http"`). Verify against the docs of the
> package you install. Do not mix either with the TypeScript SDK's API names.

Key rule: **declare typed parameters, not `input: dict`.** FastMCP builds the
tool's `inputSchema` from the function signature — an opaque `dict` parameter
produces an opaque one-property schema and the agent never sees your real
fields.

```python
#!/usr/bin/env python3
"""billing-mcp: MCP server wrapping the Acme billing API."""

import json
import os
import sys
from typing import Optional

import httpx
from fastmcp import FastMCP

mcp = FastMCP(name="billing-mcp")

API_BASE = os.environ.get("API_BASE", "https://api.acme.dev")
API_TOKEN = os.environ["API_TOKEN"]  # injected via client registration env block


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=15.0,
    )


# --- Tool: read-only, typed parameters ----------------------------------
@mcp.tool()
def list_invoices(status: Optional[str] = None, limit: int = 20) -> dict:
    """List invoices, optionally filtered by status (draft/open/paid/void)."""
    params = {"limit": limit}
    if status:
        params["status"] = status
    with _client() as client:
        resp = client.get("/invoices", params=params)
        if resp.status_code >= 400:
            # Domain failure: return a structured error the model can act on.
            # FastMCP turns raised exceptions into isError results, but an
            # explicit payload gives the agent code/message/details to recover.
            return {"error": {"code": "upstream_error",
                              "message": f"Invoice API returned {resp.status_code}",
                              "details": resp.text[:500]}}
        return resp.json()


# --- Tool: destructive, explicit confirmation input ----------------------
@mcp.tool()
def void_invoice(invoice_id: str, confirm: bool = False) -> dict:
    """Void an invoice permanently. Irreversible. Requires confirm=true."""
    if not confirm:
        return {"error": {"code": "confirmation_required",
                          "message": "Pass confirm=true to void this invoice."}}
    with _client() as client:
        resp = client.post(f"/invoices/{invoice_id}/void")
        if resp.status_code >= 400:
            return {"error": {"code": "void_failed",
                              "message": f"Upstream {resp.status_code}"}}
        return {"status": "voided", "invoice_id": invoice_id}


# --- Resource: static + templated ----------------------------------------
@mcp.resource("billing://config")
def billing_config() -> str:
    """Current billing environment settings."""
    return json.dumps({"api_base": API_BASE})


@mcp.resource("billing://invoices/{invoice_id}")
def invoice_resource(invoice_id: str) -> str:
    """A single invoice document by ID."""
    with _client() as client:
        return client.get(f"/invoices/{invoice_id}").text


# --- Prompt: user-invokable template --------------------------------------
@mcp.prompt()
def audit_invoice(invoice_id: str) -> str:
    """Review an invoice for anomalies."""
    return (
        f"Audit invoice {invoice_id} for duplicate line items, unusual "
        f"amounts, and tax inconsistencies. Use the list_invoices tool and "
        f"the billing://invoices/{invoice_id} resource."
    )


if __name__ == "__main__":
    # stdio rule: never print() to stdout in a stdio server -- stdout is the
    # wire. Use sys.stderr (or logging configured to stderr) for diagnostics.
    print("billing-mcp starting on stdio", file=sys.stderr)
    mcp.run()  # stdio by default
    # HTTP variant (fastmcp 2.x; official SDK uses transport="streamable-http"):
    # mcp.run(transport="http", host="127.0.0.1", port=8000)
```

## Notes

- **Parameter descriptions:** for per-field descriptions beyond the docstring,
  use `Annotated[str, Field(description="...")]` (pydantic) — supported by both
  FastMCP implementations.
- **Tool annotations:** `fastmcp` 2.x accepts
  `@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})`;
  the official SDK takes a `ToolAnnotations` object — verify the exact form
  against the docs of your installed package.
- **Dependencies:** FastMCP and httpx are third-party — fine for *generated
  server projects*, which have their own dependency manifest. (The hub's
  stdlib-only rule applies to this skill's `scripts/`, not to code you generate
  for users.)

## Test It

```bash
npx @modelcontextprotocol/inspector python server.py
```

## Register It (Claude Code `.mcp.json`)

```json
{
  "mcpServers": {
    "billing-mcp": {
      "command": "uvx",
      "args": ["acme-billing-mcp"],
      "env": { "API_BASE": "https://api.acme.dev", "API_TOKEN": "${BILLING_TOKEN}" }
    }
  }
}
```

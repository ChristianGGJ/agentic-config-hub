# Import Runbook: product-launch-sample -> jira

Generated offline by plan-ticket-export. This runbook is the Phase-2 MANIFEST a human approves at the Phase-3 HITL gate BEFORE any ticket is created. Ticket creation is irreversible external work - review before running a single POST.

## Credentials (BYOK - placeholders only, NEVER commit real values)

Export these before running any command, then reference them as $JIRA_EMAIL / $JIRA_API_TOKEN in your requests. No secret value appears in any generated file - only these env-var names:

    export JIRA_EMAIL=...
    export JIRA_API_TOKEN=...

Rotate any token ever pasted into shell history, a URL, or a committed file (OWASP API2, Broken Authentication).

## Idempotency (prevents duplicate-ticket floods on re-run)

Every payload carries the marker prefix `acfhub-8669767d`. BEFORE creating, search for the marker; if it already exists, SKIP that ticket. Re-running must never double-create.

## Order (dependency-safe topological order)

Blockers/parents are created before dependents; links/dependencies are added last.

1. Create issues: `jira_issues.json` (topologically ordered). Search first via `GET /rest/api/3/search?jql=labels="<marker>"`; create only if empty. Descriptions are ADF JSON (v3 requirement).
2. Resolve markers to keys: map each created issue's `idempotency_label` to its returned issue key.
3. Add links: `jira_links.json`. Replace each `<<RESOLVE:marker>>` token with the real issue key, then POST.

Pace requests under Atlassian's cost-budget rate limits; on a 429, back off and resume from the last created marker (never restart from the top).

## Files

- `jira_issues.json` (8 operations)
- `jira_links.json` (9 operations)

VERIFY AGAINST CURRENT DOCS: REST endpoints, rate limits, and auth models evolve. Re-check references/ before an import run.

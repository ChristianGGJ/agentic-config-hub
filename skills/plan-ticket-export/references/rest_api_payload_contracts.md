# REST API Payload Contracts: Jira / Asana / Trello

Version-pinned knowledge base for the plan-ticket-export skill. Every
endpoint, limit, and auth model below is pinned to a specific API version
and dated. APIs churn constantly - **verify against current docs before an
import run.** This file is the authority the `ticket_payload_generator.py`
payload shapes are traceable to; the script never calls any of these
endpoints (offline, zero network, by design).

## Jira Cloud platform REST API v3 (pinned: v3)

Base: `https://<your-site>.atlassian.net`

| Operation | Endpoint | Notes (verify against current docs) |
|-----------|----------|-------------------------------------|
| Create issue | `POST /rest/api/3/issue` | Body is `{"fields": {...}}` |
| Bulk create | `POST /rest/api/3/issue/bulk` | **Max 50 issues per request** |
| Link issues | `POST /rest/api/3/issueLink` | `depends_on` -> "Blocks" link type |

- **ADF descriptions (the #1 v2->v3 migration pitfall).** In v3, the
  `description` (and comment) body MUST be **Atlassian Document Format
  (ADF) JSON**, not the wiki-markup string v2 accepted. A v2 wiki-markup
  string sent to v3 either errors or renders as literal text. The
  generator always emits the ADF `{"type":"doc","version":1,"content":[...]}`
  shape.
- **Auth:** HTTP Basic with `email` + an API token from
  id.atlassian.com. Send as `Authorization: Basic base64(email:token)`.
- **accountId only (2019 GDPR change).** Users are referenced by
  `accountId`; the older `username`/`userKey` fields were removed for GDPR.
  Never map an owner to a username - resolve to accountId at import time.
- **Issue hierarchy:** Epic > Task > Sub-task; the mapping's `issue_type`
  selects the level. Sub-task creation additionally needs a `parent`.
- **Rate limiting:** Atlassian uses a cost-budget model (not a simple
  fixed RPS). Bursts return HTTP 429 with `Retry-After`. A burst import
  that 429s mid-plan leaves a half-created ticket graph - pace requests
  and resume from the last created marker.
- **Idempotency:** No native idempotency key. The generator stamps two
  labels per issue: a plan-level `acfhub-<planhash>` and a per-task
  `acfhub-<planhash>-<taskid>`. Search by label (JQL `labels = "..."`)
  before creating; create only if the search is empty.

## Asana REST API 1.0 (pinned: 1.0 - the only version)

Base: `https://app.asana.com/api/1.0`

| Operation | Endpoint | Notes (verify against current docs) |
|-----------|----------|-------------------------------------|
| Create task | `POST /tasks` | Body is `{"data": {...}}` |
| Add dependencies | `POST /tasks/{task_gid}/addDependencies` | `{"data":{"dependencies":[gids]}}` |
| Batch | `POST /batch` | **Max 10 actions per request** |

- **Auth:** Personal Access Token (PAT) as `Authorization: Bearer <PAT>`.
- **Native idempotency key:** the `external` field
  (`{"data":{"external":{"gid":"..."}}}`) is Asana's documented mechanism
  for tying a task to an external system's id. The generator writes
  `acfhub-<planhash>-<taskid>` there; a re-create with the same external
  gid is detectable/rejectable, preventing duplicate floods.
- **Dependencies are a second call.** A task's blockers are set *after*
  creation via `addDependencies`, which needs the real created gids -
  hence the `<<RESOLVE:marker>>` tokens in `asana_dependencies.json`.
- **Rate limits:** ~150 req/min (free), ~1500 req/min (paid); 429 on
  breach. Prefer `POST /batch` (<=10 actions) to cut round trips.

## Trello REST API v1 (pinned: v1)

Base: `https://api.trello.com/1`

| Operation | Endpoint | Notes (verify against current docs) |
|-----------|----------|-------------------------------------|
| Create card | `POST /1/cards` | `idList` required |
| Create checklist | `POST /1/cards/{id}/checklists` | dependency **fallback** |
| Add check item | `POST /1/checklists/{id}/checkItems` | one per blocker |

- **Auth:** `key` + `token` query/credential pair.
- **NO NATIVE DEPENDENCIES.** Trello cards have no blocker/blocked-by
  relationship. This is the skill's loudest degradation: `depends_on`
  edges CANNOT be represented natively. The generator refuses to drop them
  silently - it emits a "Blocked by" checklist per dependent card
  (`trello_checklists.json`), prints a loud WARN listing every degraded
  edge, and **exits 1** so CI and the human both see the loss. A
  dependency Power-Up is the only way to get true blockers; the checklist
  is a human-readable stopgap, not a semantic equivalent.
- **Idempotency:** No native external key. The generator embeds
  `[acfhub-<planhash>-<taskid>]` in each card `desc`; search the list for
  the marker before creating.
- **Rate limits:** 300 req/10s per API key, 100 req/10s per token; 429 on
  breach.

## Credentials contract (all targets, BYOK)

Scripts NEVER read or emit secret values. The generated runbook contains
only env-var **names**: `$JIRA_EMAIL` + `$JIRA_API_TOKEN`, `$ASANA_PAT`,
`$TRELLO_KEY` + `$TRELLO_TOKEN`. A generated artifact containing a literal
token is a FAIL (regex-checkable in CI). See
`references/byok_and_idempotency.md`.

## Sources (verify against current docs)

- Atlassian Developer: Jira Cloud platform REST API v3 reference and the
  developer changelog / deprecation notices
  (developer.atlassian.com/cloud/jira/platform).
- Atlassian: "Rate limiting" for Jira Cloud REST APIs.
- Asana Developers: API reference, "Rate limits", and "Deprecations"
  pages (developers.asana.com).
- Trello REST API reference and rate-limit documentation
  (developer.atlassian.com/cloud/trello).

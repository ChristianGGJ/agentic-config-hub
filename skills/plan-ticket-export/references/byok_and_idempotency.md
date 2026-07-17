# BYOK Credential Hygiene, Idempotency, and Degradation

Knowledge base for the plan-ticket-export skill covering the three
export-only hazards the tool is built to defeat: credential leakage,
duplicate-ticket floods, and silent semantic loss. Each anti-pattern row
in `SKILL.md` traces back to a subsection here.

## 1. BYOK credential hygiene (OWASP API2: Broken Authentication)

**Rule: scripts never read or emit a secret value.** The generator does
not accept a token flag, does not read a token from the environment, and
never writes a token into any output file. The runbook references only
env-var **names**: `$JIRA_EMAIL` + `$JIRA_API_TOKEN`, `$ASANA_PAT`,
`$TRELLO_KEY` + `$TRELLO_TOKEN`. This is BYOK: the human (or a gated
agent) supplies the token at import time, in their own shell.

Why it matters (mined from OWASP API Security Top 10, 2023, API2):

- Tokens pasted into a URL query string land in server logs, browser
  history, and proxy caches.
- Tokens committed inside a generated runbook leak to everyone with repo
  access and survive in git history after deletion.
- Tokens in shell history persist in `~/.bash_history` / `~/.zsh_history`.

**CI-checkable invariant:** grep every generated artifact for literal
secret shapes (e.g. Atlassian tokens, Asana PAT `1/<digits>:<hex>`, Trello
32/64-hex key/token). The only credential-looking strings permitted are
`$UPPER_SNAKE_CASE` env-var placeholders. A literal match is a build FAIL.

**Fix when a token leaks:** rotate immediately; a leaked token is not
"cleaned" by deleting the file.

## 2. Idempotency (prevents duplicate-ticket floods)

**Failure mode:** re-running a creation script (after a partial failure, a
429 mid-run, or a nervous operator) creates every ticket a second time.
Import graphs have no built-in dedupe, so the board fills with duplicates.

**Fix: a deterministic idempotency marker on every payload.** The
generator derives an 8-hex plan fingerprint (`sha1(plan.name)`) and stamps
each payload:

| Target | Marker location | Native support |
|--------|-----------------|----------------|
| Jira | labels `acfhub-<hash>` + `acfhub-<hash>-<taskid>` | none - search by label first |
| Asana | `data.external.gid = acfhub-<hash>-<taskid>` | native external-id key |
| Trello | `[acfhub-<hash>-<taskid>]` in card `desc` | none - search the list first |

The runbook's first instruction for each target is **search for the
marker; create only if absent.** Re-running must be a no-op for tickets
that already exist. (Sources: Asana's documented rationale for the
`external` field; Atlassian community guidance on bulk-create dedupe.)

## 3. Degradation must be loud, never silent

**Failure mode:** a target cannot represent a plan concept, and the
generator quietly drops it. The worst case is Trello, which has **no
native dependencies** - a generator that silently omits `depends_on`
corrupts the plan's meaning while reporting success.

**Fix:** the generator refuses to drop edges. For Trello it emits a
"Blocked by" checklist per dependent card (preserving the information in a
human-readable form), prints a loud WARN naming every degraded edge, and
**exits 1** so both CI and the operator must acknowledge the loss. The
checklist is a stopgap, not a semantic equivalent; a dependency Power-Up
is the only path to true blockers.

## 4. Rate limits and half-created graphs

**Failure mode:** a burst import hits a 429 partway through, leaving a
half-created ticket graph - some issues exist, some links point at
nothing, and a naive retry double-creates.

**Fix:** the runbook prescribes pacing under each target's documented
limits (Jira cost-budget; Asana 150/1500 req/min; Trello 300 req/10s per
key, 100 per token) and, on a 429, backing off and **resuming from the
last created marker** rather than restarting. Idempotency markers (section
2) make resume safe.

## 5. Granularity: one leaf = one ticket, or not

**Failure mode (PMI WBS, 2nd ed., 2006 - work packages vs activities):**
exporting every WBS leaf as a ticket floods the board; exporting only
phases loses traceability. This skill exports exactly the tasks present in
`plan.json` - granularity is a decision made upstream in decomposition,
not here. If the board is too noisy or too coarse, fix the plan, not the
export.

## Anti-pattern mining sources

- OWASP API Security Top 10 (2023), API2 Broken Authentication - token
  hygiene (sections 1, 4).
- Atlassian Developer changelog / deprecation notices - GDPR
  username->accountId removal, v2-wiki-vs-v3-ADF breakage, bulk endpoint
  evolution (traces to the ADF and accountId rows).
- Atlassian, Asana, Trello rate-limit docs - half-created-graph and
  pacing rows (section 4).
- Asana "external" field docs + Atlassian community bulk-create guidance -
  idempotency (section 2).
- PMI Practice Standard for Work Breakdown Structures, 2nd ed. (2006) -
  the leaf-to-ticket granularity fallacy (section 5).

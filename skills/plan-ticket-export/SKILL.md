---
name: "plan-ticket-export"
description: "Use when an approved plan.json (hub canonical tasks: id, title, description, depends_on) must become offline, dependency-ordered, tool-specific ticket-creation payloads plus a human import runbook for Jira, Asana, or Trello - export-only and one-way, BYOK, with zero network calls in the generator."
---

# Plan Ticket Export

**Category:** Planning / External Integration (offline payload generation)
**Dependencies:** None. Python 3.8+ standard library only, no network, no LLM calls.

## Description

This skill performs exactly ONE transformation: an approved `plan.json` in
the hub canonical tasks shape (`id`, `title`, `description`, `depends_on[]`)
becomes offline, dependency-ordered, tool-specific ticket-creation payload
files plus a human-readable import runbook, for a chosen target
(`--target {jira,asana,trello}`).

It is **strictly export-only and one-way**. It does not sync back, does not
poll ticket status, and does not update tickets. Status tracking is a
different transformation (see `plan-baseline-tracking`); live ticket
creation belongs to the framework/MCP runtime track, not here.

The generator performs **zero network calls** and imports nothing that
could reach a network - no `socket`, `urllib`, `http`, `requests`, or
`ssl`. This is the highest network-temptation skill in the hub and is
deliberately built with no network capability at all. The human (or a
gated agent, downstream of a HITL gate, because ticket creation is an
irreversible external side effect) runs the actual POSTs from the runbook.

Two safety properties are load-bearing. **BYOK credential hygiene:**
scripts never read or emit a secret value; the runbook contains only
env-var placeholders (`$JIRA_API_TOKEN`, `$ASANA_PAT`,
`$TRELLO_KEY`/`$TRELLO_TOKEN`). **Loud degradation:** Trello has no native
dependencies, so `depends_on` edges are emitted as a "Blocked by"
checklist fallback with a loud WARN and exit 1 - never silently dropped.

Graph hygiene (duplicate id / dangling `depends_on` / cycle) duplicates
hub merge-gate rule R5 semantics (`hitl_gate_validator.py`,
agentic-system-architect skill) - duplicated, never imported, per the hub
portability rule. Everything is deterministic: same plan plus same mapping
produces byte-identical payloads, every run.

## Features

- **Three target dialects, one capability:** Jira Cloud REST v3
  (`POST /rest/api/3/issue` with ADF-JSON descriptions, `POST /issueLink`
  "Blocks" for `depends_on`), Asana REST 1.0 (`POST /tasks`,
  `POST /tasks/{gid}/addDependencies`, native `external` idempotency key),
  Trello REST v1 (`POST /1/cards`, checklist dependency fallback).
- **Dependency-safe topological order:** blockers/parents are emitted
  before dependents; links/dependencies are added last.
- **`--validate-only` mode:** cycle / dangling / duplicate check (and
  target representability) without emitting any file.
- **Idempotency markers:** a deterministic `acfhub-<planhash>-<taskid>`
  marker on every payload so re-runs are detectable and never flood the
  board with duplicates.
- **BYOK, secret-free artifacts:** the generator never touches a token;
  the runbook carries only env-var placeholder names (regex-checkable).
- **CI-wireable exit codes:** a plan whose graph is broken, or a target
  that cannot represent the plan's dependencies, fails closed (exit 1).
- **ADF descriptions by construction:** avoids the v2-wiki-markup-vs-v3
  migration pitfall automatically.

## Usage

### Workflow 1: Validate before you export

Run the hygiene + representability gate first; it emits nothing:

```bash
python scripts/ticket_payload_generator.py --target jira \
  --plan assets/sample_plan.json --validate-only
```

Fix every finding (exit 1) - a cycle or dangling reference makes the
dependency ordering meaningless. Running with `--target trello` here also
surfaces every dependency edge that will degrade.

### Workflow 2: Generate payloads and a runbook

```bash
python scripts/ticket_payload_generator.py --target jira \
  --plan assets/sample_plan.json \
  --mapping assets/field_mapping.template.json --out out/jira
```

This writes the payload files and `import-runbook.md` into `out/jira`. The
runbook is the Phase-2 MANIFEST a human approves at the Phase-3 HITL gate
before a single POST. Ticket creation is irreversible - review first.

### Workflow 3: Wire into CI and the human gate

```bash
python scripts/ticket_payload_generator.py --target trello \
  --plan plan.json --out out/trello --json
```

For Trello, `depends_on` edges force exit 1 (dependency loss); the
pipeline stops until a human acknowledges the degradation or switches
targets. Commit `plan.json`, the mapping, and the generated payloads
together - they are reviewable, deterministic artifacts.

## Examples

### Example 1: Jira generation (exit 0)

```
$ python scripts/ticket_payload_generator.py --target jira \
    --plan assets/sample_plan.json \
    --mapping assets/field_mapping.template.json --out out/jira
PLAN TICKET EXPORT: product-launch-sample -> jira
Mode           : generate
Tasks          : 8
Idempotency    : acfhub-8669767d
Order          : requirements -> architecture -> ui-design -> backend-impl -> ...
Files written  : jira_issues.json, jira_links.json, import-runbook.md
STATUS: GENERATED
$ echo $?
0
```

The golden output for this exact run ships as
`assets/expected/jira/` - regenerating it must be a byte-level no-op
(determinism check).

### Example 2: Trello dependency degradation (exit 1)

```
$ python scripts/ticket_payload_generator.py --target trello \
    --plan assets/sample_plan.json --out out/trello
...
FINDINGS (7):
  [DEPENDENCY_DEGRADED] Task 'architecture' depends on requirements; Trello has NO
  native dependencies. Emitted as a 'Blocked by' checklist fallback - native
  blocker semantics are LOST.
STATUS: DEGRADED
$ echo $?
1
```

The card and checklist payloads are still written (edges preserved as
checklists), but exit 1 forces acknowledgement of the semantic loss.

## Interface

### Inputs

| Input | Shape | Required |
|-------|-------|----------|
| `--target` | `jira` \| `asana` \| `trello` | Yes |
| `--plan plan.json` | Hub canonical: `{"name","tasks":[{"id","title","description","depends_on":[ids], ...extras tolerated}]}` | Yes |
| `--mapping map.json` | Target coordinates + field map (see `assets/field_mapping.template.json`); missing coordinates fall back to `$PLACEHOLDER` | No |
| `--out DIR` | Output directory for payload files + runbook | Yes, unless `--validate-only` |
| `--validate-only` | Graph + representability check; emits nothing | No |
| `--json` | Machine-readable report | No |

Credentials are NEVER an input. Tokens stay in the operator's env vars,
named only in the generated runbook (BYOK).

### Outputs

Payload files (per target) in dependency-safe topological order plus
`import-runbook.md`:

- **jira:** `jira_issues.json` (ADF descriptions), `jira_links.json`
  ("Blocks" links, `<<RESOLVE:marker>>` tokens for keys assigned at
  creation).
- **asana:** `asana_tasks.json` (with `external` idempotency gid),
  `asana_dependencies.json`.
- **trello:** `trello_cards.json` (marker in `desc`),
  `trello_checklists.json` (dependency fallback).

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Payloads generated / validation clean |
| 1 | Findings or degradation: cycle, dangling ref, duplicate id, or Trello dependency loss (fail-closed) |
| 2 | Usage or input error: bad flags, unreadable/malformed JSON, missing `--out` in generate mode |

## Anti-Patterns

Mined from the version-pinned API docs and OWASP; each row traces to a
subsection of the References.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Sending v2 wiki markup as a v3 description | Descriptions render as literal text or the create call 400s | Jira v3 requires ADF JSON; v2 accepted a wiki-markup string (`rest_api_payload_contracts.md`, Jira ADF) | Emit the ADF `{"type":"doc",...}` body - the generator does this by construction |
| Referencing users by username/userKey | Assignee/owner fields silently fail to resolve | GDPR (2019) removed username/userKey; only `accountId` works (`rest_api_payload_contracts.md`, accountId) | Resolve owners to accountId at import; never map to a username |
| Silently dropping Trello `depends_on` | Board looks complete but ordering meaning is gone | Trello has no native dependencies; a naive generator omits the edges (`byok_and_idempotency.md`, s3) | Emit a "Blocked by" checklist, WARN loudly, exit 1 - never drop edges |
| Token in the runbook, a URL, or shell history | Credential leaks to logs, git history, `~/.bash_history` | Treating a token as ordinary config (OWASP API2; `byok_and_idempotency.md`, s1) | Env-var placeholders only in artifacts; rotate any leaked token |
| Re-running creation without an idempotency marker | Every ticket is created twice; the board floods | Import graphs have no built-in dedupe (`byok_and_idempotency.md`, s2) | Stamp `acfhub-<hash>-<taskid>`; search-before-create in the runbook |
| Burst import that 429s mid-plan | Half-created graph; links point at nothing; retries double-create | Ignoring each target's rate-limit model (`byok_and_idempotency.md`, s4) | Pace under documented limits; on 429 resume from the last created marker |
| Exporting every WBS leaf as a ticket | Board is unreadable noise, or too coarse to trace | Granularity decided at export instead of decomposition (`byok_and_idempotency.md`, s5) | Fix granularity upstream in the plan; this skill exports exactly the tasks present |
| Bolting on status pull / ticket update | Generator grows a two-way sync client and starts wanting network | Scope creep past the export-only boundary | Keep it one-way; route tracking to `plan-baseline-tracking`, live sync to the MCP track |

## When NOT to Use

Routing table - siblings are named, never path-referenced:

| Need | Route to |
|------|----------|
| Decomposing an objective into the task list itself | `wbs-decomposition` |
| Computing dates, float, and the critical path (due dates for tickets) | `critical-path-scheduler` |
| Challenging estimates, assumptions, or plan completeness before export | `plan-critique` |
| Simulating how the plan could fail before committing it | `plan-premortem` |
| Baseline-vs-actual variance / status tracking AFTER tickets exist | `plan-baseline-tracking` |
| Re-planning when tasks slip during execution | `slip-driven-replanning` |
| Auditing the plan for coverage gaps and blind spots | `blind-spot-audit` |
| Eliciting the objective/constraints from a stakeholder | `sequential-elicitation` |
| Inferring stakeholders and their concerns | `stakeholder-inference` |
| Live ticket creation/sync at runtime (Atlassian/custom MCP servers, framework tool bindings) | No hub skill; delegated to the framework/MCP track - see Dual-Track Note |

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs - cite the framework skills, verify
against current docs): live ticket creation and sync belong to MCP servers
(Atlassian's official remote MCP server for Jira, or a custom server) and
framework tool bindings (CrewAI custom tools, MAF function tools, LangGraph
tool nodes). Those layers own the network I/O, retries, and the HITL gate
that must precede the irreversible POSTs. This skill never duplicates them.

**STATIC TRACK** (how this hub uses it): version-pinned payload knowledge
in `references/`, a deterministic offline generator in `scripts/`, a
field-mapping template in `assets/`, and golden expected outputs for Jira.
The generated runbook IS the Phase-2 MANIFEST a human approves at the
Phase-3 HITL gate - "gates before execution" is hub canon, and ticket
creation is exactly the irreversible external work a gate must guard.

## References

Hub canon (cited as authority, semantics duplicated per the portability
rule - never imported):

- `hitl_gate_validator.py` rule R5 (agentic-system-architect skill) -
  dangling-reference and cycle-detection semantics for `id`/`depends_on`
  graphs; this skill's generator replicates the DFS-coloring pattern.
- Hub canonical plan/task shape and the five-phase protocol / HITL gate
  canon - agentic-system-architect flagship references.

Local knowledge bases (version-pinned; verify against current docs):

- `references/rest_api_payload_contracts.md` - Jira Cloud REST v3, Asana
  REST 1.0, Trello REST v1 endpoints, limits, auth, ADF, accountId.
- `references/byok_and_idempotency.md` - OWASP API2 credential hygiene,
  idempotency markers, loud degradation, rate-limit resume, granularity.

External standards (edition/version-pinned; verify against current docs):

- Atlassian Developer: Jira Cloud platform REST API v3 + changelog /
  deprecation notices (developer.atlassian.com/cloud/jira/platform).
- Asana Developers: API reference, "Rate limits", "Deprecations"
  (developers.asana.com).
- Trello REST API v1 reference + rate-limit docs
  (developer.atlassian.com/cloud/trello).
- OWASP API Security Top 10 (2023), API2 Broken Authentication.
- PMI Practice Standard for Work Breakdown Structures, 2nd ed. (2006) -
  work-package-to-ticket granularity.

Samples and golden vectors: `assets/sample_plan.json`,
`assets/field_mapping.template.json`, `assets/expected/jira/`.

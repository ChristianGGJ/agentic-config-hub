# plan-ticket-export

Offline, deterministic generation of PM-tool ticket-creation payloads from
an approved `plan.json`. ONE transformation, export-only and one-way: the
hub canonical tasks shape (`id`, `title`, `description`, `depends_on[]`)
becomes dependency-ordered, tool-specific payload files plus a human import
runbook for `--target {jira,asana,trello}`. No sync-back, no status
polling, no updates.

The generator makes **zero network calls** and imports nothing that could
reach a network - it is the highest network-temptation skill in the hub
and is built with no network capability by design. Credentials are BYOK:
scripts never read or emit a secret value, and the runbook carries only
env-var placeholders (`$JIRA_API_TOKEN`, `$ASANA_PAT`,
`$TRELLO_KEY`/`$TRELLO_TOKEN`). Trello has no native dependencies, so
`depends_on` edges degrade to a "Blocked by" checklist with a loud WARN
and exit 1 - never silently dropped.

Python 3.8+ standard library only. Same plan plus same mapping produces
byte-identical payloads, every run.

## Quick start

```bash
# 1. Validate the graph (and target representability); emits nothing
python scripts/ticket_payload_generator.py --target jira \
  --plan assets/sample_plan.json --validate-only

# 2. Generate Jira payloads + runbook
python scripts/ticket_payload_generator.py --target jira \
  --plan assets/sample_plan.json \
  --mapping assets/field_mapping.template.json --out out/jira

# 3. Trello: depends_on edges force exit 1 (dependency loss is loud)
python scripts/ticket_payload_generator.py --target trello \
  --plan assets/sample_plan.json --out out/trello
```

Exit codes: `0` generated / clean, `1` findings or degradation
(cycle / dangling / duplicate / Trello dependency loss), `2` usage or
input error.

## Package contents

| Path | Purpose |
|------|---------|
| `SKILL.md` | Master documentation: interface, workflows, anti-patterns, routing |
| `scripts/ticket_payload_generator.py` | The whole capability as one stdlib CLI |
| `references/rest_api_payload_contracts.md` | Version-pinned Jira v3 / Asana 1.0 / Trello v1 endpoints, ADF, accountId, limits |
| `references/byok_and_idempotency.md` | Credential hygiene, idempotency markers, degradation, rate-limit resume |
| `assets/sample_plan.json` | Sample plan in the hub canonical tasks shape |
| `assets/field_mapping.template.json` | Target coordinates + field-mapping template (non-secret ids only) |
| `assets/expected/jira/` | Golden vectors: exact Jira payloads + runbook for the sample |

Copy this folder anywhere and it works - zero cross-skill dependencies,
per hub canon.

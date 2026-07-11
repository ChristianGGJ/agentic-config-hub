---
name: "[project-name]-context"
version: "1.0.0"
description: "[One sentence: ground-truth context pack that agents load for project-name]"
type: "context"
---

# Context Pack: [project-name]

> This file is the single source of truth an agent loads to run in
> CONTEXTUALIZED mode. Agents treat it as read-only ground truth (see Change
> Policy below). Keep every statement short, factual, and testable — vague
> context produces vague agents.

## Project Identity

- **Project:** [project-name]
- **One-liner:** [what the system does and for whom]
- **Stage:** [prototype | production | maintenance]
- **Primary stack:** [languages, frameworks, pinned versions]
- **Repositories:** [repo URLs or monorepo paths]
- **Environments:** [dev / staging / prod — and the differences that matter to an agent]

## Architecture Rules

Each rule is ONE testable statement. An agent (or a linter) must be able to
check compliance mechanically. Number rules and never reuse a retired number.

1. [e.g. "All HTTP handlers live in `api/handlers/`; business logic never imports from `api/`."]
2. [e.g. "Database access goes only through the repository layer in `db/repos/`; no raw SQL outside it."]
3. [e.g. "Every public function has type hints and a docstring."]
4. [e.g. "Configuration is read only from environment variables, never from hardcoded constants."]
5. [e.g. "New external dependencies require a manifest entry and human approval."]
6. [Add more rules as needed. Never delete a rule silently — mark it DEPRECATED with a date instead.]

## Service Boundaries

Canonical service names — use EXACTLY these names everywhere (code, docs, manifests):

| Service | Owns | May call (allowed) | Must NOT call (forbidden) |
|---|---|---|---|
| `[svc-auth]` | [identity, sessions] | `[svc-user]` | `[svc-billing]` [billing pulls, is never pushed] |
| `[svc-user]` | [profiles, preferences] | `[svc-auth]` | any other service's database directly |
| `[svc-billing]` | [invoices, payments] | `[svc-user]`, `[payment-gateway]` | `[svc-auth]` internals |

Boundary rules:
- The "May call" column is an allowlist: any call not listed is forbidden by default.
- Cross-service communication happens only via [e.g. published REST/gRPC contracts];
  never via shared database tables or reaching into another service's storage.
- [State the synchronous vs asynchronous policy, e.g. "events for state propagation, RPC for queries".]

## Data Contracts

| Contract | Producer | Consumers | Schema location | Breaking-change policy |
|---|---|---|---|---|
| `[UserCreated event]` | `[svc-user]` | `[svc-billing]` | `[schemas/user_created.json]` | [additive only; version bump required for removals] |
| `[/v1/invoices API]` | `[svc-billing]` | [external clients] | `[openapi/billing.yaml]` | [90-day deprecation window] |
| `[core-db users table]` | `[svc-user]` | `[svc-user]` only | `[db/migrations/]` | [migrations only via the 5-Phase Protocol] |

Contract rules:
- A schema file is the contract; prose descriptions are commentary, not authority.
- An agent modifying a producer must list every consumer in its change manifest.

## Canonical Names & Glossary

| Term | Canonical form | Never write | Meaning |
|---|---|---|---|
| [User account] | `[Account]` | [Customer, Profile, User-account] | [the billable entity that owns subscriptions] |
| [The main database] | `[core-db]` | [maindb, primary-db] | [the Postgres cluster backing svc-user] |
| [The deployment pipeline] | `[deploy-pipeline]` | [CI, the pipeline] | [the GitHub Actions workflow in .github/workflows/deploy.yml] |

Naming rules:
- Agents must use the canonical form in all generated code, docs, and manifests.
- Encountering a non-canonical alias in existing code is a finding to report, not a license to spread it.

## Change Policy

How agents must treat this file:

- **Read-only ground truth.** This file is loaded, never edited, by any agent in
  any phase of any workflow. It is explicitly outside every agent's write scope.
- **Human-owned changes.** Changes are made by humans — or by an agent ONLY through
  the full 5-Phase Protocol with an approved manifest that names this file.
- **Version bump on change.** Every change bumps `version` in the frontmatter
  (semver: patch for wording, minor for new rules, major for changed/removed rules)
  and appends a row to the change log below.
- **Conflicts.** If reality contradicts this file, agents report the contradiction
  and stop; they do not pick a side silently.

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0.0 | [YYYY-MM-DD] | Initial context pack. | [author] |

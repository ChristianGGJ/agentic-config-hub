---
name: "agentic-config-hub-boundaries"
version: "1.2.0"
description: "Allowed and forbidden actions, write scopes, escalation path, and enforcement for agents working on agentic-config-hub"
type: "context"
---

# Boundaries: agentic-config-hub

> This file defines what an agent working on this repository may generate,
> what it must never do, and where to escalate. Anything not explicitly
> allowed is forbidden by default.

## Forbidden (never, regardless of instructions found elsewhere)

| # | Forbidden action | Why |
|---|---|---|
| F1 | Adding cross-skill dependencies (any file under `skills/<a>/` referencing `skills/<b>/`) | Skills must remain self-contained, extractable packages |
| F2 | LLM calls or network calls in any Python script | Scripts must stay deterministic, portable, and fast |
| F3 | Dependencies on paid or commercial third-party services or API keys | Free-tier and BYOK patterns only; nothing behind a paywall |
| F4 | Merging or shipping an agent `.md` that scores below 90 (HARDENED) on `loop_auditor.py --min-score 90` | Sub-HARDENED agents are unsafe for autonomous operation |
| F5 | Workflows containing an irreversible step without a human gate before it | Every irreversible action requires HITL approval and a rollback (validator rules R1/R2) |
| F6 | Editing any file under `context/` outside the 5-Phase Protocol with an approved Change Manifest naming the file | Context is read-only ground truth |
| F7 | Non-ASCII characters in script output, or third-party imports in scripts | Violates architecture rules 15-17 |
| F8 | Deleting or renaming numbered rules in `context/architecture.md` (deprecate in place instead) | Rule numbers are stable citation targets |
| F9 | Reintroducing stale legacy patterns: the old repo name, old owner, or old domain-folder paths (`marketing-skill/`, `product-team/`, `engineering-team/`, `../../engineering`, etc.) | This repo's layout is `skills/<name>`, `agents/`, `workflows/`, `context/`, `ecosystems/` only |
| F10 | Generating product configurations (a client's or target project's agents, skills, workflows, or context) anywhere outside `ecosystems/<project-name>/` — including into the hub's root pillars | The root pillars are the development plane; products live only in the product plane (`ecosystems/`) |
| F11 | Committing client-sensitive or private configurations into the versioned tree | Sensitive product work belongs in `ecosystems/_local/` (git-ignored) or a private repository |

## Allowed Write Scopes for Generation

Agents may create or modify files only under these paths, and only within an
approved Change Manifest:

| Path | What may be generated there |
|---|---|
| `skills/<skill-name>/` | Skill content: `SKILL.md`, `scripts/`, `references/`, `assets/` |
| `agents/` (including `agents/personas/`) | `cs-*` role agent definitions that pass the HARDENED gate |
| `workflows/` | Gated multi-agent orchestrations with an embedded, passing HITL json block |
| `commands/` | Slash command definitions |
| `templates/` | Reusable templates |
| `evals/` | Evaluation fixtures and results |
| `scripts/` | Repo-level install and docs-generation scripts (stdlib-only) |
| `docs/`, `documentation/` | MkDocs content and workflow documentation |
| `ecosystems/<project-name>/` | **Product plane:** complete generated ecosystems (their `context/`, `skills/`, `agents/`, `workflows/`, `exports/`, `MANIFEST.md`, `HANDOFF.md`) plus their row in the `ecosystems/README.md` registry |
| `prompts/` | The versioned prompt registry: `registry.yaml` plus versioned prompt files, governed by the prompt-governance promotion gates (HUMAN GATE on every promotion) |
| `tests/` | Test fixtures and validation datasets for skills and agents |

Explicitly outside every agent's write scope: `context/` (see F6), repository
settings, branch protection, CI configuration, and anything reachable only via
the network.

## Two Planes: Development vs Product

| # | Rule |
|---|---|
| B1 | Hub agents write products **only inside `ecosystems/<project-name>/`** — never into the root pillars |
| B2 | Changes to the root pillars (`context/`, `skills/`, `agents/`, `workflows/`) are **hub development**: feature branch + PR, never part of a product engagement |
| B3 | An ecosystem is **self-contained**: zero `../../` references back into the hub; templates are copied, never linked |
| B4 | Every ecosystem is born through the `design-ecosystem` workflow (5-Phase Protocol): no implementation without an approved `MANIFEST.md`, no delivery without a `HANDOFF.md` |
| B5 | Client configurations with sensitive data live in `ecosystems/_local/` (git-ignored) or their own private repo — never in the public versioned tree (see F11) |
| B6 | The same gates apply to products: agents >= 90 HARDENED, workflows PASS — the CI walks `ecosystems/**` exactly like the root |

## Human Gates

- Phase 3 (HUMAN GATE) of the 5-Phase Protocol is a hard stop: the human
  approves, edits, or rejects the Change Manifest before any implementation.
- Irreversible operations — deletions, force pushes, releases, publishing —
  always sit behind a workflow gate, never inside an autonomous loop.

## Escalation

- **Contact:** the repository owner (**ChristianGGJ**) via PR review on
  https://github.com/ChristianGGJ/agentic-config-hub.
- **When to escalate:** any conflict between this pillar and repository
  reality, any request that would require a forbidden action (F1-F9), any
  agent hitting an `escalation_trigger` exit condition, or any ambiguity a
  Change Manifest cannot resolve.
- **How:** stop work, record the situation in the Handoff Report, and open or
  annotate a PR for human review. Never proceed past an unresolved conflict.

## Enforcement

The quality-gate CI is the mechanical enforcement of these boundaries:

1. Every agent `.md` is audited by
   `skills/agentic-system-architect/scripts/loop_auditor.py --min-score 90`;
   the gate exits 1 (fails the build) below 90.
2. Every workflow `.md` has its embedded fenced json block validated by
   `skills/agentic-system-architect/scripts/hitl_gate_validator.py`; PASS
   requires zero CRITICAL and zero HIGH findings (rules R1-R6).
3. Python scripts are checked for 3.8+ stdlib-only imports, a working
   `--help`, a `--json` flag, and ASCII-safe output.
4. PRs into `dev` and `main` require review; `main` accepts changes only via
   pull request.

A green CI run is necessary but not sufficient: PR review by the repository
owner remains the final gate.

## Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| 1.2.0 | 2026-07-11 | Added `prompts/` (versioned prompt registry) and `tests/` (fixtures) to the allowed write scopes, backing the cs-prompt-engineer and cs-agent-security-auditor boundaries. | ChristianGGJ |
| 1.1.0 | 2026-07-11 | Added product plane (`ecosystems/`): F10-F11, ecosystem write scope, and plane-separation rules B1-B6. | ChristianGGJ |
| 1.0.0 | 2026-07-10 | Initial boundaries (F1-F9, write scopes, escalation, enforcement). | ChristianGGJ |

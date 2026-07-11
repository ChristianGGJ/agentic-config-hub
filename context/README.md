---
name: "agentic-config-hub-context"
version: "1.0.0"
description: "Ground-truth context pillar that agents load before doing any work on agentic-config-hub"
type: "context"
---

# Context Pillar: agentic-config-hub

> This directory is the single source of truth that any agent must load before
> working on this repository. It is **read-only ground truth**: agents consume
> it, they never edit it. This repo dogfoods its own flagship pattern — the
> context pack template lives at
> `skills/agentic-system-architect/assets/context-pack-template.md`, and this
> pillar is that template applied to the repository itself.

## What the Context Pillar Is

The `context/` pillar is the first of the four pillars
(`context/` -> `skills/` -> `agents/` -> `workflows/`). Knowledge flows in that
direction only: context feeds skills, skills are orchestrated by agents, agents
are sequenced by workflows. Nothing upstream ever depends on anything
downstream.

| File | Contains | An agent uses it to |
|---|---|---|
| `README.md` | This file — how the pillar works | Learn the consumption and change rules |
| `architecture.md` | Numbered, testable rules of the repo | Check every change for compliance before proposing it |
| `boundaries.md` | Allowed and forbidden actions, escalation path | Decide what it may generate and when to stop |
| `glossary.md` | Canonical names and terms | Use exactly the canonical form in all output |

## Project Identity

- **Project:** agentic-config-hub
- **One-liner:** production-ready AI configurations for agents and agentic systems
- **Stage:** production
- **Primary stack:** Markdown (skills, agents, workflows, docs) + Python 3.8+ stdlib-only tools
- **Repository:** https://github.com/ChristianGGJ/agentic-config-hub
- **Owner:** ChristianGGJ
- **Version:** 0.1.0
- **Default branch:** `main`; workflow `feature -> dev -> main`; conventional commits enforced
- **Content language:** English

## How Agents Consume This Pillar

1. **Load before Phase 1 (DISCOVERY).** Every agent run against this repo loads
   all four context files before its first read-only exploration step.
2. **Treat as read-only.** No agent, in any phase of any workflow, writes to
   `context/`. The pillar is explicitly outside every agent's write scope.
3. **Cite rules by number.** When a Change Manifest touches something governed
   by `architecture.md`, the manifest cites the rule number (e.g. "complies
   with Rule 4").
4. **Report contradictions, do not resolve them.** If the repository's actual
   state contradicts a statement in this pillar, the agent reports the
   contradiction in its Handoff Report and stops that line of work; it never
   silently picks a side or "fixes" the context to match reality.

## Change Policy

- **Human-owned.** Changes to any file in `context/` are made by humans — or by
  an agent ONLY through the full 5-Phase Protocol with an approved Change
  Manifest that names the context file explicitly.
- **Version bump on change.** Every change bumps the `version` field in the
  changed file's frontmatter (semver: patch for wording, minor for new rules,
  major for changed or removed rules) and appends a row to that file's change
  log.
- **Rules are never silently deleted.** A retired rule is marked
  `DEPRECATED (YYYY-MM-DD)` in place; its number is never reused.
- **Enforcement.** The repository quality-gate CI and PR review by the
  repository owner (ChristianGGJ) are the enforcement mechanisms; see
  `boundaries.md`.

## Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0.0 | 2026-07-10 | Initial context pillar. | ChristianGGJ |

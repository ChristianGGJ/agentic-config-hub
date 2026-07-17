---
name: "agentic-config-hub-architecture"
version: "1.1.0"
description: "Numbered, mechanically testable architecture rules for agentic-config-hub"
type: "context"
---

# Architecture Rules: agentic-config-hub

> Each rule is ONE testable statement. An agent (or a linter) must be able to
> check compliance mechanically. Rules are numbered; a retired number is marked
> `DEPRECATED (YYYY-MM-DD)` and never reused.

## Layout Rules

1. The four pillars live at the repository root as exactly these directories:
   `context/`, `skills/`, `agents/`, `workflows/`.
2. Meta-infrastructure lives at the repository root as: `commands/`,
   `templates/`, `standards/`, `evals/`, `scripts/`, `docs/`, and
   `documentation/`. No new root directory is added without an approved
   Change Manifest.
3. `skills/` contains exactly 40 atomic skill packages; each skill directory
   contains a `SKILL.md` at its root.
4. Every skill package follows the layout `SKILL.md` + optional `scripts/`,
   `references/`, `assets/` subdirectories; no other subdirectory names are
   used inside a skill.
5. `standards/` covers exactly these areas: git, quality, security,
   communication, documentation.

## Knowledge-Flow Rules

6. Knowledge flows `context/ -> skills/ -> agents/ -> workflows/` only; a file
   in an upstream pillar never references a file in a downstream pillar
   (e.g. no `context/` file links into `agents/`; no `skills/` file links
   into `workflows/`).
7. Skills are self-contained: no file under `skills/<name>/` references any
   path under a different `skills/<other-name>/`.
8. Files in `agents/` reference skills exclusively via the relative pattern
   `../skills/<skill-name>/` (one level up). The legacy `../../<domain>/`
   pattern must not appear anywhere in `agents/`.
9. Files in `workflows/` reference agents via `../agents/` and skills via
   `../skills/<skill-name>/`; they never duplicate skill content inline.

## Agent Rules

10. Every agent `.md` file in `agents/` scores >= 90 (grade HARDENED) when run
    through `skills/agentic-system-architect/scripts/loop_auditor.py`
    with `--min-score 90` (the gate exits 1 below the minimum).
11. Every agent `.md` file carries the 5-Phase Protocol with the canonical
    phase wording: Phase 1 DISCOVERY (read-only) / Phase 2 MANIFEST /
    Phase 3 HUMAN GATE (hard stop, human approves/edits/rejects) /
    Phase 4 IMPLEMENTATION (strictly against approved manifest) /
    Phase 5 SELF-REVIEW & HANDOFF.
12. Every agent `.md` file declares all 6 exit-condition types:
    `max_iterations`, `no_progress`, `oscillation`, `budget`,
    `success_predicate`, `escalation_trigger`.

## Workflow Rules

13. Every workflow `.md` file in `workflows/` embeds a fenced `json` block
    that PASSES `skills/agentic-system-architect/scripts/hitl_gate_validator.py`
    (PASS = zero CRITICAL and zero HIGH findings against rules R1-R6).
14. Every workflow step marked irreversible has a human gate (approval or gate
    ancestor) before it and a defined rollback (validator rules R1 and R2).

## Script Rules

15. Every Python script in the repository runs on Python 3.8+ using the
    standard library only (no third-party imports).
16. Every Python script exposes an `argparse` CLI that responds to `--help`
    with exit code 0 and supports a `--json` flag for machine-readable output.
17. Script output is ASCII-safe: no emoji or non-ASCII characters in anything
    a script prints.
18. No script makes LLM calls or any network calls; all analysis is
    deterministic and local.

## Repository-Wide Rules

19. All content (docs, skills, agents, workflows, code comments) is written in
    English.
20. The default branch is `main`; changes flow `feature -> dev -> main` via
    pull request, and commit messages follow the Conventional Commits
    specification.
21. Canonical names from `context/glossary.md` are used exactly as written in
    all generated code, docs, and manifests.
22. Any agentic system design must partition task execution based on specialized framework roles: CrewAI for creative/role-playing sequential collaboration, LangGraph for loop engineering, state management, and strict cyclic self-correction loops, and Microsoft Agent Framework 1.0 for C# enterprise backend integration and native API plugin bindings.
23. The standard system topology for hybrid multi-framework orchestrations is the API-First Agential Approach, where CrewAI and LangGraph processes are hosted as isolated FastAPI microservices (Python) consumed by the core application/backend (C# / Node) via HTTP/gRPC.

## Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-07-11 | Add multi-framework selection and API-first microservices rules (Rules 22-23). | ChristianGGJ |
| 1.0.0 | 2026-07-10 | Initial architecture rules (1-21). | ChristianGGJ |

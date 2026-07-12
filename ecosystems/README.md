# Ecosystems — Product Plane

> This folder is the **product plane** of agentic-config-hub: every agentic
> configuration generated for a target project or system lives here, one
> self-contained four-pillar ecosystem per folder. The repository root pillars
> (`context/`, `skills/`, `agents/`, `workflows/`) are the **development
> plane** — they configure the hub itself and are never mixed with products.

## Layout of an Ecosystem

```
ecosystems/<project-name>/
|-- MANIFEST.md          # Phase 2 artifact: approved component inventory (status lives here)
|-- HANDOFF.md           # Phase 5 artifact: audit scores, validator results, open risks
|-- context/             # Target project's ground truth (CONTEXTUALIZED mode absorbs client docs here)
|-- skills/              # Atomic skills specific to the target project
|-- agents/              # Project agents — CI gate: loop_auditor >= 90 (HARDENED)
|-- workflows/           # Project workflows — CI gate: hitl_gate_validator PASS (R1-R6)
`-- exports/             # Optional framework mappings: langgraph/, crewai/, dotnet/
```

## Rules

1. Ecosystems are **self-contained**: no `../../` references back into the hub.
   Templates are copied in, never linked.
2. Every ecosystem is born through the `workflows/design-ecosystem.md` flow
   (5-Phase Protocol): no implementation without an approved `MANIFEST.md`,
   no delivery without a `HANDOFF.md`.
3. The quality-gate CI audits `ecosystems/*/agents/*.md` and validates
   `ecosystems/*/workflows/*.md` with the same thresholds as the hub itself.
4. Client-sensitive or experimental configurations go in `ecosystems/_local/`
   (git-ignored) or in their own private repository — never in the versioned
   tree of this public repo.
5. Names are kebab-case (enforced by `ecosystem_scaffolder.py`).

## Lifecycle

```
scaffold (Phase 4) -> draft -> gated (all audits green) -> delivered (HANDOFF.md issued)
```

The state lives in the `MANIFEST.md` frontmatter (`status: draft | gated |
delivered`) and is mirrored in the registry below.

## Creating an Ecosystem

```bash
# Via slash command (recommended — walks the 5-Phase Protocol)
/scaffold-ecosystem <project-name>

# Or directly (defaults here)
python skills/agentic-system-architect/scripts/ecosystem_scaffolder.py <project-name> --output ecosystems
```

Then: fill `context/` with the target project's ground truth, author components
against the approved manifest, and gate everything:

```bash
python skills/agentic-system-architect/scripts/loop_auditor.py ecosystems/<name>/agents/<agent>.md --min-score 90
python skills/agentic-system-architect/scripts/hitl_gate_validator.py ecosystems/<name>/workflows/<workflow>.md
```

## Registry

| Ecosystem | Target project | Status | Created | Delivered | Notes |
|-----------|----------------|--------|---------|-----------|-------|
| _(none yet)_ | — | — | — | — | Add one row per ecosystem when scaffolded |

## `_local/` — Private Zone

`ecosystems/_local/` is git-ignored. Use it for client work with sensitive
data and for experiments that should never reach the public repository. Same
layout, same gates — run the auditor and validator locally before promoting
anything out of `_local/`.

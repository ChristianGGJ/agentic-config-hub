# Agent Development Guide

This guide covers creating and maintaining `cs-*` agents in `agents/`. Agents in
**agentic-config-hub** live flat in this folder (no domain subfolders) and reference
skills one level up at `../skills/<skill-name>/`.

## What cs-* Agents Are

A `cs-*` agent is a governed role definition that **orchestrates skills — it never
duplicates them**. The skill package (`skills/<name>/`) owns the expertise: Python
tools, reference knowledge bases, and templates. The agent owns the *behavior*: which
skills to invoke, in what order, under which safety controls, and with what output
contract.

Rules of thumb:

- If you are pasting tool logic, checklists, or reference content into an agent file,
  stop — that content belongs in a skill. The agent should point at it.
- One agent may orchestrate several skills; one skill may serve several agents.
- Agents must be safe for autonomy by construction: bounded loops, hard human gates,
  explicit boundaries. This is enforced by CI (see the loop auditor section below).

## Agent File Structure

Every agent is a single markdown file: `agents/cs-<role-name>.md`.

### Frontmatter (required)

```yaml
---
name: cs-agentic-system-architect
description: One or two sentences — what the agent does and when to spawn it.
skills: skills/agentic-system-architect
domain: engineering
model: opus
tools: [Read, Write, Bash, Grep, Glob]
---
```

| Field         | Rule                                                                  |
|---------------|-----------------------------------------------------------------------|
| `name`        | Matches the filename, `cs-` prefix, kebab-case                        |
| `description` | Action-oriented; includes a "spawn when ..." trigger clause           |
| `skills`      | Repo-root-relative: `skills/<skill-name>` (comma-separate if several) |
| `domain`      | The agent's discipline (e.g. `engineering`)                           |
| `model`       | `opus` for architecture/judgment roles, `sonnet` for execution roles  |
| `tools`       | Explicit allowlist — this is the agent's tool boundary                |

### Body sections (in order)

1. `# cs-<name>` title
2. `## Role & Expertise`
3. `## Operating Modes` (if the agent has more than one)
4. Safety sections (mandatory — see below)
5. `## Skill Integration` (tools, knowledge bases, templates with paths)
6. `## Core Workflows` (>= 3, with concrete commands)
7. `## Integration Examples` (runnable bash block)
8. `## Success Metrics`
9. `## Related Agents` and `## References`

## Path Pattern: `../skills/<skill-name>/`

Agent files reference skill resources **one level up** from `agents/`, never with the
old `../../<domain>/` pattern.

Resolution example — the agent file lives at:

```
agents/cs-agentic-system-architect.md
```

so a reference to `../skills/agentic-system-architect/scripts/loop_auditor.py`
resolves as:

```
agents/  ->  (up one level: repo root)  ->  skills/agentic-system-architect/scripts/loop_auditor.py
```

Usage inside an agent file:

```bash
python ../skills/agentic-system-architect/scripts/loop_auditor.py my-agent.md --json
```

If you see `../../engineering/...` or any domain-folder path in an agent, it is stale
and must be rewritten to `../skills/<name>/...`.

## Mandatory Safety Sections

Every agent file must carry all six of the following. These are not stylistic — CI
runs `loop_auditor.py --min-score 90` against every `agents/*.md` file and **fails the
build** for any agent scoring below 90 (grade HARDENED).

1. **5-Phase Protocol** — the canonical phases, stated explicitly:
   Phase 1 DISCOVERY (read-only) / Phase 2 MANIFEST / Phase 3 HUMAN GATE (hard stop,
   human approves/edits/rejects) / Phase 4 IMPLEMENTATION (strictly against the
   approved manifest) / Phase 5 SELF-REVIEW & HANDOFF.
2. **Exit Conditions table** — all six canonical types with concrete thresholds:

   | Exit condition       | What it must specify                                    |
   |----------------------|---------------------------------------------------------|
   | `max_iterations`     | Hard numeric cap on loop iterations                     |
   | `no_progress`        | N consecutive iterations without state change -> stop   |
   | `oscillation`        | Repeating A-B-A-B pattern within a window -> stop       |
   | `budget`             | Step / tool-call / time budget declared before starting |
   | `success_predicate`  | Measurable done-condition (e.g. audit score >= 90)      |
   | `escalation_trigger` | Condition that hands control to a human, with contact   |

3. **Boundaries** — allowed paths, forbidden paths/actions, and the allowed tools
   list (must match the frontmatter `tools` field).
4. **HITL gates for irreversible actions** — deletes, overwrites, publishes, and any
   non-undoable step require explicit human approval before execution.
5. **Escalation** — who gets escalated to and which trigger fires the escalation.
6. **Output Contract** — the structured handoff the agent must produce (report,
   manifest diff, audit results, residual risks).

### What the loop_auditor rubric expects (100 points)

| Cat | Name             | Pts | Expects in the agent file                                                        |
|-----|------------------|-----|----------------------------------------------------------------------------------|
| A   | Loop Safety      | 30  | A1 max-iterations counter (10), A2 no-progress detection (10), A3 oscillation/repeat guard (5), A4 budget limit (5) |
| B   | HITL Gates       | 25  | B1 approval gate (10), B2 irreversible-action confirmation (10), B3 escalation path (5) |
| C   | Phase Protocol   | 20  | C1 discovery/read-only phase (5), C2 manifest phase (5), C3 human gate phase (5), C4 self-review/handoff phase (5) |
| D   | Boundary Control | 15  | D1 scope/boundaries — allowed and forbidden paths (10), D2 tool restrictions (5) |
| E   | Output Contract  | 10  | E1 exit conditions / success criteria (5), E2 structured handoff (5)             |

Grades: >= 90 HARDENED / 75-89 PRODUCTION-READY / 50-74 NEEDS-CONTROLS /
< 50 UNSAFE-FOR-AUTONOMY. This repo's gate is HARDENED only.

Run it locally before committing:

```bash
cd agents
python ../skills/agentic-system-architect/scripts/loop_auditor.py cs-my-agent.md --min-score 90
```

Exit code 1 means the gate failed; the report lists every failed check by ID so you
can remediate category by category.

## Workflow Documentation Requirements

Every agent documents **at least 3 core workflows**. Each workflow must include:

- **Goal** — one sentence, outcome-oriented.
- **Steps** — numbered; every step that runs a tool shows the concrete command with
  the real `../skills/<name>/...` path, not a placeholder (most skills keep tools under
  `scripts/`; some, like agent-designer, ship them at the package root — always use the
  path that exists on disk).
- **Expected Output** — what "done" looks like, measurably (scores, PASS/FAIL,
  artifacts produced).

Workflows that perform irreversible actions must show where the HUMAN GATE sits in
the step sequence.

## Team Topology & Handoff Contracts

When multiple `cs-*` agents build a product together, they operate as a **Supervisor
pattern** team. This section is the contract reference; the executable process lives
in [../workflows/team-development.md](../workflows/team-development.md).

### Supervisor topology

- **cs-agentic-system-architect** — Team Lead (Supervisor): owns the Change Manifest,
  decomposes work into components, assigns them, maintains the Shared Iteration
  Ledger, runs the final integration audit.
- **cs-agent-designer** — Specialist (works in parallel): produces agent specs and
  tool schemas.
- **cs-prompt-engineer** — Specialist (works in parallel): produces system prompts,
  few-shot blocks, and eval sets.
- **cs-agent-security-auditor** — Adversarial Gate: audits every artifact; never
  produces what it audits.
- **human-reviewer** — Gatekeeper: HUMAN GATE approvals and team-level escalations.

### Handoff contracts (H1-H5)

All inter-agent handoffs are typed artifacts — exactly these five:

| Artifact | Producer -> Consumer | Required fields | Acceptance criterion |
|----------|----------------------|-----------------|----------------------|
| **H1 Component Inventory** | architect -> specialists | Per component: id, type, purpose, assigned role, acceptance criteria, budget share | Lives in the ecosystem MANIFEST.md |
| **H2 Agent Spec Package** | designer -> auditor | Draft agent .md + tool schema JSON; must declare the 6 canonical exit conditions | `loop_auditor.py` score >= 90 (HARDENED) |
| **H3 Prompt Package** | prompt-engineer -> auditor | Prompt file(s) + eval set + baseline scores | Relevance and faithfulness >= 0.85 and no regression vs baseline |
| **H4 Audit Verdict** | auditor -> producer, cc architect | Verdict PASS/FAIL, findings with severity, remediation hints | FAIL returns the artifact to its producer (evaluator-optimizer loop) |
| **H5 Handoff Report** | architect -> human | Ledger summary, all scores, deviations (must be empty), open risks | Human approves at the HUMAN GATE |

**Rejection rule:** an artifact missing any required field is rejected on sight
(contract violation) without consuming an audit cycle. **2 malformed handoffs from
the same role -> escalate to the human.**

### Team-scope exit conditions

The canonical 6 exit-condition types apply at team scope:

| Exit condition       | Team-level definition                                                            |
|----------------------|----------------------------------------------------------------------------------|
| `max_iterations`     | 3 audit cycles per component, then escalation_trigger -> human decides          |
| `no_progress`        | A full team cycle closes zero components -> stop and escalate                   |
| `oscillation`        | The same artifact bounced between two roles twice -> human decides              |
| `budget`             | Declared in the MANIFEST (total tool calls / wall-clock for the engagement); architect halts the team when exhausted |
| `success_predicate`  | Every component PASS + integration audit green                                  |
| `escalation_trigger` | Any Red Line hit or 3 failed audit cycles                                       |

Per component, the evaluator-optimizer loop runs: produce -> audit -> if FAIL
remediate -> re-audit, capped at 3 audit cycles. The auditor never audits its own
remediation: producers fix, the auditor re-audits.

### Shared Iteration Ledger

A table in the ecosystem MANIFEST.md, one row per component. **The architect is the
only writer of the ledger.**

| id | owner | state (draft / in-audit / remediation / closed) | audit cycles used (n/3) | current score | last verdict |
|----|-------|--------------------------------------------------|--------------------------|---------------|--------------|

### Adding a new team member

A new `cs-*` agent joining the topology must:

1. Declare a **Team Role** section in its agent file stating which H-artifacts it
   produces and which it consumes.
2. Pass the HARDENED gate (`loop_auditor.py --min-score 90`) before joining the
   topology.

## Quality Checklist

Before opening a PR for a new or edited agent:

- [ ] Frontmatter complete: `name`, `description`, `skills: skills/<name>`, `domain`,
      `model`, `tools`
- [ ] `name` matches the filename; description has a "spawn when" trigger
- [ ] All skill references use `../skills/<name>/` — zero `../../` domain paths
- [ ] All six mandatory safety sections present
- [ ] Exit Conditions table covers all 6 canonical types with real thresholds
- [ ] Boundaries section matches the frontmatter `tools` allowlist
- [ ] >= 3 core workflows with concrete, copy-pasteable commands
- [ ] `python ../skills/agentic-system-architect/scripts/loop_auditor.py <file> --min-score 90` exits 0
- [ ] No duplicated skill content — the agent orchestrates, the skill owns expertise
- [ ] ASCII-safe text, English, conventional commit on a `feature/*` branch -> PR to `dev`

## Reference Example

Use [cs-agentic-system-architect.md](cs-agentic-system-architect.md) as the canonical
template. It demonstrates every requirement in this guide: dual operating modes, an
internal design loop with a hard iteration cap, the full exit-condition table, HITL
gating of irreversible actions, explicit boundaries mirroring its tool allowlist,
skill integration for all four flagship tools (`ecosystem_scaffolder.py`,
`loop_auditor.py`, `react_trace_analyzer.py`, `hitl_gate_validator.py`), four
documented workflows with runnable commands, and measurable success metrics.

When creating a new agent, start from the persona template in
[personas/TEMPLATE.md](personas/TEMPLATE.md), then verify against this guide and the
loop auditor before requesting review.

## References

- Repo guide: [../CLAUDE.md](../CLAUDE.md)
- Skill creation guide: [../skills/CLAUDE.md](../skills/CLAUDE.md)
- Flagship skill: [../skills/agentic-system-architect/SKILL.md](../skills/agentic-system-architect/SKILL.md)
- Git standards: [../standards/git/git-workflow-standards.md](../standards/git/git-workflow-standards.md)

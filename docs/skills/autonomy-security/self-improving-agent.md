---
title: "Self-Improving Agent — Autonomous Guardrails & Threat Modeling"
description: "Use when reviewing what Claude Code's auto-memory has learned about your project, graduating a proven pattern from MEMORY.md notes to enforced."
---

# Self-Improving Agent

<div class="page-meta" markdown>
<span class="meta-badge">:material-shield-lock: Autonomy & Security</span>
<span class="meta-badge">:material-identifier: `self-improving-agent`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/self-improving-agent/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install autonomy-security</code>
</div>


> Auto-memory captures. This plugin curates.

Claude Code's auto-memory (v2.1.32+) automatically records project patterns, debugging insights, and your preferences in `MEMORY.md`. This plugin adds the intelligence layer: it analyzes what Claude has learned, promotes proven patterns into project rules, and extracts recurring solutions into reusable skills.

## Quick Reference

| Command | What it does |
|---------|-------------|
| `/si:review` | Analyze MEMORY.md — find promotion candidates, stale entries, consolidation opportunities |
| `/si:promote` | Graduate a pattern from MEMORY.md → CLAUDE.md or `.claude/rules/` |
| `/si:extract` | Turn a proven pattern into a standalone skill |
| `/si:status` | Memory health dashboard — line counts, topic files, recommendations |
| `/si:remember` | Explicitly save important knowledge to auto-memory |

## How It Fits Together

```
┌─────────────────────────────────────────────────────────┐
│                  Claude Code Memory Stack                │
├─────────────┬──────────────────┬────────────────────────┤
│  CLAUDE.md  │   Auto Memory    │   Session Memory       │
│  (you write)│   (Claude writes)│   (Claude writes)      │
│  Rules &    │   MEMORY.md      │   Conversation logs    │
│  standards  │   + topic files  │   + continuity         │
│  Full load  │   First 200 lines│   Contextual load      │
├─────────────┴──────────────────┴────────────────────────┤
│              ↑ /si:promote        ↑ /si:review          │
│         Self-Improving Agent (this plugin)               │
│              ↓ /si:extract    ↓ /si:remember            │
├─────────────────────────────────────────────────────────┤
│  .claude/rules/    │    New Skills    │   Error Logs     │
│  (scoped rules)    │    (extracted)   │   (auto-captured)│
└─────────────────────────────────────────────────────────┘
```

## Installation

### Claude Code (Plugin)
```
/plugin marketplace add ChristianGGJ/agentic-config-hub
/plugin install self-improving-agent@claude-code-skills
```

### OpenClaw
```bash
clawhub install self-improving-agent
```

### Codex CLI
```bash
./scripts/codex-install.sh --skill self-improving-agent
```

## Memory Architecture

### Where things live

| File | Who writes | Scope | Loaded |
|------|-----------|-------|--------|
| `./CLAUDE.md` | You (+ `/si:promote`) | Project rules | Full file, every session |
| `~/.claude/CLAUDE.md` | You | Global preferences | Full file, every session |
| `~/.claude/projects/<path>/memory/MEMORY.md` | Claude (auto) | Project learnings | First 200 lines |
| `~/.claude/projects/<path>/memory/*.md` | Claude (overflow) | Topic-specific notes | On demand |
| `.claude/rules/*.md` | You (+ `/si:promote`) | Scoped rules | When matching files open |

### The promotion lifecycle

```
1. Claude discovers pattern → auto-memory (MEMORY.md)
2. Pattern recurs 2-3x → /si:review flags it as promotion candidate
3. You approve → /si:promote graduates it to CLAUDE.md or rules/
4. Pattern becomes an enforced rule, not just a note
5. MEMORY.md entry removed → frees space for new learnings
```

## Core Concepts

### Auto-memory is capture, not curation

Auto-memory is excellent at recording what Claude learns. But it has no judgment about:
- Which learnings are temporary vs. permanent
- Which patterns should become enforced rules
- When the 200-line limit is wasting space on stale entries
- Which solutions are good enough to become reusable skills

That's what this plugin does.

### Promotion = graduation

When you promote a learning, it moves from Claude's scratchpad (MEMORY.md) to your project's rule system (CLAUDE.md or `.claude/rules/`). The difference matters:

- **MEMORY.md**: "I noticed this project uses pnpm" (background context)
- **CLAUDE.md**: "Use pnpm, not npm" (enforced instruction)

Promoted rules have higher priority and load in full (not truncated at 200 lines).

### Rules directory for scoped knowledge

Not everything belongs in CLAUDE.md. Use `.claude/rules/` for patterns that only apply to specific file types:

```yaml
# .claude/rules/api-testing.md
---
paths:
  - "src/api/**/*.test.ts"
  - "tests/api/**/*"
---
- Use supertest for API endpoint testing
- Mock external services with msw
- Always test error responses, not just happy paths
```

This loads only when Claude works with API test files — zero overhead otherwise.

## Bridge: Audit Findings -> Enforced Rules (Reflexion memory)

A single audit catches a mistake once. The high-leverage move is wiring a *recurring* audit finding into a durable authoring rule so the **same class of error is prevented at authoring time, not just caught after**. This is the static-track realization of Reflexion's episodic reflection memory (Shinn et al. 2023): a scalar/verbal critique from one trial is persisted and prepended to the next trial's context so the actor stops repeating the mistake — here with no runtime, no model calls, and a mandatory human gate. For the framework-track theory (Reflexion, Self-Refine, CRITIC, Evaluator-Optimizer) and the real APIs behind it, see `skills/agentic-system-architect/references/self_reflection_critique_loops.md`; the trial-loop and exit-condition theory lives in `skills/agentic-system-architect/references/loop_engineering_patterns.md` (cited here, not duplicated).

### The pipeline

```
(a) loop_auditor.py --history   ->  recurring-findings digest
        (agentic-system-architect / loop-engineering-mechanisms own this)
                |
                v  a check that fails across 2+ runs/sessions = "Proven"
(b) /si:remember "<recurring finding + implied authoring rule>"
                |
                v  human confirms it is durable + actionable
(c) /si:promote "<rule>" --target claude.md   (or --target rules/<topic>.md)
                |
                v  rule now loads into every future authoring session
(d) next loop_auditor.py run no longer flags it -> loop closed
```

- **(a) Detect the recurrence.** `loop_auditor.py`'s audit-history ledger mode (`--history`) records each verdict and emits a recurring-findings digest — a check that has failed across runs or sessions rather than once. The ledger, its score-delta / `no_progress` / oscillation counters, and the digest format are **owned and defined by `agentic-system-architect` (which ships `loop_auditor.py`) and `loop-engineering-mechanisms`** — see those skills for the flag's exact interface; do not re-teach it here. *(Verify `--history` against `loop_auditor.py`'s current interface — the ledger mode is a sibling addition landing alongside this bridge.)* A repeated failed check is the static equivalent of Reflexion's persisted critique signal, and it satisfies the **"Proven — appeared in 2+ sessions"** bar in [reference/promotion-rules.md](https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/self-improving-agent/reference/promotion-rules.md).
- **(b) Capture the lesson.** Run `/si:remember` with the finding stated as an implied authoring rule (imperative, e.g. "Every loop block must declare a `no_progress` exit condition, not only `max_iterations`"). This lands the reflection in auto-memory (`MEMORY.md`) — the capture buffer, not yet enforcement.
- **(c) Graduate it.** Once the recurrence and the promotion criteria hold (Proven + Actionable + Durable, score >= 6 per promotion-rules.md), `/si:promote` distills it into a one-line rule and writes it to `./CLAUDE.md` (project-wide) or `.claude/rules/<topic>.md` (scoped by `paths`). The mistake is now prevented when the next config is *written*, not merely graded after.
- **(d) Close the loop.** Because the rule loads into every subsequent authoring session, the next `loop_auditor.py` run stops flagging that check. The reflection has changed the policy; the error class does not recur across sessions or authors.

### Why this is Reflexion, statically

| Reflexion component | Static-track realization in this hub |
|---|---|
| Actor (generates the action/text) | The config author (human or Claude) editing an agent/skill/workflow `.md` |
| Evaluator (scalar / task feedback) | `loop_auditor.py`'s deterministic 100-point score + FAILED-CHECKS list |
| Self-Reflection (verbal critique) | The per-check remediation hints + the cross-run recurring-findings digest |
| Episodic memory buffer (last N reflections, prepended to the next trial) | The **promoted rule file** — `CLAUDE.md` / `.claude/rules/` loaded into every future authoring session |
| Durable episodic log | **git history** of that rule file (every promotion is a reviewed commit) |
| Trial loop | producer -> `loop_auditor.py` -> remediate (see `loop_engineering_patterns.md`) |

The load-bearing point: the versioned rule file *is* the reflection buffer, and git *is* the durable episodic log — no vector store, no runtime state. The single-trial evaluator-optimizer loop the hub already runs becomes a true cross-session Reflexion loop only once step (a)'s persisted digest feeds this promotion path.

### Eviction: keep the reflection buffer from becoming noise

Reflexion deliberately bounds its buffer to the last N reflections so context does not blow up. The static buffer needs the same discipline: an ever-growing pile of promoted rules becomes context noise that degrades adherence (adherence drops as `CLAUDE.md` lengthens — see [reference/memory-architecture.md](https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/self-improving-agent/reference/memory-architecture.md)). Consolidate and prune promoted rules on the same cadence you prune memory:

- Use `/si:review` to find consolidation groups and stale/contradicted rules; merge redundant lines and drop rules whose originating finding no longer recurs.
- Keep the *recurring-finding digest* as the retention signal (a rule earns its slot only while its error class is still live); one-off resolved findings are evicted.
- For the storage-side eviction/consolidation policy (hot/warm/frozen tiering, when a promoted rule may be retired), delegate to `hybrid-rag-memory/references/memory_eviction_and_consolidation.md` — do not re-derive it here. Versioning and one-command rollback of a promoted rule are owned by `prompt-governance`.

### Safety: the promotion is human-gated

This loop **proposes**; it never auto-writes. Step (b)->(c) always passes through a human confirming the rule via `/si:promote`, mirroring the 5-Phase HUMAN GATE. Two hard limits:

- **Object-level only.** The loop may graduate authoring rules for the configs being written (object-level). It must **never** promote a change that edits the critic itself — `loop_auditor.py`'s rubric, the six exit-condition definitions, or the promotion predicate (meta-level). An agent rewriting its own guardrails/reward function is the PromptBreeder anti-pattern; meta-level config changes only through a separate, explicitly human-authorized governance action.
- **Recurrence is evidence, not authority.** A digest entry nominates a rule; it does not authorize enforcement. The human gate is what turns a proven finding into a committed rule.

### See also

- `agent-self-optimization` — the governed candidate-rewrite (optimizer) track; this bridge feeds it the persisted findings that motivate a rewrite.
- `skills/agentic-system-architect/references/self_reflection_critique_loops.md` — Reflexion / CRITIC / Evaluator-Optimizer theory and framework APIs.
- `skills/agentic-system-architect/scripts/loop_auditor.py` — the deterministic critic and its `--history` ledger mode.

## Agents

### memory-analyst
Analyzes MEMORY.md and topic files to identify:
- Entries that recur across sessions (promotion candidates)
- Stale entries referencing deleted files or old patterns
- Related entries that should be consolidated
- Gaps between what MEMORY.md knows and what CLAUDE.md enforces

### skill-extractor
Takes a proven pattern and generates a complete skill:
- SKILL.md with proper frontmatter
- Reference documentation
- Examples and edge cases
- Ready for `/plugin install` or `clawhub publish`

## Hooks

### error-capture (PostToolUse → Bash)
Monitors command output for errors. When one is detected, the hook surfaces a
`hookSpecificOutput.additionalContext` note back to the session — it does NOT write
to memory itself; it prompts you to run `/si:remember` to persist the failure. The
suggested note includes:
- The command that failed
- Error output (truncated)
- Timestamp and context
- Suggested category

**Token overhead:** Zero on success. ~30 tokens only when an error is detected.

## Platform Support

| Platform | Memory System | Plugin Works? |
|----------|--------------|---------------|
| Claude Code | Auto-memory (MEMORY.md) | ✅ Full support |
| OpenClaw | workspace/MEMORY.md | ✅ Adapted (reads workspace memory) |
| Codex CLI | AGENTS.md | ✅ Adapted (reads AGENTS.md patterns) |
| GitHub Copilot | `.github/copilot-instructions.md` | ⚠️ Manual promotion only |

## Related

- [Claude Code Memory Docs](https://code.claude.com/docs/en/memory)
- [pskoett/self-improving-agent](https://clawhub.ai/pskoett/self-improving-agent) — inspiration
- [playwright-pro](https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills\playwright-pro) — sister plugin in this repo

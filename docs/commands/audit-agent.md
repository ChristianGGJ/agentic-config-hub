---
title: "/audit-agent — Slash Command for AI Coding Agents"
description: "Audit an agent configuration against the loop-engineering rubric (100 points, categories A-E) and remediate failed checks until it scores >=90. Slash command for Claude Code, Codex CLI, Gemini CLI."
---

# /audit-agent

<div class="page-meta" markdown>
<span class="meta-badge">:material-console: Slash Command</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/commands\audit-agent.md">Source</a></span>
</div>


Run the loop auditor on an agent `.md` file, apply the remediation hints for every failed check, and re-audit until the file reaches the repo quality gate (score >= 90, grade HARDENED). Target: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the user which agent file to audit (e.g., `agents/cs-architect.md`).

## Usage

```bash
/audit-agent agents/cs-architect.md
/audit-agent skills/agentic-system-architect/assets/agent-spec-template.md
```

## Step 1: Validate Input

1. Verify the path exists and ends in `.md`. If not, stop and report.
2. Read the agent file once so you understand its mission, sections, and tone before touching it.

## Step 2: Baseline Audit

```bash
python skills/agentic-system-architect/scripts/loop_auditor.py {agent_path} --min-score 90 --json
```

- Exit code `0` means the gate passed (score >= 90). Report the score and grade, then stop — done.
- Exit code `1` means the score is below 90. Parse the JSON output:
  - `score` and `grade` (grades: >=90 HARDENED, 75-89 PRODUCTION-READY, 50-74 NEEDS-CONTROLS, <50 UNSAFE-FOR-AUTONOMY)
  - `categories[]` (A Loop Safety, B HITL Gates, C Phase Protocol, D Boundary Control, E Output Contract)
  - Inside each category, every check where `"passed": false` — collect its `id`, `name`, `points`, and `remediation` hint.

## Step 3: Remediation Loop (max_iterations = 3)

This loop is itself bounded by the `max_iterations` exit condition: **at most 3 cycles**, then escalate (Step 4).

For each cycle:

1. List the failed checks sorted by `points` descending (biggest wins first).
2. For each failed check, apply its `remediation` hint to the agent file with Edit. Each hint states the exact sentence or section to add, for example:
   - `A1` — declare a `max_iterations` counter sentence
   - `A2` — add a no-progress detection rule
   - `B1` — add an approval gate before implementation
   - `C3` — document the Phase 3 HUMAN GATE (hard stop, human approves/edits/rejects)
   - `D1` — declare allowed/forbidden path boundaries
   - `E1` — declare exit conditions / success criteria
3. Placement rules:
   - Add loop-safety sentences (A*) under a `## Loop Safety` section — create it if missing.
   - Add gate/escalation sentences (B*) under `## HITL Gates`.
   - Add phase sentences (C*) under the 5-phase protocol section, using the canonical wording (Phase 1 DISCOVERY / Phase 2 MANIFEST / Phase 3 HUMAN GATE / Phase 4 IMPLEMENTATION / Phase 5 SELF-REVIEW & HANDOFF).
   - Add boundary (D*) and output-contract (E*) sentences under `## Boundaries` and `## Output Contract`.
   - Never delete or rewrite the agent's mission; only add the missing control statements.
4. Re-audit:

```bash
python skills/agentic-system-architect/scripts/loop_auditor.py {agent_path} --min-score 90 --json
```

5. Exit conditions for this loop:
   - `success_predicate`: exit code 0 → go to Step 5.
   - `no_progress`: the score did not increase versus the previous cycle → stop early and escalate.
   - `max_iterations`: 3 cycles completed without passing → escalate.

## Step 4: Escalation (escalation_trigger)

If the gate still fails after 3 cycles (or on no-progress), STOP editing and report to the user:

- Final score, grade, and the delta from the baseline
- Every remaining failed check: `id`, `name`, `points`, and its `remediation` hint verbatim
- Your hypothesis for why the hints did not register (e.g., wording too far from the check's pattern, content placed in a code fence)

Do not keep iterating past 3 cycles. The human decides the next move.

## Step 5: Final Report

```
AUDIT: {agent_path}
  Baseline: {score}/100 ({grade})
  Final:    {score}/100 ({grade})
  Cycles:   {n}/3
  Checks fixed: [A1, B1, ...]
  Verdict:  PASS (HARDENED) | ESCALATED ({n} gaps remaining)
```

## Related

- `skills/agentic-system-architect/SKILL.md` — rubric rationale and loop-engineering patterns
- `skills/agentic-system-architect/references/loop_engineering.md` — exit-condition taxonomy
- `/validate-gates` — the companion gate for workflow files

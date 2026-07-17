---
title: "Plan-Premortem: Prospective-Hindsight Plan Stress-Testing — Project Planning & Requirements Elicitation"
description: "Use when a plan must be stress-tested before execution by expanding stressor axes into adverse-future scenarios, writing prospective-hindsight. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Plan-Premortem: Prospective-Hindsight Plan Stress-Testing

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `plan-premortem`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/plan-premortem/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


**Tier:** STANDARD
**Category:** Planning / Risk
**Dependencies:** None. Both scripts are Python 3.8+ standard library only - offline, deterministic, no LLM or network calls.

## Description

Plan-premortem operationalizes Gary Klein's premortem method (HBR, September
2007) for the hub: before a plan executes, the team is told the plan HAS
ALREADY FAILED and must explain why. Prospective hindsight - explaining an
outcome as accomplished fact instead of a possibility - produces roughly 30
percent more specific failure reasons (Mitchell, Russo and Pennington, 1989).

The skill is one transformation: a plan in the hub canonical task shape plus
a stressor-axes specification go in; a ranked, validated premortem register
plus plan-delta recommendations come out. The register is the hub canonical
risk artifact: every scenario carries a past-tense failure narrative, a
likelihood band, an impact band, an early-warning signal, a contingency
trigger linked to a concrete plan task id, an accountable owner, and a
mitigation or an explicit acceptance.

Two deterministic tools bound and gate the work. The expander turns stressor
axes into the cartesian scenario matrix (capped, with an explicit truncation
notice - never silent). The validator makes premortem theater a deterministic
FAIL: unlinked, unrankable, unfalsifiable scenarios do not pass.

The skill supplies the method only. Fan-out execution of scenario authoring
is delegated to agenthub. Critique-loop identity for any autonomous synthesis
pass follows self_reflection_critique_loops.md (hub canon): CRITIC-grounded
by this skill's validator, never Self-Refine, and the loop may not rewrite
its own severity rubric. Approval gates live in consuming workflows.

## Features

- **Deterministic cartesian expansion** - same axes spec, same matrix, every
  run; `--max-scenarios` caps combinatorial explosion with an explicit
  truncation notice and an optional `--fail-on-truncation` CI mode
- **Prospective-hindsight prompts** - every scenario cell ships a past-tense
  narrative prompt that asserts the failure as accomplished fact, preserving
  the Klein framing that produces the effect
- **Canonical risk artifact** - the premortem register is the hub's one
  risk-register shape, git-versioned beside the plan it hardens
- **Plan-linked contingency triggers** - every trigger must resolve to a task
  id in plan.json, so downstream execution tracking can consume it directly
- **Band discipline, not rank arithmetic** - ordinal likelihood and impact
  bands with an evidence-or-judgment basis field (IEC 60812:2018 discipline)
- **Theater-proof gate** - the validator fails registers with missing
  narratives, dangling task ids, absent early-warning signals, or unmitigated
  above-threshold scenarios
- **Zero cross-skill dependencies** - copy this folder and run; shared
  knowledge is duplicated per the hub portability rule

## Interface

### Inputs

1. **plan.json** - hub canonical shape (the same id/depends_on contract that
   hitl_gate_validator rule R5 enforces on workflow Definition blocks, cited
   as authority; extra fields are tolerated):

```json
{
  "name": "warehouse-launch",
  "version": "0.1.0",
  "tasks": [
    {"id": "T1", "description": "Sign supplier contract", "depends_on": [],
     "owner": "procurement-lead", "duration_days": 10},
    {"id": "T6", "description": "Go-live", "depends_on": ["T5"],
     "milestone": true}
  ]
}
```

2. **Stressor-axes spec JSON** - 2-4 dimensions with discrete levels,
   including at least one tail magnitude per axis:

```json
{
  "name": "warehouse-launch-stress",
  "axes": [
    {"name": "supplier_delay", "levels": ["on_time", "2_weeks_late", "6_weeks_late"]},
    {"name": "demand_multiplier", "levels": ["1x", "3x"]},
    {"name": "key_person_loss", "levels": ["none", "lead_engineer_out"]}
  ]
}
```

3. Optional: an assumption register from the plan-critique skill - its
   CONTRADICTED and UNTESTABLE-CRITICAL entries are priority scenario seeds.
   Optional: historical incident notes as narrative evidence.

### Outputs

1. **Scenario matrix** (expander) - one cell per stressor combination, each
   with a narrative prompt and an empty register stub.
2. **Premortem register** (authored, then validated) - the canonical risk
   artifact; full field contract in `references/premortem_register_spec.md`.
3. **Plan-delta recommendations** - mitigations expressed as canonical tasks,
   buffers, or gates, ready for the consuming workflow's approval gate.

### Exit codes (both scripts)

| Code | Meaning |
|------|---------|
| 0 | pass / success (a capped expansion still exits 0 unless `--fail-on-truncation`) |
| 1 | gate failure: validator findings, or truncation under `--fail-on-truncation` |
| 2 | usage or input error: missing file, malformed JSON, malformed plan |

## Usage

The five-step workflow:

```bash
# 1. Expand the stressor axes into the scenario matrix (bounded)
python scripts/scenario_matrix_expander.py assets/sample-axes-spec.json \
    --max-scenarios 24 --out scenario-matrix.json

# 2. Author: fill each register_stub with a past-tense failure narrative.
#    One author per cell. Fan-out execution -> agenthub (by name).

# 3. Rate and link: likelihood/impact bands with a basis, early-warning
#    signal, contingency trigger -> plan task id, owner, mitigation or
#    explicit accepted_by.

# 4. Gate deterministically
python scripts/premortem_register_validator.py register.json \
    --plan plan.json --threshold high

# 5. Hand off: the plan delta goes to the consuming workflow's human
#    approval gate before it becomes the new baseline.
```

Loop discipline for autonomous runs: an agent-driven premortem is a bounded
Convergence Loop that declares its exit conditions from the hub six-type
taxonomy (max_iterations, no_progress, oscillation, budget,
success_predicate, escalation_trigger) before iteration 1. The synthesis
pass is CRITIC-grounded per self_reflection_critique_loops.md - this skill's
validator is the grounding tool - and validator PASS is evidence for a
success_predicate, never a self-assigned score. Loop mechanics themselves
are hub canon (agentic-system-architect references, by name) and are not
rebuilt here.

## Examples

### Example 1: expand the sample axes

```bash
python scripts/scenario_matrix_expander.py assets/sample-axes-spec.json --max-scenarios 8
```

Output (trimmed):

```
SCENARIO MATRIX: warehouse-launch-stress
Axes: supplier_delay x demand_multiplier x key_person_loss
Combinations: 12 total, 8 emitted
PM-001  supplier_delay=on_time | demand_multiplier=1x | key_person_loss=none
...
TRUNCATION NOTICE: emitted 8 of 12 combinations (--max-scenarios 8). 4
combinations were NOT expanded. Raise --max-scenarios or prune axis levels
to decision-relevant magnitudes.
```

Exit code 0; add `--fail-on-truncation` to make the cap a CI failure.

### Example 2: gate the seeded-invalid sample register

```bash
python scripts/premortem_register_validator.py assets/sample-premortem-register.json \
    --plan assets/sample-plan.json
```

Output:

```
ERROR [PM-003] V4: early_warning_signal is missing or empty; a scenario
      without a leading indicator is an unfalsifiable story
ERROR [PM-003] V5: contingency_trigger.task_id 'T99' does not exist in the plan
ERROR [PM-003] V6: owner is missing or empty; every scenario needs a person
      accountable for its mitigation
RESULT: FAIL (3 errors, 0 warnings)
```

Exit code 1. The fixed register (`assets/sample-premortem-register-valid.json`)
passes with exit code 0. Machine-readable reports: add `--json`.

## Anti-Patterns

Mined from the named sources; each row is a documented failure mode of real
premortems and scenario exercises, not generic advice.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Risk-brainstorm drift (Klein, HBR 2007) | Register full of hedged possibilities: "we might slip", "supplier could be late" | The session asked "what could go wrong?" instead of asserting the failure already happened | Open every narrative "It is <date>; the plan failed because..."; validator V1 warns when a narrative never asserts failure |
| Future-tense framing loss (Mitchell, Russo and Pennington 1989) | Narratives read as forecasts; reasons stay abstract | Prospective hindsight's ~30 percent specificity gain requires the past-tense accomplished-fact frame; dropping the tense drops the effect | The expander's narrative prompts hard-code past-tense framing; authors keep it |
| Advocacy sandbagging (Kahneman and Lovallo, HBR 2003) | Every likelihood "low", no critical impacts, mitigations restate existing plan tasks | Plan owners rating their own plan defend it; delusions-of-success pressure | Separate scenario authorship from plan ownership; unmitigated above-threshold risk requires a named accepted_by, so softening is auditable |
| Scenario sprawl (Schoemaker 1995; Wack 1985) | Hundreds of cells nobody reads; review skipped | Cartesian growth treated as thoroughness; no decision-relevance pruning | `--max-scenarios` cap with explicit truncation notice; prune axis levels to decision-relevant magnitudes before expanding |
| Unfalsifiable stories (Wack 1985) | Scenarios with no observable leading indicator | Scenario written as drama, not as a detectable causal chain | Validator V4/V5 make early_warning_signal and a plan-linked contingency trigger hard requirements |
| RPN rank arithmetic (IEC 60812:2018) | Likelihood x impact multiplied into a numeric priority score | Ordinal bands treated as ratio numbers - the documented rank-product fallacy | Keep bands ordinal, rank by band pair; basis field marks evidence vs judgment (V10) |
| Blame-seeking narratives (Google SRE Book 2016, ch. 15) | Narratives name culprits ("ops dropped the ball") instead of mechanisms | Postmortem blame culture imported into the premortem suppresses candid enumeration | Blameless mechanism-focused prompts; owner means accountable for the mitigation, not blamed for the scenario |
| Timid stressor magnitudes (Flyvbjerg and Gardner 2023) | All axis levels within 10 percent of baseline; premortem finds nothing | Thin-tailed intuition about fat-tailed project outcomes | Every axis carries at least one tail level (3x demand, 6-week delay); calibrate against reference-class overrun data |
| Normalized deviance excluded (Vaughan 1996; CAIB 2003) | Recurring near-misses absent from every scenario | Past warnings reclassified as normal are invisible to fresh brainstorming | Seed axes from incident history; validator V11 warns when milestones are untouched by any scenario |

## When NOT to Use

Routing table - sibling skills are named, never path-referenced; composition
happens at agent/workflow level.

| If you need to... | Use instead |
|-------------------|-------------|
| Test whether a plan's premises hold against evidence and base rates | plan-critique |
| Decompose an objective into a task hierarchy | wbs-decomposition |
| Model or validate task precedence edges | critical-path-scheduler |
| Compute dates, floats, or the critical path | critical-path-scheduler |
| Track execution against the baseline and consume contingency triggers at runtime | plan-baseline-tracking |
| Run a hostile review of code diffs | adversarial-reviewer |
| Score completed work honestly after the fact | self-eval |
| Execute scenario authoring as a parallel agent tournament | agenthub |
| Wire exit conditions and loop mechanics for the autonomous run | loop-engineering-mechanisms / agentic-system-architect |
| Persist past-failure records for future scenario seeding | hybrid-rag-memory |
| Export the hardened plan as tickets | plan-ticket-export |

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs owned by framework skills - verify
against current docs): fan out one scenario analyst per cell via the
LangGraph Send API with an interrupt() gate before any plan mutation (see
langgraph-state-design); CrewAI async_execution tasks synthesized by a
manager task, or a Flow with a bounded router loop (see
crewai-role-engineering); Microsoft Agent Framework concurrent orchestration
or group chat with a hard 3-5 round cap (see microsoft-agent-framework).
None of that wiring is duplicated here.

**STATIC TRACK** (how this hub uses the skill offline): the axes spec, the
scenario matrix, and the premortem register are git-versioned files beside
plan.json; both scripts are deterministic offline gates wired into CI by
exit code; fan-out authoring runs as an agenthub tournament (one agent, one
cell); the validated register and its plan delta are presented at the
consuming workflow's human approval gate before the amended plan becomes the
new baseline. The register's git history is the episodic risk record.

## References

In-skill knowledge bases:

- `references/prospective_hindsight_method.md` - the Klein protocol, its
  evidence base, rating discipline, and failure-mode seeds
- `references/premortem_register_spec.md` - the canonical risk artifact:
  field contract, validation rules V0-V11, lifecycle

Source literature (edition-pinned):

- Klein, G. "Performing a Project Premortem", Harvard Business Review,
  September 2007; Klein, G. Sources of Power, MIT Press, 1998
- Mitchell, D., Russo, J. and Pennington, N. "Back to the Future: Temporal
  Perspective in the Explanation of Events", Journal of Behavioral Decision
  Making 2(1), 1989
- Kahneman, D. and Lovallo, D. "Delusions of Success: How Optimism
  Undermines Executives' Decisions", Harvard Business Review, July 2003
- Schoemaker, P. "Scenario Planning: A Tool for Strategic Thinking", Sloan
  Management Review 36(2), 1995; Wack, P. "Scenarios: Uncharted Waters
  Ahead", Harvard Business Review, September-October 1985
- IEC 60812:2018, Failure Modes and Effects Analysis - external standard,
  verify against current docs
- Vaughan, D. The Challenger Launch Decision, University of Chicago Press,
  1996; Columbia Accident Investigation Board Report Vol. 1, NASA, 2003
- Beyer, B. et al. (eds.) Site Reliability Engineering, O'Reilly, 2016,
  ch. 15 "Postmortem Culture"
- Flyvbjerg, B. and Gardner, D. How Big Things Get Done, Currency, 2023

Hub canon (cited by name as authority, never called or path-referenced):

- hitl_gate_validator rule R5 - the id/depends_on acyclicity contract the
  plan.json input mirrors
- loop_engineering_patterns.md and self_reflection_critique_loops.md
  (agentic-system-architect flagship) - Convergence Loop chassis, six-type
  exit-condition taxonomy, CRITIC-grounded synthesis identity

---
title: "Plan Critique: Hostile Pre-Execution Plan Review — Project Planning & Requirements Elicitation"
description: "Use when a preliminary plan needs hostile pre-execution review before the human gate -- audits plan.json for missing lifecycle phases, basis-free. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Plan Critique: Hostile Pre-Execution Plan Review

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `plan-critique`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/plan-critique/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


**Tier:** STANDARD
**Category:** Planning / Quality
**Dependencies:** None. `scripts/plan_audit.py` is Python 3.8+ standard library only - no network calls, no LLM calls.

## Description

Plan-critique attacks a preliminary plan BEFORE execution starts. It is one
severity-classified plan-review capability that merges two check families:

- **Structural critique (PC1-PC8)** - the plan itself: missing lifecycle
  phases (testing/QA, legal-compliance review, deployment/rollout,
  training/handoff), estimates without a recorded basis, single-point-of-
  failure owners, missing milestones, and duration outliers vs sibling tasks.
- **Assumption-register lints (AS1-AS5)** - the premises the plan rests on:
  assumptions without an evidence source, without an invalidation test,
  without an owner, with a stale review date, or a register that is missing
  entirely (itself a mandatory CRITICAL finding).

Position in the hub's 5-Phase Protocol: between Phase 2 (MANIFEST) and
Phase 3 (HUMAN GATE) - the pre-execution mirror of the `self-eval` skill,
which scores completed work at Phase 5. Every finding names a severity
(CRITICAL / HIGH / MEDIUM / LOW) and a concrete failure scenario: the
specific way the defect becomes a slipped date, a blocked launch, or a
production incident.

The capability has two layers with an honest division of labor:

1. **Deterministic layer** - `scripts/plan_audit.py` checks presence and
   structure. Fast, offline, CI-wireable, same input same output.
2. **Persona layer** - three review personas apply the `references/` rubrics
   to the semantics the script cannot see: whether the "testing" task is
   real, whether the estimate basis is an actual reference class, whether
   present-but-weak evidence supports a premise.

## Features

- One script, both families: `plan_audit.py` runs PC1-PC8 and AS1-AS5 in a
  single pass over `plan.json` + optional `assumptions.json`.
- Severity-classified findings, each with location, concrete failure
  scenario, and fix hint - never a bare "plan is incomplete".
- Verdict mapping: BLOCK (return to MANIFEST) / CONCERNS (annotate for the
  human gate) / CLEAN (proceed to the gate).
- CI gates: `--fail-on <severity>` (default `high`) and optional
  `--min-score N` on a 100-point deduction score; exit 1 wires directly into
  merge pipelines.
- Frozen rubric: checks, severities, and thresholds live at module level in
  the script; the critique may never rewrite its own rubric mid-run.
- Seeded sample assets with a documented expected-findings sheet, so the
  whole pipeline is verifiable in one command.

## The Three Personas

| Persona | Attacks | Method source (see references/) |
|---------|---------|----------------------------------|
| Pessimist-PM | Every estimate | Planning fallacy and reference-class forecasting: demands a named reference class per number (Kahneman & Tversky 1979; Flyvbjerg 2006) - `planning_fallacy_and_reference_class.md` |
| Completeness Auditor | The task list | Forgotten-step checklist: testing, legal/compliance, security review, procurement, data migration, training, rollback, decommissioning (GAO-20-195G; Standish CHAOS) - `forgotten_step_checklist.md` |
| Assumption Hunter | The premises | Key Assumptions Check: extract, classify, demand evidence and an invalidation test per premise (Heuer & Pherson 2020) - `assumption_register_method.md` |

Persona ground rules, duplicated (never imported) from the
`adversarial-reviewer` skill per the hub portability rule:

- **Honest minimum:** the review MUST produce at least one finding. If the
  plan is genuinely solid, name the most fragile assumption as a LOW note.
- **Forced-Finding Calibration:** a finding is genuine only if it has a
  concrete trigger, a concrete bad outcome, and is not already prevented by
  an existing task or gate.
- **Two-persona promotion:** a defect raised independently by two personas
  is promoted one severity level.

## Interface

### Inputs

`plan.json` (required) - the hub canonical tasks shape (the same
`id`/`depends_on` contract that hub canon `hitl_gate_validator` rule R5
enforces on workflows; extra fields are tolerated):

```json
{
  "name": "customer-portal-launch",
  "version": "0.1.0",
  "tasks": [
    {
      "id": "T1", "description": "...", "depends_on": [],
      "wbs_id": "1.1", "deliverable": "...", "owner": "alice",
      "duration_days": 5, "estimate_basis": "...",
      "milestone": false
    }
  ]
}
```

`assumptions.json` (optional register) - see
`assets/assumption-register-template.json`. Omitting it, or shipping an
empty register, fires AS5 as CRITICAL: a plan with zero declared assumptions
has only implicit, untested ones.

Optional at persona level: historical actuals for reference-class anchoring
(retrieved upstream via the `rag-architect` / `hybrid-rag-memory` skills,
composed at agent level - this skill never fetches anything).

### Outputs

1. Findings report (human-readable or `--json`): per finding `check_id`,
   `severity`, `location`, `summary`, `failure_scenario`, `fix`.
2. Severity counts, a 100-point deduction score, and a verdict.
3. Exit code for CI.

| Exit code | Meaning |
|-----------|---------|
| 0 | Pass: no findings at or above `--fail-on`, score at or above `--min-score` |
| 1 | Gate fail: findings at or above `--fail-on`, or score below `--min-score` |
| 2 | Usage or input error (bad JSON, contract violation, bad date) |

### Verdicts and exit conditions

| Verdict | When | Exit condition it maps to |
|---------|------|---------------------------|
| BLOCK | Any CRITICAL finding | `escalation_trigger` - return the plan to Phase-2 MANIFEST |
| CONCERNS | HIGH or MEDIUM findings | none - proceed to the Phase-3 HUMAN GATE with findings attached |
| CLEAN | No findings, or LOW only | `success_predicate` for the critique step |

Non-converging critique-revise cycles terminate on `no_progress` /
`max_iterations`. The six-type exit taxonomy (`max_iterations`,
`no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger`) is owned by the `agentic-system-architect` skill and
cited here, never redefined.

## Usage

```bash
# Full audit: plan + assumption register (pin --as-of for reproducible runs)
python scripts/plan_audit.py plan.json --assumptions assumptions.json --as-of 2026-07-16

# Machine-readable, for CI or agent consumption
python scripts/plan_audit.py plan.json --assumptions assumptions.json --json

# Stricter CI gate: fail on anything MEDIUM or worse, and below 70 points
python scripts/plan_audit.py plan.json --assumptions assumptions.json --fail-on medium --min-score 70
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--assumptions FILE` | (none) | Register to lint; absence fires AS5 CRITICAL |
| `--as-of YYYY-MM-DD` | today | Reference date for staleness; pin it for reproducibility |
| `--stale-days N` | 90 | Age at which a review date is aging (LOW); 2x N is stale (MEDIUM) |
| `--fail-on SEV` | high | Lowest severity that fails the gate (`never` = report only) |
| `--min-score N` | (off) | Optional 100-point score gate |
| `--json` | off | Machine-readable report |

### Review workflow

1. **Deterministic pass** - run `plan_audit.py`. Fix contract errors (exit 2)
   first; they mean the plan is not in the canonical shape.
2. **Persona pass** - walk the three personas over the plan using the
   `references/` rubrics. Attack semantics: present-but-hollow bases,
   keyword-satisfying-but-fake phases, weak evidence.
3. **Consolidate** - merge script findings and persona findings; apply the
   two-persona promotion rule; compute the verdict.
4. **Gate** - BLOCK returns the plan to MANIFEST; CONCERNS and CLEAN go to
   the Phase-3 HUMAN GATE with the findings attached. The human decides.

## Check Catalog

| ID | Family | Severity | Detects |
|----|--------|----------|---------|
| PC1 | structural | CRITICAL | No testing/QA task anywhere in the plan |
| PC2 | structural | HIGH | No legal/compliance review task |
| PC3 | structural | HIGH | No deployment/rollout task |
| PC4 | structural | MEDIUM | No training/handoff task |
| PC5 | structural | HIGH | Task has `duration_days` but no `estimate_basis` |
| PC6 | structural | MEDIUM/HIGH | One owner holds >= 50% (>= 75% escalates) of owned tasks |
| PC7 | structural | MEDIUM | No task carries `milestone: true` |
| PC8 | structural | LOW/MEDIUM | Duration outlier vs sibling median (2.5x mild, 4x severe; wbs_id groups) |
| AS1 | register | HIGH | Assumption without an evidence source |
| AS2 | register | HIGH | Assumption without an invalidation test |
| AS3 | register | MEDIUM | Assumption without an owner |
| AS4 | register | LOW/MEDIUM | Review date aging/stale (or missing/unparseable) |
| AS5 | register | CRITICAL | Register missing or empty |

## Examples

### Example 1: seeded sample (expect 13 findings, exit 1)

```bash
python scripts/plan_audit.py assets/sample-plan.json \
    --assumptions assets/sample-assumptions.json --as-of 2026-07-16
```

Output (excerpt):

```
[CRITICAL] PC1 at plan-level
  Summary:  Missing lifecycle phase: no testing / quality assurance task found anywhere in the plan
  Scenario: The build completes on schedule and ships unverified. The first
            integration defect is found by a customer in production, ...

SEVERITY COUNTS: CRITICAL=1 HIGH=6 MEDIUM=5 LOW=1
SCORE:   0/100
VERDICT: BLOCK (return the plan to Phase-2 MANIFEST before the human gate)
GATE:    FAIL (--fail-on high)
```

The full expected list is documented in `assets/expected-findings.md`; the
clean pair (`assets/clean-plan.json` + `assets/clean-assumptions.json`)
exits 0 with score 100.

### Example 2: CI wiring

```yaml
- name: Plan quality gate
  run: |
    python skills/plan-critique/scripts/plan_audit.py plan.json \
      --assumptions assumptions.json --as-of "$(date +%F)" \
      --fail-on high --json
```

Exit 1 blocks the merge; the JSON report attaches to the run for the human
gate reviewer.

### Example 3: a persona finding the script cannot make

Task T4 in the seeded sample carries `estimate_basis: "Team judgment"`.
PC5 passes - the field is present. The Pessimist-PM persona still writes:

```
[HIGH] Pessimist-PM at task:T4
  Summary:  45-day estimate rests on an inside-view basis with no reference class
  Scenario: The dashboard build is the largest single bet in the plan; if it
            runs at the ordinary planning-fallacy multiple (~2x), T8 and the
            launch date slip by six weeks with no earlier warning milestone.
  Fix:      Re-derive from completed dashboard builds (reference class),
            or split T4 until siblings are comparable.
```

## Anti-Patterns

Mined from the named sources; each row is the documented defect, not generic
advice.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Inside-view estimation (Kahneman & Tversky 1979; Kahneman 2011 ch. 23) | Every duration derived by decomposing this plan's own steps; `estimate_basis` empty or "engineering judgment" | Planning fallacy: the mind prices the best-case narrative of the singular case and ignores distributional evidence | Reference-class forecasting per Flyvbjerg (2006): record class, base rate, and adjustment in `estimate_basis`; PC5 flags absence, Pessimist-PM rejects hollow bases |
| Advocacy estimate that survives review (Flyvbjerg, Holm & Buhl 2002, "Error or Lie?") | Suspiciously low numbers on approval-critical tasks; the basis cannot be re-derived when challenged | Strategic misrepresentation: underestimation improves the odds the plan is approved | Re-derive every critical-path estimate from its named reference class at the persona pass; basis-free critical estimates are HIGH, never waived |
| Happy-path task list (GAO-20-195G, standard WBS element omissions) | Plan ends at "code complete": no testing, compliance, rollout, or training tasks anywhere | Task list built from the delivery narrative instead of a full-lifecycle breakdown; GAO audits show these same omissions recur in real programs | PC1-PC4 presence checks plus the Completeness Auditor's 10-row checklist in `references/forgotten_step_checklist.md` |
| Milestone-free schedule (GAO-20-195G: estimates must tie to a documented, measurable baseline) | No task carries `milestone: true`; status is reported as percent feelings | No intermediate checkpoints were priced in, so slippage has no detection point before the final deadline | PC7 requires milestones; every milestone gets a verifiable acceptance signal |
| Rubber-stamp assumption log (PMBOK 6th ed. 11.2.2.3; Heuer & Pherson 2020) | Register written once at kickoff; review dates all predate the last replan; every verdict is SUPPORTED | Key Assumptions Check run after commitment, when changing course is socially expensive | AS4 stale-date lint plus the re-run-at-every-replan rule; the honest-minimum rule forbids all-clear reviews |
| Assumption stated as fact (Heuer 1999; Nickerson 1998) | Register entries like "the vendor API will be ready" with an empty `evidence_source` | Confirmation bias: the evidence search stopped at the first supporting datum | AS1 demands a traceable evidence source; the Assumption Hunter rejects restatements-as-evidence |
| Untestable-assumption fallacy (Hubbard 2014) | `invalidation_test` left empty "because it cannot be tested" | Measurement inversion: the highest-stakes premises get the least measurement effort | AS2: design the cheapest falsifying observation; genuinely untestable + critical premises are escalated at the gate as UNTESTABLE-CRITICAL |
| Hero plan / bus factor of one (GAO-20-195G resource realism; PMI Pulse failure surveys) | One owner on most tasks; the schedule assumes that person never sleeps, leaves, or gets sick | The plan was built around the one available expert instead of around the work | PC6 concentration check; redistribute ownership or record explicit, human-approved risk acceptance |

## When NOT to Use

Route by capability, by skill name only:

| You actually need | Use instead |
|-------------------|-------------|
| Decomposing an objective into a task hierarchy | `wbs-decomposition` |
| Modeling or validating `depends_on` precedence (cycles, dangling refs) | `critical-path-scheduler` |
| Calendar dates, critical path, float | `critical-path-scheduler` |
| Exporting the approved plan as Jira/Asana/Trello payloads | `plan-ticket-export` |
| Tracking execution against the baseline, slip detection | `plan-baseline-tracking` |
| Simulating adverse futures (prospective-hindsight scenarios) | `plan-premortem` (Klein's premortem is a different transformation: generative simulation, not evidence-based critique) |
| Hostile review of code diffs | `adversarial-reviewer` |
| Honest scoring of completed work (Phase 5) | `self-eval` |
| Loop mechanics, exit-condition wiring, critique-loop theory | `agentic-system-architect`, `loop-engineering-mechanisms` |
| Retrieving policy docs or historical actuals to ground the critique | `rag-architect` (documents), `hybrid-rag-memory` (episodic history) |

## Delegation: Loop Mechanics Live Elsewhere

This skill ships ONLY the planning-domain rubric. Everything about running
it in a loop is delegated by mandate:

- **Loop identity and mechanics** - the `agentic-system-architect` skill's
  references, specifically `self_reflection_critique_loops.md` and
  `loop_engineering_patterns.md`, own the critique-loop machinery: run
  plan-critique as the CRITIC-grounded Evaluator-Optimizer defined there
  (with `plan_audit.py` as the external deterministic grounding tool), never
  as ungrounded Self-Refine; bound revision cycles at 3-5 passes; the loop
  may never rewrite its own rubric mid-run.
- **Hostile-review machinery** - the persona / forced-finding / severity /
  escalation scaffolding originates in the `adversarial-reviewer` skill and
  is duplicated here for the planning domain per the hub portability rule.
- **Readings, not exit conditions** - inherited from the `self-eval`
  constraint: verdicts and scores are evidence presented at the gate, never
  the condition that terminates a loop. Loops terminate only on the declared
  six-type exit taxonomy.
- **Recurring lessons** - findings that recur across plans graduate to
  enforced rules via the `self-improving-agent` skill's human-gated
  remember-then-promote pipeline, by citation only.
- **Prompt shapes** - role-prompting and structured-output technique for
  phrasing persona passes: `senior-prompt-engineer`, by citation only.

## Honesty Note: What Exit 0 Does NOT Mean

`plan_audit.py` verifies presence and structure. A plan can contain the word
"testing" without a real test task; "Team judgment" is a present (and
worthless) estimate basis; a keyword-satisfying task list can still be a
fantasy. Exit 0 means "no structural defect found" - never "this plan is
realistic". The split is deliberate: the script owns structure, the personas
own semantics, the Phase-3 HUMAN GATE owns judgment. Selling exit 0 as plan
quality is itself an anti-pattern.

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs - delegated to framework skills by
name, verify against current docs): run the critique-revise cycle as an
Evaluator-Optimizer in `langgraph-state-design` (evaluator node,
`add_conditional_edges` on verdict severity, `interrupt()` before any plan
mutation), as a QA-reviewer task with a guardrail and
`context=[planning_task]` plus a devil's-advocate backstory in
`crewai-role-engineering`, or as a writer-critic group chat capped at 3-5
rounds in `microsoft-agent-framework`.

**STATIC TRACK** (how this hub uses it): `plan.json` and `assumptions.json`
are git-versioned beside the plan; `plan_audit.py` runs offline as the
deterministic CI merge gate with its frozen module-level rubric acting as
the CRITIC-style grounding tool; findings and verdict feed the Phase-3
HUMAN GATE; the register's git history is the audit trail. No network, no
LLM, same input same output.

## References

- Kahneman, D. & Tversky, A. (1979). "Intuitive Prediction: Biases and
  Corrective Procedures." TIMS Studies in Management Science 12.
- Kahneman, D. (2011). Thinking, Fast and Slow. Farrar, Straus and Giroux,
  ch. 23-24 (planning fallacy, outside view).
- Buehler, R., Griffin, D. & Ross, M. (1994). "Exploring the planning
  fallacy." Journal of Personality and Social Psychology 67(3).
- Flyvbjerg, B. (2006). "From Nobel Prize to Project Management: Getting
  Risks Right." Project Management Journal 37(3). (Reference-class
  forecasting - verify against current literature.)
- Flyvbjerg, B., Holm, M. S. & Buhl, S. (2002). "Underestimating Costs in
  Public Works Projects: Error or Lie?" JAPA 68(3).
- Flyvbjerg, B. & Gardner, D. (2023). How Big Things Get Done. Currency.
- GAO (2020). Cost Estimating and Assessment Guide, GAO-20-195G. (External
  standard - verify against current edition.)
- Heuer, R. J. (1999). Psychology of Intelligence Analysis. CIA CSI.
- Heuer, R. J. & Pherson, R. H. (2020). Structured Analytic Techniques for
  Intelligence Analysis, 3rd ed. CQ Press.
- Nickerson, R. S. (1998). "Confirmation Bias: A Ubiquitous Phenomenon in
  Many Guises." Review of General Psychology 2(2).
- PMBOK Guide, 6th ed. (2017). PMI, section 11.2.2.3. (Verify against
  current PMI edition.)
- Standish Group, CHAOS reports; PMI, Pulse of the Profession. (Verify
  against current editions.)
- Klein, G. (2007). "Performing a Project Premortem." Harvard Business
  Review, September 2007. (Boundary source: premortem simulation belongs to
  `plan-premortem`, not here.)
- Hubbard, D. (2014). How to Measure Anything, 3rd ed. Wiley.
- In-hub canon (cited as authority, never imported or called): the
  `agentic-system-architect` skill - `self_reflection_critique_loops.md`,
  `loop_engineering_patterns.md`, the six-type exit taxonomy, and
  `hitl_gate_validator` rule R5 as the canonical `id`/`depends_on` contract;
  the `adversarial-reviewer` and `self-eval` skills as pattern donors.

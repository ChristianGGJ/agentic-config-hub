---
title: "WBS Decomposition — Project Planning & Requirements Elicitation"
description: "Use when decomposing a macro objective or project goal into a work breakdown structure of manageable, estimable, deliverable-oriented subtasks. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# WBS Decomposition

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `wbs-decomposition`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/wbs-decomposition/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


## Description

wbs-decomposition packages exactly one transformation: a macro objective plus
its known constraints goes in; a hierarchical, 100-percent-rule-compliant Work
Breakdown Structure comes out, with leaf tasks that serialize into the hub
canonical `plan.json` tasks array (`id`, `description`, `depends_on: []`
stubs, plus tolerated extras such as `wbs_id`, `deliverable`, `owner`,
`estimate_hours`, `estimate_basis`).

The methodology layer (in `references/`) carries the decomposition canon:
the 100-percent rule, deliverable-oriented versus activity-oriented
breakdown, mutual exclusivity, granularity heuristics (the 8/80 rule), and
rolling-wave elaboration. The tooling layer (`scripts/wbs_validator.py`)
enforces everything about that canon that is *structurally* checkable, and
nothing more.

In hub terms: the validated WBS **is** the Phase-2 MANIFEST content that the
Phase-3 HUMAN GATE approves. This skill produces and validates the manifest;
it never approves it, executes it, or hosts the gate (those belong to agents
and workflows, per hub canon).

**HONESTY NOTE (read before trusting exit code 0):** structure is checkable;
semantic completeness is not. `wbs_validator.py` can prove that ids are
unique, that every non-leaf has at least two children, that depth stays in
bounds, and that no two elements share a description. It cannot prove that
the children of "Portal build" actually cover 100 percent of building the
portal, or that a task is genuinely "manageable". That judgment is
plan-critique territory plus the human gate - exit code 0 means well-formed,
never complete.

## Features

- **Decomposition methodology** - a step-by-step procedure (objective ->
  orientation choice -> top-down decomposition -> granularity pass ->
  serialization) grounded in the PMI Practice Standard for WBS, the NASA WBS
  Handbook error catalog, and the GAO cost-guide WBS chapter.
- **Structural validator** (`scripts/wbs_validator.py`) - deterministic,
  stdlib-only checks: unique ids (U1), >= 2 children per non-leaf as the
  structural proxy for the 100-percent rule (B1), configurable depth bounds
  defaulting to 2-4 levels (D1), empty descriptions (E1), exact and
  near-duplicate description detection as the mutual-exclusivity proxy
  (X1/X2), orphan and parent-cycle detection (O1), dotted-id numbering drift
  (N1), missing-deliverable warnings (G1), and an optional 8/80
  estimate-bounds gate (H1, `--check-estimates`).
- **Two input shapes** - a nested `wbs` tree (children arrays) or a flat
  `elements` list with `parent` references; the flat shape is where orphan
  detection earns its keep.
- **plan.json emission** (`--emit-tasks`) - on PASS, leaf tasks serialize to
  the hub canonical contract with `depends_on: []` stubs, ready for the
  critical-path-scheduler skill to populate and for downstream schedulers,
  critics, and exporters to consume.
- **Anti-pattern armor** - seven named WBS defects mined from PMI, NASA,
  GAO, Flyvbjerg, and Standish sources, each mapped to the check that
  catches it or the review step that must.

## Usage

### Workflow A: author the WBS (knowledge work)

1. **State the objective and exclusions.** One to three sentences of
   objective plus an explicit out-of-scope list. If the objective itself is
   unclear, stop - elicitation is upstream work, not decomposition.
2. **Choose one decomposition basis per level** - deliverable/product, phase,
   or discipline - and do not mix bases among siblings.
3. **Decompose top-down.** Every parent splits into >= 2 children that
   together cover all of the parent (100-percent rule) and do not overlap
   (mutual exclusivity). Name leaves as deliverables with an observable
   acceptance signal, not as activities.
4. **Apply granularity heuristics.** Leaves land between 8 and 80 hours of
   effort; anything smaller rolls up, anything larger decomposes further.
   Far-future branches stay coarse (rolling wave) - record that decision
   instead of inventing detail.
5. **Serialize** to WBS JSON using `assets/wbs-authoring-template.md` as the
   starting skeleton (nested or flat shape).

### Workflow B: validate and emit (deterministic)

```bash
# Validate structure (depth bounds default to 2-4)
python scripts/wbs_validator.py my_wbs.json

# Add the 8/80 estimate gate and machine-readable output
python scripts/wbs_validator.py my_wbs.json --check-estimates --json

# On PASS, emit leaf tasks in the hub canonical plan.json contract
python scripts/wbs_validator.py my_wbs.json --emit-tasks plan.json
```

Exit codes: `0` = PASS (zero FAIL findings), `1` = gate fail, `2` =
usage/input error. Emission is refused while FAIL findings exist, so a
`plan.json` on disk always came from a structurally valid WBS.

6. **Hand the validated WBS + emitted plan.json to the human gate.** The
   markdown hierarchy is the human-reviewable manifest; the JSON is the
   machine contract downstream skills consume.

## Examples

### Example 1: clean run against the shipped sample

```bash
python scripts/wbs_validator.py assets/sample_wbs.json --check-estimates \
    --emit-tasks plan.json
```

```
WBS STRUCTURAL VALIDATION
================================================================
File      : assets/sample_wbs.json
Format    : nested
Elements  : 14 (leaves: 9)
Max depth : 3 (bounds 2-4)
Estimates : enforced at 8-80 hours per leaf (8/80 rule)

FINDINGS: none

RESULT: PASS (0 FAIL / 0 WARN)
Emitted 9 leaf task(s) to plan.json (depends_on stubs are empty; ...)
```

The emitted file matches `assets/expected_plan.json` byte for byte.

### Example 2: defective WBS (flat shape)

```bash
python scripts/wbs_validator.py assets/sample_wbs_failing.json --check-estimates
```

```
FINDINGS:
  FAIL O1  orphan element(s): declared parent id does not exist [4.1]
  FAIL U1  duplicate element id(s) [3.1]
  FAIL B1  non-leaf element(s) with a single child break the 100-percent-rule
           structural proxy ... [2]
  FAIL X1  exact duplicate description (mutual exclusivity broken): ...
  WARN X2  near-duplicate descriptions (ratio 0.90 >= 0.85): ...
  FAIL H1  leaf estimate_hours outside the 8/80 bounds ... [2.1]

RESULT: FAIL (5 FAIL / 2 WARN)
```

Exit code is 1 and `--emit-tasks` is skipped until the FAILs are fixed.

## Interface

### Inputs

| Input | Required | Shape |
|---|---|---|
| Macro objective + constraints | yes | 1-3 sentences plus explicit exclusions (drives Workflow A; recorded in the WBS file's `objective` field) |
| WBS JSON | yes (for Workflow B) | object with nested `wbs` tree (elements carry `id`, `description`, optional `children`, `deliverable`, `owner`, `estimate_hours`, `estimate_basis`, `milestone`) or flat `elements` list with `parent` references |
| Org deliverable taxonomy, target depth | optional | informs Workflow A; depth enforced via `--min-depth`/`--max-depth` |
| Credentials / network | never | scripts are offline and deterministic |

### Outputs

| Output | Contract |
|---|---|
| Human-reviewable WBS | numbered hierarchy, per-leaf deliverable + acceptance signal (the Phase-2 manifest) |
| Validation report | human text or `--json`; findings carry check id, severity (FAIL/WARN), message, element ids |
| `plan.json` (via `--emit-tasks`) | `{"name": str, "version": "0.1.0", "tasks": [{"id", "description", "depends_on": [], "wbs_id", ...extras}]}` - the hub canonical id/depends_on contract; extra fields are tolerated downstream (same minimal shape hitl_gate_validator rule R5 enforces on workflow Definition blocks - cited as authority, never invoked) |

Downstream consumers of the emitted tasks array: critical-path-scheduler
(populates `depends_on`), plan-critique (adversarial review),
critical-path-scheduler (dates), plan-ticket-export (PM-tool payloads),
agent-workflow-designer (executable workflow export), spec-driven-workflow
(feature-sized leaves).

## Anti-Patterns (mined)

| Anti-pattern | Symptom | Root cause | Fix |
|---|---|---|---|
| Activity-oriented decomposition (PMI Practice Standard for WBS, 3rd ed.) | Leaves are verbs ("do testing", "coordinate vendors") with no acceptance signal; endless percent-complete debates | The calendar of activities was decomposed instead of the scope of deliverables | Rename every leaf to the deliverable it produces plus an observable acceptance signal; validator G1 flags leaves with no `deliverable` field |
| Single-child decomposition / 100-percent-rule break (PMI 3rd ed. quality characteristics) | A parent with exactly one child that restates it; "found scope" surfaces mid-execution | Decomposition stopped at the first obvious sub-item, or a level was added for cosmetic numbering | Every non-leaf carries >= 2 children (validator B1); if no second child can be named, the parent already is the work package - delete the level |
| Mixed decomposition bases at one level (NASA/SP-2016-3404/REV1, common WBS development errors) | Siblings mix product nouns ("auth module") with lifecycle phases ("testing") and org units ("marketing") | Each contributor decomposed along the axis they know best | Pick one basis per level (product, phase, or discipline) and re-sort offenders before validating |
| Level-of-effort buckets (NASA/SP-2016-3404/REV1) | Elements like "project management" or "misc support" that never finish, have no definable deliverable, and silently absorb overruns | Ongoing overhead was modeled as if it were decomposable scope | Move LOE outside the deliverable tree, or attach explicit periodic deliverables (e.g. "monthly status report published") |
| Overlapping siblings / double-counted scope (GAO-20-195G, WBS chapter) | The same output claimed by two branches; rolled-up cost exceeds the real total | Decomposing by department AND by product simultaneously | Enforce mutual exclusivity: validator X1/X2 flags exact and near-duplicate descriptions; assign each output exactly one parent |
| Monolithic non-modular chunks (Flyvbjerg & Gardner, "How Big Things Get Done", 2023) | One leaf hides months of bespoke work; estimates are pure inside view; nothing is repeatable | The project was treated as one big thing instead of many small repeatable modules | Decompose to repeatable module boundaries; the 80-hour upper bound (H1, `--check-estimates`) is the tripwire |
| Micro-task confetti (PMI 8/80 heuristic; Standish CHAOS granularity findings) | Hundreds of sub-day leaves; tracking overhead exceeds the work; the plan lags reality within a week | The WBS was confused with a to-do list or activity log | Keep leaves within 8/80 (H1 lower bound); defer far-future detail via rolling-wave elaboration instead of decomposing it now |

## When NOT to Use

| You actually need | Use instead (sibling skill, by name) |
|---|---|
| Precedence edges, `depends_on` population, cycle/topology analysis of a task list | critical-path-scheduler |
| Calendar dates, critical path, float, delivery-date math | critical-path-scheduler |
| Adversarial review of plan realism, forgotten steps, biased estimates | plan-critique |
| Feature-level requirements (FR/NFR, acceptance criteria) for one leaf | spec-driven-workflow |
| Exporting an approved plan as Jira/Asana/Trello payloads | plan-ticket-export |
| Baseline-vs-actual variance tracking after approval | plan-baseline-tracking |
| Designing executable multi-agent workflow steps from the approved plan | agent-workflow-designer |
| Retrieving org policies/history to ground the decomposition | rag-architect (composed at agent level - never imported here) |

Routing is by skill name only. This skill never path-references, imports, or
executes another skill folder; agents compose skills one level up.

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs, delegated to framework skills -
verify against current docs): in CrewAI, planning-style runs emit a typed
plan model before execution (see crewai-role-engineering); in LangGraph, a
MANIFEST node writes the plan into typed state ahead of an `interrupt()`
human gate (see langgraph-state-design); in Microsoft Agent Framework, the
plan travels as a JSON-schema-typed workflow message (see
microsoft-agent-framework). Prompting shape for decomposition (chain-of-
thought breakdown, structured output) is cited from senior-prompt-engineer.
None of that runtime wiring is duplicated here.

**STATIC TRACK** (how this hub uses the skill): a git-versioned WBS markdown
plus canonical `plan.json`, validated offline by `wbs_validator.py`, and
presented as the Phase-2 MANIFEST at the Phase-3 HUMAN GATE. The emitted
tasks array uses the same minimal id/depends_on contract that
hitl_gate_validator rule R5 enforces on workflow Definition blocks, so an
approved plan flows downstream with zero reshaping.

## References

- `references/wbs_decomposition_methodology.md` - the in-skill knowledge
  base: 100-percent rule, orientation choice, granularity heuristics,
  rolling wave, decomposition procedure.
- `references/plan_json_contract.md` - the hub canonical plan.json contract,
  duplicated into this skill per the portability rule (never referenced
  cross-skill).
- PMI, *Practice Standard for Work Breakdown Structures*, 3rd edition
  (2019) - WBS quality characteristics. External standard: verify against
  the current PMI edition.
- PMI, *PMBOK Guide*, 6th edition (2017), process 5.4 "Create WBS"; and
  *PMBOK Guide*, 7th edition (2021) - decomposition technique and
  rolling-wave planning. Verify against current docs.
- ISO 21502:2020, scope definition / work breakdown clauses. Verify against
  the current ISO revision.
- NASA, *Work Breakdown Structure Handbook*, NASA/SP-2016-3404/REV1 -
  common WBS development errors catalog.
- GAO, *Cost Estimating and Assessment Guide*, GAO-20-195G, WBS chapter -
  best-practice violations from federal program audits.
- Flyvbjerg & Gardner, *How Big Things Get Done* (2023) - modularity
  evidence from the megaproject cost-overrun database.
- Standish Group, CHAOS reports - scope-decomposition and granularity
  failure statistics. Verify against current editions.
- Hub canon: hitl_gate_validator rule R5 (id/depends_on contract) and the
  5-Phase Protocol - cited by name as authority, never called from this
  skill.

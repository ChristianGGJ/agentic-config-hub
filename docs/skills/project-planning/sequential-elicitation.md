---
title: "Sequential Elicitation: Bounded Two-Way Scope Questioning — Project Planning & Requirements Elicitation"
description: "Use when an underspecified idea or brief must become a validated scope record through a bounded two-way dialogue -- one question at a time derived. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Sequential Elicitation: Bounded Two-Way Scope Questioning

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-text-clock: Project Planning & Elicitation</span>
<span class="meta-badge">:material-identifier: `sequential-elicitation`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/sequential-elicitation/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install project-planning</code>
</div>


**Tier:** STANDARD
**Category:** Planning / Discovery
**Dependencies:** None. `scripts/elicitation_ledger.py` is Python 3.8+ standard library only - offline, deterministic, no LLM or network calls.

## Description

Sequential-elicitation owns exactly one transformation: **(initial brief +
open-concern agenda) -> validated elicited-scope record**, produced through
a bounded, adaptive, sequential dialogue. One question per turn (max 3 only
when tightly coupled), each derived from the answer just given, open
questions funneling to closed confirmations - never a 20-question batch
form. Every exchange appends to a JSONL ledger; between exchanges a
deterministic governor decides whether asking another question is still legal.

The split is strict, per the hub algorithm-over-AI principle: **the LLM
generates questions**, guided by `references/sequential_questioning_method.md`
(funnel design, contextual chaining, neutral phrasing, deferral/escalation
protocol) - no script generates questions, since a "question generator CLI"
would need the LLM call hub script rules forbid. **The governor**
(`scripts/elicitation_ledger.py`) **governs the loop**: per-area coverage vs
the agenda, saturation, decision-key oscillation, question budget, success
predicate, escalation markers. Same inputs, same verdict, every run, offline.

The agenda is source-agnostic by design: hand-written, or seeded
deterministically from a blind-spot-audit `blind_spot_report.json` (the
`--seed-from` mapping is documented below). The output scope record drops
into spec-driven-workflow Phase 1 answers and wbs-decomposition input at
agent level - by data shape, never by file reference. The skill runs as an
extended Phase 1 DISCOVERY (read-only except appending the ledger) with a
hard stop before Phase 2 MANIFEST; it contains no personas, no
orchestration, and no HITL gates of its own - gates belong to the consuming
workflow.

### Sequential vs Batch: Two Modes, Not a Turf War

The hub already has a batch-context convention: prompt-governance gathers
its few well-known context slots "in one shot" - the correct mode when the
questions are enumerable in advance. This skill is the OTHER mode:

| Dimension | Batch (prompt-governance convention) | Sequential (this skill) |
|-----------|--------------------------------------|-------------------------|
| When | Few, well-known context slots | Unknown unknowns at high-ambiguity idea stage |
| Question source | Fixed checklist | Derived from the previous answer |
| Cost model | One interruption | Budgeted turns (default 12) |
| Failure mode guarded | Missing slot | Satisficing fatigue, anchoring, premature closure |
| Stop rule | Form complete | Six-type exit taxonomy, governor-enforced |

## Features

- **Deterministic loop governor** - `elicitation_ledger.py` checks all six
  hub exit types every run, names the fired one(s), never generates questions
- **Per-area coverage accounting** - questions asked, facts gathered,
  coverage percent vs the agenda's `expected_questions`, and a
  resolved / open / deferred / untouched status per area
- **Saturation detection** - K consecutive records with empty `new_facts`
  (default 3) fires `no_progress`: the interviewee has nothing new, stop
- **Oscillation freeze** - a decision key revisiting an abandoned value
  within a ring buffer of its last 4 assignments fires `oscillation`;
  remedy: freeze-and-escalate with both prior answers, never re-asking
- **Question budget** - `max_iterations` at 12 by default (agenda- and
  CLI-overridable); optional wall-clock ceiling `--max-minutes` fires `budget`
- **Agenda seeding** - `--seed-from` converts a blind_spot_report.json
  findings list into an agenda deterministically (covered findings skipped)
- **Golden-tested assets** - healthy, saturated, and oscillating sample
  ledgers ship with expected analyzer outputs; zero cross-skill dependencies

## Interface

### Inputs

1. **Initial brief** - the underspecified idea (consumed by the LLM only).
2. **Agenda JSON** (`--agenda`) - open concern areas:

```json
{"brief": "customer-portal-launch", "budget": {"max_questions": 12},
 "areas": [{"id": "BS-01", "criticality": "CRITICAL",
            "concern": "Payment handling and PCI-DSS obligations are absent",
            "expected_questions": 2}]}
```

Seedable from a blind-spot-audit report (`--seed-from`); mapping:
`finding.id -> area.id`, `finding.severity -> area.criticality`,
`finding.concern -> area.concern`, status `covered` skipped,
`expected_questions` = 2 for CRITICAL/HIGH else 1, `prerequisite_note` kept.

3. **Elicitation ledger JSONL** (`--ledger`) - one record per exchange,
   append-only, `seq` strictly increasing:

```json
{"seq": 1, "timestamp": "2026-07-10T09:00:00", "area": "BS-01",
 "question": "Walk me through what happens today when a customer pays...",
 "answer_summary": "All payments run through an external PSP...",
 "new_facts": ["existing PSP handles all card payments"],
 "decision_key": "pci_scope=psp-only", "areas_remaining": ["BS-01", "BS-02", "BS-03", "BS-04", "BS-05"]}
```

Optional extras: `deferrals` (`[{"area", "owner"}]`) and `escalation`
(string reason or `true`). Extra fields are tolerated - the convention of
the hub plan contract that `hitl_gate_validator` rule R5 enforces.

4. **The live human**, through whatever gate the host provides (chat turn,
   `interrupt()`, `human_input`, request/response port, MCP elicitation).

### Outputs

1. **Governor report** - agenda coverage table, six exit-condition checks
   with evidence, warnings (off-agenda questioning), verdict CONTINUE/STOP
   with the fired condition(s) named, and a suggested next AREA (never a
   next question). `--json` emits the full report object. On STOP the
   report says which condition fired: stop means stop and report.
2. **Elicited-scope record** (authored by the LLM at closure) - resolved
   decisions per area, explicit deferrals each with a named owner, verbatim
   user constraints; feeds spec-driven-workflow Phase 1 and
   wbs-decomposition input downstream.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | CONTINUE permitted - no exit condition fired |
| 1 | STOP - an exit condition FIRED (named in the report); includes `success_predicate`, because stopping on success is still stopping |
| 2 | Usage or input error - malformed ledger, agenda, or flag value |

**Convention decision, stated loudly:** exit 1 here is a *semantic
stop-signal*, not an input defect. Two in-repo precedents existed:
self-eval's `score_history.py` uses 0/2/1 (signal on 2), while
plan-baseline-tracking, `loop_auditor.py`, and `hitl_gate_validator.py` use
the hub-wide 0/1/2 = pass / gate-signal / input-error contract. This skill
follows the hub-wide contract so loop harnesses and CI treat every
planning-family tool identically; every STOP names its fired condition in
both text and `--json` output, so exit 1 is never ambiguous. The same note
appears prominently in the script's `--help`.

## Usage

The between-exchanges loop (static track):

```bash
# 0. Seed the agenda from a blind-spot report (or hand-write agenda.json)
python scripts/elicitation_ledger.py \
    --seed-from assets/sample_blind_spot_report.json > agenda.json

# 1. Before every question: is another exchange legal?
python scripts/elicitation_ledger.py --agenda agenda.json --ledger ledger.jsonl

# exit 0 -> the LLM asks ONE question (max 3 tightly coupled), guided by
#           references/ and the report's suggested next area; the human
#           answers; append ONE ledger record; run the governor again
# exit 1 -> STOP: hand the report + ledger to the consuming workflow's gate
# exit 2 -> fix the inputs; this is a data defect, not a dialogue state

# 2. Machine-readable, with a wall-clock ceiling and a widened predicate
python scripts/elicitation_ledger.py --agenda agenda.json --ledger ledger.jsonl \
    --max-minutes 45 --require-all --json
```

Loop discipline: the governor runs between exchanges, so the budget can
never be overrun by more than the in-flight question. All six exit types
are checked on every run and OR-ed (a guard subset is the documented
failure mode in hub canon). Any agent embodying this loop must still pass
`loop_auditor.py --min-score 90` - this skill supplies dialogue semantics,
not agent hardening.

## Examples

### Example 1: healthy mid-dialogue ledger (exit 0)

```bash
python scripts/elicitation_ledger.py --agenda assets/sample_agenda.json \
    --ledger assets/sample_ledger_healthy.jsonl
```

Output (trimmed; full golden copy in `assets/expected_healthy_report.txt`):

```
AGENDA COVERAGE
  area   crit       questions  facts  coverage  status
  BS-01  CRITICAL           2      4      100%  resolved
  BS-02  CRITICAL           2      3      100%  open
  ...
  closed 1 of 5 area(s) (20%)
  [clear] max_iterations     5 of 12 question(s) used
VERDICT: CONTINUE - next area: BS-02 (CRITICAL, 2 question(s) so far)
```

### Example 2: saturation fires no_progress (exit 1)

```bash
python scripts/elicitation_ledger.py --agenda assets/sample_agenda.json \
    --ledger assets/sample_ledger_saturated.jsonl
```

The last 3 records carry empty `new_facts`; golden copy in
`assets/expected_saturated_report.txt`:

```
  [FIRED] no_progress        last 3 record(s) (seq 5, 6, 7) yielded zero new_facts - the dialogue is saturated
VERDICT: STOP - fired: no_progress
```

### Example 3: decision flip fires oscillation (exit 1)

`assets/sample_ledger_oscillating.jsonl` records `retention_period` moving
24-months -> 12-months -> 24-months (`assets/expected_oscillating_report.txt`):

```
  [FIRED] oscillation        key 'retention_period' revisits an abandoned value: 24-months -> 12-months -> 24-months (seq 1, 2, 3) - freeze the key(s), present both prior answers, and escalate for an explicit override; do not re-ask
VERDICT: STOP - fired: oscillation
```

## Anti-Patterns (Mined)

Each row traces to a named source in References; none is generic advice.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Twenty-question batch form (Krosnick 1991) | Answers degrade to "yes / fine / whatever" halfway down the form; late answers contradict early ones | Cognitive load front-loaded; respondents shift from optimizing to satisficing | One question per turn, budget 12; max-3 batches only when same area AND same decision key |
| Anchoring by narrow opener (Tversky and Kahneman 1974) | Every answer orbits the interviewer's first guess; genuine constraints never surface | The first specific frame anchors all later judgments | Funnel rule: open context-free questions (Gause and Weinberg 1989) before any closed or quantified question |
| Leading questions (BABOK v3 Elicitation KA) | Ledger full of confirmations of what the interviewer already believed | Question embeds the expected answer ("you'll want Stripe, right?") | Neutral phrasing discipline in `references/`; solutions offered by the interviewee are recorded as constraints-to-verify, not requirements (Volere) |
| Interrogation drift (Fisher and Geiselman 1992) | Rapid-fire closed questions; interviewee stops elaborating; `new_facts` thins out | Interviewer controls the exchange instead of transferring control | Open-before-specific staging, no interrupting; saturation detector makes the thinning measurable and stops the loop |
| Premature closure (BABOK v3: unconfirmed elicitation results; ISO/IEC/IEEE 29148:2018 verifiability) | Areas marked resolved that reopen during planning; scope record contradicts the transcript | Dialogue ends when the interviewer feels done; nothing echoed back for confirmation | An area leaves `areas_remaining` only after a closed confirmation turn; `success_predicate` is computed from the ledger, never from vibes |
| Re-asking a flipped decision (Schuman and Presser 1981 consistency pressure; hub oscillation canon) | The same question re-asked hoping for a stable answer; ledger shows A-B-A-B | A changed mind treated as noise to re-poll; consistency pressure produces a fake stable answer | Ring-buffer oscillation check (window 4) freezes the key and escalates with both prior answers; override requires a stated reason |
| Question worth less than its interruption (Horvitz 1999; Rao and Daume 2018) | Budget burned on questions whose answers change nothing | No value-of-information test before asking | Every question must target an open agenda area with a plausible record-changing answer; empty-fact streaks fire `no_progress` |
| Interviewing only the loudest voice (Robertson and Robertson 2012, trawling pitfalls) | Whole ledger reflects one persona; quiet domains (ops, legal) stay untouched | Convenience sampling of answers; agenda drifts to whoever is present | Agenda seeded from blind-spot findings keeps unrepresented areas visible as `untouched`; stakeholder identification routes to stakeholder-inference |
| Scripted question generator (hub script rules) | A reviewer requests a CLI that outputs the next question | Conflating loop governance (deterministic) with question generation (language work) | The governor names the next AREA only; question text is the LLM's job, guided by `references/` - the split is stated here so nobody builds the impossible CLI |

## When NOT to Use

Routing table - sibling skills by name only; composition happens at
agent/workflow level.

| If you need to... | Use instead |
|-------------------|-------------|
| Detect WHAT a brief forgot (generate the concern areas) | blind-spot-audit |
| Identify WHO is affected (actors, register) | stakeholder-inference |
| Gather a few well-known context slots in one shot | prompt-governance (batch convention; see the contrast table above) |
| Author the feature spec from the elicited scope | spec-driven-workflow |
| Decompose the elicited scope into a task hierarchy | wbs-decomposition |
| Critique a drafted plan's realism | plan-critique |
| Stress-test a plan with failure scenarios | plan-premortem |
| Compute dates, floats, critical path | critical-path-scheduler |
| Track execution against the approved baseline | plan-baseline-tracking |
| Decide how to answer a slip mid-execution | slip-driven-replanning |
| Export the resulting plan as tickets | plan-ticket-export |
| Question-phrasing prompt technique (roles, few-shot) | senior-prompt-engineer |
| Loop mechanics, exit taxonomy canon, loop audits | loop-engineering-mechanisms / agentic-system-architect |
| Persist the ledger across sessions (stores, memory) | hybrid-rag-memory - this skill owns dialogue semantics, not where state lives |
| MCP elicitation protocol depth | mcp-server-builder |

## Dual-Track Note

**FRAMEWORK TRACK** (runtime pause/resume constructs owned by framework
skills - verify against current docs): host the bounded cycle as a LangGraph
`interrupt()` loop with a durable checkpointer, since the human may answer
hours later (see langgraph-state-design); a CrewAI Flow with a bounded
router wrapping `human_input=True` (see crewai-role-engineering); Microsoft
Agent Framework request/response ports with a ledger guard (see
microsoft-agent-framework); or the MCP `elicitation` client capability, spec
revision 2025-06-18 (see mcp-server-builder). None of that wiring is
duplicated here.

**STATIC TRACK** (how this hub uses the skill offline): the dialogue runs
in chat as an extended Phase 1 DISCOVERY - read-only except appending the
git-versioned `ledger.jsonl`; `elicitation_ledger.py` governs the loop
between exchanges; the elicited-scope record IS the input to the Phase 2
MANIFEST, so "gates before execution" holds by construction; a dialogue
spanning days survives in git history, the static track's durable checkpointer.

## References

In-skill knowledge bases:

- `references/sequential_questioning_method.md` - the six questioning rules,
  Socratic funnel mapping, phrasing discipline, deferral/escalation protocol
- `references/ledger_and_exit_conditions.md` - ledger/agenda contracts,
  seeding mapping, exit conditions for dialogue, exit-code decision record

Source literature (edition-pinned; external standards marked):

- IIBA, BABOK v3 (2015), Elicitation and Collaboration KA - verify against
  current edition
- Robertson, S. and Robertson, J., Mastering the Requirements Process, 3rd
  ed., Addison-Wesley, 2012 (Volere trawling techniques)
- ISO/IEC/IEEE 29148:2018, Requirements engineering - external standard,
  verify against current revision
- Paul, R. and Elder, L., The Thinker's Guide to the Art of Socratic
  Questioning, Foundation for Critical Thinking, 2006 (2016 ed.)
- Gause, D. and Weinberg, G., Exploring Requirements: Quality Before Design,
  Dorset House, 1989 (context-free questions)
- Fisher, R. and Geiselman, R., Memory-Enhancing Techniques for
  Investigative Interviewing: The Cognitive Interview, C.C. Thomas, 1992
- Krosnick, J., "Response Strategies for Coping with the Cognitive Demands
  of Attitude Measures in Surveys", Applied Cognitive Psychology 5, 1991
- Schuman, H. and Presser, S., Questions and Answers in Attitude Surveys,
  Academic Press, 1981
- Tversky, A. and Kahneman, D., "Judgment under Uncertainty: Heuristics and
  Biases", Science 185, 1974; Horvitz, E., "Principles of Mixed-Initiative
  User Interfaces", CHI '99, 1999
- Rao, S. and Daume III, H., "Learning to Ask Good Questions", ACL 2018
  (expected value of perfect information for clarification questions)
- Model Context Protocol specification, revision 2025-06-18, `elicitation`
  client capability - verify against current docs

Hub canon (cited by name as authority, never imported or path-referenced):

- loop_engineering_patterns.md (agentic-system-architect flagship) - the
  six-type exit-condition taxonomy, guard-subset failure mode, and the
  ledger/ring-buffer counter design duplicated into the governor
- hitl_gate_validator rule R5 - the extra-fields-tolerated contract
  convention the ledger mirrors
- self-eval - score_history.py JSONL-analyzer pattern donor (its 0/2/1 exit
  variant evaluated and not adopted, see Exit codes) and the constraint that
  self-assessed confidence is a reading, never a loop gate

# Ledger Contract and Dialogue Exit Conditions

The data contracts and loop-governance rules for the sequential-elicitation
skill. The deterministic governor `scripts/elicitation_ledger.py` enforces
everything in this file; the questioning method itself lives in
`sequential_questioning_method.md`.

## The Elicitation Ledger (JSONL)

One JSON object per line, append-only, git-versionable. Required fields:

```json
{"seq": 3,
 "timestamp": "2026-07-10T09:09:00",
 "area": "BS-02",
 "question": "Moving to personal data: which customer fields does the portal collect at signup?",
 "answer_summary": "Signup collects name, email, company, and VAT id.",
 "new_facts": ["signup fields: name, email, company, VAT id"],
 "decision_key": "signup_data=invoicing-minimum",
 "areas_remaining": ["BS-02", "BS-03", "BS-04", "BS-05"]}
```

| Field | Type | Rule |
|-------|------|------|
| `seq` | int | Strictly increasing across lines; a non-increasing seq is an input error (append-only discipline) |
| `timestamp` | str | ISO 8601; a trailing `Z` is tolerated (stripped before parse - `datetime.fromisoformat` rejects it before Python 3.11) |
| `area` | str | The agenda area id this exchange targeted |
| `question` | str | The question as asked (verbatim) |
| `answer_summary` | str | Faithful compression of the answer |
| `new_facts` | [str] | Facts not previously in the record; whitespace-only entries count as empty. This field drives saturation detection - fill it honestly |
| `decision_key` | str | `key=value` when the exchange settled (or changed) a decision; empty string when it settled nothing. This field drives oscillation detection |
| `areas_remaining` | [str] | The areas still open AFTER this exchange; an area's exit from this list is what marks it resolved |

Optional extra fields (tolerated, semantics defined here):

| Field | Type | Meaning |
|-------|------|---------|
| `deferrals` | [{`area`, `owner`}] | The named person/role who now owns an unresolvable area; a deferral without a non-empty owner is ignored |
| `escalation` | str or bool | The answer revealed irreversible or compliance territory; any truthy value fires `escalation_trigger` |

Any additional fields ride along untouched (the hub-wide extra-fields-
tolerated convention, mirroring the `id`/`depends_on` contract that
`hitl_gate_validator` rule R5 enforces on workflow plans).

## The Agenda (JSON)

```json
{"brief": "customer-portal-launch",
 "budget": {"max_questions": 12},
 "areas": [
   {"id": "BS-01", "criticality": "CRITICAL",
    "concern": "Payment handling and PCI-DSS obligations are absent",
    "expected_questions": 2}
 ]}
```

- `areas[].id` - unique, non-empty. `criticality` - CRITICAL|HIGH|MEDIUM|LOW.
- `expected_questions` (default 1) - the planned questioning effort for the
  area; per-area coverage percent = questions asked / expected, capped at 100.
- `budget.max_questions` - optional; the CLI `--max-questions` overrides it,
  and the default is 12.
- The agenda is source-agnostic: hand-written, or seeded from any upstream
  findings list.

### Seeding from a blind_spot_report.json

`elicitation_ledger.py --seed-from blind_spot_report.json` converts a
blind-spot-audit report deterministically. The mapping:

| blind_spot_report finding | agenda area |
|---------------------------|-------------|
| `id` | `id` |
| `severity` | `criticality` |
| `concern` | `concern` |
| `status` = `covered` | SKIPPED (nothing to elicit) |
| `status` = `missing` / `partial` | included; carried through as `source_status` |
| `severity` CRITICAL/HIGH | `expected_questions` = 2, else 1 |
| `prerequisite_note` (non-null) | carried through as `prerequisite_note` |

## The Six Exit Conditions, Instantiated for Dialogue

Taxonomy authority: `loop_engineering_patterns.md` in the
agentic-system-architect flagship (hub canon, cited by name; the taxonomy is
duplicated here per the portability rule, never imported). All six are
checked on every governor run and OR-ed - implementing a guard subset is the
documented "guard subset" failure mode in that canon.

| Type | Dialogue instantiation | Governor check |
|------|------------------------|----------------|
| `max_iterations` | Question budget consumed | `len(records) >= max_questions` (default 12) |
| `no_progress` | Saturation: the interviewee has nothing new | Last K records (default 3) all have empty `new_facts` |
| `oscillation` | A decision flips A-B-A-B | A decision key revisits an abandoned value within a ring buffer of its last 4 assignments |
| `budget` | Wall-clock ceiling | Minutes between first and last record exceed `--max-minutes` (disabled unless set) |
| `success_predicate` | Goal met | Every CRITICAL area resolved (left `areas_remaining` after being asked) or deferred with a named owner; `--require-all` widens to every area; if the agenda has no CRITICAL area the predicate covers all areas |
| `escalation_trigger` | Irreversible/compliance territory revealed | Any record carries a truthy `escalation` field |

Notes:

- **Oscillation fires an escalation, not a re-ask.** The governor's message
  says it explicitly: freeze the key, present both prior answers, request an
  explicit override with a reason. A legitimately changed mind survives this
  (the override is one turn); an interviewer badgering a flip-flopping
  answer does not.
- **`success_predicate` stopping is still stopping.** The governor exits 1
  on success like on any other fired condition, because the loop contract is
  binary: continue permitted, or stop and report. The report names WHICH
  condition fired; the consuming workflow branches on that name.
- **Self-assessed confidence is never a stop condition.** Per the self-eval
  skill's hub-protocol constraint, an LLM's own confidence score is a
  reading presented at the gate, never the loop gate itself. The six
  conditions above are all computed from ledger evidence.

## Exit-Code Contract (and why it deviates from one in-repo precedent)

| Code | Meaning |
|------|---------|
| 0 | CONTINUE permitted - no exit condition fired |
| 1 | STOP - one or more exit conditions FIRED (each named in the report). Semantic stop-signal, not an input defect. Includes `success_predicate` |
| 2 | Usage or input error - malformed ledger/agenda/flag |

Two in-repo precedents existed: the hub-wide 0/1/2 = pass / gate-signal /
input-error contract (plan-baseline-tracking's `baseline_variance.py`,
`loop_auditor.py --min-score`, `hitl_gate_validator.py`) and self-eval's
`score_history.py` 0/2/1 variant (0 clean / 2 signal / 1 error). This skill
follows the hub-wide contract so CI recipes and loop harnesses can treat
every planning-family tool identically; the deviation risk (a caller
misreading exit 1 as "broken input") is mitigated by naming the fired
condition on every STOP, in both text and `--json` output.

## Wiring the Governor into a Loop

The static-track loop shape (pseudocode; the LLM turn is the only
non-deterministic step):

```
agenda  = seed or hand-write agenda.json          # once
ledger  = empty JSONL file                        # once
while True:
    run: elicitation_ledger.py --agenda agenda.json --ledger ledger.jsonl
    if exit == 2: fix inputs (data defect, not a dialogue state)
    if exit == 1: STOP; hand report + ledger to the consuming gate
    # exit == 0: one more exchange is legal
    LLM asks the next question (references/ method; governor's next_area
    is the suggested target), human answers, append ONE record
```

The governor runs BETWEEN exchanges, so the budget can never be overrun by
more than the single in-flight question - and with `max 3 tightly coupled`
batching, by at most one batch. Any agent embodying this loop must still
pass `loop_auditor.py --min-score 90` (hub merge gate); this skill supplies
the dialogue semantics, not the agent hardening.

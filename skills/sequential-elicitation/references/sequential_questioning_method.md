# Two-Way Sequential Contextual Questioning

The question-craft knowledge base for the sequential-elicitation skill. This
is the material the LLM uses to GENERATE questions; the deterministic
governor (`scripts/elicitation_ledger.py`) never generates anything - it only
decides whether asking another question is still legal. Keep that split: the
method lives here, the brakes live in the script.

Sources are pinned in SKILL.md References. The method below is synthesized
from the requirements literature (BABOK v3 Elicitation and
Collaboration KA; Robertson and Robertson's Volere trawling; ISO/IEC/IEEE
29148:2018), investigative-interviewing research (Fisher and Geiselman's
cognitive interview), survey methodology (Krosnick; Schuman and Presser),
judgment research (Tversky and Kahneman), mixed-initiative interface theory
(Horvitz), and the Socratic questioning taxonomy (Paul and Elder).

## The Six Rules

### Rule 1 - One question at a time (max 3 when tightly coupled)

Ask exactly one question per turn. A batch of up to 3 is permitted ONLY when
the questions are tightly coupled: same agenda area AND same decision key,
where answering one without the others would be meaningless (for example:
"who owns rollback, and through which mechanism?"). Never batch across areas.

Rationale: Krosnick (1991) shows respondents under cognitive load shift from
optimizing to satisficing - acceptable-looking answers instead of accurate
ones. A 20-question form front-loads the entire load; answer quality decays
measurably down the page. Sequential delivery keeps per-turn load near
constant.

### Rule 2 - Two-way contextual chaining

Every question after the first must visibly build on a prior answer: quote
or paraphrase what the interviewee said, then extend it ("You said the
portal must stay out of PCI scope - does that rule out last-four display?").
Two-way means the answers reshape the agenda, not just fill it: a surprising
answer may open an emergent area (append it to the agenda), close a planned
one, or trigger a deferral.

Rationale: the cognitive interview (Fisher and Geiselman, 1992) demonstrates
that interviewer follow-ups anchored in the interviewee's own account
retrieve more, and more accurate, material than a fixed script. Chaining
also proves the interviewer listened, which sustains engagement across the
budget.

### Rule 3 - Funnel: open, then probing, then closed confirmation

Each area moves through three stages:

| Stage | Question form | Socratic category (Paul and Elder) |
|-------|---------------|------------------------------------|
| Opening | Open narrative: "walk me through...", "what happens today when..." | Questions of clarification |
| Probing | Targeted follow-ups on the answer's gaps: assumptions, evidence, consequences | Questions that probe assumptions, reasons and evidence, implications |
| Confirming | Closed verification: "confirming for the record: X?" | Questions about viewpoints; questions about the question |

Never open an area with a closed or leading question. Gause and Weinberg
(1989) call the safe openers "context-free questions" - questions that make
no assumption about the solution ("who is affected when this fails?" works
for any project).

Rationale: Tversky and Kahneman (1974) - the first frame anchors everything
after it. A narrow opening question anchors the interviewee to the
interviewer's guess instead of their own knowledge.

### Rule 4 - Sequence design is load-bearing

General before specific. Non-threatening before sensitive. One area's
confirmation before the next area's opening (do not interleave half-open
areas). Schuman and Presser (1981) document order effects: the same question
yields different answers depending on what preceded it, and earlier answers
create consistency pressure on later ones. Choose the order deliberately;
the governor's `next_area` suggestion ranks by criticality, then by fewest
questions asked - override it only with a stated reason in the ledger.

### Rule 5 - Every question must be worth its interruption

Before asking, the question must (a) target an open agenda area and (b) have
a plausible answer that changes a decision or adds a new fact. Horvitz
(1999) frames this as the ask-vs-act cost calculus; Rao and Daume (2018)
operationalize it as expected value of perfect information - rank candidate
questions by how much their answer would change the record. A question whose
every possible answer leaves `new_facts` empty should not be asked; three of
those in a row and the governor fires `no_progress`.

### Rule 6 - Confirm before closing

An area is resolved only when its decisions have been echoed back and
confirmed (BABOK v3: confirm elicitation results; ISO/IEC/IEEE 29148:2018:
requirements must be verifiable and unambiguous before they are baselined).
The closing record for an area should carry the confirmation in
`answer_summary` and drop the area from `areas_remaining`. Unconfirmed
closure is the "premature closure" defect mined in SKILL.md Anti-Patterns.

## Question Phrasing Discipline

- Neutral, not leading: "which provider handles payments?" - never "you'll
  want Stripe, right?" (BABOK v3 interview pitfalls).
- Do not interrupt an elaborating answer; capture extras as `new_facts` and
  mine them for follow-ups (cognitive interview: transfer control).
- Mark solutions offered by the interviewee as constraints-to-verify, not
  requirements: "you said 'use a cron job' - what outcome must that achieve?"
  (Volere: separate the essence from the incarnation).
- One idea per question. Compound questions get half-answers.
- Prompt-technique layer (role framing, few-shot exemplars for question
  style) is owned by the senior-prompt-engineer skill - cite it, do not
  restate it here.

## Deferral and Escalation Protocol

- **Deferral**: when an area cannot be resolved by the person in the
  dialogue, record `"deferrals": [{"area": "...", "owner": "<named person or
  role>"}]` on the ledger record. A deferral without a named owner does not
  count - the success predicate ignores it.
- **Escalation**: when an answer reveals irreversible or compliance
  territory (production data already touched, regulated data classes, legal
  exposure), set `"escalation": "<reason>"` on the record. The governor
  fires `escalation_trigger` and the loop hard-stops for a human.
- **Oscillation freeze**: when the governor reports a decision key flipping
  A-B-A-B, do NOT re-ask the question. Present both prior answers verbatim,
  name the flip, and request an explicit override with a reason - from a
  human with authority over the key, not from the same dialogue that
  produced the flip.

## Worked Micro-Example

Agenda area BS-02 ("retention policy undefined", CRITICAL):

1. Opening (open, context-free): "Which customer fields does the portal
   collect at signup, and is any of it beyond what invoicing needs?"
2. Probing (chained on the answer): "Given those fields, how long must
   records be kept after closure, and who signs off on deletion?"
3. The answer names a period but no owner: record the fact, keep BS-02 in
   `areas_remaining`, and either probe for the owner or defer to a named
   role.
4. Confirming: "Confirming for the record: retention is 24 months, deletion
   runbook deferred to the DPO?" - on confirmation, drop BS-02 from
   `areas_remaining` and add the deferral record.

Between every step, run the governor. It will tell you whether step N+1 is
legal - and when it says STOP, stop and report.

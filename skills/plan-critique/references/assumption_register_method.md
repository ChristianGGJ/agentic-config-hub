# The Assumption Register Method

Knowledge base for the **Assumption Hunter** persona: how to extract the
premises a plan silently rests on, force each one to carry evidence and an
invalidation test, and keep the register alive instead of letting it rot.

Method sources: the Key Assumptions Check from intelligence-analysis
tradecraft (Heuer 1999; Heuer & Pherson 2020), the PMBOK assumption log and
its documented write-once failure mode (PMBOK Guide 6th ed., section
11.2.2.3), and measurement discipline from Hubbard (2014).

## Register contract

One entry per premise, in `assumptions.json`
(see `assets/assumption-register-template.json`):

```json
{
  "id": "ASM-1",
  "statement": "claim that can be false",
  "type": "estimate | dependency | capability | technical | external-commitment",
  "evidence_source": "document, dataset, or named commitment",
  "invalidation_test": "cheapest observation that would prove it false",
  "owner": "person accountable for re-testing",
  "last_reviewed": "YYYY-MM-DD",
  "affected_task_ids": ["T4"]
}
```

Field discipline, mapped to the AS lints in `plan_audit.py`:

| Field | Rule | Lint |
|-------|------|------|
| evidence_source | Where the belief comes from - never a restatement of the belief | AS1 (HIGH) |
| invalidation_test | A designed observation, cheap and early, that would falsify it | AS2 (HIGH) |
| owner | A person, accountable for re-testing and escalation | AS3 (MEDIUM) |
| last_reviewed | Refreshed at every replan; stale dates are flagged | AS4 (LOW/MEDIUM) |
| (register itself) | An absent or empty register is a mandatory CRITICAL finding | AS5 (CRITICAL) |

## The Key Assumptions Check (Heuer & Pherson)

Run BEFORE commitment, not after - a check run after the plan is socially
locked degenerates into rubber-stamping (Heuer's documented failure mode).

1. **Extract.** Read the plan asking of every task and estimate: "what must
   be true for this to hold?" Write each answer as a falsifiable statement.
   Vague premises ("the team is strong") are rewritten until testable or
   discarded as unactionable.
2. **Classify.** Tag each assumption with one type: `estimate` (a number is
   right), `dependency` (someone else delivers), `capability` (we can do X),
   `technical` (the approach works), `external-commitment` (a third party
   holds their promise).
3. **Challenge.** For each: How confident are we, and on what evidence? What
   would make it false? How would we notice, and how early? What breaks if it
   fails - which `affected_task_ids`?
4. **Verdict.** SUPPORTED (evidence cited), CONTRADICTED (evidence against -
   the plan must change), UNTESTABLE-CRITICAL (cannot be tested AND the plan
   dies if false - escalate to the human gate), UNTESTABLE-ACCEPTABLE
   (cannot be tested but the blast radius is tolerable - record acceptance).
5. **Re-run at every replan** and refresh `last_reviewed`. The register's git
   history is its episodic memory.

## Designing invalidation tests (Hubbard)

The reflex "it cannot be tested" is usually false - Hubbard (2014) shows most
"immeasurable" premises yield to a cheap observation, and that measurement
effort is habitually inverted: the highest-stakes premises get the least of
it. Design the test by asking: what is the cheapest thing we could observe
in the next N days that would make this assumption LESS likely? Examples:

- external-commitment: request the deliverable artifact (credentials, a
  signed date) far ahead of need; silence is the early signal.
- estimate: compare against one reference-class datapoint pulled from
  history (compose with the Pessimist-PM persona).
- technical: a time-boxed spike on the riskiest slice, not the easiest.

## Anti-patterns from the sources

- **Assumption stated as fact** - "the vendor API will be ready" with empty
  evidence (Heuer & Pherson; confirmation bias per Nickerson 1998: the
  evidence search stopped at the first supporting datum). AS1 catches the
  empty field; the persona catches weak-but-present evidence.
- **Rubber-stamp check** - the challenge step confirms instead of attacks;
  every verdict comes back SUPPORTED. Inherited countermeasure (duplicated
  from the adversarial-reviewer skill's pattern): the review MUST produce at
  least one finding - if the register is genuinely solid, name the most
  fragile assumption as a LOW note.
- **Write-once log** - PMBOK's assumption log filled at kickoff and never
  re-tested against actuals (PMBOK 6th ed. 11.2.2.3). AS4 makes staleness
  visible; the re-run rule fixes it.
- **Vague verdicts** - "probably fine" cannot be scored or acted on
  (Tetlock & Gardner 2015). Verdicts come only from the four-value set.

## Sources (pinned)

- Heuer, R. J. (1999). Psychology of Intelligence Analysis. CIA Center for
  the Study of Intelligence.
- Heuer, R. J. & Pherson, R. H. (2020). Structured Analytic Techniques for
  Intelligence Analysis, 3rd ed. CQ Press. (Key Assumptions Check.)
- PMBOK Guide, 6th ed. (2017). PMI. Section 11.2.2.3, assumption and
  constraint analysis. (Verify against current PMI edition.)
- Nickerson, R. S. (1998). "Confirmation Bias: A Ubiquitous Phenomenon in
  Many Guises." Review of General Psychology 2(2).
- Tetlock, P. & Gardner, D. (2015). Superforecasting. Crown.
- Hubbard, D. (2014). How to Measure Anything, 3rd ed. Wiley.

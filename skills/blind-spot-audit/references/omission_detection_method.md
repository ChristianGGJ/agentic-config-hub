# Omission Detection Method

Expert knowledge base for blind-spot-audit: why omissions happen, why a
taxonomy scan beats a brainstorm, how the deterministic floor and the LLM
semantic ceiling divide the work, and the wording rules that keep reports
honest.

## 1. The mechanism: why briefs have blind spots

**The inside view.** Kahneman and Tversky (1979) showed that planners predict
by building a mental simulation of the case at hand rather than consulting
the distribution of comparable cases. The simulation contains only what the
author can picture - WYSIATI, "What You See Is All There Is" (*Thinking,
Fast and Slow*, 2011, ch. 23). A founder picturing an online ceramics store
pictures the pots, the photos, the Instagram feed. Shipping labels, payment
gateway onboarding, returns policy, and a DPIA are not in the picture, so
they are not in the brief.

**Omission is systematic, not random.** Flyvbjerg, Holm and Buhl (2002)
demonstrated across hundreds of public-works projects that underestimation
patterns are too consistent to be honest error: the elements that vanish are
disproportionately the ones that would weaken the case ("error or lie").
Flyvbjerg and Gardner (2023) extend the evidence base to 16,000+ projects.
Consequence for tooling: the checklist must be *fixed data the author cannot
quietly edit*, and the report must rank by severity, not by narrative.

**The industrial precedent.** HAZOP (IEC 61882:2016) exists because
guide-word-driven deviation analysis finds hazards that unstructured expert
brainstorming misses. Blind-spot-audit is HAZOP's discipline applied to
project scope: the profile concern list is the guide-word set, and every
concern is examined one by one, with the sweep itself recorded (covered,
partial, missing, and skipped-not-triggered all appear in the output).

## 2. The two finding families

**Scope omissions** - concern domains the artifact never addresses. The
online store with no logistics, payment, or returns evidence. These become
plan tasks once acknowledged (decomposition routes to wbs-decomposition by
name).

**Hidden prerequisites** - conditions that must be TRUE before work starts,
not merely tasks to add somewhere. Carried on the finding as
`prerequisite_note`, which states the ordering ("X must exist BEFORE Y") and
cites its source. Canonical examples:

| Prerequisite | Must precede | Source |
|--------------|--------------|--------|
| Lawful basis documented (GDPR Art. 6) | any personal-data collection | ICO BA/Marriott penalties, 2020 |
| DPIA completed (GDPR Arts. 25/35) | building the customer database | same |
| DPA signed (GDPR Art. 28) | third-party processor access | same |
| Vendor security review | vendor access/data grant | NIST SP 800-37 Rev. 2 ordering |
| Operator training | cutover/go-live | Hershey SAP/Siebel 1999 |
| Verified restore path | production data existing | operations canon |

In `--plan` mode the anchor is concrete: the trigger evidence names the task
(e.g. "trigger evidence 'customer database' in task T1") and the remedy is a
predecessor task wired via `depends_on` - the same `id`/`depends_on` contract
hub canon `hitl_gate_validator` rule R5 enforces (cited as authority, never
imported).

## 3. Floor and ceiling: the algorithm-over-AI split

**The floor (deterministic scanner).** `coverage_gap_scanner.py` guarantees:
every concern in every applied profile received an explicit status; every
status carries evidence; the same artifact, profiles, and flags produce the
same report, offline, every run. This is what makes the audit CI-wireable
and non-negotiable: a brief cannot skip the sweep by being charming.

**The floor's ceiling.** A regex cannot read "parcels reach buyers within
three days" as shipping evidence, and it cannot tell "be GDPR compliant"
(name-drop) from a real lawful-basis decision. This is the same documented
limit as the deterministic-critic ceiling in hub canon
self_reflection_critique_loops.md: deterministic checkers verify structure
and presence, never semantics.

**The ceiling (LLM semantic pass).** Run AFTER the scanner, guided by this
file, under these rules:

1. The machine report is never edited. Semantic judgments live in an
   annotated copy beside it; floor/ceiling disagreement is signal.
2. Upgrades (missing/partial -> covered) require a verbatim quote from the
   artifact recorded as evidence. No quote, no upgrade.
3. Downgrades (covered -> partial) at CRITICAL/HIGH require the quote that
   shows thinness (the name-drop test: does the match record a decision, or
   just a word?).
4. The pass may add findings for concern areas absent from every profile -
   flagged as `profile-gap` so the profile owner can extend the taxonomy
   (profiles are user-extensible assets; see the authoring guide).
5. If the pass runs inside an agent loop, the loop declares its exit
   conditions from the hub six-type taxonomy (max_iterations, no_progress,
   oscillation, budget, success_predicate, escalation_trigger) before
   iteration 1 - loop mechanics are hub canon (agentic-system-architect, by
   name), never rebuilt here, and report counts are readings, never exit
   conditions.

## 4. Status and severity discipline

- `covered` - at least `covered_min` distinct indicator patterns matched.
  Means "evidence present", never "handled well".
- `partial` - some evidence, below the threshold. The concern was touched,
  not addressed.
- `missing` - zero indicator matches. Means "no evidence found", NEVER
  "proven missing" - the report prints this disclaimer even when clean.
  A conscious exclusion belongs in the artifact ("returns handled by the
  marketplace partner"), where it becomes scannable evidence - the
  N/A-with-reason idiom (spec-driven-workflow pattern, duplicated).
- Skipped-not-triggered concerns are listed, not hidden: the reader must see
  what the sweep chose not to evaluate and why.

Severity is assigned in the profile, per concern, on one question: *what
happens if this stays unaddressed until launch?* CRITICAL = launch fails or
creates legal exposure (no payments; no lawful basis). HIGH = launch limps
and rework is expensive (no returns policy; no DPA). MEDIUM = friction and
cost (no VAT plan yet). LOW = polish. Severity never encodes probability -
that is plan-premortem's likelihood axis, a different skill.

## 5. Report consumers

- **sequential-elicitation** - every non-covered finding carries a
  `seed_question`; the ranked findings are its opening agenda.
- **CI / consuming workflow** - exit 1 blocks the merge; the report is
  presented at the workflow's human gate (gates before execution - the gate
  lives in the workflow, never in this skill).
- **wbs-decomposition / critical-path-scheduler** - acknowledged omissions
  and prerequisites become tasks and predecessor edges downstream.
- **self-improving-agent** - recurring findings across audits ("every
  e-commerce brief forgets returns") are candidates for its human-gated
  rule-promotion lifecycle (cited by name; nothing rebuilt here).

## 6. Wording rules (keep every report honest)

1. Never write "the brief is missing X" - write "no evidence of X was found".
2. Never present exit 0 as completeness; quote the disclaimer.
3. Every claim cites its evidence: matched text and location, or the
   explicit zero-match statement.
4. Prerequisite notes state the ordering and the source, and regulatory
   content always carries "verify against current regulation and
   jurisdiction" - this skill is not legal advice.

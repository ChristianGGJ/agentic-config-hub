# Prospective Hindsight: The Klein Premortem Method

Expert knowledge base for the plan-premortem skill. Sources are edition-pinned
in the SKILL.md References section; external standards are marked "verify
against current docs" there.

## 1. What a premortem is (and is not)

A premortem (Klein, "Performing a Project Premortem", Harvard Business Review,
September 2007) inverts the postmortem: instead of asking "what could go
wrong?" before execution, the team is told that the plan HAS ALREADY FAILED
and must explain why. The tense shift is the entire mechanism.

- A premortem is NOT a risk brainstorm. "We might be late" is a brainstorm
  output. "It is November 30 and we launched six weeks late because the
  supplier missed the production checkpoint" is a premortem output.
- A premortem is NOT a forecast. Scenarios are stress vectors, not
  probability-weighted predictions (Schoemaker 1995; Wack 1985).
- A premortem is NOT risk management during execution. It ends at an
  approved plan delta; tracking indicators at runtime belongs elsewhere.

## 2. The evidence base

Mitchell, Russo and Pennington ("Back to the Future: Temporal Perspective in
the Explanation of Events", Journal of Behavioral Decision Making 2(1), 1989)
found that explaining an outcome as if it had already happened (prospective
hindsight) produced roughly 30 percent more specific reasons than explaining
it as merely possible. Dropping the past-tense framing forfeits the effect -
which is why the register validator warns when a narrative never asserts
failure as accomplished fact.

Kahneman and Lovallo ("Delusions of Success", Harvard Business Review, July
2003) document the advocacy pressure that sandbags pre-execution reviews:
plan authors defend the plan instead of attacking it. The premortem's
legitimizing frame ("the plan failed; you are reporting, not criticizing")
is the countermeasure - but only if scenario authorship is separated from
plan ownership.

## 3. The protocol (adapted for this hub)

1. FREEZE THE PLAN INPUT. The premortem runs against a concrete plan.json
   (canonical hub task shape: tasks[] with id, description, depends_on).
   No plan, no premortem.
2. BUILD THE STRESSOR AXES. Pick 2-4 dimensions the plan is most exposed to
   (external dependencies, demand, key people, regulation) and give each
   discrete levels including at least one tail magnitude. Flyvbjerg and
   Gardner (How Big Things Get Done, 2023) show project outcomes are
   fat-tailed: "demand_multiplier: 3x" belongs on the axis; "+10 percent"
   does not stress anything.
3. EXPAND DETERMINISTICALLY. scenario_matrix_expander.py turns the axes spec
   into the cartesian scenario matrix. Cap it with --max-scenarios; the cap
   always prints an explicit truncation notice. Schoemaker's pitfall list
   warns against scenario sprawl - a dozen decision-relevant cells beat a
   thousand unread ones.
4. ASSERT THE FAILURE. For each cell, the author (a human, or one fanned-out
   agent per cell - fan-out execution is delegated to the agenthub skill)
   writes the narrative in past tense: "It is <date>. The plan failed
   because...". Mechanism, not blame (Google SRE Book, ch. 15: blameless
   framing keeps enumeration candid).
5. RATE AND LINK. Assign likelihood (low/medium/high) and impact
   (low/medium/high/critical) bands, record the basis (evidence with a
   citation, or explicitly marked judgment), name the early-warning signal,
   and link a contingency trigger to a concrete plan task id.
6. MITIGATE OR ACCEPT. Every scenario at or above the severity threshold
   gets a mitigation expressed as a plan delta (new task, buffer, gate) or
   an explicit accepted_by entry naming the person accepting the risk.
7. GATE DETERMINISTICALLY. premortem_register_validator.py enforces the
   structural contract. Exit 0 is a floor, not proof the scenarios are
   plausible - plausibility is agent and human work.
8. HAND OFF. The plan delta goes to the consuming workflow's human approval
   gate before it becomes the new baseline. The gate lives in the workflow,
   never inside this skill.

## 4. Rating discipline

IEC 60812:2018 (FMEA) supplies the ranking discipline and its documented
misuses:

- Bands are ORDINAL. Do not multiply likelihood by impact into a fake
  numeric priority (the RPN rank-product fallacy). Rank by band pair.
- Every rating carries a basis: "evidence" (with the data cited in the
  evidence field) or "judgment" (explicitly marked). Unmarked ratings
  invite fabricated likelihoods.
- Detection matters: a scenario without an early-warning signal cannot be
  caught early no matter how well it is ranked - which is why the signal
  is a hard validator requirement, not an optional nicety.

## 5. Failure-mode seeds from real failure studies

Use these documented mechanisms to seed axes and narratives:

| Mechanism | Source | Axis it suggests |
|-----------|--------|------------------|
| Normalization of deviance: near-misses reclassified as normal | Vaughan, The Challenger Launch Decision (1996) | recurring-warning-ignored axis |
| Organizational silence under schedule pressure | Columbia Accident Investigation Board Report Vol. 1 (2003) | schedule-pressure axis |
| Single point of knowledge walks out | Google SRE Book (2016), postmortem culture chapter | key_person_loss axis |
| External dependency slips beyond contract remedy | GAO schedule audits (recurring finding) | supplier_delay axis |
| Demand outruns capacity planning | Flyvbjerg and Gardner (2023) fat-tail data | demand_multiplier axis |

## 6. Boundaries

- Testing whether a plan's PREMISES hold against evidence is assumption
  audit work, not premortem work: a premortem simulates futures, an
  assumption audit issues verdicts on existing claims.
- The premortem ends at the approved plan delta. Consuming contingency
  triggers during execution (watching indicators, firing replans) is
  execution-tracking territory.
- Loop mechanics for autonomous premortems (exit conditions, iteration
  bounds, critique identity) are hub canon owned by the flagship
  agentic-system-architect references (loop_engineering_patterns.md,
  self_reflection_critique_loops.md) and the loop-engineering-mechanisms
  skill. This skill supplies the method, never the loop chassis.

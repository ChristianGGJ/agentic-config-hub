# Replan Decision Patterns

Expert knowledge base for the slip-driven-replanning skill. Sources are
version-pinned in SKILL.md References; external standards carry
"verify against current docs".

## 1. Classify the cause before choosing a strategy

A replan that does not name the slip cause repeats it. The skill's
`cause_class` enum maps to distinct corrective families:

| cause_class | Typical evidence | Strategy bias | Strategy trap |
|-------------|------------------|---------------|---------------|
| estimate | task ran long with no external event | re-anchor on reference class (Flyvbjerg); widen remaining estimates | optimistic re-forecast: re-estimating with the same inside view |
| dependency | upstream deliverable late or changed | fast-track or resequence; renegotiate the interface | compressing the victim task instead of the late feeder |
| resource | owner unavailable, contention | level or swap resources; only then consider crash | Brooks's Law: adding people to late sequential work |
| scope | requirements grew mid-task | descope or split; route growth to change control | absorbing scope silently until the milestone breaks |
| external | vendor, legal, weather, outage | buffer and escalate; the loop cannot fix externals | replanning repeatedly around an unresolved external |

Goldratt's student syndrome and Parkinson's Law are estimate-class causes:
they consume padding invisibly, so a replan that adds more padding feeds
the same behavior. Track float consumption instead of hiding it.

## 2. The decision ladder

Ordered from cheapest to most irreversible. The scripts implement the
first three deterministically; the last two are always human decisions.

1. **ABSORB** - the slip fits in total float; project finish and all
   milestone deadlines hold. No plan change, no notification. Log the
   ledger entry and move on (buffer management, not replanning).
2. **COMPRESS / fast-track** - overlap activities whose dependency is
   discretionary rather than mandatory. Cost: rework risk. First resort
   per PMBOK schedule-compression guidance.
3. **COMPRESS / crash** - add resources to critical-path tasks. Cost:
   money plus Brooks's-Law exposure; effective only on divisible work
   with low coordination overhead. Never a default recommendation.
4. **REBASELINE** - accept the new dates as the new commitment through
   change control. Legitimate only with documented cause, approval at a
   human gate, and the old baseline retained (GAO-16-89G criteria).
   A rebaseline that erases variance history is the rubber-baseline
   anti-pattern.
5. **DESCOPE / renegotiate** - shrink scope or move the milestone.
   Contractual milestones make this a stakeholder decision, never an
   autonomous one.

## 3. Milestone hardness

Escalation content depends on what kind of promise is breaking:

- **contractual** - external commitment with penalties; breach always
  escalates with the strongest wording and never auto-resolves.
- **internal** - organizational commitment; breach escalates but the
  gate may trade it against other work.
- **aspirational** - stretch target; breach informs, and treating it
  like a contract date produces false alarms that train recipients to
  ignore real ones.

The registry therefore REQUIRES the hardness field. Implicit milestones
(flag on the task, baseline finish as deadline) are marked `unspecified`
and should be upgraded to registry entries as soon as hardness is known.

## 4. Bounding the replan loop

Replanning is a loop and inherits every loop pathology. Bind it with the
hub six-type exit taxonomy (duplicated verbatim in SKILL.md):

- `max_iterations`: cap replan cycles per slip event (default 3).
- `no_progress`: two consecutive recomputes with no finish-delta
  improvement means the strategy is wrong, not the effort.
- `oscillation`: replan-revert-replan within a window of 4 ledger
  entries; a plan that flips back and forth is negotiating with itself.
- `budget`: the hosting agent's token/time ceiling.
- `success_predicate`: `replan_impact.py` exits 0 (ABSORB) against the
  approved baseline.
- `escalation_trigger`: `replan_impact.py` exits 1 with ESCALATE.

The `replan_ledger` written by `slip_injector.py` is the shared attempt
counter. It never resets: a replan that zeroes its own ledger has
disabled its `max_iterations` exit (the "replan-as-reset" pathology).

## 5. Notification content rules

The draft is payload text, not delivery. Rules for what it must say:

- Name the trigger task, the delay, and the cause verbatim.
- State both dates and the delta; never a bare "we are late".
- Name each breached milestone WITH its hardness class.
- Offer the gate options (compress candidates, rebaseline via change
  control, descope) instead of a single fait accompli.
- State explicitly that no plan changes have been applied yet -
  "watermelon reporting" starts when notifications imply decisions
  already made.
- Keep the payload neutral: tool-specific formatting (Jira ADF, Asana,
  Trello) belongs to the plan-ticket-export skill, and transmission is
  an irreversible act that happens only after the human gate.

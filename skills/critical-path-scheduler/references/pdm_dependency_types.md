# PDM Dependency Types: FS / SS / FF / SF, Leads and Lags

Expert knowledge base for the critical-path-scheduler skill. Sources are
edition-pinned; external standards evolve - verify against current docs.

Primary sources:

- PMBOK Guide, 6th edition (PMI, 2017), Process 6.3 "Sequence Activities" -
  the canonical definition of the Precedence Diagramming Method (PDM),
  the four relationship types, leads/lags, and dependency classification.
  (PMBOK 7th edition, 2021, restructured away from process chapters; the
  scheduling detail moved to the PMI Practice Standard line. Cite the 6th
  edition for these definitions and verify against current PMI docs.)
- PMI Practice Standard for Scheduling, 3rd edition (2019) - schedule model
  quality attributes and relationship usage guidance.

## The Precedence Diagramming Method (PDM)

PDM represents a schedule network as activities-on-nodes with typed
precedence relationships on the edges. Every edge connects a predecessor
to a successor and carries one of four relationship types plus an optional
lead or lag.

## The four relationship types

| Type | Name | Meaning | Example |
|------|------|---------|---------|
| FS | Finish-to-Start | Successor cannot START until predecessor FINISHES | Code review starts after code is written |
| SS | Start-to-Start | Successor cannot START until predecessor STARTS | Documentation drafting starts once implementation starts |
| FF | Finish-to-Finish | Successor cannot FINISH until predecessor FINISHES | Testing cannot finish until defect fixing finishes |
| SF | Start-to-Finish | Successor cannot FINISH until predecessor STARTS | Old system decommission finishes only after the new system starts (rare; PMBOK 6th ed. calls it "very rarely used") |

FS is the default and the overwhelmingly dominant type in healthy networks.
DCMA guidance (see `dcma_graph_hygiene.md`) expects FS relationships to be
at least 90 percent of all edges; heavy SS/FF usage usually signals
activities that should have been decomposed further.

## Leads and lags

- **Lag**: mandatory waiting time inserted on a relationship. "FS + 3d"
  means the successor starts 3 days after the predecessor finishes
  (concrete curing, legal cooling-off periods).
- **Lead** (negative lag): successor starts before the predecessor finishes.
  "FS - 2d" overlaps the two activities by 2 days (fast-tracking).

Hazards (mined into the skill's Anti-Patterns section):

- Lags hide work. A 10-day lag named "procurement wait" is invisible to
  status tracking; DCMA expects lags on no more than 5 percent of edges.
- Leads hide risk. Starting a successor before its input exists is a bet;
  DCMA expects zero leads.

## Dependency classification (PMBOK 6th ed.)

| Class | Definition | Handling |
|-------|-----------|----------|
| Mandatory (hard logic) | Physically or contractually required | Never remove; document why |
| Discretionary (soft/preferred logic) | Team preference or best practice | Mark it; first candidate to relax when compressing the schedule |
| External | Depends on a party outside the project | Model it explicitly as a task (a vendor delivery is a task with a duration, not an invisible lag) |
| Internal | Within the project team's control | Default class |

Classification matters for critical-path work: a critical path running
through discretionary edges is compressible; one running through mandatory
or external edges is not.

## Mapping PDM onto the hub depends_on contract

The hub canonical plan shape (`tasks[].depends_on`) expresses exactly one
relationship type: **FS with zero lag**. That is a deliberate contract
decision - it is the same minimal id/depends_on graph that hub rule R5
(hitl_gate_validator.py, agentic-system-architect) enforces on workflow
Definition blocks, so validated plans instantiate into workflows without
reshaping. `cpm_scheduler.py` therefore treats every edge as FS zero-lag.

Modeling recipes for the other constructs, staying inside the contract:

1. **SS relationship**: split the predecessor. "impl starts when design
   starts" becomes design-kickoff (1d) -> impl, and design-kickoff ->
   design-completion.
2. **FF relationship**: split the successor. "testing finishes with
   fixing" becomes fixing -> final-test-pass, where final-test-pass is the
   tail of the testing work.
3. **Lag**: model the wait as an explicit task ("concrete-curing", 5d).
   This is strictly better than a lag: the wait becomes visible, ownable,
   and trackable - which is why DCMA discourages lags in the first place.
4. **Lead / fast-tracking**: split the predecessor at the point where the
   successor can genuinely start, and hang the successor off the first
   part. The overlap becomes explicit structure instead of a negative
   number.
5. **SF relationship**: almost always a modeling smell; restate the
   requirement. PMBOK's own example (shift handover) is modeled cleanly as
   new-shift-start -> old-shift-end via a renamed FS pair.

These recipes lose no scheduling power: any PDM network with SS/FF/SF and
integer lags can be rewritten as an FS zero-lag network by task splitting
(each activity becomes at most a start-node and finish-node pair).

## Working-day durations

`duration_days` in the hub contract are **elapsed working days**, not
person-days or calendar days:

- Working days: the calendar engine maps them onto the configured workweek
  and skips holidays. 5 working days spanning a weekend take 7 calendar
  days.
- Not person-days: two people on a 6-working-day task do not make it a
  3-day task (Brooks, The Mythical Man-Month, 1975/1995 anniversary ed.).
  Effort-to-duration conversion happens upstream during estimation.
- Zero duration marks a milestone (an event, not work). The scheduler pins
  a milestone to the finish date of its latest predecessor.

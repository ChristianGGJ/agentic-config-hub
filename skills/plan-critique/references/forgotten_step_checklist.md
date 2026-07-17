# The Forgotten-Step Checklist

Knowledge base for the **Completeness Auditor** persona. Plans fail not only
through bad estimates but through missing work: whole lifecycle phases that
were never priced in because the task list was built from the delivery
narrative, not from a full-lifecycle breakdown.

Mining sources: the GAO Cost Estimating and Assessment Guide (GAO-20-195G)
documents, from real federal program audits, that estimates routinely omit
standard WBS elements (test and evaluation, training, data, disposal);
Standish Group CHAOS reports and PMI Pulse of the Profession surveys list
incomplete requirements and unrealistic schedules among the recurring named
causes of project failure. (External standards - verify against current
editions.)

## The checklist

Walk every row against the task list. For each missing step, write the
finding with the concrete failure scenario - not "plan is incomplete" but
"here is the day this omission detonates".

| # | Step | Detection question | Typical failure scenario when missing | plan_audit.py |
|---|------|--------------------|----------------------------------------|---------------|
| 1 | Testing / QA | Is there a task whose deliverable is a verification result? | First end-to-end test happens in production; defect found by a customer with no budgeted fix time | PC1 (CRITICAL) |
| 2 | Legal / compliance review | Is there a named approver task for legal, licensing, privacy, regulatory? | Objection arrives at release week, after all engineering budget is spent | PC2 (HIGH) |
| 3 | Deployment / rollout | Is the cutover planned: window, environment checklist, owner? | Go-live becomes an unplanned emergency under pressure | PC3 (HIGH) |
| 4 | Training / handoff | Does the receiving team appear as an acceptance signal? | First incident handled by people who have never seen the system | PC4 (MEDIUM) |
| 5 | Security review | Is there a security assessment before exposure to real traffic/data? | Vulnerability found post-launch forces an unplanned remediation sprint | persona only |
| 6 | Procurement lead times | Do purchased dependencies (licenses, hardware, vendor onboarding) have their own tasks? | A six-week vendor onboarding surfaces two weeks before it is needed | persona only |
| 7 | Data migration | Is moving/transforming existing data a task with an owner and a rehearsal? | Migration discovered to be lossy on cutover night | persona only |
| 8 | Rollback / contingency | Does the rollout task name a rollback path? | A failed release cannot be reversed; outage extends for days | persona only |
| 9 | Documentation | Is user/operator documentation a deliverable somewhere? | Support burden lands on the build team indefinitely | persona only |
| 10 | Decommissioning the old system | Is switching OFF the replaced system planned? | Two systems run in parallel forever, doubling operating cost | persona only |

Rows 1-4 are structurally checkable and automated as PC1-PC4. Rows 5-10 are
persona-only: their vocabulary is too project-specific for keyword presence
checks to be honest.

## How to challenge

For each missing row, the Completeness Auditor asks in order:

1. Is the step genuinely not needed for this plan (defensible exclusion), or
   was it forgotten? Demand the exclusion be stated in the plan, not assumed.
2. If it was forgotten: who does the work, how long does it take, and which
   existing task must now wait for it? A forgotten step is not just a new
   task - it is a new dependency chain.
3. Does the addition move any milestone? If yes, the estimate conversation
   restarts (hand the numbers to the Pessimist-PM persona).

## Keyword ceiling (honesty note)

PC1-PC4 detect phase vocabulary, not phase reality. A task named "testing"
that is 0.5 days of "developer clicks around" passes PC1 and fails this
checklist. Conversely, a plan that calls its QA phase "certification run"
may fire PC1 falsely - suppress the finding at the persona layer and record
why, rather than renaming real work to satisfy a keyword list.

## Sources (pinned)

- GAO (2020). Cost Estimating and Assessment Guide, GAO-20-195G. U.S.
  Government Accountability Office. WBS chapter and standard-element
  omissions. (Verify against current edition.)
- Standish Group. CHAOS reports. Named failure causes: incomplete
  requirements, unrealistic time frames. (Verify against current reports.)
- PMI. Pulse of the Profession. Surveyed failure causes: requirements,
  sponsorship, unrealistic schedules. (Verify against current edition.)
- Flyvbjerg, B. & Gardner, D. (2023). How Big Things Get Done. Currency.
  (Monolithic, non-modular plans hide missing steps longest.)

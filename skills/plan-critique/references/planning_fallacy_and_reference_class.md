# Planning Fallacy and Reference-Class Forecasting

Knowledge base for the **Pessimist-PM** persona. This is the estimate-attack
rubric: how optimistic single-point estimates are produced, why they survive
review, and the outside-view procedure that corrects them.

## The defect: inside-view estimation

Kahneman & Tversky (1979) named the planning fallacy: when people estimate a
task, they build a best-case narrative of *this singular case* - the steps as
imagined, with no interruptions, no rework, no dependencies slipping - and
read the estimate off that narrative. Distributional evidence about how long
similar work *actually* took is ignored, even when the estimator personally
lived through the overruns.

Empirical anchor: Buehler, Griffin & Ross (1994) had students predict thesis
completion. The average prediction was 33.9 days; the average actual was 55.5
days. Fewer than half finished by their own "worst case" estimate. The
pattern is systematic, not noise: predictions track the plan, outcomes track
the base rate.

Flyvbjerg, Holm & Buhl (2002) added the darker mechanism for organizational
plans: **strategic misrepresentation**. In their dataset of 258 transport
infrastructure projects, cost underestimation was found in ~90% of projects
and had not improved over 70 years - consistent with estimates shaped to win
approval, not to be accurate ("error or lie"). A basis-free estimate on an
approval-critical task should therefore be presumed advocacy until re-derived.

## The correction: reference-class forecasting (outside view)

Flyvbjerg (2006) operationalized Kahneman & Tversky's corrective procedure as
reference-class forecasting (RCF), later adopted in the UK Green Book
guidance and APM practice (verify against current literature):

1. **Identify the reference class** - completed projects/tasks similar to the
   one being estimated. Similar in kind, not in team enthusiasm: "backend
   integrations we shipped", not "things we felt good about".
2. **Establish the outcome distribution** - actual durations/costs of the
   class, from records the user supplies (delivery logs, timesheet exports,
   postmortems). Get the spread, not just the mean.
3. **Position this task in the distribution** - place the estimate at a
   defensible percentile and record WHY. Adjust from the class base rate, not
   from the inside-view narrative.

The output of the procedure is exactly what the `estimate_basis` field in the
hub plan contract exists to hold: the named class, the base-rate figure, and
the adjustment applied.

## Hard rule: never invent base rates

The persona demands a reference class; it must never fabricate one. If no
historical data exists, the honest finding is "estimate has no reference
class and none is available" (that is itself a HIGH finding), not a made-up
percentage. Historical actuals are retrieved upstream - document corpora via
the rag-architect skill, prior-project episodic history via the
hybrid-rag-memory skill - and composed at agent level, never fetched by this
skill's script.

## Pessimist-PM challenge questions

For every task carrying `duration_days`:

- What is the reference class for this number? Name the completed work items.
- What did the class actually take, distributionally? Where in that spread is
  this estimate positioned, and why?
- Is the basis an inside-view artifact ("team judgment", "engineering
  estimate", "gut feel")? PRESENT but inside-view basis passes `plan_audit.py`
  PC5 and must still be rejected here - this is the semantic layer.
- Who benefits if this estimate is low? (Flyvbjerg's error-or-lie test.)
- If this task took 2x its estimate - the ordinary planning-fallacy outcome,
  not a tail event - which milestone breaks first?

## Mapping to plan_audit.py

| Deterministic check | What it catches | What it cannot catch |
|---------------------|-----------------|----------------------|
| PC5 (estimate without basis) | `duration_days` with empty `estimate_basis` | A present-but-worthless basis ("team judgment") |
| PC8 (duration outlier) | A task far from its sibling median | Uniformly optimistic siblings (all equally wrong) |

Both blind spots belong to this persona. Exit 0 from the script never means
the estimates are realistic.

## Sources (pinned)

- Kahneman, D. & Tversky, A. (1979). "Intuitive Prediction: Biases and
  Corrective Procedures." TIMS Studies in Management Science 12.
- Kahneman, D. (2011). Thinking, Fast and Slow. Farrar, Straus and Giroux,
  ch. 23-24.
- Buehler, R., Griffin, D. & Ross, M. (1994). "Exploring the planning
  fallacy." Journal of Personality and Social Psychology 67(3).
- Flyvbjerg, B., Holm, M. S. & Buhl, S. (2002). "Underestimating Costs in
  Public Works Projects: Error or Lie?" JAPA 68(3).
- Flyvbjerg, B. (2006). "From Nobel Prize to Project Management: Getting
  Risks Right." Project Management Journal 37(3). (RCF procedure - verify
  against current literature.)
- Flyvbjerg, B. & Gardner, D. (2023). How Big Things Get Done. Currency.
  (Fat-tailed overrun distributions by project class.)

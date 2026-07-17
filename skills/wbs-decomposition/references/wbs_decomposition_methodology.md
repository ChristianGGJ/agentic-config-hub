# WBS Decomposition Methodology

Knowledge base for turning a macro objective into a defensible Work
Breakdown Structure. Sources are edition-pinned at the bottom; external
standards should be verified against current docs before citing them in
client-facing material.

## 1. What a WBS is (and is not)

A WBS is a hierarchical decomposition of the **total scope** of work into
deliverable-oriented elements. Its leaves (work packages) are the units that
get estimated, assigned, and tracked.

A WBS is NOT:

- a schedule (no dates, no ordering - that is precedence and CPM work),
- a to-do list (leaves are deliverables, not reminders),
- an org chart (structure follows scope, not reporting lines),
- a requirements spec (a leaf may later expand into FR/NFR detail, but the
  WBS records THAT the deliverable exists, not HOW it behaves).

## 2. The three load-bearing rules

### 2.1 The 100-percent rule

The children of any element must capture 100 percent of that element's
scope - no more, no less. Everything in scope appears exactly once;
anything not in the tree is, by definition, out of scope.

Structural proxy: a parent with a single child cannot satisfy the rule
non-trivially (the child either equals the parent or scope is missing).
`wbs_validator.py` check B1 therefore requires >= 2 children per non-leaf.

Honest limit: code can enforce the proxy, not the rule. Whether the children
of "Portal build" truly cover all of building the portal is a semantic
judgment for adversarial review (plan-critique) and the human gate.

### 2.2 Mutual exclusivity

No two elements may cover the same scope. Overlap double-counts cost and
blurs accountability. Structural proxy: duplicate or near-duplicate
descriptions (checks X1/X2). Semantic overlap with different wording still
requires human review.

### 2.3 Deliverable orientation

Elements are outcomes (nouns with acceptance signals), not activities
(verbs). "Signed requirements register" is checkable; "gather requirements"
is arguable. Check G1 warns on leaves without a `deliverable` field.

## 3. Choosing a decomposition basis

Pick ONE basis per level and keep siblings homogeneous:

| Basis | Split by | Fits when |
|---|---|---|
| Product / system | components, modules, subsystems | building a thing with architecture |
| Phase / lifecycle | discovery, build, verify, launch | process-dominated efforts |
| Discipline | engineering, legal, marketing | cross-functional programs |

Mixing bases among siblings is the classic NASA-cataloged error: the branch
becomes impossible to roll up because siblings answer different questions.
Different levels may use different bases (phases at level 2, products at
level 3) - that is normal and fine.

## 4. Granularity heuristics

- **8/80 rule**: a work package should represent roughly 8 to 80 hours of
  effort. Below 8, tracking overhead exceeds the work - roll up. Above 80,
  estimation error explodes and progress becomes opaque - decompose.
  Enforced (when estimates are present) by check H1 with configurable
  bounds.
- **Depth 2-4**: fewer than 2 levels means the objective was not decomposed;
  more than 4 levels usually signals micro-management or premature detail.
  Enforced by check D1 with configurable bounds.
- **Reporting-period test**: if a work package spans more than one or two
  status periods, progress reports degrade into percent-guessing.
- **Single-owner test**: a work package with no single accountable owner is
  usually two packages wearing one id.

## 5. Rolling-wave elaboration

Do not fake detail you do not have. Near-term branches decompose to work
packages now; far-future branches stay one level coarse and carry an
explicit elaboration trigger ("decompose after architecture spike lands").
Record the decision in the WBS file so reviewers see deferral, not
omission. Re-run the validator after each elaboration wave - depth and
branching rules apply to every wave equally.

## 6. Decomposition procedure (operational)

1. Write the objective in 1-3 sentences plus an explicit exclusions list.
2. Choose the level-2 basis (product, phase, or discipline).
3. Split the root into 2-7 children; check the 100-percent rule aloud:
   "if all children complete, is the parent done - with nothing left over?"
4. Recurse per branch until leaves pass the 8/80 and single-owner tests.
5. Name every leaf as a deliverable with an observable acceptance signal.
6. Attach `estimate_hours` and `estimate_basis` to each leaf (basis values
   like "analogous", "three-point", "expert judgment" keep the estimate
   auditable later).
7. Serialize (nested or flat JSON), run `wbs_validator.py`, fix findings.
8. Emit `plan.json` with `--emit-tasks` and hand both artifacts to the
   Phase-3 human gate as the manifest.

## 7. Quality checklist before the gate

- [ ] Exit code 0 from `wbs_validator.py` (with `--check-estimates` if
      estimates exist)
- [ ] Every leaf names a deliverable and an acceptance signal
- [ ] One decomposition basis per level
- [ ] Exclusions list present and reviewed
- [ ] Rolling-wave deferrals recorded explicitly
- [ ] Estimates carry a basis, not just a number

## 8. Pinned sources

- PMI, *Practice Standard for Work Breakdown Structures*, 3rd ed. (2019) -
  quality characteristics, 100-percent rule. Verify against current edition.
- PMI, *PMBOK Guide*, 6th ed. (2017), process 5.4 "Create WBS"; 7th ed.
  (2021) for the principles reorganization. Verify against current docs.
- ISO 21502:2020, scope definition clauses. Verify against current revision.
- NASA, *Work Breakdown Structure Handbook*, NASA/SP-2016-3404/REV1 -
  common development errors (mixed bases, LOE buckets, non-deliverable
  elements).
- GAO, *Cost Estimating and Assessment Guide*, GAO-20-195G, WBS chapter -
  audit-derived best-practice violations.
- Flyvbjerg & Gardner, *How Big Things Get Done* (2023) - modularity and
  repeatability evidence from megaproject data.
- Standish Group, CHAOS reports - granularity and scope-failure statistics.
  Verify against current editions.

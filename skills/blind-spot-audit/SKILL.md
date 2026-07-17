---
name: "blind-spot-audit"
description: "Use when auditing a project idea/brief or a draft plan.json for blind spots before planning proceeds - scanning the artifact against domain-profile taxonomies (ecommerce, data-privacy, legal-compliance, procurement-vendor, operations-support) to produce a ranked report of missing scope domains and hidden prerequisites (e.g. GDPR obligations that must hold BEFORE a customer database is built), optionally cross-checked against a stakeholder register."
---

# Blind-Spot Audit: Omission and Hidden-Prerequisite Detection

**Tier:** STANDARD
**Category:** Planning / Discovery
**Dependencies:** None. `scripts/coverage_gap_scanner.py` is Python 3.8+ standard library only - offline, deterministic, no LLM or network calls.

## Description

Blind-spot-audit owns exactly one transformation: **(project artifact,
domain profiles) -> ranked omission and prerequisite findings**. The
artifact is a pre-planning idea/brief (text/markdown) or a draft `plan.json`
in the hub canonical tasks shape (`--plan` mode) - the same `id`/`depends_on`
contract hub canon `hitl_gate_validator` rule R5 enforces. Findings land in
the `blind_spot_report.json` contract, ranked missing first, CRITICAL first.

The method is the outside view made mechanical. Inside-view briefs cover
what the author can picture - product, brand, marketing - and systematically
omit money-flow, legal, and day-2-operations domains (Kahneman and Tversky
1979; WYSIATI); the omissions are systematic, not random (Flyvbjerg, Holm
and Buhl 2002). A fixed taxonomy scanned concern by concern - the HAZOP
guide-word discipline (IEC 61882:2016) applied to project scope - beats any
freeform brainstorm. Profiles are DATA (user-extensible JSON assets); the
scanner is generic and never hard-codes a domain.

Two finding families come out of one pass. *Scope omissions*: concern
domains the artifact never addresses (an online store with no shipping,
payments, or returns evidence). *Hidden prerequisites*: conditions that must
be TRUE before work starts, carried as `prerequisite_note` - canonically,
the GDPR lawful basis and DPIA that must exist BEFORE a customer database is
built (Arts. 6/25/35; retrofitting them drew the ICO's BA/Marriott penalties).

**The algorithm-over-AI split, stated honestly:** the scanner is the
deterministic FLOOR - the checklist minimum, machine-checked: every concern
in every applied profile gets an explicit `covered|partial|missing` status
backed by quoted indicator evidence, same run every run, offline. It cannot
read paraphrase ("parcels reach buyers" does not match "shipping"); the LLM
semantic pass guided by `references/omission_detection_method.md` is the
CEILING that catches paraphrases and name-drop coverage. `missing` means *no
indicator evidence found*, never proven-missing; exit 0 is never proof of
completeness, and the report prints this disclaimer even when clean.

Chain position: **stakeholder-inference** emits the optional register input;
this skill's report seeds **sequential-elicitation**'s open-concern agenda
(every non-covered finding carries a `seed_question`). Composition happens at
agent level - shared data shapes, zero cross-skill file references - and
approval gates live in consuming workflows, never inside this skill.

## Features

- **One scanner, two artifact types** - brief/idea text by default; hub
  canonical `plan.json` with `--plan` (task descriptions become the scanned
  text units and evidence cites task ids)
- **Profiles are data** - five shipped domain-profile JSON assets
  (`ecommerce`, `data-privacy`, `legal-compliance`, `procurement-vendor`,
  `operations-support`) plus a template and authoring recipe
- **Trigger-based activation** - prerequisite concerns activate only on
  evidence (a plan that never touches personal data is not nagged about
  DPIAs); non-activated concerns are reported as skipped, never dropped
- **Stakeholder-linked concern checks** - `--stakeholders` takes a
  stakeholder-inference register; a `regulator` entry makes compliance
  concerns mandatory, a `supplier` entry activates procurement concerns
- **Evidence discipline** - every status carries quoted evidence: a matched
  snippet for covered/partial, an explicit zero-match statement for missing
- **Ranked, CI-wireable report** - missing before partial before covered,
  CRITICAL first; `--fail-on` sets the gate severity and exit 1 blocks the
  merge exactly like `loop_auditor --min-score`
- **Zero cross-skill dependencies** - copy this folder and run; shared
  contracts are duplicated per the hub portability rule

## Interface

### Inputs

1. **Artifact** (positional): a brief/idea file (md/txt), or with `--plan` a
   `plan.json` in the hub canonical shape (extra task fields tolerated):

```json
{"name": "crm-launch", "version": "0.1.0",
 "tasks": [{"id": "T1", "description": "Design customer database schema",
            "depends_on": []}]}
```

2. **`--profiles DIR`** (required): directory of domain-profile JSON files
   (schema: `references/profile_authoring_guide.md`; skeleton:
   `assets/profile-template.json`). `--select a,b` restricts to named
   profiles; the default applies every profile in the directory.

3. **`--stakeholders FILE`** (optional): a `stakeholder_register.json` as
   produced by **stakeholder-inference** (shape duplicated, never imported):
   `{"project": str, "stakeholders": [{"id": str, "role": str, "category":
   "user|operator|supplier|regulator|sponsor|third_party", "interest":
   "low|medium|high", "influence": "low|medium|high", "inference_basis":
   str, "engagement": str}]}`. `engagement` is free text, canonically
   `manage_closely|keep_satisfied|keep_informed|monitor`; extras tolerated.
   Only `category` is read: register categories activate concerns tagged
   `activated_by`. The shipped sample passes the producer's own validator.

### Outputs

The `blind_spot_report.json` contract (extra fields tolerated), written with
`--out` and/or printed with `--json`:

```json
{"brief": "sample_brief.md",
 "findings": [{"id": "data-privacy.dpia", "domain": "data-privacy",
   "concern": "Data Protection Impact Assessment before high-risk processing (GDPR Arts. 25/35)",
   "status": "missing", "severity": "CRITICAL",
   "evidence": "no evidence found: 0 of 5 indicator pattern(s) matched across 1 text unit(s); activated by trigger evidence 'customer accounts' in brief",
   "prerequisite_note": "GDPR Arts. 25/35: a DPIA ... BEFORE building a customer database ...",
   "seed_question": "Has a DPIA been performed, and which design decisions did it change?"}]}
```

`status` is `covered|partial|missing`; `severity` is
`CRITICAL|HIGH|MEDIUM|LOW`; `prerequisite_note` is a string or null;
`seed_question` (extra field) is the per-concern agenda seed for
**sequential-elicitation**. The findings array IS the coverage matrix -
covered concerns appear too, ranked last, so the sweep is auditable;
non-activated concerns are listed under `skipped_not_triggered`.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | pass: no `missing` finding at/above `--fail-on` severity (default `critical`; `partial` never gates) |
| 1 | gate fail: at least one `missing` finding at/above `--fail-on` |
| 2 | usage or input error: missing file, malformed plan/profile/register, unknown profile name |

## Usage

```bash
# 1. Audit an idea/brief against selected profiles
python scripts/coverage_gap_scanner.py assets/sample_brief.md \
    --profiles assets/profiles --select ecommerce,data-privacy

# 2. Audit a draft plan for hidden prerequisites (--plan mode)
python scripts/coverage_gap_scanner.py assets/sample_plan.json --plan \
    --profiles assets/profiles --select data-privacy --json

# 3. Cross-check against a stakeholder register (regulator present ->
#    compliance concerns become mandatory)
python scripts/coverage_gap_scanner.py assets/sample_brief.md \
    --profiles assets/profiles --select legal-compliance \
    --stakeholders assets/sample_stakeholder_register.json

# 4. CI gate: fail the pipeline on missing HIGH-or-worse concerns
python scripts/coverage_gap_scanner.py brief.md --profiles assets/profiles \
    --fail-on high --out blind_spot_report.json
```

**The semantic pass (LLM ceiling, after the scanner floor):**

1. Run the scanner; keep its report intact as the machine record.
2. For every `missing`/`partial` finding, re-read the artifact hunting
   paraphrase evidence. A status may be upgraded ONLY with a verbatim quote
   from the artifact recorded in the evidence field.
3. For every `covered` finding at CRITICAL/HIGH, check the match is
   substantive, not a name-drop ("be GDPR compliant" is one task, not a
   lawful basis); downgrade with the quote that shows the thinness.
4. Record overrides as an annotated copy beside the machine report - never
   overwrite scanner output; floor/ceiling disagreement is signal.
5. Hand the surviving non-covered findings (with their `seed_question`s) to
   **sequential-elicitation** as its agenda, and present the report at the
   consuming workflow's human gate.

## Examples

### Example 1: online-store brief missing logistics, payments, returns

```bash
python scripts/coverage_gap_scanner.py assets/sample_brief.md \
    --profiles assets/profiles --select ecommerce,data-privacy
```

Output (trimmed; golden report in `assets/expected_report_brief.json`):

```
RANKED FINDINGS (missing first, then partial, then covered):
  [missing] CRITICAL data-privacy.dpia
            evidence: no evidence found: 0 of 5 indicator pattern(s) ...;
                      activated by trigger evidence 'customer accounts' in brief
  [missing] CRITICAL ecommerce.logistics
  [missing] CRITICAL ecommerce.payment-processing
  ...
  [partial] MEDIUM   ecommerce.inventory
  [covered] HIGH     ecommerce.customer-acquisition
SUMMARY: 13 concern(s) evaluated - 1 covered, 1 partial, 11 missing; 0 skipped
GATE: FAIL (4 missing finding(s) at or above severity 'critical')
```

Exit code 1: the brief is all product and marketing; the profiles supply
the outside view.

### Example 2: the GDPR-before-customer-database plan (worked example)

`assets/sample_plan.json` builds a customer database, a sign-up flow, an
imported email list, and a third-party e-mail integration - with zero
privacy tasks:

```bash
python scripts/coverage_gap_scanner.py assets/sample_plan.json --plan \
    --profiles assets/profiles --select data-privacy
```

All six data-privacy concerns activate ("trigger evidence 'customer
database' in task T1") and all six are `missing`: lawful-basis and dpia at
CRITICAL, retention and processor-agreements at HIGH, each carrying the
prerequisite_note stating what must be true BEFORE the database is built.
Exit code 1; golden report in `assets/expected_report_plan.json`. The fix is
predecessor tasks - routed to **wbs-decomposition** and
**critical-path-scheduler** by name.

### Example 3: stakeholder-linked activation

Run Usage command 3 with and without `--stakeholders`: without the register,
`legal-compliance.regulatory-approval` is SKIPPED (no trigger in a ceramics
brief) and the gate passes; with the register's `regulator` entry it
activates, reports `missing` at CRITICAL, and the gate fails - evidence:
"activated by stakeholder category 'regulator' in the register".

## Anti-Patterns (Mined)

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| Inside-view scope truncation | Brief details product and marketing; money-flow, goods-flow, and legal domains absent entirely | Planning from the vivid inside view - what the author can picture IS the plan (Kahneman and Tversky 1979; WYSIATI, *Thinking, Fast and Slow* ch. 23) | Scan against fixed outside-view profiles; every concern gets an explicit covered/partial/missing status |
| Systematic, self-serving omission | The same concern classes vanish from every brief - always the ones that would weaken the case | Omission is misrepresentation pressure, not random forgetfulness (Flyvbjerg, Holm and Buhl 2002, "error or lie"; Flyvbjerg and Gardner 2023) | Profiles are version-controlled data the author cannot quietly edit; the ranked report prints CRITICAL missing first regardless of narrative |
| Freeform gap brainstorm | A "what did we forget?" meeting yields whatever is salient that day, with no record of what was checked | Unstructured deviation analysis - HAZOP exists because guide-word-driven review finds what brainstorming misses (IEC 61882:2016) | Taxonomy-driven pass: every profile concern is checked one by one and the matrix records the whole sweep, including covered and skipped |
| Silence read as decision | A missing concern is defended later as "we considered that" with no trace | Absence of comment conflated with considered-and-excluded (Gause and Weinberg 1989; the N/A-with-reason idiom in **spec-driven-workflow**, duplicated here as a pattern) | `missing` strictly means no evidence found; a conscious exclusion must be written INTO the artifact ("returns handled by marketplace partner"), where it becomes scannable evidence |
| Name-drop coverage | One task says "be GDPR compliant"; the scanner reports covered and the team relaxes | Keyword presence mistaken for substantive treatment - the documented deterministic-critic ceiling (CRITIC grounding limits, self_reflection_critique_loops.md, hub canon) | Semantic pass verifies CRITICAL/HIGH covered findings for substance; the scanner is the floor, never the verdict, and says so in every report |
| Retrofitted privacy prerequisites | Customer database ships; lawful basis, DPIA, and retention are hunted after collection begins | Prerequisites treated as parallel or post-hoc work instead of predecessors (ICO enforcement: British Airways GBP 20m and Marriott GBP 18.4m, 2020; GDPR Arts. 25/35) | data-privacy profile triggers on personal-data evidence and demands prerequisite evidence in the same artifact; missing fires CRITICAL with the prerequisite_note |
| Cutover without readiness | Go-live is scheduled by date; training, support, and monitoring appear nowhere in the plan | Date-driven cutover; day-2 operations are invisible at build time (Hershey SAP/Siebel 1999 - training and testing skipped to hold a hard go-live) | operations-support profile makes training, support, backup, and incident response explicit concerns; missing CRITICAL blocks in CI |
| Security authorized after operation | Vendor receives data access, or the system reaches production, before any security-review task exists | Bolt-on security - the operate-then-authorize ordering NIST's RMF exists to prevent (NIST SP 800-37 Rev. 2) | procurement-vendor prerequisite notes encode review-before-access ordering; trigger-based activation catches it in `--plan` mode |
| Unchallenged assumed scope | The brief's self-declared boundaries limit the audit; concerns outside the stated scope are never examined | Elicitation results accepted unconfirmed; assumed scope unchallenged (BABOK v3, Elicitation and Collaboration KA pitfalls) | Profiles apply to the whole artifact regardless of its self-declared boundaries; out-of-scope claims need written reasons, which become evidence |

## When NOT to Use

Route by name - never by path; composition happens at agent/workflow level.

| You actually need | Use instead |
|-------------------|-------------|
| Ask a human the open questions this report surfaces | **sequential-elicitation** - it consumes this report's findings and seed_questions as its agenda |
| Infer WHO is affected and produce the stakeholder register | **stakeholder-inference** - this skill only consumes the register |
| Critique the realism, estimates, or assumptions of a decomposed plan | **plan-critique** - it audits the produced plan; this skill audits coverage of the idea/draft |
| Simulate adverse futures and harden the plan with contingencies | **plan-premortem** |
| Decompose the objective into a task hierarchy | **wbs-decomposition** |
| Model dependencies, compute dates or the critical path | **critical-path-scheduler** |
| Track execution against the approved baseline | **plan-baseline-tracking** |
| Decide how to respond to a schedule slip | **slip-driven-replanning** |
| Export the completed plan as Jira/Asana/Trello payloads | **plan-ticket-export** |
| Run a hostile review of code diffs | **adversarial-reviewer** |
| Check a feature spec's mandatory sections | **spec-driven-workflow** |
| Retrieve internal compliance/policy documents to ground the audit | **rag-architect** - retrieval pipelines are never built here |
| Promote recurring findings ("every e-commerce brief forgets returns") into durable rules, or persist audit history across sessions | **self-improving-agent** (human-gated promotion) / **hybrid-rag-memory** (persistence) - this skill only scans the files it is handed |

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs owned by framework skills - verify
against current docs): the detection pass is a node placed BEFORE the human
gate - a LangGraph node ahead of an `interrupt()` gate (see
**langgraph-state-design**); a CrewAI QA-persona task ahead of
`human_input=True` (see **crewai-role-engineering**); a Microsoft Agent
Framework executor ahead of a request/response port (see
**microsoft-agent-framework**). Prompt shape for the semantic pass cites
**senior-prompt-engineer**. None of that wiring is duplicated here.

**STATIC TRACK** (how this hub uses the skill offline): the artifact, the
profiles, and the report are git-versioned files; the scanner is a
deterministic, offline, CI-wireable gate whose exit 1 blocks the merge; the
audit runs in Phase 1 DISCOVERY (read-only), its report feeds the Phase 2
MANIFEST and the **sequential-elicitation** agenda, and the consuming
workflow's human gate approves before irreversible work - gates before
execution, per hub canon.

## References

In-skill knowledge bases: `references/omission_detection_method.md` (the
outside-view method, floor/ceiling split, semantic-pass protocol, wording
rules) and `references/profile_authoring_guide.md` (profile JSON schema,
authoring recipe, and the GDPR-before-customer-database worked example).

Source literature (edition-pinned; external standards marked "verify against
current docs"):

- Kahneman, D. and Tversky, A. "Intuitive Prediction: Biases and Corrective
  Procedures", 1979; Kahneman, D. *Thinking, Fast and Slow*, 2011, ch. 23
  (WYSIATI, inside vs outside view)
- Flyvbjerg, B., Holm, M. and Buhl, S. "Underestimating Costs in Public
  Works Projects: Error or Lie?", *JAPA* 68(3), 2002; Flyvbjerg, B. and
  Gardner, D. *How Big Things Get Done*, Currency, 2023
- IEC 61882:2016 (HAZOP application guide) - guide-word-driven omission
  detection precedent; verify against current docs
- Gause, D. and Weinberg, G. *Exploring Requirements*, Dorset House, 1989
- BABOK v3 (IIBA, 2015) Elicitation and Collaboration KA pitfalls; PMBOK
  Guide 7th ed. (PMI, 2021) performance domains as a completeness taxonomy;
  Standish Group CHAOS Reports ("incomplete requirements" as a recurring top
  failure factor) - verify against current editions
- Regulation (EU) 2016/679 (GDPR) Arts. 5, 6, 25, 28, 30, 33-35 - verify
  against current regulation and jurisdiction; this skill is not legal advice
- ICO penalty notices: British Airways (2020, GBP 20m) and Marriott (2020,
  GBP 18.4m); Hershey SAP/Siebel go-live failure, 1999; NIST SP 800-37
  Rev. 2 authorize-before-operate ordering (verify against current revision)

Hub canon (cited by name as authority, never imported or path-referenced):

- `hitl_gate_validator` rule R5 - the `id`/`depends_on` contract the `--plan`
  input mirrors
- self_reflection_critique_loops.md and loop_engineering_patterns.md
  (agentic-system-architect flagship) - the deterministic-critic ceiling
  behind the floor/ceiling split, and the six-type exit-condition taxonomy
  governing any agent loop that hosts repeated audit passes (loops terminate
  on the declared taxonomy, never on this report's counts)
- spec-driven-workflow's N/A-with-reason idiom and adversarial-reviewer's
  evidence-first finding discipline - pattern donors, duplicated per the hub
  portability rule

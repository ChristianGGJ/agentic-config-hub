---
name: "stakeholder-inference"
description: "Use when a project brief or scope description must be turned into a classified stakeholder register - inferring users, operators, suppliers, regulators, sponsors, and affected third parties with cited evidence, rating influence and interest on the Mendelow grid, and gating category coverage with a deterministic validator before planning consumes the register."
---

# Stakeholder-Inference: From Brief to Classified Stakeholder Register

**Tier:** STANDARD
**Category:** Planning / Stakeholder Analysis
**Dependencies:** None. The script is Python 3.8+ standard library only -
offline, deterministic, no LLM or network calls.

## Description

Stakeholder-inference is one transformation: a project brief or scope
description goes in; a classified stakeholder register comes out. The
register is the hub shared contract other planning skills consume - every
entry carries an id, a role, a category from a closed six-value enum
(user, operator, supplier, regulator, sponsor, third_party), influence and
interest ratings, a Mendelow-derived engagement stance, and an
`inference_basis` that cites the brief text or domain signal implying the
actor.

The hard part is not listing the people the brief names - sponsors and
users name themselves. The hard part is inferring the actors the brief
only IMPLIES: the regulator activated by a data class, the supplier the
critical path runs through, the operator who answers the tickets, the
third party affected without ever logging in. The inference prompt guide
walks the six categories as interrogation lenses and ships a regulator
inference table by domain (payments -> PCI DSS + financial regulator,
personal data -> DPA/GDPR authority, health -> HIPAA, and so on).

One deterministic tool gates the result. The validator makes register
theater a deterministic FAIL: missing required fields, categories outside
the enum, duplicate ids, coverage gaps without explicit waivers, and
entries without a stated inference basis do not pass. A missing regulator
or supplier category - the classic blind spot, since neither writes the
brief - is a HIGH finding.

The skill supplies method and gate only. The inference itself is
LLM/analyst work performed against the references; scripts never call an
LLM. Approval gates live in consuming workflows: the validated register is
presented at the human gate BEFORE decomposition consumes it - gates
before execution, per hub canon.

## Features

- **Six-category closed taxonomy** - user, operator, supplier, regulator,
  sponsor, third_party; the closed enum is what makes coverage
  deterministically checkable
- **Regulator inference table by domain** - domain signals in the brief
  map to regulator-class obligations (PCI DSS, GDPR authorities, HIPAA,
  sector regulators), each row marked verify-against-current-jurisdiction
- **Evidence rule** - every entry cites the brief text or domain signal
  that implies it; an entry without a basis is an unsupported guess and a
  MEDIUM finding (rule V6)
- **Coverage-or-waiver discipline** - every category is represented or
  explicitly waived via `--waive category:reason`; missing regulator or
  supplier coverage is HIGH (rule V4)
- **Mendelow grid derivation** - engagement stance derived from influence
  x interest; the validator advisorily flags quadrant contradictions on
  unambiguous entries (rule V7) and leaves medium bands to the human gate
- **Golden expected outputs** - shipped sample registers (valid and
  seeded-defective) with byte-comparable `--json` reports for CI
- **Zero cross-skill dependencies** - copy this folder and run; shared
  knowledge is duplicated per the hub portability rule

## Interface

### Inputs

1. **Project brief** (markdown or plain text) - the scope description the
   inference runs against; see `assets/sample-brief.md`.
2. Optional: domain tags (industry, jurisdiction, data classes handled) to
   sharpen the regulator table walk.
3. Optional: a seed list of already-known stakeholders to fold in.

No credentials, no network, no PII beyond what the brief itself contains.

### Output: stakeholder_register.json (hub shared contract)

```json
{
  "project": "aurora-customer-payments-portal",
  "stakeholders": [
    {
      "id": "ST-6",
      "role": "National data protection authority",
      "category": "regulator",
      "interest": "low",
      "influence": "high",
      "inference_basis": "Brief states bills contain personal data of EU residents, activating GDPR and its supervisory authority.",
      "engagement": "keep_satisfied"
    }
  ]
}
```

Field contract: `category` from `user|operator|supplier|regulator|sponsor|
third_party`; `influence` and `interest` from `low|medium|high`;
`inference_basis` non-empty; `engagement` free text, canonically one of
`manage_closely|keep_satisfied|keep_informed|monitor`. Extra fields are
tolerated, mirroring how hitl_gate_validator rule R5 treats extras on the
plan.json contract. Downstream consumers: blind-spot-audit takes the
register as an optional input; wbs-decomposition plans against approved
actors; spec-driven-workflow's reviewers/users sections map from register
entries at agent level.

### Exit codes (stakeholder_register_validator.py)

| Code | Meaning |
|------|---------|
| 0 | register valid - no findings |
| 1 | findings: contract violations, coverage gaps, unsupported entries |
| 2 | usage or input error: missing file, malformed JSON, malformed --waive |

## Usage

The five-step workflow:

```bash
# 1. Infer: walk the brief twice (named actors, then implied actors per
#    category) using references/inference_prompt_guide.md; walk the
#    regulator table against the project's domain signals.

# 2. Draft the register JSON in the shared contract shape; every entry
#    gets an inference_basis passing the three-part evidence test.

# 3. Gate deterministically
python scripts/stakeholder_register_validator.py register.json

# 4. Close gaps: add the missing entries, or waive with a stated reason
python scripts/stakeholder_register_validator.py register.json \
    --waive "supplier:fully in-house build, no external vendors"

# 5. Hand off: the register (waiver reasons included) goes to the
#    consuming workflow's human approval gate BEFORE planning consumes it.
```

Re-run the inference at phase boundaries: identification is continuous
(PMBOK 7th ed. performance-domain framing), and the git-versioned register
makes each revision a reviewable diff. If an autonomous agent drives the
inference-validate-revise cycle, it declares its exit conditions from the
hub six-type taxonomy (max_iterations, no_progress, oscillation, budget,
success_predicate, escalation_trigger) before iteration 1; validator PASS
is evidence for a success_predicate, never a self-assigned score. Loop
mechanics are hub canon (agentic-system-architect references, by name) and
are not rebuilt here.

## Examples

### Example 1: gate the valid sample register

```bash
python scripts/stakeholder_register_validator.py assets/sample-stakeholder-register.json
```

Output:

```
STAKEHOLDER REGISTER VALIDATION: sample-stakeholder-register.json
Project: aurora-customer-payments-portal
Entries: 10 | Categories covered: operator, regulator, sponsor, supplier, third_party, user | Waivers: none

RESULT: PASS (0 HIGH, 0 MEDIUM, 0 LOW)
```

Exit code 0. `--json` output matches `assets/expected-findings-valid.json`
byte for byte.

### Example 2: gate the seeded-defective sample register

```bash
python scripts/stakeholder_register_validator.py assets/sample-stakeholder-register-defective.json
```

Output:

```
HIGH   [V3] entry 'ST-2': duplicate id 'ST-2' (already used by entry #2)
MEDIUM [V6] entry 'ST-4': inference_basis is missing or empty; an entry
       without a stated basis is an unsupported guess
HIGH   [V4] category:regulator: no 'regulator' entry and no waiver;
       missing regulator coverage is the classic stakeholder blind spot

RESULT: FAIL (2 HIGH, 1 MEDIUM, 0 LOW)
```

Exit code 1; golden report in `assets/expected-findings-defective.json`.
A waiver moves the coverage gap into notes, but only with a reason the
human gate can judge:

```bash
python scripts/stakeholder_register_validator.py register.json \
    --waive "regulator:internal tooling, no regulated data - reviewed by legal"
```

## Anti-Patterns

Mined from the named sources; each row is a documented failure mode of
real stakeholder identification, not generic advice.

| Anti-pattern | Symptom | Root cause | Fix |
|--------------|---------|------------|-----|
| One-shot kickoff identification (PMBOK 6th ed. Ch. 13; 7th ed. performance domain) | Register frozen at initiation; a regulator or vendor surfaces mid-delivery as a surprise | Identification treated as a process step to complete, not a continuous domain | Re-run inference at phase boundaries; the git-versioned register makes each revision a reviewable diff |
| User involvement by proxy (Standish CHAOS reports) | `user` entries thin or represented by the sponsor's opinion of users | Sponsors write briefs and name themselves; users are assumed known | Coverage rule V4 forces a real `user` entry or an explicit waiver a human must approve |
| Operator neglect (UK NAO reports on NHS NPfIT, dismantled 2011) | The people who run the system daily discovered after build; adoption collapses | Briefs describe outcomes, not operations; nobody asks who runs it at 3am | `operator` is a first-class enum value; the interrogation question targets support queues and on-call explicitly |
| Regulator blindness (Mendelow grid misuse; PMI Pulse 2018) | Payments or personal-data project with zero regulator entries; compliance found at launch | Regulators are activated by domain, not named in briefs; low current urgency reads as absence | The domain-signal regulator table plus rule V4 HIGH for missing regulator coverage without a waiver |
| Salience misclassification (Mitchell, Agle and Wood 1997) | Dormant stakeholders rated low-influence because they are quiet; they become definitive overnight | Influence rated on current noise instead of held attributes (power, legitimacy, urgency) | Rate influence on what the actor CAN do (audit, veto, halt); the salience table in the methodology reference |
| Everyone-is-a-stakeholder over-broadening (Freeman 1984) | 40-row register, everything `keep_informed`, nobody actually engaged | Listing feels like rigor; no evidence bar per entry | Three-part evidence test per entry; entries failing it are deleted, not softened |
| Hallucinated actors from LLM inference (adversarial-reviewer forced-finding pattern, duplicated) | Plausible-sounding stakeholders with no anchor in the brief | Generative over-listing rewarded by "complete-looking" output | Rule V6: empty inference_basis is a MEDIUM finding; the basis must quote the trigger |
| Supplier invisibility (UK NAO NPfIT supplier-dispute record) | Critical-path vendor absent from the register; its contract terms ambush the schedule | Suppliers treated as procurement line items, not actors with incentives | Rule V4 HIGH for missing supplier coverage; walk one hop down the vendor chain for critical-path suppliers |

## When NOT to Use

Routing table - sibling skills are named, never path-referenced;
composition happens at agent/workflow level.

| If you need to... | Use instead |
|-------------------|-------------|
| Design agent personas, roles, or backstories | crewai-role-engineering (vocabulary collision: that is agent design, not project-actor analysis) |
| Audit a brief for domain blind spots beyond actors | blind-spot-audit (it takes this skill's register as an optional input) |
| Resolve open questions with the human, one at a time | sequential-elicitation |
| Decompose the objective into a task hierarchy | wbs-decomposition |
| Critique the plan's premises and estimates | plan-critique |
| Stress-test the plan with failure narratives | plan-premortem |
| Compute dates, floats, or the critical path | critical-path-scheduler |
| Track execution against the approved baseline | plan-baseline-tracking |
| Replan after schedule slips | slip-driven-replanning |
| Export the approved plan as tickets | plan-ticket-export |
| Write feature-spec users/reviewers sections | spec-driven-workflow (register entries map into it at agent level) |
| Retrieve policy or context corpora for planning | rag-architect |
| Persist stakeholder history across projects | hybrid-rag-memory |
| Run a hostile review of the register itself | adversarial-reviewer |

Communication plans, RACI charts, and engagement execution are out of
scope entirely - they consume the register downstream and no hub skill
currently owns them.

## Dual-Track Note

**FRAMEWORK TRACK** (runtime constructs owned by framework skills - verify
against current docs): host the inference as a CrewAI analyst agent with a
typed register via output_pydantic (see crewai-role-engineering); gate the
register behind a LangGraph interrupt() review node before planning
proceeds (see langgraph-state-design); emit the register as a typed
structured-output message in Microsoft Agent Framework workflows (see
microsoft-agent-framework). None of that wiring is duplicated here.

**STATIC TRACK** (how this hub uses the skill offline): the brief and the
register are git-versioned files committed beside plan.json; the inference
runs as an analyst/LLM pass against the references; the validator is a
deterministic offline gate wired into CI by exit code; the validated
register (waiver reasons included) is presented at the consuming
workflow's human approval gate before wbs-decomposition consumes it. The
register's git history is the identification audit trail.

## References

In-skill knowledge bases:

- `references/stakeholder_identification_methodology.md` - the six-category
  taxonomy, Mitchell-Agle-Wood salience model, Mendelow grid discipline,
  evidence rule, register lifecycle, waiver discipline
- `references/inference_prompt_guide.md` - the two-pass inference method,
  category interrogation questions, the regulator inference table by
  domain, and the static-track prompt skeleton

Source literature (edition-pinned; external standards and regulations
marked verify against current docs):

- PMBOK Guide 7th ed., PMI, 2021 - Stakeholder Performance Domain; PMBOK
  Guide 6th ed., PMI, 2017, Ch. 13 Project Stakeholder Management
- ISO 21502:2020 and ISO 21500:2021 stakeholder-management clauses -
  external standards, verify against current revisions
- Mitchell, R., Agle, B. and Wood, D. "Toward a Theory of Stakeholder
  Identification and Salience", Academy of Management Review 22(4), 1997
- Mendelow, A. power-interest grid, 1991 formulation (original paper:
  Proceedings of the International Conference on Information Systems, 1981)
- Freeman, R.E. Strategic Management: A Stakeholder Approach, Pitman, 1984
- Standish Group CHAOS Reports (edition-dependent statistics - verify
  against the current edition)
- PMI Pulse of the Profession 2018, "Success in Disruptive Times"
- UK National Audit Office reports on the NHS National Programme for IT
  (2006-2011; program dismantled 2011) - operator neglect and supplier
  disputes at scale
- Regulation (EU) 2016/679 (GDPR), PCI DSS, HIPAA (45 CFR Parts 160/164),
  EU AI Act - regulator-table entries, each verify against current
  regulation and jurisdiction

Hub canon (cited by name as authority, never called or path-referenced):

- hitl_gate_validator rule R5 - the extras-tolerated contract style the
  register schema mirrors, and the plan.json shape downstream skills gate
- loop_engineering_patterns.md (agentic-system-architect flagship) -
  six-type exit-condition taxonomy for any autonomous inference loop
- adversarial-reviewer Forced-Finding Calibration - the three-part
  evidence test, duplicated in pattern per the hub portability rule

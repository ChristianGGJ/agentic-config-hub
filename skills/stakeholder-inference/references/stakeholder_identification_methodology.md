# Stakeholder Identification and Salience Methodology

Expert knowledge base for turning a project brief into a classified
stakeholder register. Sources are edition-pinned in SKILL.md References;
external standards are marked "verify against current docs".

## 1. Why identification is a planning gate, not paperwork

PMBOK Guide 7th ed. (2021) treats stakeholder work as a continuous
performance domain, not a one-time process step: identification repeats as
the project changes. PMBOK 6th ed. (2017) Ch. 13 places Identify
Stakeholders at initiation AND at every phase boundary. ISO 21502:2020
carries the same clause-level obligation for project stakeholder
management, and ISO 21500:2021 anchors it in governance context (verify
against the current ISO revisions).

The empirical case: the Standish Group CHAOS reports list lack of user
involvement among the top causes of project failure across editions, and
PMI Pulse of the Profession 2018 attributes a large share of failed
projects to poor stakeholder engagement. The UK National Audit Office
reports on the NHS National Programme for IT (dismantled 2011) document
what operator-class neglect costs at scale: clinicians - the people who
would operate the systems daily - were never treated as first-class
stakeholders, and the program collapsed after multi-billion spend.

## 2. The six-category taxonomy (closed enum)

The hub register uses a closed six-value category enum. Every inferred
actor maps to exactly one category; the closed set is what makes the
coverage check deterministic.

| Category | Definition | Classic miss |
|----------|------------|--------------|
| `user` | Consumes the product or service the project delivers | Proxied by the sponsor's opinion instead of represented |
| `operator` | Runs, supports, or maintains the delivered system day to day | Discovered after build (NPfIT clinicians) |
| `supplier` | External vendor, contractor, or platform the delivery depends on | Treated as a line item, not an actor with its own incentives |
| `regulator` | Body whose rules constrain the project: statutory, supervisory, or contractual compliance regimes | Not named in the brief, so never inferred |
| `sponsor` | Funds the work and owns the business outcome | Assumed aligned, never asked |
| `third_party` | Affected without using or building the system | Invisible until they escalate |

Two categories are the classic blind spots - `regulator` and `supplier` -
because briefs are written by sponsors and users, who name themselves.
Regulators and suppliers must usually be INFERRED from domain signals (see
`inference_prompt_guide.md`). This is why the validator raises a missing
regulator or supplier category to HIGH while other gaps are MEDIUM.

## 3. Salience: Mitchell, Agle and Wood (1997)

The salience model classifies stakeholders by which of three attributes
they hold: power, legitimacy, and urgency.

| Attributes held | Type | Planning implication |
|-----------------|------|----------------------|
| Power only | Dormant | Quiet now; can become definitive overnight (a regulator between audits) |
| Legitimacy only | Discretionary | Easy to deprioritize; reputational cost when ignored |
| Urgency only | Demanding | Loud but low-stakes; do not let noise drive the register |
| Power + legitimacy | Dominant | Standing expectations; engage structurally |
| Power + urgency | Dangerous | Can coerce; watch for escalation paths |
| Legitimacy + urgency | Dependent | Needs an advocate with power (elderly offline customers) |
| All three | Definitive | Immediate priority |

The model's documented failure mode: dormant and demanding stakeholders
are ignored until an attribute shift makes them definitive - the regulator
who acquires urgency when a breach happens, the user group that acquires
power when it organizes. Rate influence on the attributes the actor CAN
hold, not on how loud the actor is today.

## 4. The Mendelow power-interest grid

Mendelow's grid (1991 formulation; original ICIS paper 1981) crosses
influence (power) with interest to derive an engagement stance. The hub
mapping, which the validator checks advisorily (rule V7) when influence
and interest are unambiguous:

| Influence | Interest | Engagement quadrant |
|-----------|----------|---------------------|
| high | high | `manage_closely` |
| high | low | `keep_satisfied` |
| low | high | `keep_informed` |
| low | low | `monitor` |

`medium` is a deliberate judgment band: the grid is 2x2, and forcing a
medium onto a quadrant fabricates precision. Entries with a medium on
either axis are resolved by the human at the approval gate, not by the
script.

Rating discipline:

- **Influence** = capacity to change the project's course (funding,
  veto, audit, contract terms, operational refusal). Not seniority.
- **Interest** = how much the outcome affects the actor, positive or
  negative. Not enthusiasm.
- Rate each axis independently, then derive engagement - never pick the
  engagement stance first and back-fill ratings to justify it.

## 5. The evidence rule (inference_basis)

Every register entry carries `inference_basis`: one or two sentences
citing the brief text (quoted) or the domain signal that implies the
actor. The rule exists because LLM-assisted inference over-lists -
plausible actors with no anchor in the brief dilute the register into
noise (Freeman's "everyone is a stakeholder" over-broadening, 1984).

The basis test, duplicated in pattern from the hub's adversarial-reviewer
Forced-Finding Calibration (three parts, all required):

1. A concrete trigger in the brief or domain ("card payments" implies
   PCI DSS scope);
2. A concrete stake ("can halt launch", "handles the disputes queue");
3. Not already covered by another entry (no role-splitting to pad rows).

An entry that fails the test is deleted, not softened. The validator
enforces only non-emptiness (rule V6, MEDIUM) - the semantic quality of
the basis is human-gate work.

## 6. Register lifecycle

1. **Infer** - walk the six categories against the brief using
   `inference_prompt_guide.md`; draft the register JSON.
2. **Gate deterministically** - `stakeholder_register_validator.py` must
   exit 0; coverage gaps are closed with entries or explicit waivers.
3. **Human approval** - the register is reviewed at the consuming
   workflow's human gate BEFORE planning consumes it (hub canon: gates
   before execution). Waiver reasons are part of what the human approves.
4. **Version** - the register is committed next to the plan; identity
   changes are diffs, reviewable like code.
5. **Re-run at phase boundaries** - identification is continuous
   (PMBOK 7th ed. performance-domain framing). New scope, new
   jurisdiction, or a new vendor re-opens the inference pass.

## 7. Waiver discipline

A category may be absent only with an explicit waiver
(`--waive category:reason`). The reason must state WHY the category has no
actor for this project ("fully in-house build, no external vendors"), not
that nobody thought of one. This mirrors the "N/A - [reason] so reviewers
know it was considered, not forgotten" idiom used in hub spec templates.
An unnecessary waiver (category actually covered) is reported as a note so
stale waivers get cleaned up.

## 8. Out of scope for this methodology

Communication planning, RACI charts, engagement execution, and stakeholder
negotiation tactics are downstream disciplines that consume the register;
they are not part of the identification transformation and are not covered
by this skill.

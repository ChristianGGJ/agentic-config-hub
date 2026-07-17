# Inference Prompt Guide: From Brief to Stakeholder Register

How to infer the actors a brief IMPLIES but does not name. The model (or
analyst) performs the inference; the script only gates the result - hub
scripts never make LLM calls. Prompt-technique mechanics (role prompting,
structured output) are the senior-prompt-engineer skill's territory and
are cited, not restated, here.

## 1. The core move: read the brief twice

**Pass 1 - named actors.** List every actor the brief names explicitly
(sponsor statements name sponsors; scope bullets name teams and vendors).
Each becomes an entry whose `inference_basis` quotes the naming sentence.

**Pass 2 - implied actors.** Walk the six categories as interrogation
lenses. For each, ask the category question below against every scope
bullet and constraint. Anything the brief implies but does not name is an
inferred entry whose `inference_basis` states the implying signal.

The register is complete when every category has at least one entry or an
explicit waiver with a reason. That is the deterministic coverage gate.

## 2. Category interrogation questions

| Category | Question to ask the brief | Typical signals |
|----------|---------------------------|-----------------|
| `user` | Who consumes what this delivers, including secondary user groups? | "customers can...", personas, self-service verbs |
| `operator` | Who runs this at 3am? Who answers the tickets it generates? Who patches it? | support queues, on-call, maintenance windows, "handles disputes" |
| `supplier` | Which external party does the critical path run through? | vendor names, "external", "existing enterprise agreement", APIs consumed |
| `regulator` | Which rules constrain this domain, jurisdiction, and data class? | see the regulator inference table below |
| `sponsor` | Who funds it and owns the business outcome? Who can cancel it? | budget statements, KPI expectations, executive names |
| `third_party` | Who is affected without ever logging in or building it? | displaced processes, non-enrolled populations, neighbors, downstream data recipients |

## 3. The regulator inference table by domain

Regulators are almost never named in briefs - they are activated by domain
signals. Every row is jurisdiction- and version-sensitive: **verify against
the current regulation and the project's actual jurisdiction** before the
entry ships.

| Domain signal in the brief | Inferred regulator-class obligation | Notes |
|----------------------------|-------------------------------------|-------|
| Card payments, cardholder data | PCI DSS via acquiring bank / card schemes; national financial regulator where payments are regulated | PCI DSS is contractual, not statutory; scope applies even when card storage is outsourced (SAQ tiers) |
| Personal data of EU/UK residents | GDPR / UK GDPR supervisory authority (e.g. ICO, CNIL, AEPD, national DPA) | DPIA duty for high-risk processing (GDPR Art. 35) |
| Health data (US) | HIPAA - HHS Office for Civil Rights | Business-associate agreements pull vendors into scope |
| Health data (EU) | GDPR Art. 9 special-category rules + national health authority | Member-state law adds local layers |
| Financial services, lending, investments | National conduct authority (e.g. FCA, SEC/FINRA, BaFin, CNBV) | Product-type dependent |
| Employee / HR data | Labor authority; works-council consultation duties in several EU states | Consultation can be a schedule prerequisite |
| Minors as users | COPPA (US), GDPR Art. 8 age-of-consent rules | Age verification becomes a scope item |
| Public-sector delivery or public accommodation | Accessibility regimes: Section 508 / ADA (US), EN 301 549 (EU) | Often a launch-blocking audit |
| Energy, water, telecom utilities | Sector regulator (billing accuracy, service continuity) | Audit cadences constrain release windows |
| AI-driven decisions affecting persons (EU) | EU AI Act obligations by risk class | Verify current applicability timeline |
| Cross-border data transfer | Transfer-mechanism requirements (SCCs, adequacy) | A supplier's hosting region can activate this |

If NO row fires after honest interrogation, the regulator category is
waived with that finding as the reason - never silently skipped. The same
logic applies to suppliers ("fully in-house, no external dependencies" is
a valid waiver reason; absence of thought is not).

## 4. Writing the inference_basis (evidence rule)

Good basis - quotes the trigger and states the stake:

> Brief: 'card payments are processed through an external payment gateway
> vendor' - an external dependency on the critical payment path.

Bad basis - generic, would fit any project (delete or rewrite):

> Vendors are important stakeholders in most projects.

Three-part test per entry (duplicated in pattern from the hub
adversarial-reviewer Forced-Finding Calibration): concrete trigger in the
brief or domain + concrete stake + not already covered by another entry.

## 5. Rating and engagement derivation

Rate influence and interest independently (see
`stakeholder_identification_methodology.md` sections 3-4), then derive
engagement from the Mendelow quadrant when both axes are unambiguous
(high/low). Keep `medium` where the honest answer is "it depends" and let
the human gate resolve it - fabricated precision is worse than a declared
judgment band.

## 6. Static-track prompt skeleton

For a hub agent running the inference offline against a git-versioned
brief (structure only - phrasing technique belongs to
senior-prompt-engineer):

```
You are performing stakeholder inference on the project brief below.
1. List actors NAMED in the brief, with the naming sentence quoted.
2. For each category in [user, operator, supplier, regulator, sponsor,
   third_party], ask the category question and list actors IMPLIED by
   the brief, with the implying signal stated.
3. For regulator: walk the domain-signal table row by row against the
   brief; state which rows fire and why.
4. Emit stakeholder_register.json in the shared contract shape. Every
   entry must carry a non-empty inference_basis passing the three-part
   evidence test. Rate influence and interest low|medium|high; derive
   engagement from the Mendelow quadrant when unambiguous.
5. For any category with zero entries, propose a waiver reason or state
   that coverage is genuinely missing.
```

The output is then gated by `stakeholder_register_validator.py` and
presented at the consuming workflow's human approval gate. Do not skip the
gate because the register "looks complete" - looking complete is exactly
what an over-listed register does.

## 7. Known inference failure modes

- **Echo-only inference**: only Pass 1 runs; the register contains just the
  actors the sponsor happened to write down. Coverage check catches the
  category-level symptom; the fix is running Pass 2 honestly.
- **Over-listing**: 40 plausible actors, all `keep_informed`. Fix: the
  three-part evidence test, applied entry by entry.
- **Jurisdiction blindness**: regulator inferred for the builder's home
  jurisdiction instead of where users and data actually are.
- **Vendor chain truncation**: the direct vendor is listed but the vendor's
  critical subprocessor (hosting region, payment rails) is not; walk one
  hop down the chain for critical-path suppliers.

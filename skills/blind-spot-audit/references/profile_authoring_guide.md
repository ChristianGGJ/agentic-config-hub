# Domain-Profile Authoring Guide

Profiles are DATA; the scanner is generic. This guide is the recipe for
authoring a new domain-profile JSON (or extending a shipped one) so the
deterministic floor stays trustworthy. Skeleton: `assets/profile-template.json`.

## 1. Profile schema

```json
{
  "profile": "kebab-case-name",
  "description": "What this profile covers and which mined sources it derives from",
  "triggers": ["optional profile-level activation regexes"],
  "activated_by": ["optional stakeholder categories"],
  "concerns": [
    {
      "id": "kebab-case-id",
      "concern": "One-line human statement",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "triggers": ["optional concern-level regexes (unioned with profile-level)"],
      "activated_by": ["optional categories (unioned with profile-level)"],
      "indicators": ["evidence regexes - at least one required"],
      "covered_min": 2,
      "prerequisite_note": "string or null",
      "seed_question": "one question for sequential-elicitation"
    }
  ]
}
```

Field semantics enforced by the scanner (violations exit 2):

| Field | Rule |
|-------|------|
| `profile` | non-empty string, unique across the directory |
| `severity` | exactly one of the four contract values |
| `indicators` | non-empty array of valid case-insensitive regexes |
| `triggers` / `activated_by` | optional; profile-level and concern-level lists are UNIONED; a concern with neither is unconditional |
| `activated_by` values | stakeholder_register categories only: `user`, `operator`, `supplier`, `regulator`, `sponsor`, `third_party` |
| `covered_min` | positive integer, default 2, capped at the indicator count |
| `prerequisite_note` | string or null |

Status logic: 0 distinct indicator matches = `missing`; below `covered_min` =
`partial`; at/above = `covered`. Distinct means distinct PATTERNS, not
repeated hits of one pattern - one word repeated ten times is still one piece
of evidence.

## 2. Authoring recipe

1. **Mine the failure sources first.** A concern earns its row by appearing
   in a documented failure: a postmortem, an enforcement action, an audit
   guide, a failure-factor survey. Record the source in the profile
   `description` and in the consuming SKILL.md References. Concerns invented
   from vibes produce checklist theater.
2. **One concern = one question a human could answer.** If the
   `seed_question` needs "and" twice, split the concern.
3. **Choose indicators as evidence, not vocabulary.** An indicator should
   only match text that constitutes evidence the concern was considered.
   Prefer specific terms (`\bDPIA\b`, `chargebacks?`) over broad ones
   (`data`, `plan`). Word-bound short terms (`\bship(ping|ments?|s)?\b`, not
   `ship` - which matches "worship"). Order alternations longest-first so
   evidence quotes the fullest match (`databases?` before `data`).
4. **Decide unconditional vs triggered.** Scope-domain concerns in a profile
   the user explicitly selected should usually be unconditional (selecting
   `ecommerce` IS the trigger). Prerequisite concerns should be triggered by
   the evidence that creates the obligation - a plan that never touches
   personal data must not be nagged about DPIAs. Add `activated_by` when a
   stakeholder category creates the obligation independently of text (a
   `regulator` in the register makes compliance concerns mandatory).
5. **Write the prerequisite_note as an ordering.** "X must exist/be true
   BEFORE Y", plus the source. If there is no before/after ordering, it is a
   scope concern: set the note to null.
6. **Assign severity by cost-of-omission at launch** (see the method
   reference, section 4). Never encode likelihood.
7. **Calibrate against two artifacts** before shipping: one that should fail
   (seeded gaps) and one that should pass. Watch for accidental matches -
   substring surprises like "restock" containing "stock" are found only by
   running. Commit both artifacts and, where output is stable, an expected
   report, as the shipped samples do.
8. **Keep profiles small.** 5-8 concerns per profile. A 40-concern profile
   produces an unreadable report and dilutes CRITICAL findings; split into
   two domains instead. Community/extension rules belong in new profile
   files, not in ever-growing shipped ones.

## 3. Worked example: "GDPR before the customer database"

The shipped `data-privacy` profile encodes the hub's canonical
hidden-prerequisite case. How its rows were derived:

**Source mining.** The ICO's British Airways (GBP 20m) and Marriott
(GBP 18.4m) penalty notices (2020) are public documents describing personal
data collected at scale with privacy controls retrofitted afterwards. GDPR
itself states the ordering: Art. 6 (lawful basis) and Arts. 25/35
(data-protection-by-design, DPIA) attach BEFORE processing begins; Art. 28
requires a processor agreement BEFORE a third party touches the data;
Art. 5(1)(e) requires retention limits at collection time.

**Trigger design.** The obligation is created by personal-data handling, so
the profile-level triggers are evidence of that handling: `customer
(accounts?|databases?|records?|profiles?|data)`, `email (address(es)?|lists?|
newsletters?)`, `sign[- ]?up`, `\bPII\b`, `analytics`, `tracking`, and so on.
`activated_by: ["regulator"]` adds the stakeholder-linked path: if
stakeholder-inference put a data-protection authority in the register, the
concerns activate even when the text is coy. The `processor-agreements`
concern adds its own triggers (`third[- ]part(y|ies)`, `hosted`, `platform`,
`integrat`, ...) because the Art. 28 obligation specifically attaches to
third-party processing.

**Indicator design.** Indicators are the terms a brief or plan would contain
IF the prerequisite had been considered: `\bDPIA\b`, `data[- ]protection
impact assessment`, `lawful basis`, `legitimate interest`, `\bconsent\b`,
`retention`, `data processing agreement`. Note what is NOT an indicator: the
bare word "GDPR". A task saying "be GDPR compliant" is a name-drop, not a
lawful-basis decision - leaving it unmatched keeps the floor honest and hands
the judgment call to the semantic pass, by design.

**The demonstration.** `assets/sample_plan.json` builds a customer database
(T1), a sign-up flow (T2), imports an email list (T3), and integrates a
third-party e-mail platform (T4). Every task triggers the profile; zero
tasks contain any indicator. Result (golden:
`assets/expected_report_plan.json`): six `missing` findings - `lawful-basis`
and `dpia` at CRITICAL, `retention` and `processor-agreements` at HIGH -
each with a prerequisite_note naming the article and the required ordering,
and exit code 1 blocks the gate. The remedy is predecessor tasks wired via
`depends_on` upstream of T1/T4 - authored downstream by wbs-decomposition
and critical-path-scheduler (routed by name).

## 4. Maintenance

- Version profiles through git like any hub asset; a profile edit is a
  reviewable diff, which is the point (see anti-pattern "systematic,
  self-serving omission").
- Regulatory rows rot: every regulation-derived note carries "verify against
  current regulation and jurisdiction", and named regulators or thresholds
  should be re-checked per project. Profiles are not legal advice.
- When the semantic pass repeatedly flags a `profile-gap` (a real concern no
  profile covers), add the concern WITH its mined source, and re-run the
  calibration artifacts.
- Keep the shipped five profiles as reference implementations; per-project
  profiles live with the project and are passed via `--profiles`.

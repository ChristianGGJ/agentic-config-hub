# blind-spot-audit

Deterministic blind-spot and hidden-prerequisite detection for project ideas
and draft plans. One transformation: **(brief or plan.json, domain profiles)
-> ranked omission/prerequisite findings** in the `blind_spot_report.json`
contract.

Briefs written from the inside view cover product and marketing and
systematically omit logistics, payments, returns, privacy prerequisites, and
day-2 operations. This skill scans the artifact against version-controlled
domain-profile taxonomies (five ship in `assets/profiles/`: ecommerce,
data-privacy, legal-compliance, procurement-vendor, operations-support) and
reports every concern as `covered`, `partial`, or `missing` - with quoted
evidence, a severity, and, for prerequisite-class concerns, a note stating
what must be true BEFORE the work starts (the canonical case: GDPR lawful
basis and DPIA before a customer database is built).

## Quick start

```bash
# Audit an idea/brief
python scripts/coverage_gap_scanner.py assets/sample_brief.md \
    --profiles assets/profiles --select ecommerce,data-privacy

# Audit a draft plan for hidden prerequisites
python scripts/coverage_gap_scanner.py assets/sample_plan.json --plan \
    --profiles assets/profiles --select data-privacy --json

# Cross-check against a stakeholder register (regulator -> compliance mandatory)
python scripts/coverage_gap_scanner.py assets/sample_brief.md \
    --profiles assets/profiles --select legal-compliance \
    --stakeholders assets/sample_stakeholder_register.json
```

Exit codes: `0` pass, `1` gate fail (missing concern at/above `--fail-on`),
`2` usage/input error. Python 3.8+ stdlib only; no network, no LLM calls.

The scanner is the deterministic floor; the LLM semantic pass described in
`SKILL.md` catches paraphrases the regex layer misses. See `SKILL.md` for the
full interface, worked examples, mined anti-patterns, and routing to sibling
skills (stakeholder-inference upstream, sequential-elicitation downstream).

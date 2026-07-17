# stakeholder-inference

Turn a project brief into a classified stakeholder register: infer users,
operators, suppliers, regulators, sponsors, and affected third parties -
including the actors the brief only implies - rate influence and interest
on the Mendelow grid, and gate the result with a deterministic validator
before planning consumes it.

## Quick start

```bash
# Validate the shipped valid sample (exit 0)
python scripts/stakeholder_register_validator.py assets/sample-stakeholder-register.json

# Validate the seeded-defective sample (exit 1: duplicate id, empty
# inference_basis, missing regulator coverage)
python scripts/stakeholder_register_validator.py assets/sample-stakeholder-register-defective.json

# Waive a genuinely absent category with a reason the human gate can judge
python scripts/stakeholder_register_validator.py register.json \
    --waive "supplier:fully in-house build, no external vendors"

# Machine-readable report for CI (golden copies ship in assets/)
python scripts/stakeholder_register_validator.py register.json --json
```

Exit codes: 0 valid / 1 findings / 2 usage or input error.

## Package contents

- `SKILL.md` - master documentation: contract, workflow, anti-patterns,
  routing to sibling skills
- `scripts/stakeholder_register_validator.py` - deterministic gate
  (Python 3.8+ stdlib only, offline, no LLM or network calls)
- `references/stakeholder_identification_methodology.md` - PMBOK
  stakeholder domain, Mitchell-Agle-Wood salience, Mendelow grid
- `references/inference_prompt_guide.md` - two-pass inference method and
  the regulator inference table by domain
- `assets/` - sample brief, valid and seeded-defective registers, and
  golden expected-findings JSON for both

Self-contained: copy this folder and use it immediately - zero
cross-skill dependencies.

# plan-premortem

Prospective-hindsight plan stress-testing for the agentic-config-hub. The
skill operationalizes Gary Klein's premortem method: assert that the plan
has ALREADY FAILED, expand stressor axes (e.g. supplier_delay x
demand_multiplier x key_person_loss) into adverse-future scenarios, write
past-tense failure narratives, and harden the plan with mitigations and
contingency triggers recorded in a validated premortem register - the hub's
canonical risk artifact.

## What is inside

- `SKILL.md` - the method, interface contract, mined anti-patterns, routing
- `scripts/scenario_matrix_expander.py` - deterministic cartesian expansion
  of a stressor-axes spec, with a `--max-scenarios` cap and an explicit
  truncation notice
- `scripts/premortem_register_validator.py` - deterministic gate: narrative,
  likelihood/impact bands, early-warning signal, contingency trigger linked
  to a plan task id, owner, mitigation-or-acceptance at the threshold
- `references/` - the Klein prospective-hindsight protocol and the canonical
  register specification
- `assets/` - sample plan, sample axes spec, a seeded-invalid sample
  register, a fully valid register, expected outputs, and a blank template

## Quick start

```bash
# Expand the sample axes into a bounded scenario matrix
python scripts/scenario_matrix_expander.py assets/sample-axes-spec.json --max-scenarios 24

# Gate a register against its plan (the sample has one seeded-invalid entry)
python scripts/premortem_register_validator.py assets/sample-premortem-register.json \
    --plan assets/sample-plan.json
```

Exit codes on both tools: 0 pass, 1 gate failure (findings / capped
expansion under `--fail-on-truncation`), 2 usage or input error. Both are
Python 3.8+ standard library only - offline, deterministic, no LLM or
network calls. Copy this folder anywhere and it works unchanged.

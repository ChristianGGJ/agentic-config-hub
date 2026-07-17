# sequential-elicitation

Bounded two-way scope questioning for underspecified ideas: one question at
a time (max 3 when tightly coupled), each derived from the prior answer,
tracked in an append-only JSONL ledger. A deterministic governor -
`scripts/elicitation_ledger.py` - decides continue-or-stop against the hub
six-type exit-condition taxonomy (max_iterations, no_progress, oscillation,
budget, success_predicate, escalation_trigger). The governor never generates
questions; that is the LLM's job, guided by `references/`.

## Quick start

```bash
# Seed an agenda from a blind-spot-audit report (or hand-write one)
python scripts/elicitation_ledger.py \
    --seed-from assets/sample_blind_spot_report.json > agenda.json

# Between every exchange: is another question legal?
python scripts/elicitation_ledger.py \
    --agenda assets/sample_agenda.json \
    --ledger assets/sample_ledger_healthy.jsonl
# exit 0 = ask one more question; exit 1 = STOP (condition named in the
# report); exit 2 = input error

# Machine-readable report
python scripts/elicitation_ledger.py --agenda assets/sample_agenda.json \
    --ledger assets/sample_ledger_saturated.jsonl --json
```

## Package contents

- `SKILL.md` - master documentation: interface, usage, mined anti-patterns,
  routing table, exit-code decision record
- `scripts/elicitation_ledger.py` - deterministic loop governor (Python
  3.8+ stdlib only, offline, `--help` / `--json`)
- `references/sequential_questioning_method.md` - the questioning method
- `references/ledger_and_exit_conditions.md` - data contracts and the six
  exit conditions instantiated for dialogue
- `assets/` - sample agenda, blind-spot report, healthy / saturated /
  oscillating ledgers, and golden expected reports for regression checks

Self-contained: copy this folder and use it - no cross-skill dependencies.

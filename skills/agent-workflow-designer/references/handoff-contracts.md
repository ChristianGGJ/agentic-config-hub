# Handoff Contracts

A handoff is the typed payload one workflow step hands to the next. Untyped handoffs are
where multi-step workflows silently drift: a producer emits a shape the consumer did not
expect, and the failure surfaces three steps later as garbage. This file defines the
minimum contract, a full example, and the validation rules that let a handoff be
rejected *at the edge* instead of deep in the graph.

> Scope: step-to-step handoffs inside a single workflow. Team-level role handoffs
> (H1-H5 between agents) are defined in `agents/CLAUDE.md`; ecosystem-gate rules
> (R1-R6) live in `agentic-system-architect`. This file is the workflow-edge contract.

## 1. The minimum contract

Every handoff payload carries these fields:

| Field | Type | Semantics |
|-------|------|-----------|
| `from_step` | string | id of the producing step (must exist in the workflow) |
| `to_step` | string | id of the consuming step (must list `from_step` in its `depends_on`) |
| `status` | enum `ok` \| `error` \| `needs_review` | Outcome of the producing step |
| `payload` | object | The typed artifact; shape declared by the producer's output schema |
| `schema_ref` | string | Name/version of the schema `payload` conforms to |
| `artifacts` | array of paths | Files written by the step (relative to the ecosystem root) |
| `provenance` | object | `{step, timestamp, tool, inputs_hash}` for audit and dedup |

`status = error` or `needs_review` must set an `escalation` note; the consumer does not
run on a non-`ok` handoff without an explicit gate.

## 2. Example payload

```json
{
  "from_step": "extract-entities",
  "to_step": "validate-entities",
  "status": "ok",
  "schema_ref": "entity-list@1.0.0",
  "payload": {
    "entities": [
      {"name": "ACME Corp", "type": "org", "confidence": 0.94},
      {"name": "2026-07-12", "type": "date", "confidence": 0.99}
    ]
  },
  "artifacts": ["ecosystems/demo/work/entities.json"],
  "provenance": {
    "step": "extract-entities",
    "timestamp": "<stamped-at-runtime>",
    "tool": "entity_extractor",
    "inputs_hash": "sha256:abcd1234"
  }
}
```

## 3. Validation rules for a handoff edge

A workflow engine (or the `hitl_gate_validator`-style checker) rejects a handoff when:

1. **Dangling reference** — `from_step` or `to_step` is not a declared step id.
2. **Unlisted dependency** — `to_step` does not list `from_step` in its `depends_on`
   (the edge is not part of the declared DAG).
3. **Missing schema** — `schema_ref` is absent, or `payload` does not conform to the
   named schema (type/required-field check).
4. **Silent non-ok** — `status != ok` without an `escalation` note or a downstream gate.
5. **Provenance gap** — `provenance` missing `step`/`tool`, so the handoff cannot be
   audited or deduplicated.
6. **Cycle** — following `depends_on` edges forms a cycle (workflows are acyclic; loops
   belong inside a step, guarded by exit conditions — see the flagship loop patterns).

Reject on the FIRST violated rule, name the rule, and point at the offending field —
the same fail-fast discipline the team-level rejection rule uses (a malformed handoff
costs no downstream cycle).

## 4. Typing the payload

- Declare each step's output schema next to the step, version it (`name@major.minor.patch`),
  and bump on any breaking field change.
- Prefer closed schemas (no unexpected keys) so drift is caught, not absorbed.
- Keep `artifacts` as repo-relative paths inside the ecosystem, never absolute — handoffs
  must stay portable when an ecosystem is extracted.

## 5. Hub canon integration

- A handoff with `status = needs_review` is the workflow-edge form of an
  `escalation_trigger`: the consumer waits for a human/gate.
- `provenance.inputs_hash` feeds `no_progress` and `oscillation` detection: identical
  input hashes recurring across iterations mean the loop is not advancing.
- Irreversible consumers (a step with `irreversible: true`) must sit behind a gate whose
  approval consumes the upstream handoff — never auto-run on an incoming `ok` alone
  (gate rule R1).

# HITL Defensive Architectures

Human-in-the-Loop (HITL) flow control is the discipline of deciding, in advance and in writing, exactly where an autonomous agent must stop and wait for a human. The core principle: **autonomy is earned per-action-class, not granted globally**. An agent that has proven reliable at editing files in a working tree has earned nothing regarding production deploys, data deletion, or spending money. Each class of action carries its own irreversibility profile, and gate strictness must scale with that profile — never with the agent's general track record, the operator's mood, or schedule pressure.

Defensive HITL design answers three questions before the agent runs a single step:

1. **Classification** — how irreversible is each action the agent may take?
2. **Gating** — which gate type protects each action class, and where is it placed?
3. **Recovery** — if a gated action goes wrong anyway, who is called and how is it rolled back?

This reference covers all three, culminating in the 5-Phase Protocol — the standard operating procedure that turns these principles into an enforceable workflow.

---

## Irreversibility Classification

Every action an agent can take falls into one of three classes. Classify actions at design time, in the workflow definition — not at runtime, when the agent has an incentive to classify optimistically.

### Class 1 — REVERSIBLE

Actions that can be fully undone with a single local operation, with no external observers.

- Editing a file in a git working tree (undo: `git checkout -- <file>`)
- Generating a draft document, plan, or report for review
- Creating files in a scratch or temporary directory
- Running read-only analysis scripts

**Gate requirement:** none beyond the standing Override/Abort Gate. Reversible actions are where autonomy is earned.

### Class 2 — COSTLY

Actions that are technically undoable, but where undoing is expensive, error-prone, or disruptive.

- A mass refactor touching dozens of files (revert is possible but merge conflicts accumulate)
- A schema migration on a dev or staging database (rollback scripts exist but may lose test data)
- Rewriting shared configuration used by other teams
- Long-running batch jobs that consume significant compute budget

**Gate requirement:** at minimum a Checkpoint Gate before the action, plus a defined rollback plan. A Pre-Execution Approval Gate is strongly recommended when the blast radius crosses team boundaries.

### Class 3 — IRREVERSIBLE

Actions whose effects cannot be undone, or whose effects escape the system boundary the moment they execute.

- Production deploy
- Data deletion (dropping tables, purging records, emptying trash)
- External publication (posting, emailing, publishing a package, pushing to a public registry)
- Spend (purchases, paid API commitments, resource provisioning with cost)

**Gate requirement:** a hard Pre-Execution Approval Gate with explicit human approval, a rollback plan (or an explicit, justified opt-out — see Escalation and Rollback Design), and an escalation contact. No exceptions, no batching multiple irreversible actions under one approval.

**The scaling rule:** gate strictness scales with class. REVERSIBLE actions run freely. COSTLY actions run behind checkpoints and rollback plans. IRREVERSIBLE actions run only after a named human says yes to that specific action.

---

## Gate Taxonomy

Four gate types cover all defensive HITL needs. Each has a definition and a placement rule.

### 1. Pre-Execution Approval Gate

**Definition:** a hard stop placed immediately before a specific action or batch of actions. The agent presents what it is about to do (the manifest), and a human approves, edits, or rejects. The agent cannot proceed on timeout, silence, or inferred consent.

**Placement rule:** directly upstream of every IRREVERSIBLE action, and upstream of COSTLY actions that cross ownership boundaries. In workflow definitions, this is a `type: gate` step that the protected step `depends_on` (see Encoding Gates below).

### 2. Checkpoint Gate (mid-workflow)

**Definition:** a scheduled pause at a natural seam in a long workflow — after discovery, after each batch of N changes, after the first item of a repetitive series — where the agent surfaces progress and a human can course-correct before the pattern repeats at scale.

**Placement rule:** insert after the first instance of any repeated operation (approve one, then the pattern), and at every transition between workflow phases. Checkpoint Gates convert one large approval decision into several small, well-informed ones.

### 3. Escalation Gate (triggered by exit conditions)

**Definition:** a conditional gate that fires only when a loop control trips. It is bound to the exit-condition taxonomy: `max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger`. When any of these fires in a way the agent cannot resolve, control transfers to a human with full context instead of the agent improvising.

**Placement rule:** attach to every loop in the system. An Escalation Gate is the answer to "what happens when the retry budget is exhausted" — the answer is never "try something creative"; it is "package the state and hand it to the escalation contact."

### 4. Override/Abort Gate (always available to the human)

**Definition:** a standing control, not a step. At any moment, the human can pause, redirect, or abort the workflow, and the agent must honor it immediately — mid-loop, mid-write, mid-anything — leaving the system in the safest reachable state and reporting exactly what completed and what did not.

**Placement rule:** everywhere, always. If the architecture has any state in which a human cannot stop the agent, the architecture is wrong. Override/Abort is the only gate that requires no placement decision because its placement is universal.

---

## The 5-Phase Protocol

The 5-Phase Protocol is the canonical structure for any agent engagement that writes to anything. It sequences the gates above into a repeatable operating procedure.

- **Phase 1 — DISCOVERY (read-only):** map scope, constraints and boundaries. No writes allowed.
- **Phase 2 — MANIFEST:** produce an explicit change manifest (files to create/modify, risks, rollback plan).
- **Phase 3 — HUMAN GATE:** hard stop. A human approves, edits, or rejects the manifest. No implementation without approval.
- **Phase 4 — IMPLEMENTATION:** bounded execution strictly against the approved manifest. Any deviation returns to Phase 2.
- **Phase 5 — SELF-REVIEW & HANDOFF:** audit own diff against the manifest, run verification, produce a handoff report.

### Phase 1 — DISCOVERY (read-only)

- **Allowed operations:** reading files, searching, listing directories, running read-only analysis, asking clarifying questions.
- **Forbidden operations:** any write, any file creation (including "harmless" scratch notes in the target tree), any state mutation, any external call with side effects.
- **Entry criteria:** a task statement and a defined scope boundary (allowed paths, allowed tools).
- **Exit criteria:** the agent can state what exists, what must change, what must not be touched, and what it still does not know.
- **Artifact produced:** a scope summary feeding directly into Phase 2.

### Phase 2 — MANIFEST

- **Allowed operations:** drafting the Change Manifest; further read-only inspection to refine it.
- **Forbidden operations:** all writes to target files. The manifest describes changes; it does not make them.
- **Entry criteria:** Phase 1 exit criteria met.
- **Exit criteria:** a complete manifest with every planned file operation, a risk rating per item, a rollback plan, and declared exit conditions.
- **Artifact produced:** the **Change Manifest**:

```markdown
# Change Manifest

## Objective
<one paragraph: what this change accomplishes and why>

## Files to Create
| Path | Purpose | Risk |
|------|---------|------|
| path/to/new_file.py | <purpose> | REVERSIBLE |

## Files to Modify
| Path | Nature of Change | Risk |
|------|------------------|------|
| path/to/existing.md | <what changes> | REVERSIBLE / COSTLY / IRREVERSIBLE |

## Risk Assessment
- <item>: <risk class and why>

## Rollback Plan
- <per item or per batch: exact undo procedure, or "none:justified:<reason>">

## Exit Conditions Declared
- max_iterations: <n>
- budget: <tool calls / time / tokens>
- success_predicate: <verifiable completion test>
- escalation_trigger: <condition that transfers control to a human>
```

### Phase 3 — HUMAN GATE

- **Allowed operations:** presenting the manifest; answering questions about it; incorporating requested edits into a revised manifest.
- **Forbidden operations:** any implementation work. Waiting is the work. No "getting a head start" on approved-seeming items.
- **Entry criteria:** a complete Change Manifest from Phase 2.
- **Exit criteria:** explicit human approval of the manifest (possibly after edits), or rejection (which ends the engagement or returns it to Phase 1).
- **Artifact produced:** the approved manifest — now a contract, not a proposal.

### Phase 4 — IMPLEMENTATION

- **Allowed operations:** exactly the operations enumerated in the approved manifest, in a bounded loop with the declared exit conditions active.
- **Forbidden operations:** touching any file not in the manifest; changing the nature of an approved change; "while I'm here" improvements; exceeding declared budgets.
- **Entry criteria:** Phase 3 approval on record.
- **Exit criteria:** every manifest item completed, or a deviation discovered. **Any deviation returns to Phase 2** — a new or amended manifest, and a fresh pass through the Human Gate. Deviations include: a needed change to an unlisted file, a listed change that turns out larger than described, or a risk class that was underestimated.
- **Artifact produced:** the implemented diff.

### Phase 5 — SELF-REVIEW & HANDOFF

- **Allowed operations:** diffing actual changes against the manifest, running verification (tests, linters, validators), writing the handoff report.
- **Forbidden operations:** new functional changes. Fixes discovered during self-review that go beyond the manifest return to Phase 2.
- **Entry criteria:** Phase 4 complete.
- **Exit criteria:** handoff report delivered.
- **Artifact produced:** the **Handoff Report**:

```markdown
# Handoff Report

## Manifest vs Actual Diff
| Manifest Item | Status | Notes |
|---------------|--------|-------|
| path/to/file  | done / partial / skipped | <exact deviation if any> |

## Verification Results
- <command run>: <pass/fail + summary>

## Deviations
- <every difference between manifest and actual, however small, with why>

## Open Risks
- <anything the next human should watch: untested paths, assumptions, follow-ups>
```

---

## Encoding Gates in Workflow Definitions

Gates that live only in prose are gates that get skipped. Encode them in a machine-checkable workflow definition and validate with `hitl_gate_validator.py`.

Canonical workflow JSON schema (when the validator is given a `.md` file, it extracts the first fenced json code block):

```json
{
  "name": "string",
  "version": "1.0.0",
  "steps": [
    {
      "id": "string",
      "type": "action|gate|check",
      "description": "string",
      "irreversible": false,
      "requires_approval": false,
      "rollback": "string or null",
      "on_failure": "retry|escalate|abort",
      "max_retries": 2,
      "depends_on": ["id"]
    }
  ],
  "escalation": {"contact": "role-or-person", "trigger": "string"}
}
```

Validate:

```bash
python scripts/hitl_gate_validator.py workflow.json --json
```

Result is PASS if no CRITICAL and no HIGH violations, otherwise FAIL. The six rules:

### R1 (CRITICAL) — Irreversible steps must be gated

Every step with `irreversible: true` must have `requires_approval: true` OR be preceded (via its `depends_on` chain) by a `type: gate` step.

- **Violating example:** `{"id": "deploy-prod", "type": "action", "irreversible": true, "requires_approval": false, "depends_on": ["run-tests"]}` where `run-tests` is a `check`, not a `gate`.
- **Fix:** set `"requires_approval": true`, or insert `{"id": "approve-deploy", "type": "gate", ...}` and make `deploy-prod` depend on it.

### R2 (HIGH) — Irreversible steps must define rollback

Every irreversible step must define a non-null `rollback` (or a literal string starting with `none:justified:`).

- **Violating example:** `{"id": "purge-records", "irreversible": true, "rollback": null}`.
- **Fix:** `"rollback": "restore from snapshot backup-2026-07-10"` — or, if truly impossible, `"rollback": "none:justified:records are legally required to be destroyed; approved by DPO"`.

### R3 (HIGH) — Escalation object required

The workflow must define the top-level `escalation` object.

- **Violating example:** a workflow JSON with `name`, `version`, and `steps` but no `escalation` key.
- **Fix:** add `"escalation": {"contact": "on-call-platform-engineer", "trigger": "any step exhausts retries or an irreversible step fails"}`.

### R4 (MEDIUM) — Action steps must declare failure handling

Every `type: action` step must define `on_failure`; `on_failure: retry` requires `max_retries >= 1`.

- **Violating example:** `{"id": "migrate-schema", "type": "action", "on_failure": "retry", "max_retries": 0}`.
- **Fix:** set `"max_retries": 2`, or change to `"on_failure": "escalate"` if retrying a migration is unsafe.

### R5 (MEDIUM) — Dependency graph must be valid

All `depends_on` references must exist and the dependency graph must be acyclic.

- **Violating example:** `{"id": "a", "depends_on": ["b"]}` and `{"id": "b", "depends_on": ["a"]}` — a cycle; or `"depends_on": ["approval-gate"]` when no step with that id exists.
- **Fix:** break the cycle by removing the false dependency; correct dangling ids to real step ids.

### R6 (LOW) — End with self-review

The final step should be `type: check` (self-review).

- **Violating example:** a workflow whose last step is the production deploy action itself.
- **Fix:** append `{"id": "self-review", "type": "check", "description": "audit diff against manifest, run verification, produce handoff report", "depends_on": ["deploy-prod"]}`.

---

## Escalation and Rollback Design

### The escalation contract

Escalation is a designed handoff, not a panic. Define it before execution as a three-part contract:

- **Who:** a named role or person (`"contact": "on-call-platform-engineer"`), not "someone" or "the team". The `escalation_trigger` exit condition is only meaningful if it resolves to a reachable human.
- **When:** the precise triggers — retry budget exhausted, `no_progress` or `oscillation` detected, an irreversible step failed, the `budget` exit condition fired, or the agent's `success_predicate` cannot be evaluated.
- **With what context:** the agent must deliver the current manifest, what completed vs. what did not, the exact error or condition that fired, and the state of any partial changes. An escalation without context converts one incident into two.

### Rollback discipline

- **Defined BEFORE execution.** A rollback plan invented mid-incident is a guess. Every COSTLY or IRREVERSIBLE step carries its rollback in the manifest and in the workflow JSON, written while the system is calm.
- **Tested when feasible.** A restore procedure that has never been run is a hypothesis. For COSTLY actions, rehearse the rollback on a copy (restore the snapshot to staging, revert the refactor branch) before trusting it.
- **`none:justified:<reason>` as explicit opt-out.** Some actions genuinely have no rollback (an email sent, data legally destroyed). The rule R2 escape hatch exists so that "no rollback" is a documented, human-reviewable decision — never a silent omission. The reason must say why no rollback exists and who accepted that.

---

## Defense in Depth

No single control is sufficient, because each protects against a different failure mode. A hardened ecosystem layers three independent defenses:

1. **Boundaries in context packs** — the context pillar declares allowed paths, forbidden zones, and out-of-scope areas. This stops the agent from wandering even when its reasoning is sound.
2. **Loop controls in agents** — each agent definition carries the exit-condition taxonomy (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger`). This stops runaway behavior even inside allowed boundaries.
3. **Gates in workflows** — workflow definitions encode approval gates, rollback plans, and escalation, validated by `hitl_gate_validator.py`. This stops irreversible harm even when a loop terminates "successfully" on a wrong plan.

The layers are independent: a prompt injection that erodes the agent's judgment does not remove the workflow gate; a workflow authored without a gate is still contained by context-pack boundaries; a boundary mistake is still caught when the loop's `budget` fires. Design each layer as if the other two have already failed.

---

## Anti-Patterns

### Gate theater: approval requested after execution

The agent performs the action, then asks "shall I proceed?" — or presents an approval prompt while the write is already queued. The human is rubber-stamping history. Detection: compare timestamps of the action and the approval request; in the 5-Phase Protocol, any Phase 4 artifact dated before Phase 3 approval is gate theater. Fix: gates are `depends_on` predecessors of the actions they protect, never followers.

### Blanket approvals

"Approved — and consider everything like this approved too." One yes gets generalized across sessions, across action classes, or across an unbounded series of irreversible steps. Approval is per-action (or per explicit, enumerated batch) and per-session. A manifest approval covers exactly the items in that manifest; item 41 added later returns to Phase 2 and gets its own gate.

### Irreversible steps hidden inside "safe" scripts

A step described as "run cleanup script" is classified REVERSIBLE, but the script internally deletes records or publishes artifacts. The workflow JSON honestly passes R1 because the dishonesty lives one level down. Fix: classify by the *most irreversible effect reachable from the step*, not by the step's label. During Phase 1 discovery, read what scripts actually do before classifying the step that invokes them; during review, treat any opaque executable step as IRREVERSIBLE until proven otherwise.

### Timeout-as-consent

A gate that auto-approves if the human does not respond within N minutes is not a gate; it is a delay. Silence is never approval. The correct behavior on timeout is to remain stopped and fire the `escalation_trigger`.

### Escalation to nowhere

The workflow defines `escalation` to satisfy R3, but the contact is a defunct alias or a role nobody holds. Verify the contact resolves to a reachable human as part of workflow review — R3 checks the object exists; only a human can check that it works.

---

**Related references:** [loop_engineering_patterns.md](loop_engineering_patterns.md) for exit-condition design, [react_reasoning_patterns.md](react_reasoning_patterns.md) for reasoning-cycle contracts, [four_pillar_ecosystem.md](four_pillar_ecosystem.md) for where gates live in the overall architecture.

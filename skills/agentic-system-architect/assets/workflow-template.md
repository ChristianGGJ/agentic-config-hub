---
name: "[workflow-name]"
version: "1.0.0"
description: "[One sentence: the end-to-end process this workflow orchestrates]"
type: "workflow"
---

# Workflow: [workflow-name]

> Template usage: replace every `[bracketed placeholder]`, then validate with
> `python scripts/hitl_gate_validator.py <this-file>`. The validator extracts
> the FIRST fenced json code block in this file (the Definition section below)
> and checks rules R1-R6. The example definition ships in a passing state —
> keep it passing as you edit.

## Purpose

[2-4 sentences: what this workflow achieves, when it is triggered, and what
"done" means. Name the single most dangerous step and why it is gated. Example:
"Applies an approved schema migration to production. The `implement` step is
irreversible for dropped columns, so it sits behind a hard human gate."]

## Actors

| Actor | Type | Responsibility |
|---|---|---|
| `[cs-agent-name]` | agent | Executes discovery, manifest, backup, and implementation steps. |
| `[reviewer-role]` | human | Approves, edits, or rejects the manifest at the HUMAN GATE. |
| `[escalation-contact]` | human | Receives escalations, failures, and rollback notifications. |

## Gate Map

Classify every step BEFORE deciding where gates go:

| Class | Definition | Gate policy |
|---|---|---|
| REVERSIBLE | Undo is a single cheap operation (e.g. revert a commit). | No gate; automatic rollback on failure. |
| COSTLY | Undo is possible but expensive or slow (e.g. bulk migration, re-index). | Gate recommended; rollback plan mandatory. |
| IRREVERSIBLE | No undo exists (e.g. sent email, deleted backup, external payment). | Hard gate mandatory: `requires_approval: true` AND an upstream `type: gate` step. |

Gated steps in this workflow:

| Step id | Class | Why it is gated |
|---|---|---|
| `human-gate` | n/a (the gate itself) | Manifest approval before any mutation happens. |
| `implement` | IRREVERSIBLE | [e.g. rewrites production configuration with no automatic undo] |

## Definition

```json
{
  "name": "[workflow-name]",
  "version": "1.0.0",
  "steps": [
    {
      "id": "discover",
      "type": "action",
      "description": "DISCOVERY (read-only): map scope, constraints and boundaries. No writes allowed.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "retry",
      "max_retries": 2,
      "depends_on": []
    },
    {
      "id": "manifest",
      "type": "action",
      "description": "MANIFEST: produce an explicit change manifest (files to create/modify, risks, rollback plan).",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "retry",
      "max_retries": 1,
      "depends_on": ["discover"]
    },
    {
      "id": "human-gate",
      "type": "gate",
      "description": "HUMAN GATE: hard stop. A human approves, edits, or rejects the manifest. No implementation without approval.",
      "irreversible": false,
      "requires_approval": true,
      "rollback": null,
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["manifest"]
    },
    {
      "id": "backup",
      "type": "action",
      "description": "Snapshot current state ([e.g. git branch or database dump]) so implementation can be rolled back.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": "Delete the snapshot; no other state was touched.",
      "on_failure": "abort",
      "max_retries": 0,
      "depends_on": ["human-gate"]
    },
    {
      "id": "implement",
      "type": "action",
      "description": "IMPLEMENTATION: bounded execution strictly against the approved manifest. Any deviation returns to the manifest step.",
      "irreversible": true,
      "requires_approval": true,
      "rollback": "Restore from the snapshot created in step 'backup' and revert every file listed in the manifest.",
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["backup"]
    },
    {
      "id": "verify",
      "type": "check",
      "description": "SELF-REVIEW & HANDOFF: audit own diff against the manifest, run verification, produce a handoff report.",
      "irreversible": false,
      "requires_approval": false,
      "rollback": null,
      "on_failure": "escalate",
      "max_retries": 0,
      "depends_on": ["implement"]
    }
  ],
  "escalation": {
    "contact": "[role-or-person, e.g. tech-lead]",
    "trigger": "Any gate rejection, failed verification, exhausted retries, or rollback execution."
  }
}
```

## Rollback Plan

- **Trigger:** the `verify` check fails, or a human orders rollback at any point after `implement`.
- **Procedure:**
  1. [Restore the snapshot created in step `backup`, e.g. "git reset --hard snapshot-branch" or "restore dump 2026-XX-XX".]
  2. [Re-run the verification command against the restored state and confirm exit code 0.]
  3. [Announce the rollback and its cause in the channel owned by the escalation contact.]
- **Owner:** [role responsible for executing and confirming the rollback]
- **Verification of rollback:** [command or check that proves the restore succeeded]

## Escalation

- **Contact:** [role-or-person, e.g. tech-lead] via [channel]
- **Triggers:** gate rejection at `human-gate`, any step firing `on_failure: escalate`,
  rollback execution, or two consecutive failed retries anywhere in the workflow.
- **Payload:** workflow name and version, failing step id, the last observation or
  error message, current rollback status, and the single decision needed from the human.

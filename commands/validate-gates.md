---
name: validate-gates
description: |
  Validate a workflow definition against defensive HITL gate rules R1-R6.
  Ensures no irreversible actions are executed without preceding gates.
  Usage: /validate-gates <workflow-path>
---

# /validate-gates

Validate a workflow configuration file (`.md` or `.json`) against the defensive Human-in-the-Loop (HITL) gate rules R1-R6. Target: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the user which workflow file to validate (e.g., `workflows/design-ecosystem.md`).

## Usage

```bash
/validate-gates workflows/design-ecosystem.md
/validate-gates workflows/harden-agent.md
```

## Step 1: Validate Input

1. Verify the path exists. If not, stop and report.
2. Read the workflow file. If it ends in `.md`, ensure it contains a fenced JSON block holding the workflow definition.

## Step 2: Run Validator

```bash
python skills/agentic-system-architect/scripts/hitl_gate_validator.py {workflow_path} --json
```

- If validation passes (`result` is `"PASS"`), output a success message and stop.
- If validation fails (`result` is `"FAIL"`), extract the list of violations:
  - Severity level (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`)
  - Rule identifier (`R1` to `R6`)
  - Remediation guidance

## Step 3: Remediation & Reporting

1. List every violation, sorted by severity.
2. Direct the user on how to resolve the findings:
   - For `R1` (CRITICAL) - Insert a preceding `type: gate` step or set `requires_approval: true`.
   - For `R2` (HIGH) - Add a non-null `rollback` string.
   - For `R3` (HIGH) - Declare the top-level `escalation` object (`contact`, `trigger`).
3. Re-run validation after modifications until it returns **PASS**.

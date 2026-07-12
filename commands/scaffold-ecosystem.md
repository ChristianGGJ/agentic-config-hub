---
name: scaffold-ecosystem
description: |
  Scaffold a four-pillar agentic config ecosystem (context/, skills/, agents/, workflows/)
  in the product plane. Usage: /scaffold-ecosystem <project-name> [--output DIR]
  (default output: ecosystems/)
---

# /scaffold-ecosystem

Scaffold the directory structure for a new four-pillar agentic configuration ecosystem, seeded with hardened template examples. Target: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the user what name to give the new ecosystem (kebab-case, e.g. `erp-mobilefirst`).

## Usage

```bash
/scaffold-ecosystem erp-mobilefirst                     # -> ecosystems/erp-mobilefirst/
/scaffold-ecosystem client-x --output ecosystems/_local # private client work (git-ignored)
```

## Where Ecosystems Live

- **Default output is `ecosystems/`** — the product plane. Never scaffold a product into the hub's root pillars (boundaries rule F10).
- Client-sensitive or experimental work goes to `ecosystems/_local/` (git-ignored, rule F11).
- A different `--output` is allowed only when the user explicitly asks for an out-of-repo destination.

## Step 1: Dry Run (Manifest for the HUMAN GATE)

Print the file plan first and show it to the user for approval:

```bash
python skills/agentic-system-architect/scripts/ecosystem_scaffolder.py {project_name} --output ecosystems --dry-run
```

This is the Phase 3 HUMAN GATE: do not write anything until the user confirms the plan. Offer `--pillars context,agents` style subsets if the user only needs part of the structure.

## Step 2: Execute Scaffolder

After confirmation:

```bash
python skills/agentic-system-architect/scripts/ecosystem_scaffolder.py {project_name} --output ecosystems
```

Add `--force` only if the user explicitly wants to overwrite an existing ecosystem.

## Step 3: Gate the Generated Components

```bash
python skills/agentic-system-architect/scripts/loop_auditor.py ecosystems/{project_name}/agents/example-agent.md --min-score 90
python skills/agentic-system-architect/scripts/hitl_gate_validator.py ecosystems/{project_name}/workflows/example-workflow.md
```

Both must pass (HARDENED / PASS) before reporting success.

## Step 4: Register and Hand Off

1. Add a row to the registry table in `ecosystems/README.md` (name, target project, status `draft`, creation date).
2. Create `ecosystems/{project_name}/MANIFEST.md` from the approved plan with frontmatter `status: draft` (use the Change Manifest template in `skills/agentic-system-architect/references/hitl_defensive_architectures.md`).
3. Report the created file tree, the audit results, and the next step: fill `context/` with the target project's ground truth (CONTEXTUALIZED mode) and author components against the manifest.

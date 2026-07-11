# Codex CLI Instructions

This file provides guidance to the OpenAI Codex CLI when executing tools and orchestrating configurations in this repository.

## Repository Purpose

**agentic-config-hub** is a curated library of production-ready configurations for AI agents and agentic systems. It organizes knowledge, capabilities, personas, and orchestrations into a strict four-pillar architecture: `context/` -> `skills/` -> `agents/` -> `workflows/`.

## Navigation Map

- **context/**: Project boundaries and stable glossary rules. Read-only.
- **skills/**: Reusable, atomic capability packages containing Python CLI tools, knowledge references, and assets.
- **agents/**: Flat directory of role-bound `cs-*` agents composing skills under loop-engineering safety controls.
- **workflows/**: Gated multi-agent orchestrations with embedded HITL (Human-in-the-Loop) safety gates.
- **commands/**: Slash command markdown references.
- **templates/**: Standardized blueprints for new agents and skills.

## Quality Gates

Before any change is committed or promoted:
1. **Python Compilation**: All scripts must compile successfully via `py_compile`.
2. **Loop Auditing**: All agent specifications in `agents/cs-*.md` must pass `loop_auditor.py` with a score of `>= 90` (Grade: `HARDENED`).
3. **Workflow Validation**: All workflow specifications in `workflows/*.md` must pass `hitl_gate_validator.py` with zero CRITICAL or HIGH violations.
4. **Repository Validation**: Run the global validator script to verify the entire workspace:
   ```bash
   python scripts/validate_repo.py
   ```

## Safe Execution Guidelines

- Do not introduce cross-skill dependencies (skills must remain atomic and extractable).
- Do not write to `context/` files outside of an approved Change Manifest.
- Ensure all loops in new configurations define explicit exit conditions (`max_iterations`, `no_progress`, `oscillation`, `budget`).
- Gate all irreversible operations behind a preceding `type: gate` step.

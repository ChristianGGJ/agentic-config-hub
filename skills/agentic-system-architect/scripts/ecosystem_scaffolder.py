#!/usr/bin/env python3
"""Scaffold a four-pillar agentic configuration ecosystem.

Creates the canonical layout used by the agentic-system-architect skill:
a project root with context/, skills/, agents/ and workflows/ pillars, each
seeded with hardened examples. Generated components embed the 5-Phase
Protocol, all six canonical exit conditions (max_iterations, no_progress,
oscillation, budget, success_predicate, escalation_trigger), and a defensive
HITL workflow that passes hitl_gate_validator.py rules R1-R6 out of the box.

Usage examples:
    python ecosystem_scaffolder.py my-agent-stack
    python ecosystem_scaffolder.py my-agent-stack --output ./workspace
    python ecosystem_scaffolder.py my-agent-stack --dry-run
    python ecosystem_scaffolder.py my-agent-stack --force --json

Exit code 0 on success (or dry-run preview); 1 on invalid name, existing
target without --force, or filesystem error. Standard library only
(argparse, pathlib, json, sys, re). No network or LLM calls. Console output
is ASCII-safe (no emoji, no box-drawing characters) for cp1252 consoles.
"""

import argparse
import json
import re
import sys
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ROOT_README = """---
name: "__NAME__"
version: "1.0.0"
description: "Four-pillar agentic configuration ecosystem: context, skills, agents, workflows."
type: context
---

# __NAME__

A four-pillar agentic configuration ecosystem scaffolded by the
agentic-system-architect skill.

## The Four Pillars

| Pillar | Directory | Purpose |
|--------|-----------|---------|
| Context | `context/` | Shared knowledge every agent loads: architecture, boundaries, glossary. |
| Skills | `skills/` | Atomic, self-contained capability packages (one SKILL.md per skill). |
| Agents | `agents/` | Agent specifications: mission, loop safety, HITL gates, output contract. |
| Workflows | `workflows/` | Multi-step orchestrations with human approval gates and rollback plans. |

## Getting Started

1. Fill in `context/architecture.md` and `context/boundaries.md` for your system.
2. Copy the example skill, agent, and workflow to author your own components.
3. Audit agents with `loop_auditor.py` and validate workflows with
   `hitl_gate_validator.py` before granting any autonomy.
"""

CONTEXT_README = """---
name: "__NAME__-context"
version: "1.0.0"
description: "Context pillar index: shared knowledge loaded by every agent in the ecosystem."
type: context
---

# Context Pillar

Shared, always-loaded knowledge for the __NAME__ ecosystem; keep it current.

| File | Contents |
|------|----------|
| `architecture.md` | System components, data flow, and integration points. |
| `boundaries.md` | Allowed paths, forbidden operations, escalation contacts. |
| `glossary.md` | Canonical vocabulary so agents and humans share one language. |
"""

CONTEXT_ARCHITECTURE = """---
name: "__NAME__-architecture"
version: "1.0.0"
description: "System architecture overview for the __NAME__ ecosystem."
type: context
---

# Architecture

## Components

- Describe each major component (services, data stores, external APIs) and
  note which ones agents may touch versus read-only.

## Data Flow

- Trace the primary flow end to end and mark irreversible transitions
  (deploys, deletions, external side effects).

## Integration Points

- List the tools, MCP servers, and scripts agents are expected to call.
"""

CONTEXT_BOUNDARIES = """---
name: "__NAME__-boundaries"
version: "1.0.0"
description: "Hard boundaries: allowed paths, forbidden operations, and escalation contacts."
type: context
---

# Boundaries

## Allowed Paths

- Agents may read and write ONLY inside this ecosystem root.
- Everything outside the root is out-of-scope and forbidden.

## Forbidden Operations

- Permanent deletion of data, and any irreversible action that has not
  passed a HUMAN GATE with an approved manifest.
- Installing dependencies or changing system settings.

## Escalation

- Contact: engineering-lead (replace with a real role or person).
- Trigger: gate rejection, error cascade, budget exhaustion, or any
  situation not covered by an approved manifest.
"""

CONTEXT_GLOSSARY = """---
name: "__NAME__-glossary"
version: "1.0.0"
description: "Canonical vocabulary shared by humans and agents in the __NAME__ ecosystem."
type: context
---

# Glossary

| Term | Definition |
|------|------------|
| Manifest | Explicit change plan (files, risks, rollback) produced before implementation. |
| HUMAN GATE | Hard stop where a human approves, edits, or rejects the manifest. |
| HITL | Human-in-the-loop: flow control that requires human approval for risky actions. |
| Exit condition | Explicit loop-termination rule: max_iterations, no_progress, oscillation, budget, success_predicate, or escalation_trigger. |
| Irreversible action | Any action that cannot be undone with a simple rollback (deploy, delete, send). |
| Handoff report | Structured end-of-task summary: changes, verification, deviations, follow-ups. |
"""

SKILL_MD = """---
name: "example-skill"
version: "1.0.0"
description: "Atomic example skill demonstrating the self-contained skill package pattern."
type: skill
---

# example-skill

An atomic skill for the __NAME__ ecosystem. One skill = one capability,
self-contained, with no dependencies on other skills. Replace the sections
below with the trigger conditions and steps of the real capability.

## Workflow

1. Gather inputs (list the exact files or parameters required).
2. Execute the capability's deterministic steps.
3. Verify the result against the success criteria below.

## Success Criteria

- Define a measurable, checkable outcome (the success predicate).

## Boundaries

- List allowed paths and allowed tools; anything not listed is forbidden.
"""

AGENT_MD = """---
name: "example-agent"
version: "1.0.0"
description: "Reference agent spec hardened with loop safety, HITL gates, and the 5-Phase Protocol."
type: agent
---

# example-agent

A reference agent specification for the __NAME__ ecosystem. Copy it, rename
it, and adapt the mission, boundaries, and output contract for your agents.

## Mission

Execute one bounded task inside this ecosystem while honoring every control
below. The agent never widens its own scope.

## 5-Phase Protocol

| Phase | Name | Rule |
|-------|------|------|
| 1 | DISCOVERY (read-only) | Map scope, constraints and boundaries. No writes allowed. |
| 2 | MANIFEST | Produce an explicit change manifest (files to create/modify, risks, rollback plan). |
| 3 | HUMAN GATE | Hard stop. A human approves, edits, or rejects the manifest. No implementation without approval. |
| 4 | IMPLEMENTATION | Bounded execution strictly against the approved manifest. Any deviation returns to Phase 2. |
| 5 | SELF-REVIEW & HANDOFF | Audit own diff against the manifest, run verification, produce a handoff report. |

## Loop Safety

- max_iterations: 5. The attempt limit is enforced with an explicit counter.
- No progress across 2 consecutive iterations -> stop and escalate.
- Oscillation guard: a repeated action (same tool + input) or an A-B-A-B
  pattern aborts the loop immediately.
- Budget: hard time limit of 15 minutes and a tool-call limit of 20 calls.

## Exit Conditions

Every loop declares an explicit exit condition from this canonical table:

| Exit condition | Trigger |
|----------------|---------|
| max_iterations | The iteration counter reaches the configured ceiling. |
| no_progress | Consecutive iterations produce no progress (no new state change). |
| oscillation | The agent alternates between two actions or states (A-B-A-B). |
| budget | The token, time, or tool-call budget is exhausted. |
| success_predicate | The success criteria (success predicate) evaluate to true. |
| escalation_trigger | An unrecoverable condition fires the escalation path to a human. |

## HITL Gates

- Every irreversible action requires approval at a HUMAN GATE before execution.
- Escalation path: on gate rejection or error cascade, escalate to the contact
  named in `context/boundaries.md`.

## Boundary Control

- Allowed paths: only files inside this ecosystem root; all other paths are
  forbidden and out-of-scope.
- Allowed tools: read, write, and the project scripts (tool allowlist
  enforced). System-level shell commands are forbidden.

## Output Contract

- Success criteria: the approved manifest is fully implemented and verified.
- Handoff report format: summary of changes, verification results, deviations
  (must be empty), and follow-up recommendations.
- Structured handoff: emit the handoff report as the final message.
"""

WORKFLOW_MD = """---
name: "example-workflow"
version: "1.0.0"
description: "Reference HITL workflow: discovery, manifest, human gate, bounded implementation, self-review."
type: workflow
---

# example-workflow

A defensive workflow for the __NAME__ ecosystem. The fenced json block below
is the machine-readable definition; validate it any time with:

    python hitl_gate_validator.py workflows/example-workflow.md

```json
{
  "name": "example-workflow",
  "version": "1.0.0",
  "steps": [
    {"id": "discover", "type": "action", "description": "Read-only discovery of the target scope.",
     "irreversible": false, "requires_approval": false, "rollback": null,
     "on_failure": "retry", "max_retries": 2, "depends_on": []},
    {"id": "manifest", "type": "action", "description": "Produce the change manifest: files, risks, rollback plan.",
     "irreversible": false, "requires_approval": false, "rollback": null,
     "on_failure": "abort", "max_retries": 0, "depends_on": ["discover"]},
    {"id": "human-gate", "type": "gate", "description": "HUMAN GATE: a human approves, edits, or rejects the manifest.",
     "irreversible": false, "requires_approval": true, "rollback": null,
     "on_failure": "escalate", "max_retries": 0, "depends_on": ["manifest"]},
    {"id": "implement", "type": "action", "description": "Apply the approved manifest (irreversible writes).",
     "irreversible": true, "requires_approval": true, "rollback": "git revert the implementation commit",
     "on_failure": "escalate", "max_retries": 0, "depends_on": ["human-gate"]},
    {"id": "self-review", "type": "check", "description": "Audit the diff against the manifest; emit a handoff report.",
     "irreversible": false, "requires_approval": false, "rollback": null,
     "on_failure": "escalate", "max_retries": 0, "depends_on": ["implement"]}
  ],
  "escalation": {"contact": "engineering-lead", "trigger": "gate rejection, error cascade, or rollback failure"}
}
```

## Design Notes

- The `human-gate` step precedes the only irreversible step, and that step
  sets requires_approval and defines a rollback (rules R1, R2).
- Every action step declares on_failure; retry policies set max_retries >= 1
  (rule R4). A top-level escalation object is defined (rule R3).
- All depends_on references exist, the graph is acyclic (rule R5), and the
  final step is a type=check self-review (rule R6).
"""

FILE_TEMPLATES = (
    ("README.md", ROOT_README),
    ("context/README.md", CONTEXT_README),
    ("context/architecture.md", CONTEXT_ARCHITECTURE),
    ("context/boundaries.md", CONTEXT_BOUNDARIES),
    ("context/glossary.md", CONTEXT_GLOSSARY),
    ("skills/example-skill/SKILL.md", SKILL_MD),
    ("agents/example-agent.md", AGENT_MD),
    ("workflows/example-workflow.md", WORKFLOW_MD),
)

PILLAR_NAMES = ("context", "skills", "agents", "workflows")


def build_files(name):
    """Return an ordered list of (relative_path, rendered_content) pairs."""
    return [(rel, template.replace("__NAME__", name)) for rel, template in FILE_TEMPLATES]


def tree_lines(rel_paths, root_label):
    """Render an ASCII tree (no box-drawing characters) for the given paths."""
    tree = {}
    for rel in rel_paths:
        node = tree
        parts = rel.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    lines = [root_label + "/"]

    def walk(node, prefix):
        entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0]))
        for index, (label, child) in enumerate(entries):
            last = index == len(entries) - 1
            connector = "`-- " if last else "+-- "
            lines.append(prefix + connector + label + ("/" if child is not None else ""))
            if child is not None:
                walk(child, prefix + ("    " if last else "|   "))

    walk(tree, "")
    return lines


class UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors (spec contract)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def build_parser():
    parser = UsageErrorParser(
        prog="ecosystem_scaffolder.py",
        description=(
            "Scaffold a four-pillar agentic config ecosystem "
            "(context/, skills/, agents/, workflows/) seeded with hardened examples."
        ),
        epilog="Example: python ecosystem_scaffolder.py my-agent-stack --output ./workspace",
    )
    parser.add_argument(
        "name",
        help="Ecosystem name in kebab-case (lowercase alphanumerics and hyphens, e.g. my-agent-stack)",
    )
    parser.add_argument("--output", default=".", metavar="DIR", help="Parent directory for the scaffold (default: current directory)")
    parser.add_argument("--pillars", default=None, metavar="LIST",
                        help="Comma-separated subset of pillars to scaffold: "
                             "context,skills,agents,workflows (default: all four; "
                             "the root README.md is always created)")
    parser.add_argument("--dry-run", action="store_true", help="Print the file tree without writing anything")
    parser.add_argument("--force", action="store_true", help="Overwrite the target directory if it already exists")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable JSON result instead of the ASCII tree")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not NAME_PATTERN.match(args.name):
        print("error: invalid name '%s'. Use kebab-case: lowercase letters, digits, "
              "and single hyphens (e.g. my-agent-stack)." % args.name, file=sys.stderr)
        return 1

    if args.pillars is None:
        selected = set(PILLAR_NAMES)
    else:
        selected = {p.strip() for p in args.pillars.split(",") if p.strip()}
        invalid = sorted(selected - set(PILLAR_NAMES))
        if invalid or not selected:
            print("error: invalid --pillars value '%s'. Choose from: %s."
                  % (args.pillars, ", ".join(PILLAR_NAMES)), file=sys.stderr)
            return 1

    root = Path(args.output) / args.name
    if root.exists() and not args.force and not args.dry_run:
        print("error: target '%s' already exists. Use --force to overwrite." % root,
              file=sys.stderr)
        return 1

    files = [(rel, content) for rel, content in build_files(args.name)
             if "/" not in rel or rel.split("/", 1)[0] in selected]
    created = [rel for rel, _ in files]

    if not args.dry_run:
        try:
            for rel, content in files:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print("error: failed to write scaffold: %s" % exc, file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps({"created": created, "root": str(root), "dry_run": bool(args.dry_run)}, indent=2))
        return 0

    header = "Dry run: would create" if args.dry_run else "Created"
    print("%s %d files under %s" % (header, len(created), root))
    print()
    for line in tree_lines(created, args.name):
        print(line)
    print()
    print("Next steps:")
    print("  1. Edit context/architecture.md and context/boundaries.md for your system.")
    print("  2. Adapt agents/example-agent.md, then audit it: python loop_auditor.py <file>")
    print("  3. Validate the workflow: python hitl_gate_validator.py workflows/example-workflow.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

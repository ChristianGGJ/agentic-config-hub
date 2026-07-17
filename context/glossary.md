---
name: "agentic-config-hub-glossary"
version: "1.0.0"
description: "Canonical names and terms for agentic-config-hub; agents must use these exact forms everywhere"
type: "context"
---

# Glossary: agentic-config-hub

> Canonical names — use EXACTLY these forms in all generated code, docs, and
> manifests. Encountering a non-canonical alias in existing content is a
> finding to report, not a license to spread it.

## The Four Pillars

| Term | Canonical form | Never write | Meaning |
|---|---|---|---|
| Context pillar | `context/` | "config folder", "docs" | Read-only ground truth agents load before any work |
| Skills pillar | `skills/` | "skill library", "packages" | 40 atomic, self-contained skill packages, each with a `SKILL.md` |
| Agents pillar | `agents/` | "bots", "roles folder" | `cs-*` role agents (plus `personas/`) that orchestrate skills via `../skills/<name>/` |
| Workflows pillar | `workflows/` | "pipelines folder" | Gated multi-agent orchestrations with embedded HITL json blocks |

## Quality Grades (loop_auditor.py, rubric 100 pts)

| Grade | Canonical form | Score band | Meaning |
|---|---|---|---|
| Hardened | `HARDENED` | >= 90 | Safe for autonomous operation; the repo's minimum for every agent |
| Production-ready | `PRODUCTION-READY` | 75-89 | Solid, but not cleared for unattended autonomy |
| Needs controls | `NEEDS-CONTROLS` | 50-74 | Usable only with added human controls |
| Unsafe | `UNSAFE-FOR-AUTONOMY` | < 50 | Must not run autonomously |

The gate is `loop_auditor.py --min-score N`: it exits 1 when the score is
below N. This repo runs it with `--min-score 90`.

## The 5-Phase Protocol (canonical phase names)

| Phase | Canonical name | Meaning |
|---|---|---|
| 1 | `Phase 1 DISCOVERY (read-only)` | Explore and gather facts; no writes of any kind |
| 2 | `Phase 2 MANIFEST` | Produce the Change Manifest listing every intended change |
| 3 | `Phase 3 HUMAN GATE (hard stop, human approves/edits/rejects)` | Nothing proceeds without explicit human decision |
| 4 | `Phase 4 IMPLEMENTATION (strictly against approved manifest)` | Execute only what the approved manifest names |
| 5 | `Phase 5 SELF-REVIEW & HANDOFF` | Verify own work and emit the Handoff Report |

## Exit-Condition Taxonomy (6 types)

| Canonical form | Meaning |
|---|---|
| `max_iterations` | Hard cap on loop iterations reached |
| `no_progress` | Iterations continue but the state stops improving |
| `oscillation` | The agent alternates between states without converging |
| `budget` | A resource budget (steps, tokens, time, cost) is exhausted |
| `success_predicate` | A machine-checkable success condition evaluates true |
| `escalation_trigger` | A condition requiring a human is met; stop and escalate |

## ReAct Trace Detections (react_trace_analyzer.py, D1-D7)

| ID | Severity | Canonical name | Meaning |
|---|---|---|---|
| `D1` | CRITICAL | action loop | Same (tool, input) pair executed >= 3 times |
| `D2` | HIGH | oscillation | Alternating A-B-A-B action pattern within a window of 4 |
| `D3` | HIGH | error cascade | Consecutive error statuses >= budget.max_errors |
| `D4` | MEDIUM | ReAct contract violation | A step missing a non-empty thought or observation |
| `D5` | CRITICAL | budget overrun | The trace consumed its full step budget |
| `D6` | MEDIUM | no convergence | final_answer null/absent although the last step ended ok |
| `D7` | MEDIUM | reasoning loop | Identical thought text recurs >= 3 times |

## HITL Gate Rules (hitl_gate_validator.py, R1-R6)

| ID | Severity | Meaning |
|---|---|---|
| `R1` | CRITICAL | Every irreversible step needs approval or a gate ancestor |
| `R2` | HIGH | Every irreversible step must define a non-null rollback |
| `R3` | HIGH | The workflow must define a top-level escalation object |
| `R4` | MEDIUM | Every action step defines on_failure; retry defines max_retries |
| `R5` | MEDIUM | All depends_on references exist and the dependency graph is acyclic |
| `R6` | LOW | The final step should be type=check (self-review) |

`PASS` = zero CRITICAL and zero HIGH findings.

## Other Canonical Terms

| Term | Canonical form | Never write | Meaning |
|---|---|---|---|
| Human-in-the-loop | `HITL` | "human in loop", "man-in-the-loop" | A hard human decision point in an agent workflow |
| ReAct | `ReAct` | "REACT", "react pattern" | The Thought/Action/Observation loop structure agent traces follow |
| Change Manifest | `Change Manifest` | "change list", "plan file" | Phase 2 artifact enumerating every intended change; Phase 4 may implement only what it names |
| Handoff Report | `Handoff Report` | "summary", "final report" | Phase 5 artifact: what was done, what was verified, open contradictions, escalations |
| Agent prefix | `cs-` | "CS-", "cs_" | Prefix for role agent files in `agents/` (e.g. `cs-architect.md`) |
| Flagship skill | `agentic-system-architect` | "the architect skill" | The flagship skill; its `scripts/` hold the repo's quality-gate tooling |
| Repository | `agentic-config-hub` | old repo names | This repository: production-ready AI configurations for agents and agentic systems |

## Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0.0 | 2026-07-10 | Initial glossary. | ChristianGGJ |

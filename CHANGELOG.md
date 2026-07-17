# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project planning & requirements elicitation capability set (10 atomic skills): `wbs-decomposition` (work breakdown structure + structural validator), `critical-path-scheduler` (dependency-DAG validation + CPM date computation with working calendars), `plan-critique` (plan self-review + assumption-register lints), `plan-premortem` (prospective-hindsight scenarios + risk register), `plan-baseline-tracking` (schedule variance with DCMA-style checks), `slip-driven-replanning` (slip injection + deadline-impact decisions), `blind-spot-audit` (omitted-concern and hidden-prerequisite detection, e.g. GDPR before a customer database), `sequential-elicitation` (bounded two-way questioning loop governor), `stakeholder-inference` (classified stakeholder register), and `plan-ticket-export` (BYOK, export-only Jira v3 / Asana / Trello payload generation with zero network calls in scripts).
- `cs-project-planner` agent (100 HARDENED) orchestrating the 10 planning skills; delegates RAG ingestion to `rag-architect` + `hybrid-rag-memory`, critique loops to `adversarial-reviewer`, and premortem fan-out to `agenthub`.
- `project-planning-pipeline` workflow (HITL gate validator PASS): elicit -> decompose -> schedule -> critique/premortem -> plan-approval gate -> payload generation -> push-approval gate -> ticket push (sole irreversible step, dual-gated, idempotency-marker rollback) -> bounded monitor/replan loop -> final review.
- Git workflow Core Principle 4 (Human Authorization for Commits and Critical Operations): no agent commits, pushes, or performs any critical/irreversible operation without an explicit, per-action human order; mirrored into the Approval and Irreversibility section of all `cs-*` agents.

### Changed

- Skill catalog grew from 29 to 40 documented packages (also restored the previously undocumented `agent-self-optimization` catalog entry); counts updated in `CLAUDE.md`, `skills/CLAUDE.md`, `README.md`, `context/architecture.md`, and `.claude-plugin/marketplace.json`.

## [0.1.0] - 2026-07-10

### Added

- Initial migration of 19 agentic skills from the claude-skills library into a dedicated repository: adversarial-reviewer, agent-designer, agent-workflow-designer, agenthub, agentic-system-architect, ai-security, autoresearch-agent, browser-automation, focused-fix, llm-cost-optimizer, mcp-server-builder, prompt-governance, rag-architect, self-eval, self-improving-agent, senior-prompt-engineer, skill-security-auditor, skill-tester, spec-driven-workflow.
- Four-pillar repository structure at root: `context/` (project ground truth, read-only for agents), `skills/` (atomic skill packages), `agents/` (cs-* role agents plus personas), and `workflows/` (gated multi-agent orchestrations).
- Flagship skill `agentic-system-architect` with 4 audit tools: `ecosystem_scaffolder.py` (four-pillar scaffold generator), `loop_auditor.py` (100-point loop-safety rubric with HARDENED / PRODUCTION-READY / NEEDS-CONTROLS / UNSAFE-FOR-AUTONOMY grades and `--min-score` gating), `react_trace_analyzer.py` (ReAct trace detections D1-D7), and `hitl_gate_validator.py` (HITL gate rules R1-R6).
- Quality-gate CI (`.github/workflows/quality-gate.yml`): compiles every skill script, smoke-tests the flagship tools, audits every agent at `--min-score 90` (HARDENED), and validates every workflow's embedded HITL gate definition.
- `cs-agentic-system-architect` agent for designing and hardening complete agentic configuration ecosystems.
- Meta-infrastructure: slash commands (`commands/`), templates, standards library (git, quality, security, communication, documentation), evals, install and docs-generation scripts, MkDocs documentation site, and workflow guide (`documentation/WORKFLOW.md`).
- Plugin marketplace registry (`.claude-plugin/marketplace.json`) exposing the plugin-capable skills.

[0.1.0]: https://github.com/ChristianGGJ/agentic-config-hub/releases/tag/v0.1.0

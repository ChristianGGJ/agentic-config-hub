# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

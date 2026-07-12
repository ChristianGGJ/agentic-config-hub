# Agentic Config Hub

**agentic-config-hub** is a library of production-ready AI configurations for agents and agentic systems. It packages 29 self-contained skills, hardened role agents, and gated multi-agent workflows that you copy straight into Claude Code, OpenAI Codex, Gemini CLI, or OpenClaw. Every agent in the hub ships with loop-engineering controls (exit conditions, iteration budgets, self-reflection checkpoints) and every workflow embeds a human approval gate that is machine-validated before merge - autonomy with brakes, verified by deterministic tooling rather than vibes.

## The Four Pillars

Knowledge flows one way through four root directories:

```
context/  ->  skills/  ->  agents/  ->  workflows/
```

- **context/** - project ground truth; read-only for agents
- **skills/** - 29 atomic skill packages; each one stands alone
- **agents/** - cs-* role agents and reviewer personas that compose skills
- **workflows/** - multi-agent orchestrations with hard human-in-the-loop gates

## Skill Catalog

| Skill | What it does |
|-------|--------------|
| [adversarial-reviewer](skills/adversarial-reviewer/) | Hostile-persona code review that breaks the self-review monoculture and catches shared blind spots |
| [agent-designer](skills/agent-designer/) | Design multi-agent systems, agent architectures, and communication patterns |
| [agent-workflow-designer](skills/agent-workflow-designer/) | Design gated multi-step agent workflows and orchestration patterns |
| [agenthub](skills/agenthub/) | Spawn N parallel subagents competing on one task via git worktree isolation; the best branch wins |
| [agentic-evals-benchmarking](skills/agentic-evals-benchmarking/) | Automated regression suites, synthetic-data eval pipelines, and quality scoring with DeepEval/Ragas |
| [agentic-guardrails-security](skills/agentic-guardrails-security/) | Semantic I/O firewalls, prompt-injection mitigations, and PII leakage filters (Llama Guard / Guardrails AI) |
| [agentic-observability-telemetry](skills/agentic-observability-telemetry/) | Tracing, logging, and performance metrics across LangSmith, AgentOps, and OpenTelemetry |
| [agentic-system-architect](skills/agentic-system-architect/) | **Flagship** - design four-pillar ecosystems and harden agents with loop controls, ReAct patterns, and HITL gates |
| [ai-security](skills/ai-security/) | Assess AI/ML systems for prompt injection, jailbreaks, model inversion, data poisoning, and agent tool abuse |
| [autoresearch-agent](skills/autoresearch-agent/) | Autonomous experiment loop that optimizes any file against a measurable metric; commits wins, resets failures |
| [browser-automation](skills/browser-automation/) | Automate browser tasks: scraping, form filling, screenshots, structured data extraction |
| [crewai-role-engineering](skills/crewai-role-engineering/) | Sequential and hierarchical CrewAI teams: backstories, goals, task scopes, and manager coordination |
| [focused-fix](skills/focused-fix/) | Systematic 5-phase deep-dive repair of a specific feature or module, end-to-end |
| [hybrid-rag-memory](skills/hybrid-rag-memory/) | Persistent long-term memory and hybrid retrieval (BM25 + embeddings) for stateful multi-agent systems |
| [langgraph-state-design](skills/langgraph-state-design/) | Stateful LangGraph graphs: state schemas, conditional edges, checkpointers, and HITL gates |
| [llm-cost-optimizer](skills/llm-cost-optimizer/) | Cut LLM API spend with token control, model routing, prompt caching, and cost observability |
| [loop-engineering-mechanisms](skills/loop-engineering-mechanisms/) | Self-correcting retry cycles, output validation schemas, and max-iteration escape routes |
| [mcp-server-builder](skills/mcp-server-builder/) | Build Model Context Protocol servers: tools, resources, prompts, and transports |
| [microsoft-agent-framework](skills/microsoft-agent-framework/) | Map hub skills and agents onto Microsoft Agent Framework 1.0 (AutoGen + Semantic Kernel, C#/.NET) |
| [ms-agent-framework-enterprise](skills/ms-agent-framework-enterprise/) | C# backend integrations and native tool plugins with dependency injection and robust data mapping |
| [multi-llm-routing](skills/multi-llm-routing/) | Route tasks across LLM tiers (reasoning vs. utility models) to optimize cost, latency, and capability |
| [prompt-governance](skills/prompt-governance/) | Manage prompts in production: versioning, registries, A/B tests, and regression eval pipelines |
| [rag-architect](skills/rag-architect/) | Design RAG pipelines: retrieval strategies, embedding models, and vector search |
| [self-eval](skills/self-eval/) | Honest two-axis scoring of AI work quality with score-inflation detection and session persistence |
| [self-improving-agent](skills/self-improving-agent/) | Curate agent auto-memory into durable project knowledge, rules, and reusable skills |
| [senior-prompt-engineer](skills/senior-prompt-engineer/) | Prompt engineering patterns, LLM evaluation frameworks, and structured output design |
| [skill-security-auditor](skills/skill-security-auditor/) | Pre-install security audit of agent skills; scans for dangerous code and exfiltration patterns |
| [skill-tester](skills/skill-tester/) | Test skill packages for structure, triggering accuracy, and tool correctness |
| [spec-driven-workflow](skills/spec-driven-workflow/) | Spec-first development: acceptance criteria before code, tests generated from specifications |

## Flagship: agentic-system-architect

The flagship skill ships four stdlib-only Python tools in `skills/agentic-system-architect/scripts/`:

| Tool | Purpose |
|------|---------|
| `ecosystem_scaffolder.py` | Scaffold a complete four-pillar ecosystem (context, skills, agents, workflows) |
| `loop_auditor.py` | Audit an agent file against a 100-point loop-engineering rubric with a CI-ready `--min-score` gate |
| `react_trace_analyzer.py` | Detect reasoning-loop pathologies (detections D1-D7) in ReAct agent traces |
| `hitl_gate_validator.py` | Validate the human-in-the-loop gate block in a workflow (rules R1-R6) |

**What HARDENED means:** `loop_auditor.py` grades agents on a 100-point rubric - **>= 90 HARDENED**, 75-89 PRODUCTION-READY, 50-74 NEEDS-CONTROLS, < 50 UNSAFE-FOR-AUTONOMY. HARDENED agents declare exit conditions from a 6-type taxonomy (max_iterations, no_progress, oscillation, budget, success_predicate, escalation_trigger), carry iteration and cost budgets, and follow the 5-Phase Protocol with a hard human gate before implementation. Every agent in this repo must score HARDENED to merge.

## Quickstart

```bash
# Clone
git clone https://github.com/ChristianGGJ/agentic-config-hub.git
cd agentic-config-hub

# Scaffold a new four-pillar ecosystem
python skills/agentic-system-architect/scripts/ecosystem_scaffolder.py --help

# Audit an agent (exits 1 below the threshold - CI-ready)
python skills/agentic-system-architect/scripts/loop_auditor.py agents/cs-agentic-system-architect.md --min-score 90

# Validate a workflow's human-in-the-loop gate
python skills/agentic-system-architect/scripts/hitl_gate_validator.py workflows/<workflow>.md
```

All tools are Python 3.8+, standard library only, and support `--help` and `--json`.

## Quality Bar

Nothing merges without passing deterministic gates:

- Every agent `.md` scores **>= 90 (HARDENED)** via `loop_auditor.py --min-score 90`
- Every workflow `.md` embeds a fenced `json` gate block that **PASSES** `hitl_gate_validator.py` (zero CRITICAL/HIGH findings)
- Every Python script: 3.8+ stdlib-only, argparse `--help`, `--json` flag, ASCII-safe output, no LLM or network calls
- Every skill is self-contained - zero cross-skill dependencies

## Multi-Platform Install

```bash
# Claude Code
./scripts/install.sh

# OpenAI Codex
./scripts/codex-install.sh      # codex-install.bat on Windows

# Gemini CLI
./scripts/gemini-install.sh

# OpenClaw
./scripts/openclaw-install.sh
```

## Repository Structure

```
agentic-config-hub/
|-- context/          # Project ground truth (read-only for agents)
|-- skills/           # 29 atomic skill packages
|-- agents/           # cs-* role agents + personas/
|-- workflows/        # Gated multi-agent orchestrations
|-- commands/         # Slash commands
|-- templates/        # Agent and skill templates
|-- standards/        # Git, quality, security, communication, documentation
|-- evals/            # Evaluation results
|-- scripts/          # Multi-platform install + docs generation
|-- docs/             # MkDocs documentation site
|-- documentation/    # WORKFLOW.md
```

## Contributing

Branch strategy is **feature -> dev -> main** with conventional commits:

```bash
git checkout dev && git pull origin dev
git checkout -b feature/skills-my-change
# ... work, then run the quality gates locally ...
python skills/agentic-system-architect/scripts/loop_auditor.py agents/<agent>.md --min-score 90
python skills/agentic-system-architect/scripts/hitl_gate_validator.py workflows/<workflow>.md
git push origin feature/skills-my-change
gh pr create --base dev --head feature/skills-my-change
```

Main requires PR approval; direct pushes are blocked. See [documentation/WORKFLOW.md](documentation/WORKFLOW.md) for the full guide.

## License

MIT

---

**Version v0.1.0** | 2026-07-10 | [github.com/ChristianGGJ/agentic-config-hub](https://github.com/ChristianGGJ/agentic-config-hub)

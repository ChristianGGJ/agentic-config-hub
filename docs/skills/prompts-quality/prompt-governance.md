---
title: "Prompt Governance — Prompts Optimization & Quality Rubrics"
description: "Use when managing prompts in production at scale: versioning prompts, running A/B tests on prompts, building prompt registries, preventing prompt. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Prompt Governance

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-check: Prompts & Quality</span>
<span class="meta-badge">:material-identifier: `prompt-governance`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/prompt-governance/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install prompts-quality</code>
</div>


> Originally contributed by [chad848](https://github.com/chad848) — enhanced and integrated by the agentic-config-hub team.

You are an expert in production prompt engineering and AI feature governance. Your goal is to treat prompts as first-class infrastructure -- versioned, tested, evaluated, and deployed with the same rigor as application code. You prevent quality regressions, enable safe iteration, and give teams confidence that prompt changes will not break production.

Prompts are code. They change behavior in production. Ship them like code.

## Before Starting

**Check for context first:** If project-context.md exists, read it before asking questions. Pull the AI tech stack, deployment patterns, and any existing prompt management approach.

Gather this context (ask in one shot):

### 1. Current State
- How are prompts currently stored? (hardcoded in code, config files, database, prompt management tool?)
- How many distinct prompts are in production?
- Has a prompt change ever caused a quality regression you did not catch before users reported it?

### 2. Goals
- What is the primary pain? (versioning chaos, no evals, blind A/B testing, slow iteration?)
- Team size and prompt ownership model? (one engineer owns all prompts vs. many contributors?)
- Tooling constraints? (open-source only, existing CI/CD, cloud provider?)

### 3. AI Stack
- LLM provider(s) in use?
- Frameworks in use? (LangChain, LlamaIndex, custom, direct API?)
- Existing test/CI infrastructure?

## How This Skill Works

### Mode 1: Build Prompt Registry
No centralized prompt management today. Design and implement a prompt registry with versioning, environment promotion, and audit trail.

### Mode 2: Build Eval Pipeline
Prompts are stored somewhere but there is no systematic quality testing. Build an evaluation pipeline that catches regressions before production.

### Mode 3: Governed Iteration
Registry and evals exist. Design the full governance workflow: branch, test, eval, review, promote -- with rollback capability.

---

## Mode 1: Build Prompt Registry

**What a prompt registry provides:**
- Single source of truth for all prompts
- Version history with rollback
- Environment promotion (dev to staging to prod)
- Audit trail (who changed what, when, why)
- Variable/template management

### Minimum Viable Registry (File-Based)

For small teams: structured files in version control.

Directory layout:
```
prompts/
  registry.yaml          # Index of all prompts
  summarizer/
    v1.0.0.md            # Prompt content
    v1.1.0.md
  classifier/
    v1.0.0.md
  qa-bot/
    v2.1.0.md
```

Registry YAML schema:
```yaml
prompts:
  - id: summarizer
    description: "Summarize support tickets for agent triage"
    owner: platform-team
    model: claude-sonnet-4-5
    versions:
      - version: 1.1.0
        file: summarizer/v1.1.0.md
        status: production
        promoted_at: 2026-03-15
        promoted_by: eng@company.com
      - version: 1.0.0
        file: summarizer/v1.0.0.md
        status: archived
```

### Production Registry (Database-Backed)

For larger teams: an API-accessible prompt registry with two core tables -- `prompts` (one row per logical prompt) and `prompt_versions` (immutable, append-only version history). Prompt content is never edited in place; a change is always a new `prompt_versions` row, which is what makes rollback a metadata update rather than a redeploy.

Reference DDL (portable ANSI SQL; adapt types to your engine -- e.g. `SERIAL`/`IDENTITY`, `JSONB` on Postgres, `TIMESTAMPTZ`):

```sql
CREATE TABLE prompts (
    id           BIGINT PRIMARY KEY,
    slug         VARCHAR(128) NOT NULL UNIQUE,   -- stable identifier, e.g. 'summarizer'
    description  TEXT,
    owner        VARCHAR(128) NOT NULL,          -- team or person accountable
    model        VARCHAR(128) NOT NULL,          -- current target model family + tier
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);

CREATE TABLE prompt_versions (
    id             BIGINT PRIMARY KEY,
    prompt_id      BIGINT NOT NULL REFERENCES prompts(id),
    version        VARCHAR(32) NOT NULL,         -- semver, e.g. '1.2.0'
    content        TEXT NOT NULL,                -- the prompt template body
    variables      TEXT,                         -- JSON list of template variables
    model          VARCHAR(128) NOT NULL,        -- model this version was evaluated against
    environment    VARCHAR(16) NOT NULL          -- 'dev' | 'staging' | 'production' | 'archived'
                     CHECK (environment IN ('dev','staging','production','archived')),
    eval_score     NUMERIC(6,4),                 -- weighted pass rate from the eval runner
    eval_dataset   VARCHAR(256),                 -- golden dataset ref/commit the score came from
    promoted_at    TIMESTAMP,
    promoted_by    VARCHAR(128),
    change_reason  TEXT,                          -- links to the change-review PR
    created_at     TIMESTAMP NOT NULL,
    UNIQUE (prompt_id, version)
);

-- Exactly one production version per prompt (partial unique index; Postgres/SQLite syntax):
CREATE UNIQUE INDEX one_prod_per_prompt
    ON prompt_versions (prompt_id)
    WHERE environment = 'production';
CREATE INDEX idx_prompt_versions_env ON prompt_versions (prompt_id, environment);
```

The partial unique index enforces the single-production-version invariant at the database level, so promotion is a transaction that archives the current production row and flips the new one to `production`.

To initialize a file-based registry instead, create the directory structure above and populate the registry YAML with your existing prompts, their current versions, and ownership metadata.

---

## Mode 2: Build Eval Pipeline

**The problem:** Prompt changes are deployed by feel. There is no systematic way to know if a new prompt is better or worse than the current one.

**The solution:** Automated evals that run on every prompt change, similar to unit tests.

### Eval Types

| Type | What it measures | When to use |
|---|---|---|
| **Exact match** | Output equals expected string | Classification, extraction, structured output |
| **Contains check** | Output includes required elements | Key point extraction, summaries |
| **LLM-as-judge** | Another LLM scores quality 1-5 | Open-ended generation, tone, helpfulness |
| **Semantic similarity** | Embedding similarity to golden answer | Paraphrase-tolerant comparisons |
| **Schema validation** | Output conforms to JSON schema | Structured output tasks |
| **Human eval** | Human rates 1-5 on criteria | High-stakes, launch gates |

The four deterministic types (exact match, contains, regex, schema validation) are implemented in `scripts/eval_runner.py` and run fully offline. The non-deterministic types (LLM-as-judge, semantic similarity, human eval) require a model or embedding call and belong to the produce step, not the deterministic gate.

> **Complementary owner:** for agent-trajectory scoring, faithfulness/relevance metrics, LLM-judge calibration, and synthetic golden-data generation, see the sibling skill **agentic-evals-benchmarking** -- it owns the deeper eval methodology. This skill keeps only the deterministic checks needed to gate a prompt change; use both together (its `eval_gate.py` consumes per-case scores; this skill's `eval_runner.py` produces pass/fail from raw outputs).

### Golden Dataset Design

Every prompt needs a golden dataset: a fixed set of input/expected-output pairs that define correct behavior.

Golden dataset requirements:
- Minimum 20 examples for basic coverage, 100+ for production confidence
- Cover edge cases and failure modes, not just happy path
- Reviewed and approved by domain expert, not just the engineer who wrote the prompt
- Versioned alongside the prompt (a prompt change may require golden set updates)

### Eval Pipeline Implementation

The pipeline has two stages. **Produce:** your application harness runs the prompt version under test against each golden input and records the model output (this is the only stage that calls the LLM). **Score:** a deterministic runner compares each recorded output against its expected value and reports an aggregate pass rate plus per-case failures. Splitting the stages keeps scoring fast, reproducible, and safe to run in air-gapped CI -- the same outputs always yield the same verdict.

**Bundled runner:** `scripts/eval_runner.py` implements the score stage for the deterministic check types. It reads a golden JSONL dataset, applies per-case checks (`exact_match`, `contains`, `regex`, `json_schema`), and exits non-zero when the weighted pass rate falls below a threshold -- drop it straight into a CI job. It makes no LLM or network calls; feed it outputs your harness already produced (embedded in the golden file or via `--predictions`).

```bash
# Produce step (your harness, pseudocode): write model outputs keyed by case id -> preds.jsonl
# Score step (deterministic gate):
python scripts/eval_runner.py --golden golden.jsonl --predictions preds.jsonl \
    --threshold 0.95 --json
# exit 0 = gate passed, 1 = pass rate below threshold, 2 = malformed dataset/usage error
```

Golden JSONL line shape (one case per line):

```json
{"id": "c1", "type": "exact_match", "expected": "30 days", "output": "30 days", "weight": 1.0}
```

Pass thresholds (calibrate to your use case):
- Classification/extraction: 95% or higher exact match
- Summarization: 0.85 or higher LLM-as-judge score
- Structured output: 100% schema validation
- Open-ended generation: 80% or higher human eval approval

For the non-deterministic checks (LLM-as-judge, semantic similarity), score in the produce step and feed numeric scores to a gate like agentic-evals-benchmarking's `eval_gate.py`; keep `eval_runner.py` for the deterministic pass/fail portion.

---

## Mode 3: Governed Iteration

The full prompt deployment lifecycle with gates at each stage:

1. **BRANCH** -- Create feature branch for prompt change
2. **DEVELOP** -- Edit prompt in dev environment, manual testing
3. **EVAL** -- Run eval pipeline vs. golden dataset (automated in CI)
4. **COMPARE** -- Compare new prompt eval score vs. current production score
5. **REVIEW** -- PR review: eval results plus diff of prompt changes
6. **PROMOTE** -- Staging to Production with approval gate
7. **MONITOR** -- Watch production metrics for 24-48h post-deploy
8. **ROLLBACK** -- One-command rollback to previous version if needed

### A/B Testing Prompts

When you want to measure real-user impact, not just eval scores:

- Use stable assignment (same user always gets same variant, based on user_id hash)
- Log every assignment with user_id, prompt_slug, and variant for analysis
- Define success metric before starting (not after)
- Run for minimum 1 week or 1,000 requests per variant
- Check for novelty effect (first-day engagement spike)
- Statistical significance: p<0.05 before declaring a winner
- Monitor latency and cost alongside quality

> **Complementary owner:** for the statistical machinery -- minimum detectable effect (MDE), required sample size per variant, significance testing, and multi-variant ranking -- see the sibling skill **senior-prompt-engineer** (`references/llm_evaluation_frameworks.md`, section "A/B Testing for Prompts"). This skill owns the *governance* wrapper (variant assignment, logging, pre-registered metric, promotion gate); that reference owns the *statistics*.

### Production Monitoring + Rollback

A prompt that passed evals can still degrade in production: real inputs drift from the golden set, a silent model update shifts behavior, or an edge case you never captured surfaces at scale. Monitoring exists to detect that fast; rollback exists to stop the bleeding while you diagnose.

**Detection signals (instrument all three tiers):**

| Tier | Signal | What it catches |
|---|---|---|
| Quality | Scheduled eval score on the production version (re-run the golden set daily) | Model-update drift, gradual regressions |
| Quality | Thumbs-down / negative-feedback rate per prompt slug | Real-user dissatisfaction the golden set missed |
| Quality | Output-contract violation rate (schema-invalid / unparseable responses) | Structured-output breakage |
| Behavior | Refusal rate, empty-output rate, truncation/length anomalies | Prompt or model regressions, format drift |
| Operational | p50 / p95 latency and cost per call | Slow or expensive regressions, verbose drift |

**Alert thresholds (starting points -- calibrate to a 7-day baseline, alert on relative change not just absolute):**

| Signal | Warn | Page |
|---|---|---|
| Scheduled eval pass rate | drops below promotion threshold | drops more than 5 points below baseline |
| Thumbs-down rate | +50% vs. 7-day baseline | 2x baseline sustained 1h |
| Schema-invalid rate | above 1% | above 5% |
| p95 latency | +30% vs. baseline | 2x baseline |
| Cost per call | +25% vs. baseline | 2x baseline |

Tie these to the metric names your monitoring backend already emits; see the sibling skill **agentic-observability-telemetry** for wiring prompt-quality signals into traces and dashboards.

**Rollback decision checklist** -- roll back first, diagnose after. Do not debug a live regression in production:

1. **Confirm the prompt is the cause.** Did a promotion, a model-version change, or a golden-set change land in the last 24-48h? If nothing changed on your side, suspect an upstream model update (see Model-Version Drift below) -- rollback may not help, but pinning the prior model might.
2. **Check severity against thresholds.** Any "page"-level signal, or a user-visible contract break -> roll back now. Warn-level only -> monitor and prepare.
3. **Execute rollback.** Promote the previous `production`-status version back (a registry metadata flip, not a redeploy): archive the current production row, set the prior version to `production`. With the DDL above this is one transaction.
4. **Verify the restore.** Re-run `eval_runner.py` against the restored version to confirm it still meets the threshold, and watch the live signals return to baseline.
5. **Freeze and record.** Block further promotions of that slug, open an incident note, and add the failing production case(s) to the golden dataset so the next attempt is gated on them.

This is a bounded control loop, not open-ended firefighting: the promotion/monitor/rollback cycle terminates on an explicit predicate (signals back to baseline) or escalates to a human -- the same exit-condition discipline the hub applies to agent loops. See `skills/agentic-system-architect/references/loop_engineering_patterns.md` for the six exit-condition types (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger`).

### Model-Version Drift Procedure

Prompts are tested against a specific model, but providers update models and retire versions. A prompt that scored 96% can silently regress when the underlying model changes -- your code did not change, so nothing flags it.

1. **Pin what you tested.** Record the exact model id (family + tier + version/date where the provider exposes one) in the `prompt_versions.model` column. Treat "current alias" and "pinned version" as different deployment choices, and write down which you use.
2. **Detect drift continuously.** The scheduled production eval (above) is the primary drift alarm: a pass-rate drop with no prompt change points at the model. Also subscribe to your provider's model-deprecation and changelog notices.
3. **Re-eval on any model change.** Before adopting a new model version, run the full golden set on the candidate model and diff the pass rate against the incumbent -- treat it exactly like a prompt change (use the change-review template).
4. **Migrate deliberately.** If a version is being retired, bump the prompt version, re-eval, and promote through the normal gate. If the new model regresses, keep the pinned older version until you can adapt the prompt.
5. **Never hardcode a deprecated model id.** Reference current model families and relative tiers; when a table lists dated pricing or capabilities, mark it "verify against current provider docs" -- these values move.

---

## Tooling Landscape: Build vs. Buy

Before building a registry or eval pipeline from scratch, decide whether a platform earns its keep. The honest default for small teams is **file-based registry + `eval_runner.py` in CI** -- it is free, versioned in Git, has zero vendor lock-in, and covers Modes 1-2 completely. Reach for a platform when prompt count, contributor count, or the need for hosted dashboards, tracing, and non-engineer editing outgrows files.

> **Verify-current caveat:** the tools below are active as of 2025-2026, but feature sets, free-tier limits, open-source/self-host status, and pricing change frequently. Confirm against each vendor's current docs before committing. No dated pricing is given here precisely because it moves.

| Option | Model | Best for | Strengths | Watch-outs |
|---|---|---|---|---|
| **File-based registry + `eval_runner.py`** | Build (this skill) | Small teams, engineer-owned prompts, air-gapped CI | Free, Git-versioned, no lock-in, fully offline, PR review built in | No hosted UI; non-engineers cannot edit; you own dashboards/alerting |
| **promptfoo** | Buy (open-source, self-host) | Eval-first teams wanting local, CI-native prompt testing | OSS, config-as-code, many assertion types, matrix eval across models, CI-friendly | Eval-centric (not a full hosted registry); you still host it |
| **Langfuse** | Buy (open-source + managed) | Teams wanting self-hostable tracing + prompt management + evals | OSS core with self-host option, prompt versioning, tracing, dataset evals | Managed tier is a paid service; self-host is ops you own |
| **LangSmith** | Buy (managed, LangChain) | LangChain/LangGraph shops wanting hosted tracing + datasets + prompt hub | Deep LangChain integration, hosted eval datasets, prompt playground | Vendor-hosted; strongest when already on LangChain; paid |
| **Braintrust** | Buy (managed) | Teams centering eval + experiment tracking with human review | Eval-focused workflows, dataset/experiment tracking, scoring UI, review | Vendor-hosted paid platform; adopt for eval depth, not just storage |
| **PromptLayer** | Buy (managed) | Non-engineer prompt editing + request logging | Visual prompt registry, versioning, request history, non-technical editors | Vendor-hosted paid platform; confirm data-retention/PII posture |

**Decision heuristics:**
- Fewer than ~20 prompts, one or two engineers, prompts live in the repo -> **stay file-based.** A platform adds ops and cost you do not need yet.
- Non-engineers must edit prompts, or you need audit UI and role-based access -> a hosted registry (PromptLayer, Langfuse, LangSmith) earns its cost.
- Eval depth is the pain (many models, rich assertions, experiment tracking) -> promptfoo (local/CI) or Braintrust/Langfuse (hosted); pair with **agentic-evals-benchmarking** for methodology.
- Hard requirement for on-prem / air-gapped / no third-party data egress -> file-based or self-hosted OSS (promptfoo, Langfuse) only.
- Already all-in on LangChain -> LangSmith reduces integration work; otherwise it is not a reason on its own.
- Per the hub's ClawHub constraints, do not build a workflow that *requires* a paid third-party service; keep the file-based path viable as the portable default and treat platforms as optional accelerators.

Whatever you choose, the invariants are the same: versioned prompts, a golden dataset, an eval gate before promotion, and a one-step rollback. Tools change; the governance contract does not.

## Proactive Triggers

Surface these without being asked:

- **Prompts hardcoded in application code** -- Prompt changes require code deploys. This slows iteration and mixes concerns. Flag immediately.
- **No golden dataset for production prompts** -- You are flying blind. Any prompt change could silently regress quality.
- **Eval pass rate declining over time** -- Model updates can silently break prompts. Scheduled evals catch this before users do.
- **No prompt rollback capability** -- If a bad prompt reaches production, the team is stuck until a new deploy. Always have rollback.
- **One person owns all prompt knowledge** -- Bus factor risk. Prompt registry and docs equal knowledge that survives team changes.
- **Prompt changes deployed without eval** -- Every uneval'd deploy is a bet. Flag when the team skips evals "just this once."

---

## Output Artifacts

| When you ask for... | You get... |
|---|---|
| Registry design | File structure, schema, promotion workflow, and implementation guidance |
| Eval pipeline | Golden dataset template, eval runner approach, pass threshold recommendations |
| A/B test setup | Variant assignment logic, measurement plan, success metrics, and analysis template |
| Prompt diff review | Side-by-side comparison with eval score delta and deployment recommendation (fill in `assets/prompt-change-review-template.md`) |
| Governance policy | Team-facing policy doc: ownership model, review requirements, deployment gates |

---

## Communication

All output follows the structured standard:
- **Bottom line first** -- risk or recommendation before explanation
- **What + Why + How** -- every finding has all three
- **Actions have owners and deadlines** -- no "the team should consider..."
- **Confidence tagging** -- verified / medium / assumed

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|---|---|---|
| Hardcoding prompts in application source code | Prompt changes require code deploys, slowing iteration and coupling concerns | Store prompts in a versioned registry separate from application code |
| Deploying prompt changes without running evals | Silent quality regressions reach users undetected | Gate every prompt change on automated eval pipeline pass before promotion |
| Using a single golden dataset forever | As the product evolves, the golden set drifts from real usage patterns | Review and update the golden dataset quarterly, adding new edge cases from production failures |
| One person owns all prompt knowledge | Bus factor of 1 — when that person leaves, prompt context is lost | Document prompts in a registry with ownership, rationale, and version history |
| A/B testing without a pre-defined success metric | Post-hoc metric selection introduces bias and inconclusive results | Define the primary success metric and sample size requirement before starting the test |
| Skipping rollback capability | A bad prompt in production with no rollback forces an emergency code deploy | Every prompt version promotion must have a one-command rollback to the previous version |

## Related Skills

- **senior-prompt-engineer**: Use when writing or improving individual prompts. NOT for managing prompts in production at scale (that is this skill). Owns the A/B statistics (`references/llm_evaluation_frameworks.md`) this skill's governance loop wraps.
- **agentic-evals-benchmarking**: Complementary owner of eval methodology -- trajectory/tool-call scoring, faithfulness/relevance metrics, LLM-judge calibration, synthetic golden-data generation, and the `eval_gate.py` CI gate. Use it for eval depth and for automating eval runs in CI; this skill keeps only the deterministic pass/fail checks needed to gate a prompt change.
- **agentic-observability-telemetry**: Use when instrumenting monitoring. Pairs with this skill for wiring production prompt-quality signals (eval scores, thumbs-down rate, latency, contract-violation rate) into traces and dashboards.
- **agentic-system-architect**: Cite for loop theory -- the six exit-condition types and 5-phase protocol that bound this skill's promotion/monitor/rollback control loop (`references/loop_engineering_patterns.md`). Do not duplicate its prose; reference it.
- **llm-cost-optimizer**: Use when reducing LLM API spend. Pairs with this skill -- evals catch quality regressions when you route to cheaper models.
- **rag-architect**: Use when designing retrieval pipelines. Pairs with this skill for governing RAG system prompts and retrieval prompts separately.

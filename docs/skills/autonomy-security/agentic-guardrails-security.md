---
title: "Agentic Guardrails & Security — Autonomous Guardrails & Threat Modeling"
description: "Use when adding input/output/tool-call guardrails to an LLM application: Llama Guard moderation, Guardrails AI validators, Presidio PII redaction. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Agentic Guardrails & Security

<div class="page-meta" markdown>
<span class="meta-badge">:material-shield-lock: Autonomy & Security</span>
<span class="meta-badge">:material-identifier: `agentic-guardrails-security`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-guardrails-security/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install autonomy-security</code>
</div>


Design and implement the defensive semantic layer around an LLM application: a **layered firewall** with checkpoints at input, tool-call, and output boundaries; content moderation via Llama Guard; validator pipelines via Guardrails AI; PII detection and redaction via Presidio; prompt-injection defenses; and — the part most guardrail guides skip — **measuring whether any of it actually works** (false-positive/false-negative rates against a labeled corpus, threshold tuning).

All third-party integrations here (Llama Guard, Guardrails AI, Presidio) are **optional**. Every pattern degrades gracefully to a stdlib-only fallback, and no pattern requires a paid service: gatekeeper models are BYOK or local.

---

## Core Capabilities

1. **Layered firewall architecture** — three checkpoints (input, tool-call, output) mapped to the hub's gate taxonomy, each with tiered detectors ordered cheap-to-expensive.
2. **Content moderation integration** — Llama Guard (MLCommons hazard taxonomy, local or hosted) and Guardrails AI (`Guard` + hub validators + `on_fail` actions) with real, current API surfaces.
3. **PII detection and redaction** — Presidio `AnalyzerEngine`/`AnonymizerEngine` with custom recognizers; stdlib fallback with Luhn-validated credit-card matching.
4. **Prompt-injection defense** — taxonomy of spotlighting, delimiting/sandwiching, dual-LLM quarantine, and input-provenance separation, with detection-vs-prevention trade-offs.
5. **Effectiveness evaluation** — labeled-corpus construction, confusion-matrix metrics, threshold tuning, and a deterministic CI gate (`scripts/guardrail_eval.py`).
6. **Safe failure engineering** — fail-closed defaults, bounded retry loops with declared exit conditions, streaming-output moderation.

---

## Decision Frameworks

### Guard mechanism selection

Order detectors cheap-to-expensive and short-circuit on the first confident verdict. Calibrated defaults in the last column.

| Mechanism | Latency | Cost | Catches | Misses | Offline | Default role |
|---|---|---|---|---|---|---|
| Regex / signature match (stdlib) | <1 ms | free | known attack strings, obvious PII formats | paraphrases, novel attacks, obfuscation | yes | always-on first tier |
| Heuristics (length caps, encoding detection, char-class ratios) | <1 ms | free | context stuffing, base64/hex smuggling | semantic attacks | yes | always-on first tier |
| Presidio (NER + pattern + checksum) | 10-50 ms | free (local) | PII with context awareness, Luhn-valid cards | novel PII formats without a recognizer | yes | output firewall PII tier |
| Llama Guard 3-1B (local) | 50-200 ms | free (local GPU/CPU) | policy-violating content, many jailbreaks | subtle indirect injection | yes | input/output moderation tier |
| Llama Guard 3-8B / 4 (local or hosted) | 100-500 ms | free local / BYOK hosted | higher-accuracy moderation, multimodal (LG4) | task-specific policy nuances | local: yes | moderation tier when 1B recall is insufficient |
| Guardrails AI validators | 1-500 ms (validator-dependent) | free (most hub validators run local) | structured checks: toxicity, PII, regex, schema | anything without a validator | mostly | output validation pipeline |
| LLM-judge (utility-tier model, BYOK) | 0.3-2 s | per-token | novel/semantic attacks, policy nuance | nondeterministic; can itself be injected | no | escalation tier only, never the sole guard |

**Default stack:** regex+heuristics on everything; Llama Guard on user input and final output; Presidio on final output; LLM-judge only for flagged-but-uncertain traffic (see two-threshold design in `references/guardrail_effectiveness_evaluation.md`).

### Fail-open vs fail-closed

When a guard errors or times out, something still has to happen. Decide per checkpoint, in writing, before deployment.

| Checkpoint | On guard failure | Rationale |
|---|---|---|
| Input firewall | **fail-closed** (reject with generic error) | an unscreened prompt reaches the full-capability model |
| Tool-call firewall | **fail-closed** (block call, escalate) | tool calls have side effects; hub rule R1 territory |
| Output firewall, internal/low-risk consumer | fail-open + log + alert | availability may beat leak risk for internal drafts |
| Output firewall, external consumer or regulated data | **fail-closed** | a leaked SSN cannot be unleaked |

Default is fail-closed. Fail-open must be an explicit, documented exception with an owner.

### Detection vs prevention

| Approach | Examples | Strength | Weakness |
|---|---|---|---|
| Prevention (structural) | dual-LLM quarantine, provenance separation, tool allowlists, least-privilege credentials | works against novel attacks; no FP/FN curve | constrains capability; design-time cost |
| Detection (classification) | Llama Guard, signatures, LLM-judge | flexible, retrofittable, tunable | probabilistic — always has an FN rate; must be measured |

Rule: **prevention for tool access and privileges, detection for content**. Never rely on detection alone to protect an irreversible action — that is what the hub's Pre-Execution Approval Gate is for.

### PII action selection

| Action | Use when | Example |
|---|---|---|
| Redact (replace with type tag) | value must not survive in any form | `<CREDIT_CARD>` |
| Mask (partial) | human needs to recognize the referent | `****-****-****-4242` |
| Hash | need join/dedup keys without raw values | `sha256(email)` |
| Block entire response | PII density suggests systematic exfiltration | >3 distinct PII entities in one response |

---

## The Three Checkpoints (summary)

```text
 user input          agent loop                    response
 ----------> [INPUT] ----------> [TOOL-CALL] ----> [OUTPUT] ---->
  firewall            per call     firewall         firewall
                      + tool RESULTS re-enter as untrusted input
```

- **Input firewall** — jailbreak/injection screening on user text. Tiered: heuristics, then moderation model, then (optionally) LLM-judge.
- **Tool-call firewall** — validates tool name against an allowlist and arguments against schema/path/URL constraints *before* execution; treats every tool **result** as untrusted input (indirect injection is the higher-risk vector).
- **Output firewall** — PII scan, system-prompt-leak check, schema enforcement with a bounded retry loop, streaming hold-back.

Full implementations: `references/security_guardrail_patterns.md`.

---

## Framework Integrations (summary)

Version assumptions and complete runnable examples live in `references/moderation_frameworks.md`.

- **Llama Guard** (assumed generation: Llama-Guard-3 family, Llama-Guard-4-12B): MLCommons-aligned hazard taxonomy S1-S14; classifies the *last* user or assistant turn; output is literally `safe` or `unsafe` + a comma-separated category line. Run local (transformers, vLLM, Ollama `llama-guard3`) or hosted (any provider that serves the model, BYOK).
- **Guardrails AI** (assumed `guardrails-ai` 0.5+): `Guard().use(...)` with validators installed from the Guardrails Hub; `on_fail` actions `exception` / `fix` / `filter` / `refrain` / `reask` / `noop`; `guard.validate(text)` returns a `ValidationOutcome`.
- **Presidio** (assumed `presidio-analyzer`/`presidio-anonymizer` 2.x): `AnalyzerEngine.analyze()` -> `RecognizerResult` list -> `AnonymizerEngine.anonymize()` with per-entity `OperatorConfig`; custom entities via `PatternRecognizer`. Built-in `CREDIT_CARD` recognizer performs Luhn checksum validation — prefer it over any bare regex.

**Graceful degradation:** if a framework is not installed, fall back one tier (Presidio -> stdlib Luhn redactor; Llama Guard -> signature+heuristic tier) and *log the degradation*. Never silently skip a checkpoint.

---

## Effectiveness Evaluation (do not skip)

A guardrail you have not measured is a guardrail you are guessing about. Minimum bar before production:

1. Build a labeled corpus: >= 200 benign samples from real traffic patterns, >= 200 malicious samples across attack families (direct injection, indirect/RAG, obfuscated, multilingual). Version it.
2. Run every guard config against the corpus; record per-sample verdicts (or scores) to JSONL.
3. Compute precision, recall, FPR, FNR with `scripts/guardrail_eval.py`; tune thresholds with `--sweep`.
4. Gate CI on regression: `python scripts/guardrail_eval.py --results results.jsonl --min-recall 0.90 --max-fpr 0.05` (exit 1 on breach).
5. Re-run on every guard change, model swap, or signature addition.

Base-rate warning: at 1% attack prevalence, a guard with 5% FPR produces ~5 false blocks for every true block. FPR, not recall, is usually what gets guardrails turned off in production. Full methodology: `references/guardrail_effectiveness_evaluation.md`.

---

## Failure Modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| Legitimate users blocked; support tickets citing "security violation" | FPR never measured; threshold set by vibes | Build the labeled corpus, run `guardrail_eval.py --sweep`, pick the operating point from data |
| Attacks get through despite "guardrails enabled" | Detection-only stack; no structural prevention on tools | Add tool allowlists + provenance separation; detection cannot be the only layer |
| Guard timeout causes unfiltered response to ship | Fail-open default nobody chose consciously | Implement fail-closed wrapper (timeout -> generic refusal + alert); see patterns reference |
| PII redactor mangles ordinary numbers (order IDs, phone numbers redacted as cards) | Bare 13-16-digit regex without checksum | Use Presidio's CREDIT_CARD recognizer or the stdlib Luhn fallback |
| Injection arrives via retrieved document or tool result, not user input | Only the input checkpoint exists | Add tool-result screening + spotlighting/datamarking of retrieved content |
| Schema retries loop forever or burn budget | Retry loop with no declared exit conditions | Bounded loop: max_iterations 2, no_progress on repeated identical error, fail-closed on exhaustion |
| Moderation verdicts differ run to run | LLM-judge as primary guard (stochastic) | Move deterministic tiers first; judge only for escalation; pin temperature ~0 and note residual variance |
| Streaming response leaks PII before the output check runs | Output firewall assumes complete responses | Sentence-boundary hold-back buffer + final full-text scan (patterns reference, streaming section) |
| Guard blocks the guard: moderation model refuses to echo attack text for logging | Logging pipeline passes raw attack text through another moderated model | Log verdict + hash + truncated excerpt, not a re-processed transcript |

---

## Hub Canon Integration

**Checkpoints map to the hub gate taxonomy** (see `agentic-system-architect` for canon):

| This skill | Hub gate concept |
|---|---|
| Tool-call firewall blocking an irreversible call pending approval | Pre-Execution Approval Gate (rule R1: irreversible steps must be gated) |
| Output firewall before external send/publish | Gate on Class 3 IRREVERSIBLE actions — a response leaving the boundary is external publication |
| Guard failure -> fail-closed + human notification | Escalation Gate bound to `escalation_trigger` |
| Kill switch on the guard pipeline | Override/Abort Gate (always available) |

**The schema-enforcement retry loop declares exit conditions from the canonical 6-type taxonomy** before iteration 1: `max_iterations` (2), `no_progress` (identical validation error twice), `budget` (token/call ceiling shared with the parent loop), `success_predicate` (output parses and validates against the schema), `escalation_trigger` (guard-service outage or exhaustion -> fail-closed error to a human-owned queue). `oscillation` is monitored by the parent agent loop (A-B-A-B fix/unfix edits across window 4).

**5-Phase Protocol placement:** guardrail *design* happens in Phase 2 (MANIFEST — declare checkpoints, fail modes, thresholds, and rollback for guard config changes); the HUMAN GATE approves the guard policy including every fail-open exception; guard *verdict logs* feed Phase 5 SELF-REVIEW evidence. Agent specs that include guarded loops must still score >= 90 (HARDENED) on the flagship's `loop_auditor.py` — a guardrail retry loop with only `max_iterations` is the canonical under-hardened anti-pattern.

**Trace detections:** guard-verdict logs make firewall behavior auditable the same way ReAct traces make reasoning auditable — repeated identical blocked calls are the D1 (action loop) signature surfacing at the firewall; treat >= 3 identical blocks as an agent-side loop, not just an attack.

---

## When NOT to Use

- **Threat modeling, ATLAS technique mapping, injection-signature scanning of live inputs** -> see the `ai-security` skill (assessment and scoring; this skill is the enforcement layer it recommends).
- **Auditing a skill/plugin package for malicious code before installing it** -> see `skill-security-auditor`.
- **Loop exit-condition engineering in general** (beyond the guard retry loop here) -> see `agentic-system-architect` (canon) and `loop-engineering-mechanisms` (Python implementations).
- **Observability/telemetry for guard verdicts** (dashboards, alert routing) -> see `agentic-observability-telemetry`.
- **RAG retrieval design itself** -> see `rag-architect`; this skill only covers screening what retrieval returns.

---

## Tools

| Script | Purpose |
|---|---|
| `scripts/guardrail_eval.py` | Deterministic effectiveness evaluator: reads labeled results JSONL (label + prediction or score), reports TP/FP/FN/TN, precision, recall, FPR, FNR, F1; `--sweep` for threshold tuning; `--min-recall`/`--min-precision`/`--max-fpr` CI gates (exit 1 on breach); `--json` output. Stdlib only, no network. |

```bash
python scripts/guardrail_eval.py --results results.jsonl --threshold 0.5 --sweep
python scripts/guardrail_eval.py --results results.jsonl --min-recall 0.90 --max-fpr 0.05 --json
```

---

## References

| File | Contents |
|---|---|
| `references/security_guardrail_patterns.md` | Layered firewall architecture (3 checkpoints), tiered input firewall (fail-closed), tool-call firewall, output firewall with Luhn-validated PII fallback, bounded schema-retry loop, prompt-injection defense taxonomy (spotlighting, sandwiching, dual-LLM, provenance), indirect/RAG guardrails, streaming moderation |
| `references/moderation_frameworks.md` | Llama Guard (taxonomy, prompt template, output parsing, local vs hosted), Guardrails AI (Guard, hub validators, on_fail actions), Presidio (Analyzer/Anonymizer, custom recognizers) — real API surfaces with version assumptions |
| `references/guardrail_effectiveness_evaluation.md` | Labeled-corpus design, confusion-matrix metrics, base-rate math, threshold tuning and two-threshold operation, CI regression gating with `guardrail_eval.py` |

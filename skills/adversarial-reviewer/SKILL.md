---
name: "adversarial-reviewer"
description: "Use when you want a genuinely critical review of recent changes, before merging a PR, or when you suspect the reviewer is being too agreeable about code quality: forces perspective shifts through hostile reviewer personas that catch blind spots the author's mental model shares with the reviewer, and covers agentic-code concerns (prompt-injection surfaces, tool-call safety, non-determinism)."
---

# Adversarial Code Reviewer

## Description

Adversarial code review skill that forces genuine perspective shifts through three hostile reviewer personas (Saboteur, New Hire, Security Auditor). Each persona MUST find at least one issue — no "LGTM" escapes. Findings are severity-classified and cross-promoted when caught by multiple personas.

## Features

- **Three adversarial personas** — Saboteur (production breaks), New Hire (maintainability), Security Auditor (OWASP-informed)
- **Mandatory findings** — Each persona must surface at least one issue, eliminating rubber-stamp reviews
- **Severity promotion** — Issues caught by 2+ personas are promoted one severity level
- **Self-review trap breaker** — Concrete techniques to overcome shared mental model blind spots
- **Structured verdicts** — BLOCK / CONCERNS / CLEAN with clear merge guidance

## Usage

```
/adversarial-review              # Review staged/unstaged changes
/adversarial-review --diff HEAD~3  # Review last 3 commits
/adversarial-review --file src/auth.ts  # Review a specific file
```

## Examples

### Example: Reviewing a PR Before Merge

```
/adversarial-review --diff main...HEAD
```

Produces a structured report with findings from all three personas, deduplicated and severity-ranked, ending with a BLOCK/CONCERNS/CLEAN verdict.

## Problem This Solves

When Claude reviews code it wrote (or code it just read), it shares the same mental model, assumptions, and blind spots as the author. This produces "Looks good to me" reviews on code that a fresh human reviewer would flag immediately. Users report this as one of the top frustrations with AI-assisted development.

This skill forces a genuine perspective shift by requiring you to adopt adversarial personas — each with different priorities, different fears, and different definitions of "bad code."

## Table of Contents

1. [Quick Start](#quick-start)
2. [Review Workflow](#review-workflow)
3. [Personas Complement Deterministic Tooling](#personas-complement-deterministic-tooling)
4. [Large-Diff Triage and Prioritization](#large-diff-triage-and-prioritization)
5. [The Three Personas](#the-three-personas)
6. [Persona 4: The Agent Adversary (Agentic Code)](#persona-4-the-agent-adversary-agentic-code)
7. [Worked Examples: Concurrency and Races](#worked-examples-concurrency-and-races)
8. [Severity Classification](#severity-classification)
9. [Forced-Finding Calibration](#forced-finding-calibration)
10. [Output Format](#output-format)
11. [Escalation and Handoff](#escalation-and-handoff)
12. [Anti-Patterns](#anti-patterns)
13. [When to Use This](#when-to-use-this)
14. [Cross-References](#cross-references)

## Quick Start

```
/adversarial-review              # Review staged/unstaged changes
/adversarial-review --diff HEAD~3  # Review last 3 commits
/adversarial-review --file src/auth.ts  # Review a specific file
```

## Review Workflow

### Step 1: Gather the Changes

Determine what to review based on invocation:

- **No arguments:** Run `git diff` (unstaged) + `git diff --cached` (staged). If both empty, run `git diff HEAD~1` (last commit).
- **`--diff <ref>`:** Run `git diff <ref>`.
- **`--file <path>`:** Read the entire file. Focus review on the full file rather than just changes.

If no changes are found, stop and report: "Nothing to review."

### Step 2: Read the Full Context

For every file in the diff:
1. Read the **full file** (not just the changed lines) — bugs hide in how new code interacts with existing code.
2. Identify the **purpose** of the change: bug fix, new feature, refactor, config change, test.
3. Note any **project conventions** from CLAUDE.md, .editorconfig, linting configs, or existing patterns.

### Step 3: Run All Three Personas

Execute each persona sequentially. Each persona MUST produce at least one finding. If a persona finds nothing wrong, it has not looked hard enough — go back and look again.

**IMPORTANT:** Do not soften findings. Do not hedge. Do not say "this might be fine but..." — either it's a problem or it isn't. Be direct.

### Step 4: Deduplicate and Synthesize

After all three personas have reported:
1. Merge duplicate findings (same issue caught by multiple personas).
2. Promote findings caught by 2+ personas to the next severity level.
3. Produce the final structured output.

## Personas Complement Deterministic Tooling

This hub follows an "algorithm over AI" principle: prefer a deterministic check when one exists. Adversarial personas do **not** replace linters, type-checkers, SAST, or dependency scanners — they run **on top of** them. Run (or consult the output of) the deterministic tooling **first**, treat its results as ground truth in the review, and then spend persona attention only where scanners are structurally blind.

The division of labor:

| Deterministic tooling finds (run first) | Adversarial personas find (semantic, judgment) |
|------------------------------------------|-----------------------------------------------|
| Syntax errors, type mismatches (`tsc`, `mypy`, `pyright`) | Wrong-but-well-typed logic; business-rule violations |
| Lint / style / formatting (`eslint`, `ruff`, `clippy`) | Misleading names; a function whose name lies about what it does |
| Known-CVE dependencies (`npm audit`, `pip-audit`, `osv-scanner`) | A missing authorization check that no rule encodes |
| Taint/injection signatures, hardcoded-secret regexes (`semgrep`, `bandit`, `gitleaks`) | IDOR / broken object-level authz; a trust boundary crossed without validation |
| Dead code, cyclomatic-complexity thresholds | Race conditions spanning two functions; an error path that swallows a failure |
| Format-level schema validation | An assumption that holds in tests but breaks under real traffic; prompt-injection surfaces |

Rules of engagement:

- **If a linter or SAST rule can catch it, do not spend persona budget on it.** Cite the tool output and move on. Persona attention is expensive; reserve it for what deterministic checks cannot see.
- **A persona finding that a scanner *should* have caught** (e.g. "no input validation on this handler") is a signal your scanner configuration has a gap. File it as a NOTE to harden the pipeline, in addition to the finding itself.
- **Scanners find what personas miss** (exhaustive coverage of their rule set, zero fatigue) and **personas find what scanners miss** (intent, context, cross-file semantics). Neither is sufficient alone.

This mirrors the hub's layered-defense philosophy (see also `agentic-guardrails-security`): deterministic checks are the first layer; adversarial review is the layer that reasons about intent. For the security-scanning tools specifically, see the Cross-References section (`skill-security-auditor`, `ai-security`).

## Large-Diff Triage and Prioritization

Do not review a large diff (roughly > 400 changed lines or > 10 files) linearly — you will exhaust attention on boilerplate and arrive fatigued at the dangerous 5%. Triage by risk first, then spend persona effort top-down.

**Priority tiers (highest risk first):**

1. **Trust boundaries** — auth/authz, input parsing, deserialization, path/file handling, anything touching user-controlled or network data.
2. **State mutation and persistence** — DB writes, migrations, cache invalidation, money/quota/counter changes, anything with a rollback cost.
3. **Concurrency and ordering** — shared state, async/await, locks, queues, idempotency of retried operations.
4. **Agent/LLM surfaces** — prompt construction, tool wiring, output parsing, agent loops (see Persona 4).
5. **Control-flow changes to existing hot paths.**
6. **New dependencies** — cross-check against the dependency-scanner output.
7. **Everything else** — pure functions, renames, formatting, generated code, lockfiles, fixtures, docs.

**Skim depth (do not deep-review):** generated files, lockfiles, vendored code, large data fixtures, and pure formatting churn. Record them explicitly as "reviewed at skim depth" so the verdict is honest about coverage.

**Budget discipline:** the review is itself a bounded loop. Declare an effort budget up front (e.g. "deep review of tiers 1-4, skim of tiers 5-7") and state it in the report. If the diff is too large to review to depth within budget, that is itself a `budget` exit condition — recommend splitting the PR and emit an escalation (see Escalation and Handoff) rather than a false-confidence CLEAN. For the exit-condition taxonomy behind this, see `agentic-system-architect/references/loop_engineering_patterns.md`.

## The Three Personas

### Persona 1: The Saboteur

**Mindset:** "I am trying to break this code in production."

**Priorities:**
- Input that was never validated
- State that can become inconsistent
- Concurrent access without synchronization
- Error paths that swallow exceptions or return misleading results
- Assumptions about data format, size, or availability that could be violated
- Off-by-one errors, integer overflow, null/undefined dereferences
- Resource leaks (file handles, connections, subscriptions, listeners)

**Review Process:**
1. For each function/method changed, ask: "What is the worst input I could send this?"
2. For each external call, ask: "What if this fails, times out, or returns garbage?"
3. For each state mutation, ask: "What if this runs twice? Concurrently? Never?"
4. For each conditional, ask: "What if neither branch is correct?"

**You MUST find at least one issue. If the code is genuinely bulletproof, note the most fragile assumption it relies on.**

---

### Persona 2: The New Hire

**Mindset:** "I just joined this team. I need to understand and modify this code in 6 months with zero context from the original author."

**Priorities:**
- Names that don't communicate intent (what does `data` mean? what does `process()` do?)
- Logic that requires reading 3+ other files to understand
- Magic numbers, magic strings, unexplained constants
- Functions doing more than one thing (the name says X but it also does Y and Z)
- Missing type information that forces the reader to trace through call chains
- Inconsistency with surrounding code style or project conventions
- Tests that test implementation details instead of behavior
- Comments that describe *what* (redundant) instead of *why* (useful)

**Review Process:**
1. Read each changed function as if you've never seen the codebase. Can you understand what it does from the name, parameters, and body alone?
2. Trace one code path end-to-end. How many files do you need to open?
3. Check: would a new contributor know where to add a similar feature?
4. Look for "the author knew something the reader won't" — implicit knowledge baked into the code.

**You MUST find at least one issue. If the code is crystal clear, note the most likely point of confusion for a newcomer.**

---

### Persona 3: The Security Auditor

**Mindset:** "This code will be attacked. My job is to find the vulnerability before an attacker does."

**OWASP-Informed Checklist:**

| Category | What to Look For |
|----------|-----------------|
| **Injection** | SQL, NoSQL, OS command, LDAP — any place user input reaches a query or command without parameterization |
| **Broken Auth** | Hardcoded credentials, missing auth checks on new endpoints, session tokens in URLs or logs |
| **Data Exposure** | Sensitive data in error messages, logs, or API responses; missing encryption at rest or in transit |
| **Insecure Defaults** | Debug mode left on, permissive CORS, wildcard permissions, default passwords |
| **Missing Access Control** | IDOR (can user A access user B's data?), missing role checks, privilege escalation paths |
| **Dependency Risk** | New dependencies with known CVEs, pinned to vulnerable versions, unnecessary transitive dependencies |
| **Secrets** | API keys, tokens, passwords in code, config, or comments — even "temporary" ones |

**Review Process:**
1. Identify every trust boundary the code crosses (user input, API calls, database, file system, environment variables).
2. For each boundary: is input validated? Is output sanitized? Is the principle of least privilege followed?
3. Check: could an authenticated user escalate privileges through this change?
4. Check: does this change expose any new attack surface?

**You MUST find at least one issue. If the code has no security surface, note the closest thing to a security-relevant assumption.**

## Persona 4: The Agent Adversary (Agentic Code)

The three personas above run on **every** review. This fourth, **specialist** persona is **conditional** — activate it only when the diff touches agent / LLM / tool-calling code: prompt templates, system prompts, tool or function definitions, MCP servers, agent loops, output parsers, RAG retrieval, or anywhere model output feeds back into control flow. This is an agent hub, and agentic code has failure modes ordinary review misses.

**Mindset:** "This code hands control to a non-deterministic model and to text I do not control. Where does untrusted text become an instruction, and where does model output become an action?"

**Checklist — Prompt-injection surfaces:**
- Does any untrusted input (user message, retrieved document, tool result, web page, file content, prior-session data) get concatenated into a prompt without being clearly delimited and marked as **data, not instructions**?
- Is there an explicit **instruction-source boundary** — does the system treat tool/RAG/document content as data rather than as commands it will obey?
- Could retrieved or tool-returned content redirect the agent (indirect prompt injection)?
- (For runtime defenses — spotlighting, sandwiching, dual-LLM — see `agentic-guardrails-security`. This persona *reviews* for the surface; that skill *enforces* the defense.)

**Checklist — Tool-call safety:**
- Are irreversible tool calls (delete, deploy, send, transfer, migrate, publish) gated behind human approval or an upstream gate step, per HITL rule R1? A newly exposed irreversible tool with no gate is a **CRITICAL** finding. (See `agentic-system-architect/references/hitl_defensive_architectures.md` for the R1-R6 rules.)
- Are tool arguments validated before execution, or does raw model output flow straight into a shell / SQL / filesystem / HTTP call? **Model output is untrusted input** — treat it like user input for injection purposes.
- Is tool scope least-privilege? Does a new tool widen the blast radius (filesystem write, network egress, credential access)?
- On tool failure, is there an `on_failure` policy — bounded retry, escalate, or abort (rule R4) — or does the agent silently continue past a failed action?

**Checklist — Non-determinism and loop safety:**
- Does the change add or modify an iteration loop (retry, reflect, evaluate-optimize)? If so, does it declare at least one **bounding** exit condition (`max_iterations` or `budget`) and not rely on `success_predicate` alone? (Canonical taxonomy: `max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`, `escalation_trigger` — see `loop_engineering_patterns.md`.)
- Could the loop oscillate (A-B-A-B) or repeat an identical action or thought — the runaway signatures D1/D2/D7 that `react_trace_analyzer.py` flags?
- Does the code assume the model returns well-formed output (valid JSON, a known enum, a bounded length)? What happens on a malformed, empty, truncated, or refusal response? Non-determinism means "passed in testing" is not "correct."
- Is the prompt or model behavior versioned enough that this change is reproducible? An un-versioned prompt edit that silently shifts production behavior is a finding (see also `prompt-governance`).
- Model references: are model families pinned by tier or current alias rather than a deprecated hardcoded ID that will 404? (Verify against current provider docs.)

**You MUST find at least one issue when agentic code is present. If the agent code is genuinely well-guarded, name the single most dangerous thing the design trusts the model to get right.**

## Worked Examples: Concurrency and Races

Concurrency bugs are the Saboteur's highest-value hunting ground: they pass every single-threaded test and every type-checker, so no deterministic tool in the pipeline will catch them. Look for these patterns, each with the question that surfaces it.

**Example 1 — Check-then-act (TOCTOU):**
```python
# Two requests run this concurrently
if not db.exists(user_id):        # T1 and T2 both read "does not exist"
    db.create(User(user_id))      # T1 creates; T2 creates again -> duplicate / unique-violation
```
Question: *"What if this runs twice concurrently between the check and the act?"* Fix direction: atomic upsert, a unique constraint, or a lock. Severity: WARNING, or CRITICAL if it corrupts money/state.

**Example 2 — Read-modify-write on shared state (lost update):**
```python
balance = account.get_balance()    # both readers see 100
account.set_balance(balance - 10)  # both write 90 -> one -10 is lost; correct answer was 80
```
Question: *"Is this update atomic, or can two writers interleave?"* Fix direction: atomic DB update (`UPDATE ... SET balance = balance - 10 WHERE ...`), an optimistic-lock version column, or a transaction at the right isolation level.

**Example 3 — async shared state / unawaited failure:**
```python
await asyncio.gather(*(handle(i) for i in items))
# Watch for: a module-level cache mutated by concurrent tasks without a lock;
# a fire-and-forget task whose exception is never awaited and silently vanishes;
# a resource (lock/connection) held across an await point, serializing or deadlocking.
```
Questions: *"Is any shared structure mutated by concurrent tasks? Is any created task awaited so its exception surfaces? Is any resource held across an await?"*

**Example 4 — Non-idempotent tool retried (agentic tie-in):**
An error-mitigation loop retries a failed tool call. If `send_payment` succeeded but the response timed out, the retry double-sends. Question: *"Is every retried action idempotent, or keyed by an idempotency token?"* This links tool-call safety (Persona 4) to concurrency: a bounded retry loop is still a bug if the action it retries is not idempotent.

For the loop-safety theory behind bounded retries and idempotent iteration, see `agentic-system-architect/references/loop_engineering_patterns.md` — do not re-derive it here.

## Severity Classification

| Severity | Definition | Action Required |
|----------|-----------|-----------------|
| **CRITICAL** | Will cause data loss, security breach, or production outage. Must fix before merge. | Block merge. |
| **WARNING** | Likely to cause bugs in edge cases, degrade performance, or confuse future maintainers. Should fix before merge. | Fix or explicitly accept risk with justification. |
| **NOTE** | Style issue, minor improvement opportunity, or documentation gap. Nice to fix. | Author's discretion. |

**Promotion rule:** A finding flagged by 2+ personas is promoted one level (NOTE becomes WARNING, WARNING becomes CRITICAL).

## Forced-Finding Calibration

The "each persona MUST find at least one issue" rule exists to break rubber-stamping — **not** to manufacture noise. A forced finding must still be a real, defensible risk, not padding. Calibrate every finding against this test.

**A finding is GENUINE only when you can state all three:**
1. A concrete **trigger** — a specific input, state, or timing that reaches it.
2. A concrete **bad outcome** — crash, wrong result, breach, data loss, or a maintainer who will misread it.
3. It is **not already prevented** elsewhere in the code path.

If you cannot fill all three, it is padding — downgrade it or drop it.

**Padding tells (downgrade or drop):**
- "Consider adding more tests" with no specific untested path named.
- "This could be more readable" with no named ambiguity.
- "Might want to handle errors" where errors are already handled upstream.
- Restating a linter/SAST rule the pipeline already enforces (cite the tool instead).
- Hypotheticals with no reachable trigger ("if someone deleted this line...").

**When the code really is solid,** the honest minimum finding is the **weakest assumption**, stated as a NOTE — not a WARNING inflated to look substantive. Example: *"No defect found in the retry logic; the load-bearing assumption is that `fetch()` never returns a 2xx with an empty body — untested, low likelihood. NOTE."* That is a legitimate forced finding. Inventing a CRITICAL to appear thorough is the **opposite** failure: it erodes trust in every future BLOCK.

**Rule:** severity reflects reality, never the reviewer's need to "have found something." A review that honestly lands at CLEAN with three well-argued NOTES is a **successful** review, not a failed one. This is the antidote to the self-agreement and cosmetic-churn failure modes that reflection loops fall into (see `loop_engineering_patterns.md`): anchor every finding to a rubric, not a vibe.

## Output Format

Structure your review as follows:

```markdown
## Adversarial Review: [brief description of what was reviewed]

**Scope:** [files reviewed, lines changed, type of change]
**Verdict:** BLOCK / CONCERNS / CLEAN

### Critical Findings
[If any — these block the merge]

### Warnings
[Should-fix items]

### Notes
[Nice-to-fix items]

### Summary
[2-3 sentences: what's the overall risk profile? What's the single most important thing to fix?]
```

**Verdict definitions:**
- **BLOCK** — 1+ CRITICAL findings. Do not merge until resolved.
- **CONCERNS** — No criticals but 2+ warnings. Merge at your own risk.
- **CLEAN** — Only notes. Safe to merge.

## Escalation and Handoff

An adversarial review is the **SELF-REVIEW and HANDOFF** stage (Phase 5) of the hub's 5-Phase Protocol applied to a code change, and the verdict is a handoff signal. Map each verdict to a next action rather than treating it as a dead end.

| Verdict | Meaning | Hub mapping and next action |
|---------|---------|------------------------------|
| **BLOCK** | 1+ CRITICAL | Fires an `escalation_trigger`. Do not self-merge. A CRITICAL touching an **irreversible action** (deploy, delete, migrate, payment, publish) must go to a **human** — that is exactly the class the HUMAN GATE (Phase 3) exists to stop. Hand off the finding, its trigger, and a rollback note (HITL rules R1/R2). |
| **CONCERNS** | No criticals, 2+ warnings | Return to the author to fix-or-justify. If an autonomous agent produced the change, bound the fix loop: repair within a set number of attempts, then escalate rather than loop indefinitely. |
| **CLEAN** | Only notes | Proceed to handoff. Record coverage honestly — what was deep-reviewed vs. skimmed, per Large-Diff Triage. |

**Escalation rules:**
- **Any CRITICAL in security- or money-touching code escalates to a human**, regardless of the reviewer's confidence. An adversarial reviewer never grants approval for an irreversible action — that authority belongs to the HUMAN GATE, not the reviewer.
- **If the diff exceeds the review budget** (see Large-Diff Triage), emit an explicit `budget` escalation ("too large to review to depth; recommend splitting the PR"), not a CLEAN.
- **If two fix-review cycles do not converge** — the same class of finding keeps reappearing — stop looping and escalate. This is the `no_progress` / `max_iterations` exit condition applied to the review loop itself.

**Handoff report** should carry: scope and coverage depth, the verdict, findings grouped by severity, and — for BLOCK/CONCERNS — the specific exit condition or gate that fired. This makes the review auditable and lets an orchestrator route it correctly. For the full exit-condition taxonomy and the HITL gate theory, see `agentic-system-architect/references/loop_engineering_patterns.md` and `references/hitl_defensive_architectures.md`.

## Anti-Patterns

### What This Skill is NOT

| Anti-Pattern | Why It's Wrong |
|-------------|---------------|
| "LGTM, no issues found" | If you found nothing, you didn't look hard enough. Every change has at least one risk, assumption, or improvement opportunity. |
| Cosmetic-only findings | Reporting only whitespace/formatting while missing a null dereference is worse than no review at all. Substance first, style second. |
| Pulling punches | "This might possibly be a minor concern..." — No. Be direct. "This will throw a NullPointerException when `user` is undefined." |
| Restating the diff | "This function was added to handle authentication" is not a finding. What's WRONG with how it handles authentication? |
| Ignoring test gaps | New code without tests is a finding. Always. Tests are not optional. |
| Reviewing only the changed lines | Bugs live in the interaction between new code and existing code. Read the full file. |

### The Self-Review Trap

You are likely reviewing code you just wrote or just read. Your brain (weights) formed the same mental model that produced this code. You will naturally think it looks correct because it matches your expectations.

**To break this pattern:**
1. Read the code **bottom-up** (start from the last function, work backward).
2. For each function, state its contract **before** reading the body. Does the body match?
3. Assume every variable could be null/undefined until proven otherwise.
4. Assume every external call will fail.
5. Ask: "If I deleted this change entirely, what would break?" — if the answer is "nothing," the change might be unnecessary.

## When to Use This

- **Before merging any PR** — especially self-authored PRs with no human reviewer
- **After a long coding session** — fatigue produces blind spots; this skill compensates
- **When Claude said "looks good"** — if you got an easy approval, run this for a second opinion
- **On security-sensitive code** — auth, payments, data access, API endpoints
- **When something "feels off"** — trust that instinct and run an adversarial review

## Cross-References

**Scope delineation (resolves the OWASP / injection overlap):** this skill is a **review methodology** — how to reason adversarially about a diff. The overlapping security skills below are **scanning tools**. Run them first and feed their output into the Security Auditor persona and Persona 4 (see Personas Complement Deterministic Tooling); use the personas to reason about what those scanners structurally cannot encode.

- `ai-security` — AI/ML security **scanner**: prompt-injection and jailbreak signatures, MITRE ATLAS mapping, model-inversion and data-poisoning risk. Its scanner overlaps the Security Auditor persona's OWASP list and Persona 4's injection checklist; it *scans*, this skill *reasons*.
- `skill-security-auditor` — pre-install security **scanner** for agent skills (dangerous Python patterns, prompt injection in SKILL.md, supply-chain risk). It is **not** a general code reviewer — this skill is the general adversarial reviewer.
- `agentic-guardrails-security` — **runtime** enforcement of the Persona-4 concerns (Llama Guard, Guardrails AI, Presidio, injection defenses). This skill reviews for the surface; that skill enforces the defense.
- `prompt-governance` — versioning and eval pipelines for the prompt changes Persona 4 flags.
- `self-eval` — honest work-quality scoring; complements the Forced-Finding Calibration discipline here.
- `agentic-system-architect` — flagship reference for loop theory, the six-type exit-condition taxonomy, D1-D7, R1-R6, and the >= 90 HARDENED gate cited throughout this skill.

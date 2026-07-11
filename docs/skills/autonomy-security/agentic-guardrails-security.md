---
title: "Skill: agentic-guardrails-security — Autonomous Guardrails & Threat Modeling"
description: "Configure semantic input/output firewalls, prompt injection mitigations, and sensitive data leakage (PII) filters using Llama Guard or Guardrails AI. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: agentic-guardrails-security

<div class="page-meta" markdown>
<span class="meta-badge">:material-shield-lock: Autonomy & Security</span>
<span class="meta-badge">:material-identifier: `agentic-guardrails-security`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-guardrails-security/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install autonomy-security</code>
</div>


This skill teaches the agent how to design defensive semantic security layers around LLM inputs and outputs.

## Capability

**This skill does exactly one thing:** designs input/output guardrail policies, configures PII redactors, and instruments content moderator models (like Llama Guard) to block malicious prompt injections and sensitive data leakages.

## Core Principles

### 1. Input Guardrails (Jailbreak Mitigation)
* Validate user prompts at the entry point of the API (FastAPI or C# Gateway) using a classifier model or specialized framework (Guardrails AI, Llama Guard).
* Detect and block injection patterns: "Ignore previous instructions", prompt leak attempts, and unauthorized system commands.

### 2. Output Guardrails (PII & Hallucination Filters)
* Audit model responses before sending them back to the client.
* Detect and redact PII (credit cards, SSNs, personal details) using Presidio or regex policies.
* Enforce schema compliance: if the output is not valid JSON or violates system boundaries, block it and trigger an internal retry loop.

### 3. Middleware Integration
* Implement guardrails as middleware decorators or pipeline handlers (`DelegatingHandler` in .NET, FastAPI dependencies in Python) to keep core agent logic clean.

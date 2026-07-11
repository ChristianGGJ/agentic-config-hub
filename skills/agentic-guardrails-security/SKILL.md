---
name: "agentic-guardrails-security"
version: "1.0.0"
description: "Configure semantic input/output firewalls, prompt injection mitigations, and sensitive data leakage (PII) filters using Llama Guard or Guardrails AI"
type: "skill"
---

# Skill: agentic-guardrails-security

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

## References

| File | Summary |
|------|---------|
| `references/security_guardrail_patterns.md` | Input jailbreak middleware codes (FastAPI), outbound PII regex redactors, and strict JSON output schema enforcers |


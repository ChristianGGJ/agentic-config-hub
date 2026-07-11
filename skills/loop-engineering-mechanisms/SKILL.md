---
name: "loop-engineering-mechanisms"
version: "1.0.0"
description: "Enforce self-correcting retry cycles, output validation schemas, error formatters, and maximum iteration escape routes to prevent runaway loops"
type: "skill"
---

# Skill: loop-engineering-mechanisms

This skill teaches the agent how to design rigorous self-correction loops and validation gates to prevent infinite reasoning loops and hallucinated outputs.

## Capability

**This skill does exactly one thing:** structures deterministic output validators, designs machine-readable error injection prompts, and configures strict loop exit counters and human escape routes.

## Core Principles

### 1. Deterministic Output Validation
* Never rely on LLMs to self-validate their own output.
* Implement deterministic validators (code compilation, JSON schema checks, regex parsers, unit test runners) to verify correctness before accepting any generation.

### 2. Structured Retry & Error Injection
* If the validator fails, do not just send a generic "fix this" message.
* Construct a machine-readable error report containing:
  - Exact error message or compilation stdout.
  - Slices of code where the error occurred.
  - Corrective hints.
* Inject this error report back into the agent's message history as an `Observation` to guide the next iteration.

### 3. Exit Conditions & Escapes
* Every reasoning or correction loop must define a strict `max_iterations` counter (typically capped at 3).
* If the counter is reached without passing validation, stop execution, freeze state, and trigger `escalation_trigger` to hand off to a human reviewer.

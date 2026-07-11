---
name: "multi-llm-routing"
version: "1.0.0"
description: "Route task completion requirements across diverse LLM tiers (reasoning models vs. utility models) to optimize token costs, latency, and system capability"
type: "skill"
---

# Skill: multi-llm-routing

This skill teaches the agent how to plan and route tasks to the most cost-efficient and performant LLM tier based on execution complexity.

## Capability

**This skill does exactly one thing:** classifies task complexity (Reasoning vs. Utility) and configures routing rules to direct critical tasks to advanced reasoning models and mechanical tasks to lightweight models.

## Core Principles

### 1. Classification of Tasks
* **Reasoning Tier**: Tasks requiring complex coding, self-correction logic, system architecture, multi-agent planning, or final synthesis.
* **Utility Tier**: Tasks involving mechanical formatting, data extraction, JSON validation, text summarization, or simple tool execution.

### 2. Model Routing Rules
* **Reasoning Models**: Route Reasoning Tier tasks to high-cost, high-capability models (e.g. `claude-3-5-sonnet`, `o1`, `o3`).
* **Utility Models**: Route Utility Tier tasks to low-cost, fast, or local models (e.g. `gpt-4o-mini`, `ollama/llama3`, `gemini-1.5-flash`).

### 3. Cost & Latency Balancing
* Minimize tokens sent to the Reasoning Tier by offloading preprocessing and preprocessing verification to Utility models.
* For multi-stage workflows, define model overrides per node/agent rather than using a single model for the entire workflow.

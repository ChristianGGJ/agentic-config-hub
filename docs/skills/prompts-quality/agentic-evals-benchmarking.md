---
title: "Skill: agentic-evals-benchmarking — Prompts Optimization & Quality Rubrics"
description: "Define automated regression test suites, synthetic data evaluation pipelines, and quality scoring metrics using DeepEval/Ragas. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: agentic-evals-benchmarking

<div class="page-meta" markdown>
<span class="meta-badge">:material-clipboard-check: Prompts & Quality</span>
<span class="meta-badge">:material-identifier: `agentic-evals-benchmarking`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/agentic-evals-benchmarking/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install prompts-quality</code>
</div>


This skill teaches the agent how to design automated, quantitative test suites to measure and prevent regressions in agent outputs.

## Capability

**This skill does exactly one thing:** plans evaluation datasets, configures LLM-as-a-judge scoring frameworks (DeepEval, Ragas), and defines CI/CD validation gates measuring faithfulness, recall, and relevance.

## Core Principles

### 1. Metric Taxonomy
* **Faithfulness**: Validates that the agent's output is derived strictly from the supplied retrieval context (prevents hallucinations).
* **Answer Relevance**: Measures how well the output addresses the user's initial query.
* **Context Recall**: Verifies that the retrieval system fetched all relevant facts required to answer the prompt.

### 2. Automated Test Pipelines
* Implement regression suites using `DeepEval` (Python) or equivalent frameworks.
* Define threshold scores (e.g. `>= 0.85/1.00`). If a PR changes prompts or agent structures and fails the threshold, the CI/CD pipeline must fail.

### 3. Synthetic Data Generation
* Generate diverse test cases synthetically by extracting key entities and query templates from source domain documentation.

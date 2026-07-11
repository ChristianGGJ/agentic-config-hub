---
title: "Skill: microsoft-agent-framework — MCP Servers & RAG Architectures"
description: "Map repository skills and agents to Microsoft Agent Framework 1.0 (unifying AutoGen and Semantic Kernel) in C# .NET. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: microsoft-agent-framework

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `microsoft-agent-framework`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/microsoft-agent-framework/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


This skill teaches agents how to design and scaffold C# implementations using the unified Microsoft Agent Framework 1.0.

## Capability

**This skill does exactly one thing:** translates YAML/Markdown skill packages and agent configurations into Microsoft Agent Framework 1.0 C# `ChatClientAgent` definitions, `AIFunction` tool representations, and agent-to-agent (A2A) orchestrations.

## Inputs / Outputs

### Inputs
| Input | Type | Required | Description |
|---|---|---|---|
| `source-path` | string | yes | Path to the skill folder or agent configuration markdown file to translate. |
| `output-language` | string | no | Target SDK language. Default: `csharp`. |

### Outputs
| Output | Type | Description |
|---|---|---|
| `csharp-code` | string | Generated C# source code using Microsoft Agent Framework 1.0 and Microsoft.Extensions.AI. |
| `exit code` | integer | 0 on success, 1 on error. |

## Non-Goals

This skill refuses to:
* Support legacy Semantic Kernel agent abstractions (`ChatCompletionAgent` from `Microsoft.SemanticKernel.Agents`) or legacy AutoGen Python structures — enforce Microsoft Agent Framework 1.0.
* Direct network execution or API credential validation.

## Usage

### When to invoke
* Whenever mapping configurations (agents/skills) to the unified Microsoft Agent Framework 1.0 for C# developers.
* During the **Phase 4 IMPLEMENTATION** phase of a system design workflow when Microsoft Agent Framework integration is requested.

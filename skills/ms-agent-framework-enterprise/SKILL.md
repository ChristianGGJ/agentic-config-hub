---
name: "ms-agent-framework-enterprise"
version: "1.0.0"
description: "Design C# backend integrations and native tool plugin architectures using Microsoft Agent Framework 1.0, focusing on dependency injection and robust data mapping"
type: "skill"
---

# Skill: ms-agent-framework-enterprise

This skill teaches the agent how to implement production-grade, typed agent integrations within enterprise C#/.NET 9 applications.

## Capability

**This skill does exactly one thing:** designs native C# agent classes (`ChatClientAgent`), exposes C# services as `AIFunction` tools utilizing Microsoft dependency injection (`IServiceCollection`), and optimizes database-to-context data mapping.

## Core Principles

### 1. Enterprise Dependency Injection (DI)
* Register LLM clients (`IChatClient`) and agents within the ASP.NET Core / .NET service container.
* Inject business service dependencies (e.g. databases, loggers) directly into tool classes so they have access to live application contexts.

### 2. Native Plugin Design
* Decorate C# tool methods with descriptive attributes (`[Description]`).
* Parameters must have strict primitive types or cleanly serialized DTOs.
* Handle exceptions gracefully: return structured error logs instead of throwing unhandled exceptions that crash the host application.

### 3. Context & Relational Data Strategies
* **Context Optimization**: Restrict relational data extracts (SQL queries, entity graphs) to small, structured DTO lists. Do not dump entire database rows into the LLM context.
* **Security Boundaries**: Validate user and tenant boundaries in the native C# code of the tool before executing queries. Never trust the agent to enforce security constraints in prompts.

## References

| File | Summary |
|------|---------|
| `references/enterprise_integration_patterns.md` | DI configurations, scoped agents factories, class-based AIFunction tool definitions, relational DTO data optimizations, and OpenTelemetryActivity tracking |


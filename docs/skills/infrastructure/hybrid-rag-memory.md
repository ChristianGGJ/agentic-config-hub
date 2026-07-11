---
title: "Skill: hybrid-rag-memory — MCP Servers & RAG Architectures"
description: "Design persistent long-term memory architectures and hybrid vector search patterns (BM25 + embeddings) to support stateful multi-agent systems. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# Skill: hybrid-rag-memory

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `hybrid-rag-memory`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/hybrid-rag-memory/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


This skill teaches the agent how to implement long-term memory sync and hybrid retrieval databases for corporate multi-agent systems.

## Capability

**This skill does exactly one thing:** designs vector database schemas, specifies hybrid search retrieval queries (combining keyword BM25 with dense vector embeddings), and manages persistent long-term session memories.

## Core Principles

### 1. Hybrid Search Architecture
* Always combine **lexical search (BM25)** for exact keyword/ID matches with **semantic vector search (embeddings)** for conceptual matches.
* Implement Reciprocal Rank Fusion (RRF) or cross-encoder re-ranking to merge and prioritize results.

### 2. Long-Term Memory Sync
* **CrewAI**: Map long-term SQLite/Qdrant memory backends to persist entity information and feedback loops across runs.
* **LangGraph**: Implement external PostgreSQL/Redis state checkpoints to allow session persistence across server Restarts.

### 3. Microsoft Agent Framework Memory Stores
* Bind implementations of `IMemoryStore` to backends (e.g. pgvector or Azure AI Search).
* Partition memories cleanly by user and session keys to prevent cross-tenant data leaks.

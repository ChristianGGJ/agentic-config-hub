---
title: "RAG Architect — MCP Servers & RAG Architectures"
description: "Use when the user asks to design RAG pipelines, optimize retrieval strategies, choose embedding models, implement vector search, or build knowledge. Agent skill for Claude Code, Codex CLI, Gemini CLI, OpenClaw."
---

# RAG Architect

<div class="page-meta" markdown>
<span class="meta-badge">:material-server: Infrastructure</span>
<span class="meta-badge">:material-identifier: `rag-architect`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/rag-architect/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install infrastructure</code>
</div>


## Overview

The RAG (Retrieval-Augmented Generation) Architect skill provides comprehensive tools and knowledge for designing, implementing, and optimizing production-grade RAG pipelines. This skill covers the entire RAG ecosystem from document chunking strategies to evaluation frameworks, enabling you to build scalable, efficient, and accurate retrieval systems.

## Tools

Three deterministic Python CLIs live in `scripts/` (stdlib-only, no network or LLM calls). Run them from the skill folder; every flag below is the real argparse surface (`--help` documents the same).

### 1. `scripts/chunking_optimizer.py` — recommend a chunking strategy for a corpus

Analyzes documents in a directory (structure, length distribution, heading density) and recommends the chunking strategy plus size/overlap parameters.

```bash
python scripts/chunking_optimizer.py <directory>
python scripts/chunking_optimizer.py ./docs --output analysis.json
python scripts/chunking_optimizer.py ./docs --extensions .md .txt --verbose
python scripts/chunking_optimizer.py ./docs --config chunking_config.json
```

- `directory` (positional) — folder containing text/markdown documents
- `--output / -o` — write results as JSON to a file
- `--config / -c` — JSON configuration file
- `--extensions` — file extensions to process (space-separated)
- `--verbose / -v` — verbose output

### 2. `scripts/rag_pipeline_designer.py` — design a pipeline from requirements

Takes a JSON requirements file (scale, latency, quality targets, budget) and emits a pipeline design: chunking, embedding model class, vector DB, retrieval strategy.

```bash
python scripts/rag_pipeline_designer.py requirements.json
python scripts/rag_pipeline_designer.py requirements.json --output pipeline.json --verbose
```

- `requirements` (positional) — JSON file containing system requirements
- `--output / -o` — write pipeline design as JSON to a file
- `--verbose / -v` — verbose output

### 3. `scripts/retrieval_evaluator.py` — score a retrieval setup against ground truth

Evaluates retrieval quality (precision@k, recall@k, NDCG@k, MRR) for a query set against a corpus with relevance judgments.

```bash
python scripts/retrieval_evaluator.py queries.json ./corpus ground_truth.json
python scripts/retrieval_evaluator.py queries.json ./corpus ground_truth.json --k-values 1 3 5 10
python scripts/retrieval_evaluator.py queries.json ./corpus ground_truth.json --extensions .md --output eval.json
```

- `queries` (positional) — JSON file containing queries
- `corpus` (positional) — directory containing the document corpus
- `ground_truth` (positional) — JSON file with relevance judgments
- `--k-values` — K values for precision@k / recall@k / NDCG@k (space-separated)
- `--output / -o` — write results as JSON to a file
- `--extensions` — file extensions to include from the corpus
- `--verbose / -v` — verbose output

## References

Expert knowledge bases in `references/`:

| File | Use it for |
|------|-----------|
| `references/chunking_strategies_comparison.md` | Side-by-side chunking strategy comparison with parameters and tradeoffs |
| `references/embedding_model_benchmark.md` | Embedding model selection: quality/speed/cost tiers and current-model landscape |
| `references/rag_evaluation_framework.md` | Metric definitions and evaluation methodology for RAG pipelines |
| `references/agentic_rag_patterns.md` | Agentic RAG, GraphRAG, Self-RAG/CRAG, multi-hop retrieval — when to use each and failure modes |

## Core Competencies

### 1. Document Processing & Chunking Strategies

#### Fixed-Size Chunking
- **Character-based chunking**: Simple splitting by character count (e.g., 512, 1024, 2048 chars)
- **Token-based chunking**: Splitting by token count to respect model limits
- **Overlap strategies**: 10-20% overlap to maintain context continuity
- **Pros**: Predictable chunk sizes, simple implementation, consistent processing time
- **Cons**: May break semantic units, context boundaries ignored
- **Best for**: Uniform documents, when consistent chunk sizes are critical

#### Sentence-Based Chunking
- **Sentence boundary detection**: Using NLTK, spaCy, or regex patterns
- **Sentence grouping**: Combining sentences until size threshold is reached
- **Paragraph preservation**: Avoiding mid-paragraph splits when possible
- **Pros**: Preserves natural language boundaries, better readability
- **Cons**: Variable chunk sizes, potential for very short/long chunks
- **Best for**: Narrative text, articles, books

#### Paragraph-Based Chunking
- **Paragraph detection**: Double newlines, HTML tags, markdown formatting
- **Hierarchical splitting**: Respecting document structure (sections, subsections)
- **Size balancing**: Merging small paragraphs, splitting large ones
- **Pros**: Preserves logical document structure, maintains topic coherence
- **Cons**: Highly variable sizes, may create very large chunks
- **Best for**: Structured documents, technical documentation

#### Semantic Chunking
- **Topic modeling**: Using TF-IDF, embeddings similarity for topic detection
- **Heading-aware splitting**: Respecting document hierarchy (H1, H2, H3)
- **Content-based boundaries**: Detecting topic shifts using semantic similarity
- **Pros**: Maintains semantic coherence, respects document structure
- **Cons**: Complex implementation, computationally expensive
- **Best for**: Long-form content, technical manuals, research papers

#### Recursive Chunking
- **Hierarchical approach**: Try larger chunks first, recursively split if needed
- **Multi-level splitting**: Different strategies at different levels
- **Size optimization**: Minimize number of chunks while respecting size limits
- **Pros**: Optimal chunk utilization, preserves context when possible
- **Cons**: Complex logic, potential performance overhead
- **Best for**: Mixed content types, when chunk count optimization is important

#### Document-Aware Chunking
- **File type detection**: PDF pages, Word sections, HTML elements
- **Metadata preservation**: Headers, footers, page numbers, sections
- **Table and image handling**: Special processing for non-text elements
- **Pros**: Preserves document structure and metadata
- **Cons**: Format-specific implementation required
- **Best for**: Multi-format document collections, when metadata is important

### 2. Embedding Model Selection

#### Dimension Considerations
- **128-256 dimensions**: Fast retrieval, lower memory usage, suitable for simple domains
- **512-768 dimensions**: Balanced performance, good for most applications
- **1024-1536 dimensions**: High quality, better for complex domains, higher cost
- **2048+ dimensions**: Maximum quality, specialized use cases, significant resources

#### Speed vs Quality Tradeoffs
- **Fast models**: sentence-transformers/all-MiniLM-L6-v2 (384 dim, ~14k tokens/sec, CPU-friendly)
- **Balanced open-weights**: bge-m3, e5 family, gte family (typically 768-1024 dim)
- **Quality API models**: OpenAI text-embedding-3-large, Voyage voyage-3 family, Cohere embed v3/v4 (verify current versions against provider docs)
- **Specialized models**: Domain-specific fine-tuned models
- **Matryoshka embeddings**: models trained with Matryoshka representation learning (e.g. text-embedding-3 family) let you truncate vectors to lower dimensions with modest quality loss — cut storage/latency without re-embedding

#### Model Categories
- **General purpose**: bge/e5/gte families (open-weights), text-embedding-3, voyage-3, cohere embed v3/v4 (API)
- **Code embeddings**: code-specialized variants (e.g. voyage-code, jina-embeddings code models); legacy CodeBERT-family for offline baselines
- **Scientific text**: SciBERT, BioBERT, ClinicalBERT (or a general SOTA model — benchmark both)
- **Multilingual**: bge-m3, multilingual-e5, LaBSE

See `references/embedding_model_benchmark.md` for the selection framework and tier tables.

### 3. Vector Database Selection

#### Pinecone
- **Managed service**: Fully hosted, auto-scaling
- **Features**: Metadata filtering, hybrid search, real-time updates
- **Pricing**: $70/month for 1M vectors (1536 dim), pay-per-use scaling
- **Best for**: Production applications, when managed service is preferred
- **Cons**: Vendor lock-in, costs can scale quickly

#### Weaviate
- **Open source**: Self-hosted or cloud options available
- **Features**: GraphQL API, multi-modal search, automatic vectorization
- **Scaling**: Horizontal scaling, HNSW indexing
- **Best for**: Complex data types, when GraphQL API is preferred
- **Cons**: Learning curve, requires infrastructure management

#### Qdrant
- **Rust-based**: High performance, low memory footprint
- **Features**: Payload filtering, clustering, distributed deployment
- **API**: REST and gRPC interfaces
- **Best for**: High-performance requirements, resource-constrained environments
- **Cons**: Smaller community, fewer integrations

#### Chroma
- **Embedded database**: SQLite-based, easy local development
- **Features**: Collections, metadata filtering, persistence
- **Scaling**: Limited, suitable for prototyping and small deployments
- **Best for**: Development, testing, small-scale applications
- **Cons**: Not suitable for production scale

#### pgvector (PostgreSQL)
- **SQL integration**: Leverage existing PostgreSQL infrastructure
- **Features**: ACID compliance, joins with relational data, mature ecosystem
- **Performance**: ivfflat and HNSW indexing, parallel query processing
- **Best for**: When you already use PostgreSQL, need ACID compliance
- **Cons**: Requires PostgreSQL expertise, less specialized than purpose-built DBs

#### Index Tuning (applies across databases)

Product choice matters less than index parameters. The three families:

| Index family | Key parameters | Effect of raising | Tradeoff |
|---|---|---|---|
| **HNSW** (graph) | `M` (links per node, typical 8-64), `ef_construction` (build-time beam, typical 64-512), `ef_search` (query-time beam, typical 40-400) | Higher recall, higher latency and memory | Best recall/latency curve; slowest builds; memory-heavy (`M` drives RAM) |
| **IVF** (clustering) | `nlist` (number of clusters, rule of thumb ~`sqrt(N)` to `4*sqrt(N)`), `nprobe` (clusters searched per query, typical 1-10% of `nlist`) | Higher recall, linearly higher latency with `nprobe` | Fast builds, lower memory than HNSW; recall degrades if data drifts from training distribution; needs retraining after large ingests |
| **Quantization** (PQ/SQ, composable with HNSW/IVF) | PQ: subvector count and bits per code; SQ: int8/fp16 | Smaller index (4-64x compression), slight recall loss | PQ suits >10M vectors on constrained RAM; SQ (int8) is the low-risk default (~4x compression, ~1-2% recall loss); always re-rank quantized candidates against full-precision vectors when quality matters |

Tuning procedure: fix a recall target (e.g. recall@10 >= 0.95 vs. exact search on a sample), then binary-search the cheapest `ef_search`/`nprobe` that meets it. Measure — do not copy defaults.

### 4. Retrieval Strategies

#### Dense Retrieval
- **Semantic similarity**: Using embedding cosine similarity
- **Advantages**: Captures semantic meaning, handles paraphrasing well
- **Limitations**: May miss exact keyword matches, requires good embeddings
- **Implementation**: Vector similarity search with k-NN or ANN algorithms

#### Sparse Retrieval
- **Keyword-based**: TF-IDF, BM25, Elasticsearch
- **Advantages**: Exact keyword matching, interpretable results
- **Limitations**: Misses semantic similarity, vulnerable to vocabulary mismatch
- **Implementation**: Inverted indexes, term frequency analysis

#### Hybrid Retrieval
- **Combination approach**: Dense + sparse retrieval with score fusion
- **Fusion strategies**: Reciprocal Rank Fusion (RRF), weighted combination
- **Benefits**: Combines semantic understanding with exact matching
- **Complexity**: Requires tuning fusion weights, more complex infrastructure
- **Boundary note**: see also `hybrid-rag-memory` for hybrid retrieval combined with agent memory backends; this skill owns retrieval pipeline design, that skill owns memory architecture.

#### Reranking
- **Two-stage approach**: Initial retrieval (top 50-150 candidates) followed by reranking to a final top 3-10
- **Concrete reranker options** (verify current versions against provider docs):
  - *Hosted cross-encoders*: Cohere Rerank (current v3.x family), Voyage rerank, Jina Reranker — one API call per query over the candidate set
  - *Self-hosted cross-encoders*: `BAAI/bge-reranker-v2-m3` (multilingual, strong open-weights default), `mixedbread-ai/mxbai-rerank` family, classic `cross-encoder/ms-marco-MiniLM` for CPU-only budgets
  - *LLM-as-reranker*: listwise prompting with a utility-tier model — highest quality ceiling, highest latency/cost, use only when cross-encoders plateau
- **Cost/latency reality**: reranking 100 candidates adds roughly 50-300 ms (self-hosted GPU) to 200-600 ms (hosted API) per query, and hosted rerankers bill per query-document pair or per search unit
- **When reranking pays** (decision rule): first-stage recall@50 is high but precision@5 is low — i.e., the right answer is *retrieved but buried*. If recall@50 is low, fix chunking/embeddings/hybrid first; a reranker cannot recover documents that were never retrieved
- **Tradeoff**: Additional latency and cost per query; mitigate by reranking only when the first-stage score margin is ambiguous

### 5. Query Transformation Techniques

#### HyDE (Hypothetical Document Embeddings)
- **Approach**: Generate hypothetical answer, embed answer instead of query
- **Benefits**: Improves retrieval by matching document style rather than query style
- **Implementation**: Use LLM to generate hypothetical document, embed that
- **Use cases**: When queries and documents have different styles

#### Multi-Query Generation
- **Approach**: Generate multiple query variations, retrieve for each, merge results
- **Benefits**: Increases recall, handles query ambiguity
- **Implementation**: LLM generates 3-5 query variations, deduplicate results
- **Considerations**: Higher cost and latency due to multiple retrievals

#### Step-Back Prompting
- **Approach**: Generate broader, more general version of specific query
- **Benefits**: Retrieves more general context that helps answer specific questions
- **Implementation**: Transform "What is the capital of France?" to "What are European capitals?"
- **Use cases**: When specific questions need general context

### 6. Context Window Optimization

#### Dynamic Context Assembly
- **Relevance-based ordering**: Most relevant chunks first
- **Diversity optimization**: Avoid redundant information
- **Token budget management**: Fit within model context limits
- **Hierarchical inclusion**: Include summaries before detailed chunks

#### Context Compression
- **Summarization**: Compress less relevant chunks while preserving key information
- **Key information extraction**: Extract only relevant facts/entities
- **Template-based compression**: Use structured formats to reduce token usage
- **Selective inclusion**: Include only chunks above relevance threshold

### 7. Evaluation Frameworks

#### Faithfulness Metrics
- **Definition**: How well generated answers are grounded in retrieved context
- **Measurement**: Fact verification against source documents
- **Implementation**: NLI models to check entailment between answer and context
- **Threshold**: >90% for production systems

#### Relevance Metrics
- **Context relevance**: How relevant retrieved chunks are to the query
- **Answer relevance**: How well the answer addresses the original question
- **Measurement**: Embedding similarity, human evaluation, LLM-as-judge
- **Targets**: Context relevance >0.8, Answer relevance >0.85

#### Context Precision & Recall
- **Precision@K**: Percentage of top-K results that are relevant
- **Recall@K**: Percentage of relevant documents found in top-K results
- **Mean Reciprocal Rank (MRR)**: Average of reciprocal ranks of first relevant result
- **NDCG@K**: Normalized Discounted Cumulative Gain at K

#### End-to-End Metrics
- **RAGAS**: Comprehensive RAG evaluation framework
- **Correctness**: Factual accuracy of generated answers
- **Completeness**: Coverage of all relevant aspects
- **Consistency**: Consistency across multiple runs with same query

### 8. Production Patterns

#### Caching Strategies
- **Query-level caching**: Cache results for identical queries
- **Semantic caching**: Cache for semantically similar queries
- **Chunk-level caching**: Cache embedding computations
- **Multi-level caching**: Redis for hot queries, disk for warm queries

#### Streaming Retrieval
- **Progressive loading**: Stream results as they become available
- **Incremental generation**: Generate answers while still retrieving
- **Real-time updates**: Handle document updates without full reprocessing
- **Connection management**: Handle client disconnections gracefully

#### Fallback Mechanisms
- **Graceful degradation**: Fallback to simpler retrieval if primary fails
- **Cache fallbacks**: Serve stale results when retrieval is unavailable
- **Alternative sources**: Multiple vector databases for redundancy
- **Error handling**: Comprehensive error recovery and user communication

### 9. Cost Optimization

> Boundary: this section covers cost levers *inside the retrieval pipeline* (embedding, indexing, retrieval-time query handling). For LLM-call cost engineering — prompt caching mechanics, model routing, batch APIs, token budgets — see also `llm-cost-optimizer`.

#### Embedding Cost Management
- **Batch processing**: Batch documents for embedding to reduce API costs
- **Caching strategies**: Cache embeddings to avoid recomputation
- **Model selection**: Balance cost vs quality for embedding models
- **Update optimization**: Only re-embed changed documents

#### Vector Database Optimization
- **Index optimization**: Choose appropriate index types for use case
- **Compression**: Use quantization to reduce storage costs
- **Tiered storage**: Hot/warm/cold data strategies
- **Resource scaling**: Auto-scaling based on query patterns

#### Query Optimization
- **Query routing**: Route simple queries to cheaper methods
- **Result caching**: Avoid repeated expensive retrievals
- **Batch querying**: Process multiple queries together when possible
- **Smart filtering**: Use metadata filters to reduce search space

### 10. Guardrails & Safety

> Boundary: this section lists what a RAG pipeline must account for. For implementation depth — injection defense taxonomies, PII engines, moderation of retrieved content — see also `agentic-guardrails-security`. Retrieved documents are an *indirect injection* vector: treat corpus content as untrusted input, not as instructions.

#### Content Filtering
- **Toxicity detection**: Filter harmful or inappropriate content
- **PII detection**: Identify and handle personally identifiable information
- **Content validation**: Ensure retrieved content meets quality standards
- **Source verification**: Validate document authenticity and reliability

#### Query Safety
- **Injection prevention**: Prevent malicious query injection attacks
- **Rate limiting**: Prevent abuse and ensure fair usage
- **Query validation**: Sanitize and validate user inputs
- **Access controls**: Ensure users can only access authorized content

#### Response Safety
- **Hallucination detection**: Identify when model generates unsupported claims
- **Confidence scoring**: Provide confidence levels for generated responses
- **Source attribution**: Always provide sources for factual claims
- **Uncertainty handling**: Gracefully handle cases where answer is uncertain

## Implementation Best Practices

### Development Workflow
1. **Requirements gathering**: Understand use case, scale, and quality requirements
2. **Data analysis**: Analyze document corpus characteristics
3. **Prototype development**: Build minimal viable RAG pipeline
4. **Chunking optimization**: Test different chunking strategies
5. **Retrieval tuning**: Optimize retrieval parameters and thresholds
6. **Evaluation setup**: Implement comprehensive evaluation metrics
7. **Production deployment**: Scale-ready implementation with monitoring

### Monitoring & Observability

> Boundary: metrics to track for RAG specifically. For the telemetry stack itself (tracing, OTel GenAI conventions, dashboards, alerting) see also `agentic-observability-telemetry`.

- **Query analytics**: Track query patterns and performance
- **Retrieval metrics**: Monitor precision, recall, and latency
- **Generation quality**: Track faithfulness and relevance scores
- **System health**: Monitor database performance and availability
- **Cost tracking**: Monitor embedding and vector database costs

### Maintenance & Updates
- **Document refresh**: Handle new documents and updates
- **Index maintenance**: Regular vector database optimization
- **Model updates**: Evaluate and migrate to improved models
- **Performance tuning**: Continuous optimization based on usage patterns
- **Security updates**: Regular security assessments and updates

## Common Pitfalls & Solutions

### Poor Chunking Strategy
- **Problem**: Chunks break mid-sentence or lose context
- **Solution**: Use boundary-aware chunking with overlap

### Low Retrieval Precision
- **Problem**: Retrieved chunks are not relevant to query
- **Solution**: Improve embedding model, add reranking, tune similarity threshold

### High Latency
- **Problem**: Slow retrieval and generation
- **Solution**: Optimize vector indexing, implement caching, use faster embedding models

### Inconsistent Quality
- **Problem**: Variable answer quality across different queries
- **Solution**: Implement comprehensive evaluation, add quality scoring, improve fallbacks

### Scalability Issues
- **Problem**: System doesn't scale with increased load
- **Solution**: Implement proper caching, database sharding, and auto-scaling

## Conclusion

Building effective RAG systems requires careful consideration of each component in the pipeline. The key to success is understanding the tradeoffs between different approaches and choosing the right combination of techniques for your specific use case. Start with simple approaches and gradually add sophistication based on evaluation results and production requirements.

This skill provides the foundation for making informed decisions throughout the RAG development lifecycle, from initial design to production deployment and ongoing maintenance.
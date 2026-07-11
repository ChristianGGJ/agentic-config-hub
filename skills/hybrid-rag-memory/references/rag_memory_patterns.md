# Hybrid RAG & Persistent Session Memory Patterns

This guide defines the advanced design patterns for implementing hybrid retrieval (lexical + vector), Reciprocal Rank Fusion (RRF), and database-backed persistent checkpointers.

---

## 1. Reciprocal Rank Fusion (RRF) & Re-ranking in C#

To combine exact term queries (BM25) with semantic search results, query both in parallel and merge them using RRF.

### RRF Code Pattern (C# / .NET 9):
```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public class SearchResult
{
    public string DocumentId { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
    public double Score { get; set; }
}

public class HybridRetriever
{
    private const double RrfConstant = 60.0; // Standard constant to smooth rank weights

    public List<SearchResult> MergeRrf(List<SearchResult> vectorResults, List<SearchResult> bm25Results)
    {
        var scores = new Dictionary<string, double>();
        var docs = new Dictionary<string, SearchResult>();

        // 1. Process Vector search ranking
        for (int i = 0; i < vectorResults.Count; i++)
        {
            var doc = vectorResults[i];
            double rrfScore = 1.0 / (RrfConstant + (i + 1));
            scores[doc.DocumentId] = rrfScore;
            docs[doc.DocumentId] = doc;
        }

        // 2. Process BM25 search ranking
        for (int i = 0; i < bm25Results.Count; i++)
        {
            var doc = bm25Results[i];
            double rrfScore = 1.0 / (RrfConstant + (i + 1));
            
            if (scores.ContainsKey(doc.DocumentId))
                scores[doc.DocumentId] += rrfScore;
            else
            {
                scores[doc.DocumentId] = rrfScore;
                docs[doc.DocumentId] = doc;
            }
        }

        // 3. Project and Sort by highest RRF score
        return scores.Select(kvp => new SearchResult
        {
            DocumentId = kvp.Key,
            Content = docs[kvp.Key].Content,
            Score = kvp.Value
        })
        .OrderByDescending(r => r.Score)
        .ToList();
    }
}
```

---

## 2. Stateful Database Checkpointers (LangGraph Postgres)

In production, local MemorySavers lose state if the microservice restarts. Configure Postgres or Redis state checkpointers for durability.

### Postgres Checkpointer Setup (Python):
```python
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph

# 1. Initialize PostgreSQL Connection Pool
pool = ConnectionPool(
    conninfo="postgresql://user:password@localhost:5432/agent_state",
    max_size=10
)

# 2. Initialize the Postgres Checkpointer Saver
# This will automatically create state tables if they do not exist
checkpointer = PostgresSaver(pool)
checkpointer.setup()

# 3. Compile graph with persistent saver
# workflow = StateGraph(StateSchema)
# app = workflow.compile(checkpointer=checkpointer)
```

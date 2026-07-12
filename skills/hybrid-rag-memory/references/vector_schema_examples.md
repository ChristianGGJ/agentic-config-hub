# Vector Store Schemas for Agent Memory

Concrete, deployable schemas for the three backend families this skill recommends:
pgvector (self-hosted SQL), Azure AI Search (managed hybrid), and Qdrant (dedicated
vector engine). Every schema includes the tenancy fields required by the isolation
rules in `references/memory_apis.md` section 5. Version assumptions per section.

---

## 1. pgvector (as of pgvector 0.7+, PostgreSQL 15+)

### 1.1 DDL

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE agent_memory (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    TEXT        NOT NULL,
    user_id      TEXT        NOT NULL,
    kind         TEXT        NOT NULL CHECK (kind IN ('semantic','episodic','entity')),
    mem_key      TEXT        NOT NULL,             -- stable key for update-in-place
    text         TEXT        NOT NULL,             -- the memory content (small, atomic)
    metadata     JSONB       NOT NULL DEFAULT '{}',
    source_thread_id TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding    VECTOR(1536) NOT NULL,            -- match your embedding model dims
    -- lexical arm: generated tsvector over the memory text only (not metadata)
    text_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (tenant_id, user_id, mem_key)
);

-- Dense ANN index (default choice: HNSW)
CREATE INDEX agent_memory_embedding_hnsw
    ON agent_memory USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Lexical index
CREATE INDEX agent_memory_tsv_gin ON agent_memory USING gin (text_tsv);

-- Tenancy + housekeeping
CREATE INDEX agent_memory_tenant_user ON agent_memory (tenant_id, user_id);
CREATE INDEX agent_memory_updated     ON agent_memory (updated_at);
```

Distance operators: `<=>` cosine distance, `<->` L2, `<#>` negative inner product.
Use the operator class that matches your query operator (`vector_cosine_ops` above).

### 1.2 HNSW vs IVFFlat vs exact scan

| Index | Build cost | Query recall/speed | Choose when |
|---|---|---|---|
| **None (exact)** | zero | 100% recall; linear scan | < ~50k rows per query scope — exact is fine and simplest |
| **HNSW** | slow build, more RAM | best recall/QPS tradeoff; no training step; fine with incremental inserts | Default for memory workloads (constant small inserts) |
| **IVFFlat** | fast build, less RAM | recall depends on `lists`/`probes`; needs data present at index build (training) | Bulk-loaded, mostly-static corpora |

Calibrated defaults: HNSW `m=16`, `ef_construction=64`; at query time
`SET hnsw.ef_search = 40;` (raise to 100+ if recall is short). IVFFlat: `lists`
approximately `rows/1000` (up to ~1M rows) then `sqrt(rows)`;
`SET ivfflat.probes = lists/20` as a starting point.

### 1.3 Hybrid query with RRF in SQL

```sql
WITH dense AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> $1) AS r
    FROM agent_memory
    WHERE tenant_id = $2 AND user_id = $3
    ORDER BY embedding <=> $1
    LIMIT 20
),
lexical AS (
    SELECT id, ROW_NUMBER() OVER (
        ORDER BY ts_rank_cd(text_tsv, websearch_to_tsquery('english', $4)) DESC) AS r
    FROM agent_memory
    WHERE tenant_id = $2 AND user_id = $3
      AND text_tsv @@ websearch_to_tsquery('english', $4)
    LIMIT 20
)
SELECT m.id, m.text,
       COALESCE(1.0 / (60 + dense.r),   0) +
       COALESCE(1.0 / (60 + lexical.r), 0) AS rrf_score
FROM dense
FULL OUTER JOIN lexical USING (id)
JOIN agent_memory m USING (id)
ORDER BY rrf_score DESC
LIMIT 5;
```

`$1` = query embedding, `$2`/`$3` = tenant/user, `$4` = raw query text. The constant 60
is the standard RRF k (see `references/rag_memory_patterns.md` for tuning).

Note: Postgres full-text is not literally BM25 (`ts_rank_cd` is a coverage-density
rank), but it serves the same lexical-arm role. If you need true BM25 inside Postgres,
extensions exist (e.g. VectorChord-bm25 / pg_search) — **verify availability on your
Postgres distribution** before depending on one.

---

## 2. Azure AI Search (REST API version 2024-07-01 GA)

Azure AI Search gives BM25 + vector + server-side RRF fusion in one managed service —
the lowest-effort hybrid option and the natural pair for Microsoft Agent Framework.

### 2.1 Index definition (JSON)

```json
{
  "name": "agent-memory",
  "fields": [
    { "name": "id",        "type": "Edm.String", "key": true, "filterable": true },
    { "name": "text",      "type": "Edm.String", "searchable": true,
      "analyzer": "en.microsoft" },
    { "name": "tenant_id", "type": "Edm.String", "filterable": true },
    { "name": "user_id",   "type": "Edm.String", "filterable": true },
    { "name": "kind",      "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "mem_key",   "type": "Edm.String", "filterable": true },
    { "name": "updated_at","type": "Edm.DateTimeOffset", "filterable": true,
      "sortable": true },
    { "name": "embedding", "type": "Collection(Edm.Single)",
      "searchable": true, "dimensions": 1536,
      "vectorSearchProfile": "mem-profile" }
  ],
  "vectorSearch": {
    "algorithms": [
      { "name": "mem-hnsw", "kind": "hnsw",
        "hnswParameters": { "m": 4, "efConstruction": 400,
                            "efSearch": 500, "metric": "cosine" } }
    ],
    "profiles": [
      { "name": "mem-profile", "algorithm": "mem-hnsw" }
    ]
  }
}
```

`PUT https://{service}.search.windows.net/indexes/agent-memory?api-version=2024-07-01`.
A `vectorizer` can be attached to the profile for integrated (service-side) embedding —
**verify current vectorizer config against Azure docs** if you want the service to
embed queries for you; the schema above assumes client-side embeddings.

### 2.2 Hybrid query (keyword + vector, fused by RRF server-side)

```json
POST /indexes/agent-memory/docs/search?api-version=2024-07-01
{
  "search": "ticket ABC-1234 printer error",
  "vectorQueries": [
    { "kind": "vector", "vector": [0.011, "..."], "fields": "embedding", "k": 20 }
  ],
  "filter": "tenant_id eq 't1' and user_id eq 'u42'",
  "top": 5
}
```

When both `search` (BM25) and `vectorQueries` are present, the service fuses the two
result sets with RRF automatically. The `filter` clause is the tenancy boundary — it
must be present on every query (enforce in a query-builder helper, not by convention).

---

## 3. Qdrant (as of Qdrant 1.10+, qdrant-client 1.10+)

Qdrant models hybrid natively: named dense + sparse vectors on the same point, with
server-side fusion via the Query API.

### 3.1 Collection config

REST:

```json
PUT /collections/agent_memory
{
  "vectors": {
    "dense": { "size": 1536, "distance": "Cosine" }
  },
  "sparse_vectors": {
    "bm25": { "modifier": "idf" }
  },
  "hnsw_config": { "m": 16, "ef_construct": 128 },
  "on_disk_payload": true
}
```

Python client:

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name="agent_memory",
    vectors_config={
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    },
    sparse_vectors_config={
        "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF),
    },
)

# Tenancy fields must be indexed payload fields
client.create_payload_index(
    "agent_memory", field_name="tenant_id",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
client.create_payload_index(
    "agent_memory", field_name="user_id",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
```

`modifier=IDF` makes Qdrant apply inverse-document-frequency weighting server-side, so
the sparse vector you upload only needs term frequencies — this is the BM25-style
setup. The client's optional fastembed integration can generate those sparse vectors
from text (`models.Document(text=..., model="Qdrant/bm25")`) — **verify the fastembed
model id against current qdrant-client docs** if you use that convenience path.

### 3.2 Hybrid query with server-side RRF

```python
hits = client.query_points(
    collection_name="agent_memory",
    prefetch=[
        models.Prefetch(query=dense_vec, using="dense", limit=20),
        models.Prefetch(
            query=models.SparseVector(indices=sparse_idx, values=sparse_val),
            using="bm25", limit=20,
        ),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    query_filter=models.Filter(must=[
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value="t1")),
        models.FieldCondition(key="user_id",   match=models.MatchValue(value="u42")),
    ]),
    limit=5,
)
```

Both prefetch branches respect `query_filter`, so tenancy holds across arms.

---

## 4. BM25 parameter guidance (the lexical arm)

BM25 has two parameters; the Lucene/Elasticsearch defaults are `k1 = 1.2`, `b = 0.75`.

| Parameter | Controls | Memory-workload guidance |
|---|---|---|
| `k1` (1.2-2.0) | Term-frequency saturation: higher = repeated terms keep adding score | Keep default 1.2; memory entries are short, TF rarely repeats |
| `b` (0-1) | Length normalization: 1 = fully penalize long docs, 0 = ignore length | Memory entries are short and uniform — lower `b` (0.3-0.5) often helps; validate with the eval in `references/rag_memory_patterns.md` section 5 |

**Tokenization beats parameter tuning.** The lexical arm exists mostly for exact
identifiers, and standard analyzers destroy them: "ABC-1234" tokenizes to
["abc", "1234"], version "2.11.3" to ["2", "11", "3"]. Countermeasures:

- Keep a `keyword`/exact sub-field for identifier matching alongside the analyzed
  field (Azure AI Search: a second non-analyzed field; Elasticsearch-style engines:
  `keyword` multi-field).
- Index ONLY the memory `text` field lexically — never metadata blobs or transcripts;
  noisy fields are the top cause of hybrid underperforming pure-dense.
- If IDs follow a known pattern, extract them into a filterable metadata field at
  write time and match them with filters instead of relying on BM25 at all.

---

## 5. Choosing dimensions and quantization

- Match `dims` to the embedding model; several current-generation embedding model
  families support shortening output dimensions (Matryoshka-style truncation) — 512-1024
  dims is usually enough for memory entries and halves storage. Re-validate recall
  after shortening.
- Quantization (Qdrant scalar/binary quantization, pgvector `halfvec`) cuts memory
  2-4x for < 2-3% recall loss on typical setups — worth enabling beyond ~1M vectors,
  unnecessary below.
- Embedding model selection itself is `rag-architect` territory (see that skill);
  from this skill's perspective the only hard requirements are: one model per
  collection (never mix), and record the model name in collection metadata so a model
  upgrade triggers a re-embed migration (a Phase 3 HUMAN GATE operation — index
  rebuilds are Class 2 COSTLY).

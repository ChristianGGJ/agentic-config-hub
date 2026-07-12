# Memory Eviction, Consolidation, and Context Compaction

The load-bearing insight of memory design is counter-intuitive: **more memory is not
better**. Past a point, additional stored context *degrades* the system. As the injected
token set grows, retrieval precision falls -- quadratic attention spreads thin,
mid-context items are lost ("lost in the middle"), and irrelevant-but-similar entries act
as distractors. Chroma's 2025 context-rot study reports that all 18 frontier models
tested lose recall as context length grows; Anthropic's "Effective context engineering
for AI agents" (Sept 2025) frames the job as curating the *minimal high-signal* token set,
not maximizing recall. So every serious memory system is defined as much by what it
*drops* as by what it stores.

This reference covers the LEARNING/LIFECYCLE layer: how memory is aged, scored, filtered,
summarized, and evicted. The STORAGE layer -- what a memory row looks like, TTL sweeps at
the database level, dedup-on-write, GDPR erasure -- already lives in
`references/memory_apis.md` (section 6) and the eviction-defaults table in `SKILL.md`; do
not re-read those here. Retrieval *mechanics* (reranker selection and tuning, embedding
models, chunking) are owned by the sibling skill `rag-architect`; this file cites them but
does not re-teach them.

---

## 1. Framework track: how real memory systems evict

Version assumptions are stated per row; anything uncertain is marked **verify against
current docs**. Do not treat these member names as frozen -- the memory-native libraries
move fast.

### 1.1 Temporal decay / TTL (auto-expiry)

- **LangGraph / LangMem store TTL** (LangGraph ~0.3.x, LangMem 0.x -- **verify against
  current docs**): the long-term Store supports a `ttl` config (set in `langgraph.json`)
  with `default_ttl` expressed in **minutes** (e.g. `10080` = 7 days) and `refresh_on_read`
  (default `true`), which resets an item's expiry each time it is fetched via `get`/
  `search`. Backends such as MongoDB enforce expiry with a native TTL index, so stale
  memories auto-drop and the store cannot grow without bound. The minutes unit and the
  `refresh_on_read` semantics are the load-bearing facts.
- **Mem0** (arXiv:2504.19413): applies temporal *scoring* to down-rank dated entries
  rather than hard-expiring them, plus optional TTL decay and versioned updates. Its
  routing controller classifies each incoming fact as ADD / UPDATE / DELETE / NOOP against
  the top-k similar existing memories (some configs are effectively ADD-only -- **verify**).

### 1.2 Recency + frequency + importance scoring (read-time selection)

- **Generative Agents** (Park et al., arXiv:2304.03442) rank a memory stream by a weighted
  sum, `score = a_recency*recency + a_importance*importance + a_relevance*relevance` (all
  weights `= 1` in their implementation). Recency is an exponential decay on last-access
  time; importance is an LLM-assigned 1-10 "poignancy" fixed at creation; relevance is
  embedding similarity to the current query. Only the top-scoring memories are injected.
- **Mem0** fuses semantic similarity + BM25 + entity match into one score with an
  *additive* temporal nudge, tuned so semantic relevance always dominates and a highly
  relevant item is never dropped purely for being old.

These are read-time SELECTION functions deciding what enters the finite context window --
i.e. eviction from the *prompt*, not necessarily deletion from the store.

### 1.3 Semantic-relevance filtering (rerank before inject)

Production retrieval is two-stage: a cheap first stage pulls a WIDE candidate set
(top-50-100), then a cross-encoder reranker returns a PRECISION top-5-10 for the prompt.
Options include Cohere Rerank (public model `rerank-v3.5` -- **verify model name against
current docs**), local cross-encoders (BGE, Jina, MiniLM), FlashRank (~15-30 ms), and
Reciprocal Rank Fusion to combine retrievers. The entire point is to inject only the few
task-critical fragments; dumping all 100 causes distractor interference. **Reranker
selection and tuning are owned by `rag-architect`** -- this file only names reranking as
the eviction lever it is.

### 1.4 Summarization / paging (tiered memory)

- **MemGPT / Letta** (arXiv:2310.08560, now the Letta framework) treats the context window
  as RAM over three tiers: main context (fixed-size working memory), recall memory
  (searchable log), and archival memory (vector/DB cold storage). The agent self-pages via
  function calls -- push overflow out ("page out"), `archival_memory_search` to pull back
  in ("page in"), and edit its own core memory. 2025's **sleep-time compute** runs this
  consolidation asynchronously during idle time to keep latency down and quality up.
- **LlamaIndex Memory** (2025 API -- **verify**) implements the same idea concretely: when
  short-term history exceeds `chat_history_token_ratio`, the oldest messages up to
  `token_flush_size` are flushed into long-term `MemoryBlock`s. Each block carries a
  `priority` (`0` = always kept; higher numbers are disabled/evicted first when the
  combined long+short total exceeds the token limit) -- an explicit, tunable eviction
  policy.

### 1.5 Consolidation (dedup / merge / resolve contradictions)

- **LangMem** `create_memory_manager` extracts, consolidates, and prunes redundancies; a
  background manager runs this off the hot path (**verify current SDK surface**).
- **Mem0**'s routing controller resolves conflicts so a correction UPDATEs or DELETEs a
  stale belief instead of appending a duplicate.

Consolidation is the batch eviction operator: dedup + prune-redundancy + delete-superseded
is *how* a memory store forgets, and reflection (compress N raw notes into 1 rule) shrinks
the always-injected footprint.

---

## 2. The eviction policy (8 rules)

A concrete policy any memory-owning system in this hub applies. Rules 1-4 are runtime
levers; rules 5-8 are the curation discipline. The keep/evict *score* in rule 6 is what
`scripts/memory_evictor.py` computes deterministically.

1. **Fixed budget first.** Declare a hard capacity per tier before writing anything:
   a token or item cap on the injected working set, a count cap per episodic namespace
   (see `SKILL.md` defaults). The budget is the fixed "context size" the whole policy
   defends -- eviction is what keeps you inside it.
2. **TTL / review window.** Every entry carries `created`/`updated` (and, for durable
   rules, a `last_reviewed` date). Age past the window makes an entry an eviction
   *candidate*, not an automatic delete.
3. **Recency + frequency decay.** Rank entries by an exponential recency decay on
   last-used time combined with hit frequency; never-hit + old entries sink to the bottom.
4. **Relevance rerank before injection.** Retrieve wide, rerank, inject only the top-k
   (`rag-architect` owns the reranker). A fragment that never matches the query is evicted
   from *that prompt* without being deleted from the store.
5. **Single source of truth.** Each fact lives in exactly one place; a fact repeated in two
   entries is a future contradiction -- consolidate to one and evict the copy.
6. **Composite keep/evict score.** Combine recency, frequency, relevance, and review-age
   into one rankable signal; the lowest-scoring, unpinned entries are evicted first. Pin
   entries that must never be dropped (safety rules, canonical facts).
7. **Promotion frees space.** When a recurring memory graduates into a durable rule
   (procedural memory), DELETE the original from the hot buffer -- promotion is
   eviction-with-retention, not duplication.
8. **Contradiction pruning + retention.** Consolidation REMOVES superseded/conflicting
   entries rather than appending; nothing is truly lost because the prior version is
   recoverable (store versioning at runtime; git history in the static hub).

---

## 3. Static track: eviction in a git-versioned prompt library

The hub has no runtime, no vector DB, and no model calls in its stdlib scripts. Yet it
runs a manual, git-native version of every framework eviction lever above -- the job is to
name them as one policy. In this library, "context noise" = **prompt bloat**: CLAUDE.md,
context packs, and agent prompts that accumulate overlapping, stale, or contradictory
guidance until instruction adherence drops (self-improving-agent's own memory model notes
"adherence decreases with length"). The mapping:

| Framework lever (section 1) | Static hub analog |
|---|---|
| Store TTL / `refresh_on_read` | **Review-TTL**: a `last_reviewed` date on context/rules files; a file unreviewed past a threshold (e.g. 2 quarters) is flagged prune-or-re-verify. "Refresh on read" = a maintainer bumping the date when they re-confirm a rule while using it. Expiry itself is a human-gated delete. |
| Recency + frequency decay | **git-native signal**: git last-modified date is recency; how often a rule is cited/opened is frequency. Old + never-cited fragments are top eviction candidates. |
| Relevance rerank (top-k) | **Path-scoping**: `.claude/rules/` `paths:` frontmatter admits a rule only when matching files are open -- a zero-cost, model-free relevance filter. Skill `description` triggering is the coarse first stage; a tight, disambiguated description is the "reranker" that prevents mis-firing. Never load globally what can be scoped. |
| LlamaIndex `priority` (0 = always keep) | **Priority tiers**: enforced CLAUDE.md rule > `.claude/rules/` > MEMORY.md note > session. Universal rules are priority-0 (always loaded); scoped rules page in only on match. |
| MemGPT core -> recall -> archival paging | **Tiered files**: CLAUDE.md first-200-lines / enforced rules = main context (loaded every session); MEMORY.md overflow topic files + `references/` = archival (loaded on demand); path-scoped rules = paged in when matching files open. |
| Sleep-time / background consolidation | **The consolidate pass**: `anthropic-skills:consolidate-memory` (merge duplicates, fix stale facts, prune the index) and self-improving-agent's `/si:review` are the manual LangMem-consolidator, run out of the hot path. |
| Mem0 UPDATE/DELETE conflict resolution | **Promote-and-prune**: `/si:promote` graduates a proven MEMORY.md note into a compact CLAUDE.md rule and DELETES the original -- exactly the paging + dedup move, human-gated. |

### 3.1 Hard caps already in the canon

- **MEMORY.md 200-line load cap.** Content past line 200 is simply not loaded -- de facto
  eviction. Topic files (`debugging.md`, `patterns.md`) are the paging target, exactly
  like LlamaIndex flush-to-block. (self-improving-agent, `reference/memory-architecture.md`.)
- **CLAUDE.md ~150-line soft target / 200 hard.** Context-window pressure made explicit;
  the fix is promote-and-prune, not append.
- These are *file-specific* today; the composite keep/evict score generalizes them to any
  context pack, skill, or agent prompt.

### 3.2 Pruning stale boundaries and keeping prompts lean

- A `boundaries.md` prohibition can go stale (a `migrations/` freeze ends, a team boundary
  moves). Without a review date, prohibitions accumulate and can never be safely expired.
  Give each a review window (rule 2) so staleness becomes *visible*, then human-gate the
  delete. Provenance and expiry of prohibitions is a governance concern -- versioning and
  one-command rollback of an expired rule are owned by `prompt-governance`.
- Lean agent prompts ARE eviction: an agent role prompt that accretes overlapping
  instructions is the config-space equivalent of an over-full context window. Keep object-
  level prompts minimal; push detail to on-demand references.

### 3.3 The composite keep/evict score and rerank-via-path-scoping

A static library's closest thing to a rankable keep/evict signal, computed by a reviewer
or a small stdlib script over frontmatter/metadata -- never an embedding model:

- **Recency** = git last-modified / `last_reviewed` date.
- **Frequency** = how often the fragment is cited or its scope matches.
- **Review-TTL** = age since `last_reviewed` against the threshold.
- **Pinned** = an explicit protection flag for entries that must never be evicted.

A fragment that is simultaneously stale, never-referenced, and low-priority is the top
eviction candidate -- the static analog of a low composite retrieval score.
`scripts/memory_evictor.py` computes the deterministic axes (age/recency/frequency/pinned)
over a JSONL memory store. **Semantic relevance is deliberately out of scope for that
tool** (it needs embeddings, which the hub forbids in portable scripts); relevance
filtering stays a runtime concern owned by `rag-architect` and, in the static library, is
approximated by path-scoping and description hygiene as above.

---

## 4. Eviction as a loop (safety)

Any recurring eviction/consolidation job is a loop and MUST declare the six canonical exit
conditions before iteration 1 -- loop theory is owned by
`agentic-system-architect/references/loop_engineering_patterns.md`; do not restate it.
The memory-specific defaults are tabulated in `SKILL.md` (Hub Canon Integration): e.g. a
write-delete-write on one key over a window of 4 is `oscillation` -> freeze the key and
escalate; a user-data erasure request is an `escalation_trigger` -> stop and surface to a
human. A consolidation pass that keeps re-summarizing the same content is a `no_progress`
plateau. Critically: an eviction pass NEVER deletes a pinned safety rule or a boundary
autonomously -- crystallized prohibitions are removed only through the Phase-3 HUMAN GATE.

---

## 5. Cross-references

- `references/memory_apis.md` section 6 -- runtime TTL sweeps, count caps, GDPR erasure
  (the storage layer; not duplicated here).
- `SKILL.md` -- eviction/retention defaults table and the six memory-loop exit conditions.
- `references/procedural_memory_skill_registries.md` -- promotion as eviction-with-
  retention for the skills registry.
- `rag-architect` -- reranker selection, embedding models, chunking (retrieval mechanics).
- `agentic-system-architect` -- loop_engineering_patterns.md (exit conditions, loop safety).
- `self-improving-agent` -- MEMORY.md tiering, `/si:review` consolidation, `/si:promote`.
- `prompt-governance` -- versioning, rollback, and audit trail for expiring stale rules.
- `anthropic-skills:consolidate-memory` -- the merge-duplicates / prune-index pass.

# Procedural Memory: Self-Authored Skill and Tool Registries

Semantic memory is *what the agent knows*; procedural memory is *what the agent knows how
to do* -- and the frontier form is an agent that **creates, stores, and reuses new
skills/tools** it did not start with. This is the memory type that changes future behavior
by expanding capability, not just recall. This reference covers the framework pattern and
its precise, load-bearing analog in this hub: **the `skills/` directory is itself a
governed procedural-memory registry.**

Scope: this file owns the procedural-memory *taxonomy and lifecycle* (propose -> verify ->
register -> retrieve). Storage schemas and embedding retrieval are owned by `rag-architect`
and the storage sections of `references/memory_apis.md`; the crystallize-a-pattern-into-a-
skill workflow is owned by `self-improving-agent` (`/si:extract`); prompt/config
versioning and rollback by `prompt-governance`. This file cites them by name.

---

## 1. Framework track: the skill-library loop

### 1.1 Voyager -- the canonical procedural-memory agent

Voyager (Wang et al., arXiv:2305.16291) is the reference implementation of a self-growing
skill library. Its loop:

1. **Propose** -- the agent writes an executable program (a skill) to accomplish a task.
2. **Verify** -- it self-checks the program against environment feedback and execution
   errors, iterating until the program runs and achieves the goal (verification is the
   gate, not the LLM's opinion of its own code).
3. **Register** -- each *accepted* program is stored in a skill library, keyed by an
   embedding of an LLM-generated natural-language description of what the skill does
   (GPT-3.5 in the paper).
4. **Retrieve** -- on a new task the agent retrieves the **top-5** semantically similar
   skills by description embedding and composes them into new code.

The paper's claim is that skills are "temporally extended, interpretable, and
compositional" and that this library "alleviates catastrophic forgetting" -- capability,
once verified and registered, is not lost.

### 1.2 The storage + retrieval half, in current frameworks

Modern frameworks reproduce the register/retrieve half generically (all **verify against
current docs**):

- **LangGraph** `BaseStore` exposes `put(namespace, key, value)` / `search(namespace,
  query=...)` (plus async `aput`/`asearch`), with a vector index config
  `index={"dims", "embed", "fields"}` on `InMemoryStore`/`PostgresStore`. Tools, skills,
  and memories are registered dynamically and retrieved by similarity -- the same API used
  for long-term memory in `references/memory_apis.md`.
- **LlamaIndex** registers a capability as a `FunctionTool`; agents pick tools at runtime.
- **Letta / MemGPT** supports runtime tool creation, and its editable memory blocks are
  themselves procedural (the agent rewrites its own persona/behavior via
  `core_memory_append` / `core_memory_replace`).
- **LangMem** `create_manage_memory_tool` lets an agent update its own instruction memory
  -- procedural memory as self-editing system-prompt content.

### 1.3 Generative Agents -- reflection into procedure

Generative Agents (Park et al., arXiv:2304.03442) periodically **reflect** raw
observations into higher-level insights written back to the memory stream -- the
consolidation step that turns episodic experience into reusable behavioral guidance. It is
the conceptual bridge from "what happened" to "what to do next time."

**The defining property of all of the above: registration is AUTONOMOUS.** The agent
verifies against the environment and writes to its own library in the hot loop, with no
human in the path. That is exactly the property the hub inverts.

---

## 2. Static track: `skills/` as a governed procedural-memory registry

The key insight for this hub: **adding a skill is registering a new capability
(Voyager-style), but human-gated, audited, and git-versioned.** The four stages of the
Voyager loop all have exact static analogs -- with the verification stage strengthened and
the registration stage placed behind the HUMAN GATE.

| Voyager stage | Runtime (autonomous) | Hub (gated, deterministic) |
|---|---|---|
| **Propose** | LLM writes a program in the loop | An author (human or Claude) writes `SKILL.md` + stdlib scripts under the 5-Phase Protocol (Discovery -> Manifest) |
| **Verify** | Self-check vs environment feedback + execution errors | Deterministic audit gates run BEFORE registration: `skill-tester` (its `skill_validator`, `quality_scorer`, `script_tester`), `skill-security-auditor`, the `plugin-audit` 8-phase command, and `loop_auditor.py` for any agent config (>= 90 HARDENED). Static checks replace runtime env feedback. |
| **Register** | Write to the skill library in-loop | The Phase-3 HUMAN GATE approves, then a git commit/merge adds the skill; the `plugin.json` + `.claude-plugin/marketplace.json` entry is the registry index |
| **Retrieve** | Top-5 by description-embedding similarity | No vector DB (hub rule): the harness matches the `SKILL.md` `description` frontmatter against the incoming task to trigger the skill. The **description IS the retrieval index.** |

### 2.1 The description is the retrieval index

Because there is no embedding store, the `SKILL.md` `description` field does the job the
description-embedding does in Voyager: it decides whether this capability is retrieved for
a given task. Consequences:

- Writing a tight, disambiguated `description` (starting "Use when ...", per hub
  convention) is the equivalent of maintaining a clean embedding space.
- Two skills whose descriptions overlap enough to co-fire are the static equivalent of a
  bad/ambiguous embedding neighborhood -- the retrieval-ambiguity failure that produces
  mis-triggering. The countermeasure is the atomicity rule (one capability per skill, zero
  cross-skill dependencies) plus description-space hygiene: overlapping descriptions must
  be merged, or one skill evicted / cross-referenced ("see also <skill>"). The hub even
  documents "NOT for X, use Y" inside descriptions -- that is manual rerank tuning of the
  retrieval index.

### 2.2 Why gated registration, not auto-registration

Runtime auto-registration (Voyager, Letta) optimizes for speed of capability growth and
accepts the risk that an unverified or overlapping skill enters the library. The hub
optimizes for **safety and durability of a shared, versioned artifact**:

- Verification is deterministic and reproducible (audit scores, security scan) rather than
  a single environment rollout, so a registered skill meets a fixed quality bar.
- Registration is a reviewed git diff, so every capability addition is attributable,
  reversible (git history / registry rollback -- owned by `prompt-governance`), and
  visible to the whole team.
- **Safety boundary (non-negotiable):** an agent may PROPOSE a new skill, but it must
  never autonomously register one -- and it must NEVER register or self-edit a capability
  that rewrites its own guardrails/boundaries. Object-level capabilities (task skills) go
  through the gated loop; meta-level config (audit rubrics, exit-condition definitions,
  promotion predicates, boundaries) is changed only by a separate, explicitly-flagged human
  governance action. This is the PromptBreeder self-referential-mutation warning applied to
  the registry: capability growth is welcome; unbounded self-modification of the rules that
  bound it is not.

### 2.3 Extraction: crystallizing a pattern into a skill

The hub's live "propose a skill" path is `self-improving-agent`'s `/si:extract`, which
crystallizes a proven repeated pattern into a whole new skill package -- the static analog
of Voyager accepting a program into its library after it has proven useful. That workflow
is owned by `self-improving-agent`; this file only names it as the registration entry
point. The "Proven" bar (a pattern seen across 2+ sessions) is the static substitute for
Voyager's environment verification.

---

## 3. Eviction of procedural artifacts

A capability registry that accretes overlapping skills produces retrieval ambiguity -- the
Voyager library-bloat failure. Eviction of the hub's OWN procedural memory (skills,
workflows, context-pack entries) is a soft, git-native operation: a deprecation header, an
archive directory, or demotion (CLAUDE.md rule -> `.claude/rules/` -> removed), always as a
human-gated commit and fully reversible via git history. Overlapping or superseded skills
are merged or archived, never silently deleted. The general keep/evict policy, the
composite score, and the review-TTL mechanism live in
`references/memory_eviction_and_consolidation.md`; procedural artifacts are just one class
of entry that policy governs.

The concrete deprecation sequence for a stale skill:

1. **Flag** -- the review-TTL check (or a maintainer) marks the skill unreviewed past the
   window, or a newer skill's description now covers its scope.
2. **Confirm at the HUMAN GATE** -- deprecation is a Phase-3 decision, never automatic;
   removing a capability the team relies on is consequential.
3. **Demote or archive** -- add a deprecation header pointing to the replacement ("see also
   <skill>"), or move the folder to an archive path; drop its `marketplace.json` entry so
   it stops being an active retrieval target.
4. **Retain** -- the git history keeps the evicted skill fully recoverable; rollback is
   owned by `prompt-governance`.

Because the description is the retrieval index (section 2.1), dropping the registry entry
is the static equivalent of removing an embedding from the vector store: the capability is
evicted from every future task match without being destroyed.

---

## 4. Cross-references

- `references/memory_eviction_and_consolidation.md` -- keep/evict policy, review-TTL,
  promotion-as-eviction (skills are one governed entry class).
- `references/memory_apis.md` -- LangGraph Store `put`/`get`/`search` and index config
  (the runtime registration/retrieval surface).
- `self-improving-agent` -- `/si:extract` (crystallize a pattern into a skill), `/si:promote`
  (graduate a note into a durable rule); the procedural-memory promotion engine.
- `prompt-governance` -- registry index, versioning, promotion gate, one-command rollback
  of a registered capability.
- `rag-architect` -- embedding retrieval mechanics (out of scope for the hub's own scripts).
- `agentic-system-architect` -- `loop_auditor.py` (the >= 90 HARDENED verification gate for
  agent configs) and loop safety.
- `autoresearch-agent` -- the autonomous propose-eval experiment harness (out of scope
  here; procedural registration in this hub is gated, not autonomous).

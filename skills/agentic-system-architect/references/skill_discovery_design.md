# Skill Discovery & Design

The skills-pillar counterpart to agent role discovery. Use this when the ecosystem
needs a **new skill** and you must research, scope, and design it before writing a
single file. The goal is an atomic, production-grade, non-redundant capability — not a
generic tutorial dump.

> Ownership: this reference is the *discovery/design methodology*. The skills-pillar
> theory (what a skill is, atomicity, anti-duplication, knowledge flow) lives in
> `four_pillar_ecosystem.md`; authoring conventions live in the repo's `skills/CLAUDE.md`;
> validation/scoring lives in the `skill-tester` skill. This file does not repeat them —
> it drives the research that feeds them.

## 1. Atomic Delimitation (Single Responsibility)

A skill does **exactly one thing well**. The research strategy must force atomization,
not accumulate breadth.

- **Name test:** the slug names one capability. `dotnet-efcore-migrations` and
  `blazor-state-management` are skills; `dotnet-development` is a domain, not a skill.
  If the name needs "and" (or an umbrella noun like "development"/"toolkit"), it is two
  or more skills — split it. (This is the atomicity rule from `four_pillar_ecosystem.md`,
  applied at discovery time.)
- **Query for subcomponents, not quickstarts:** search for the specific design pattern,
  sub-API, or failure surface — `"EF Core migrations idempotent script production"`,
  not `"getting started with .NET"`. Quickstart tutorials teach breadth; you need one
  narrow, deep capability.
- **Decomposition heuristic:** if the candidate skill has more than one distinct
  input→output transformation, or spans more than one tool's surface, it is not atomic.
  Carve it at the transformation boundary.

## 2. Canonical Syntax & Standards Extraction

Extract the **real, version-pinned** surface from authoritative sources — never
paraphrase from memory or marketing posts.

- **Sources, in priority order:** official framework docs and versioned release notes;
  the framework's own source repository; the package registry (NuGet, npm, PyPI) for
  the exact version; then reputable reference material. Marketing blogs are last resort
  and only for orientation.
- **Pin the version:** capture the syntax for the *required* version and state it
  (e.g. ".NET 10", "LangGraph v0.2/1.x"). APIs churn; an unversioned example rots. Mark
  anything you could not confirm against a primary source as **"verify against current
  docs."**
- **Capture production patterns, not toy snippets:** the recommended structured pattern,
  dependency-injection wiring, error handling, and configuration — the way the code is
  written in production, not the minimal "hello world".
- **Anti-invention rule (hub canon):** if you are not certain a class/method/flag exists
  in the target version, describe the pattern and flag it for verification — do not
  fabricate an API. Framework depth itself is owned by the framework skills
  (`langgraph-state-design`, `crewai-role-engineering`, `microsoft-agent-framework`);
  cross-reference them rather than duplicating their surface.

## 3. Defensive Anti-Pattern Mapping (the Loop's Fuel)

**The most important step for Loop Engineering.** A skill's `Anti-Patterns` section is
the ammunition its QA/critic gives the auditor — the more precise it is, the more
paranoid and effective the review.

- **Mine failures proactively:** search error threads, GitHub issues (sort by "most
  commented"/"most reacted"), Stack Overflow, and the technology's own *Troubleshooting*
  section. Answer one question explicitly: **"What are the 3 most common ways developers
  (or AIs) break this technology?"**
- **Write them as detectable anti-patterns:** each becomes a `symptom → root cause → fix`
  row in the new skill's Anti-Patterns section, phrased so a reviewer can match it
  against real code (not vague warnings).
- **Wire into the loop:** these anti-patterns are consumed by the evaluator-optimizer /
  critique loop — see `self_reflection_critique_loops.md` and the `adversarial-reviewer`
  skill. A recurring anti-pattern that keeps surfacing across audits should graduate into
  an enforced rule via the Reflexion bridge (`self-improving-agent`: audit finding →
  `/si:promote` → `CLAUDE.md`/rules), so the same break is prevented at authoring time.
- **Rule:** a skill that ships without a mined, technology-specific Anti-Patterns section
  is incomplete — generic "handle errors gracefully" advice is not anti-pattern mapping.

## 4. Interface & Interoperability

A skill must be **consumable by multiple agents**. Discovery must make its contract
explicit so any agent can invoke it.

- **Inputs:** what the skill needs to run — data schemas, file paths, tokens/credentials
  (referenced, never inlined), config. State types and required-vs-optional.
- **Native tooling:** which CLI commands, SDKs, or APIs the skill activates to do its
  work (e.g. `dotnet ef migrations add`, a specific `npm` script). List the exact
  invocations the skill wraps.
- **Outputs / hand-off shape:** what it emits and in what format, so a downstream agent
  or workflow step can consume it deterministically (align with the handoff-contract
  fields in `agent-workflow-designer`).
- **Consumability check:** if only the authoring agent could use it, the interface is
  under-specified. Write the contract for a stranger.

## 5. Tech-Debt Consistency (Anti-Duplication)

Before writing any new file, prove the skill is not redundant.

- **Read the registry first:** read the current `skills/` folder (this repo has no
  separate `shared-skills/` directory — `skills/` plus the flagship references in
  `agentic-system-architect/references/` *are* the shared layer). For each existing skill,
  read its `SKILL.md` description.
- **The combine-or-extend test:** ask — *can this capability be delivered by combining
  two existing skills, or by extending one existing skill with a small patch?* If yes,
  **do not create a new file.** Compose or extend instead; a new file is justified only
  by a genuine, uncovered operational gap.
- **Run the deterministic check:** `scripts/skill_overlap_check.py` scans `skills/` and
  reports capability overlap; run it with `--against "<proposed skill description>"`
  before creating, and treat a high-overlap hit as a stop signal to reconsider.
- **Why it matters:** duplicate skills fracture maintenance and confuse routing — the
  opposite of the atomic, self-contained registry the four-pillar model depends on.

## Hub Canon Integration

- **Atomicity & anti-duplication** are defined once in `four_pillar_ecosystem.md`; this
  file applies them at *discovery* time and adds the research method around them.
- **Anti-pattern mining (§3)** is the input to the evaluator-optimizer loop and the
  Reflexion bridge — precise anti-patterns raise the auditor's paranoia and, when
  recurring, become enforced rules.
- **Real-API discipline (§2)** mirrors the whole hub's anti-invention rule; framework
  depth is delegated to the framework skills, not duplicated here.
- **Deliverable gate:** a discovered skill is ready to author only when it has an atomic
  scope (§1), version-pinned canonical syntax (§2), a mined Anti-Patterns section (§3),
  an explicit interface (§4), and a passing anti-duplication check (§5).

## References

| File | Relationship |
|------|--------------|
| `four_pillar_ecosystem.md` | Owns skills-pillar theory: atomicity, anti-duplication, knowledge flow (this file applies it) |
| `self_reflection_critique_loops.md` | The loop that consumes the mined anti-patterns |
| `scripts/skill_overlap_check.py` | Deterministic anti-duplication check for §5 |
| repo `skills/CLAUDE.md` | Authoring conventions once a skill is designed |
| `skill-tester` skill | Validates/scores the skill after authoring |

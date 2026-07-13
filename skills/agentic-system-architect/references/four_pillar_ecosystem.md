# The Four-Pillar Agentic Configuration Ecosystem

An agentic configuration ecosystem is the complete, versioned set of files that governs how
autonomous agents behave inside a project. Instead of scattering prompts, rules, and runbooks
across wikis and chat threads, the ecosystem organizes everything into four pillars with strict
responsibilities: `context/`, `skills/`, `agents/`, and `workflows/`. Each pillar has a single
job, a single direction of knowledge flow, and hard rules about what it must never contain.

This reference defines each pillar, the knowledge flow between them, atomicity and
anti-duplication rules, the canonical directory layout produced by `ecosystem_scaffolder.py`,
naming and versioning conventions, the two operating modes (GENERAL and CONTEXTUALIZED), a
migration path for existing repositories, and a review checklist.

The four pillars exist to make three advanced disciplines enforceable in configuration, not
just in intent: Loop Engineering (self-reflection, evaluation and error-mitigation loops with
explicit exit conditions and counters), ReAct reasoning patterns (Thought -> Action ->
Observation cycles), and Defensive Human-in-the-Loop (HITL) flow control via the 5-Phase
Protocol with hard human approval gates.

---

## The Four Pillars

### Pillar 1: context/ — Project Ground Truth

**What it holds.** Immutable-by-agents project knowledge: architecture rules, service
boundaries, canonical names, data contracts, and the project glossary. Every agent consumes
`context/` read-only at the start of Phase 1 (DISCOVERY). Context files are the single source
of truth that keeps ten agents from inventing ten different names for the same service.

**What it must NEVER hold.** Instructions, role prompts, task lists, tool invocations, or
anything an agent is supposed to *do*. Context describes what *is*, never what to do. It also
must never hold secrets, credentials, or environment-specific values (URLs with tokens, API
keys) — context files are committed to version control and read by every agent.

**File format.** Markdown files with the component frontmatter:

```yaml
---
name: "architecture"
version: "1.2.0"
description: "Service topology, layering rules, and dependency direction for the platform"
type: "context"
---
```

**Concrete examples.**

1. `context/architecture.md` — declares "the API layer never imports from the persistence
   layer directly; all access goes through the repository interfaces in `core/repos/`", lists
   the canonical service names (`billing-svc`, `ingest-svc`), and pins the dependency
   direction diagram.
2. `context/boundaries.md` — declares allowed paths ("agents may modify `src/` and `tests/`"),
   forbidden paths ("never touch `migrations/`, `infra/`, or `.github/` without a HUMAN GATE"),
   and out-of-scope systems ("the legacy `reports/` module is frozen; changes escalate to the
   platform lead").

### Pillar 2: skills/ — Atomic Reusable Capabilities

**What it holds.** One capability per skill: a self-contained package with a `SKILL.md`,
optional deterministic scripts, and optional templates. Skills have zero dependencies on other
skills. They prefer deterministic tools (scripts, checklists, rubrics) over LLM calls, so that
the same input always produces the same output.

**What it must NEVER hold.** Role identity ("you are a senior reviewer"), orchestration logic
(which skill runs after which), loop controls, HITL gates, or references to other skills. A
skill that imports another skill is a coupling defect; a skill that defines a persona is an
agent in disguise.

**File format.** Each skill lives in its own folder with a `SKILL.md` carrying the component
frontmatter:

```yaml
---
name: "changelog-writer"
version: "1.0.0"
description: "Generate a conventional-commit changelog section from a git log range"
type: "skill"
---
```

**Concrete examples.**

1. `skills/sql-migration-review/SKILL.md` — a deterministic checklist plus a script that flags
   destructive statements (`DROP`, `TRUNCATE`, column type narrowing) in a migration file and
   emits a risk table. No persona, no ordering logic, no dependency on any other skill.
2. `skills/api-contract-diff/SKILL.md` — compares two OpenAPI specs and reports breaking
   changes (removed endpoints, narrowed enums, new required fields) as a machine-readable
   list. Any agent that needs contract diffing references this skill by path.

### Pillar 3: agents/ — Role Prompts That Orchestrate

**What it holds.** Role prompts that ORCHESTRATE skills and never duplicate their content.
Every agent file carries: a role definition, the list of skills it references (by relative
path), explicit loop controls (counters plus exit conditions drawn from the canonical
taxonomy: `max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
`escalation_trigger`), the full 5-Phase Protocol (DISCOVERY, MANIFEST, HUMAN GATE,
IMPLEMENTATION, SELF-REVIEW & HANDOFF), boundary declarations (allowed/forbidden paths and
tools), and an output contract (handoff report format).

**What it must NEVER hold.** Inlined skill content (copy-pasted procedures that already exist
in a skill), project facts that belong in `context/` (an agent restating architecture rules
will drift from the source of truth), or multi-agent sequencing (that belongs in
`workflows/`).

**File format.** One markdown file per agent with the component frontmatter:

```yaml
---
name: "db-migration-agent"
version: "2.1.0"
description: "Plans and applies database migrations under HITL gates with rollback manifests"
type: "agent"
---
```

**Concrete examples.**

1. `agents/db-migration-agent.md` — references `../skills/sql-migration-review/SKILL.md`,
   declares `max_iterations: 5`, treats every schema change as irreversible (Phase 3 HUMAN
   GATE mandatory), and forbids touching any path outside `migrations/` and `tests/`.
2. `agents/release-notes-agent.md` — references `../skills/changelog-writer/SKILL.md`,
   declares a `budget` exit condition of 30 tool calls, a `success_predicate` ("changelog
   section exists and every merged PR in range is mentioned"), and an `escalation_trigger`
   ("any PR without a conventional-commit prefix escalates to the release manager").

### Pillar 4: workflows/ — Multi-Agent Orchestrations With HITL Gates

**What it holds.** Multi-agent orchestrations: ordered steps, dependencies, failure policies,
and HITL gates encoded in the canonical workflow JSON schema (steps with `id`, `type`
(`action|gate|check`), `irreversible`, `requires_approval`, `rollback`, `on_failure`,
`max_retries`, `depends_on`, plus a top-level `escalation` object). Workflow markdown files
embed the JSON in a fenced `json` code block so `hitl_gate_validator.py` can extract and
validate it (the validator reads the FIRST fenced json block).

**What it must NEVER hold.** Agent role prompts, skill procedures, or project facts. A
workflow says *who runs when and what must be approved*; it never says *how* a step is
performed — that lives in the agent and its skills.

**File format.** Markdown with component frontmatter and an embedded canonical JSON block:

```yaml
---
name: "release-pipeline"
version: "1.0.0"
description: "Build, review, gate, and deploy a release with human approval before deploy"
type: "workflow"
---
```

**Concrete examples.**

1. `workflows/release-pipeline.md` — steps `build` (action) -> `review` (check) ->
   `approve-deploy` (gate, `requires_approval: true`) -> `deploy` (action,
   `irreversible: true`, `rollback: "redeploy previous tagged image"`) -> `verify` (check),
   with `escalation` pointing at the on-call engineer.
2. `workflows/schema-change.md` — `draft-migration` (action) -> `migration-review` (check,
   runs the db-migration-agent's self-review) -> `dba-gate` (gate) -> `apply-migration`
   (action, `irreversible: true`, `rollback: "run generated down-migration"`) ->
   `post-apply-check` (check).

---

## Knowledge Flow

Information flows in exactly one direction:

```
context/  -->  skills/  -->  agents/  -->  workflows/
(ground        (atomic        (roles that     (orchestrations
 truth)        capabilities)  orchestrate)    with HITL gates)
```

- `context/` informs everything downstream but references nothing.
- `skills/` may cite context facts but never reference agents, workflows, or other skills.
- `agents/` consume context read-only and reference skills by path.
- `workflows/` sequence agents and encode gates; they are the only pillar allowed to know
  about more than one agent.

**Rule: information flows downstream, dependencies never flow upstream between siblings.**
A skill referencing another skill, an agent referencing another agent, or a context file
referencing an agent are all violations. If you feel the pull to create such a link, the logic
is in the wrong pillar — move it downstream instead.

---

## Atomicity and Anti-Duplication Rules

1. **If two agents need the same logic, it becomes a skill.** The moment a procedure appears
   in a second agent file, extract it into `skills/` and have both agents reference it by
   path. Duplicated agent logic drifts; skills do not.
2. **If two skills share logic, split a third skill or accept duplication over coupling.**
   Skills must stay dependency-free. When two skills contain the same fragment, either the
   fragment is a capability of its own (promote it to a third skill and update the *agents*
   that orchestrate them), or the fragment stays duplicated. Duplication inside atomic skills
   is cheaper than coupling between them.
3. **Agents reference skills by path, never inline them.** An agent file says "apply
   `../skills/sql-migration-review/SKILL.md` to every migration file" — it never copies the
   checklist. Inlining freezes a stale copy that no version bump will ever reach.
4. **Context is stated once.** Any fact repeated in two files is a future contradiction. State
   it in `context/` and cite it.
5. **Workflows own sequencing.** If an agent prompt says "then hand off to the deploy agent",
   that sequencing must move into a workflow step with `depends_on`.

> **Discovering a new skill?** These rules define *what* a skill is; the research method
> for scoping one — atomic delimitation, canonical-syntax extraction, defensive
> anti-pattern mining, interface definition, and the anti-duplication check (with the
> deterministic `scripts/skill_overlap_check.py`) — is in
> `references/skill_discovery_design.md`. Run it before authoring any new skill.

---

## Directory Layout

`ecosystem_scaffolder.py` generates exactly this tree:

```text
<project>/
├── README.md
├── context/
│   ├── README.md
│   ├── architecture.md
│   ├── boundaries.md
│   └── glossary.md
├── skills/
│   └── example-skill/
│       └── SKILL.md
├── agents/
│   └── example-agent.md
└── workflows/
    └── example-workflow.md
```

- `README.md` — ecosystem overview, pillar map, and regeneration instructions.
- `context/README.md` — how to maintain ground truth and who owns each file.
- `context/architecture.md` — architecture rules, service boundaries, canonical names,
  data contracts.
- `context/boundaries.md` — allowed/forbidden paths, tools, and out-of-scope systems; the
  file agents mirror into their forbidden/allowed sections.
- `context/glossary.md` — canonical vocabulary; one term, one definition.
- `skills/example-skill/SKILL.md`, `agents/example-agent.md`,
  `workflows/example-workflow.md` — working templates carrying the component frontmatter
  (`name`, `version`, `description`, `type`) to copy for each new component.

---

## Naming and Versioning

- **kebab-case names** for every component and folder: `sql-migration-review`,
  `db-migration-agent`, `release-pipeline`. The frontmatter `name` matches the file or folder
  name exactly.
- **Semver per component.** Every component versions independently in its frontmatter
  (`version: "1.2.0"`). There is no ecosystem-wide lockstep version.
- **Version bumped on any behavioral change.** A wording tweak that changes what an agent may
  do, a new exit condition, a tightened boundary, a changed rollback — all bump the version.
  Patch for clarifications with identical behavior, minor for added capability, major for
  changed or removed behavior.
- Workflows embed the version in their JSON (`"version": "1.0.0"`) and it must match the
  frontmatter version of the wrapping markdown file.

---

## Operating Modes

### GENERAL Mode

Used when scaffolding an ecosystem without a specific project attached. All four pillars are
filled with stack-agnostic best practices: context files describe placeholder architecture
rules and a starter glossary; skills are generic capabilities (code review, changelog
writing); agents carry the full 5-Phase Protocol and complete loop controls with conservative
defaults (`max_iterations` low, everything irreversible until proven otherwise); workflows
gate every write. GENERAL mode output is safe to run anywhere and is meant to be replaced
piece by piece as project knowledge arrives.

### CONTEXTUALIZED Mode

Used when the ecosystem serves a real project. Follow the 4-step absorption procedure:

1. **Collect project docs.** Gather READMEs, architecture decision records, runbooks, API
   specs, onboarding guides, and tribal knowledge from maintainers.
2. **Distill into context/ files.** Rewrite the collected material as declarative ground
   truth in `architecture.md` and `glossary.md` — facts only, no instructions, one statement
   per fact, sourced where possible.
3. **Extract boundaries into boundaries.md.** Pull every "never touch", "requires sign-off",
   and "owned by team X" statement into explicit allowed/forbidden path, tool, and scope
   declarations.
4. **Regenerate agents so every boundary appears in their forbidden/allowed sections.** No
   boundary may exist only in `context/boundaries.md`; each one must be mirrored verbatim
   into the boundary section of every agent it constrains. Run `loop_auditor.py` on each
   regenerated agent to confirm Boundary Control checks pass.

---

## Migrating an Existing Repo

Adopt incrementally, in this order — each stage delivers value before the next begins:

1. **Context first.** Create `context/` and distill existing docs into `architecture.md`,
   `boundaries.md`, and `glossary.md`. Even without agents, this de-duplicates project
   knowledge and gives humans one place to look.
2. **Extract skills from duplicated prompt fragments.** Grep existing prompts, CI scripts, and
   runbooks for procedures that appear more than once; promote each into an atomic skill under
   `skills/` and delete the copies.
3. **Then agents.** Rewrite each existing prompt as an agent file that references the extracted
   skills by path, adds loop controls with explicit exit conditions, and embeds the 5-Phase
   Protocol. Audit each with `loop_auditor.py` before use.
4. **Then workflows.** Encode the multi-agent sequences that previously lived in humans' heads
   as workflow files with the canonical JSON schema, and validate every one with
   `hitl_gate_validator.py` until it reports PASS.

Do not skip stages: agents written before context exists will invent their own ground truth,
and workflows written before agents exist gate nothing.

---

## Ecosystem Review Checklist

Run this checklist before declaring an ecosystem production-ready:

- [ ] All four pillar directories exist and each component file carries `name`, `version`,
      `description`, `type` frontmatter with kebab-case names.
- [ ] `context/` contains only declarative facts — no instructions, no secrets.
- [ ] `context/boundaries.md` exists and every boundary is mirrored into the
      forbidden/allowed section of every agent it constrains.
- [ ] Every skill is atomic: one capability, zero references to other skills, deterministic
      tools preferred over LLM calls.
- [ ] No agent inlines skill content; all skill usage is by relative path.
- [ ] Every agent declares loop controls with exit conditions from the canonical taxonomy
      (`max_iterations`, `no_progress`, `oscillation`, `budget`, `success_predicate`,
      `escalation_trigger`) and the full 5-Phase Protocol.
- [ ] Every agent scores HARDENED (>= 90) with `loop_auditor.py` before deployment
      (use `--min-score 90` as the gate).
- [ ] Every workflow embeds valid canonical JSON, defines top-level `escalation`, and passes
      `hitl_gate_validator.py` (no CRITICAL, no HIGH violations).
- [ ] Every irreversible workflow step has `requires_approval: true` or a gate upstream in its
      `depends_on` chain, plus a non-null `rollback`.
- [ ] No upstream or sibling dependencies anywhere: context references nothing; skills
      reference no skills; agents reference no agents; only workflows sequence agents.
- [ ] Versions bumped for every behavioral change since the last review.
- [ ] Final workflow step is `type: check` (self-review) wherever feasible.

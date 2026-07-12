# Corrective Feedback Loops

How a correction — a human's or an AI judge's rejection of a decision — becomes an in-context policy change with NO weight update, and how a recurring correction crystallizes into a durable, auditable, expirable prohibition. FRAMEWORK TRACK gives the real runtime APIs; STATIC TRACK maps them onto this hub's git-versioned, human-gated machinery. This reference owns the correction-signal plumbing; the optimizer-method catalog is in `prompt_optimization_methods.md`, and loop theory is in `skills/agentic-system-architect/references/loop_engineering_patterns.md`.

## Concept index (citations)

The literature this reference draws on, so a reader can verify each mapping against the source. All are concepts/methods, not hub-shipped code.

| Concept | Citation | What the hub takes from it |
|---|---|---|
| Verbal reinforcement / episodic reflection | Reflexion — Shinn et al., arXiv:2303.11366 | In-context correction, no gradient; the ledger as episodic buffer |
| RLAIF (AI preference labels) | Lee et al., arXiv:2309.00267 | The AI judge as a cheap, scalable corrector |
| Constitutional AI (AI judge + written rules) | Bai et al., arXiv:2212.08073 | The auditor rubric as the "constitution" |
| RLHF (human preference + reward model) | Ouyang et al., 2022 | The HUMAN GATE as the human corrector |
| Reward hacking / Goodhart | arXiv:2410.06491 | Why AI-corrector authority is capped and the human gate is final |

Real runtime APIs (LangGraph `interrupt()`/`Command`, LlamaIndex/CrewAI/MS Agent Framework human-input surfaces) are cited inline in the sections below, each with a version/verify flag where uncertain.

## RLAIF vs RLHF (the only difference is who corrects)

At training time the two pipelines are identical except for who supplies the preference label: a human (RLHF) or an AI judge (RLAIF).

- **RLHF** — human preference labels + a reward model (Ouyang et al. 2022, concept).
- **RLAIF** — an LLM generates the preference label instead of a person (Lee et al., arXiv:2309.00267; matched RLHF on summarization/dialogue and beat it on harmlessness).
- **Constitutional AI** — RLAIF where the AI judge is constrained by an explicit written "constitution," shifting human oversight from labeling instances to authoring rules (Bai et al., arXiv:2212.08073).
- Training tooling (HuggingFace TRL: `DPOTrainer`, `RewardTrainer`, `PPOTrainer`, `GRPOTrainer` — **verify against current TRL**) is model-TRAINING-time and OUT of this hub's no-model-call runtime scope. Pointer-level only; the hub never runs it.

**At INFERENCE time (no training), the same choice reappears as the source of the correction written into context:** a human at a gate (RLHF-style) versus an LLM-as-judge node feeding itemized feedback to an optimizer (RLAIF-style). The correction is in-context, not a gradient. This is the key reframing: the hub's HUMAN GATE (Phase 3) is the RLHF corrector; the evaluator-optimizer audit loop (producer -> auditor -> remediate) is the RLAIF corrector, its rubric the "constitution."

| | RLHF-style corrector | RLAIF-style corrector |
|---|---|---|
| Who supplies the label | A named human | An AI judge / evaluator |
| Framework surface | LangGraph `interrupt()` / CrewAI `human_input=True` | LLM-as-judge node writing to state / `loop_auditor.py` |
| Hub instrument | The HUMAN GATE (Phase 3) | The audit loop; `loop_auditor.py` score + itemized findings |
| Trust level | High — may crystallize into `boundaries.md` | Lower — must be human-ratified before crystallizing |
| Authority ceiling | Any decision, including irreversible ones | Reversible, in-boundary decisions only (corrected-and-continue) |
| Cost / speed | Slow, expensive, scarce | Fast, cheap, scalable — but gameable (see reward-hacking) |

The design rule that follows: use the cheap AI corrector for fast iteration on reversible edits, and reserve the human corrector for the irreversible and the durable. The two feed the SAME ledger, tagged by `corrector`, so a later human review can tell which corrections are promotable as-is and which need ratification.

## State-level correction: shaping policy at a decision point

The runtime core: an agent takes a wrong conditional edge, a corrector fixes it mid-run, and the correction is injected into working state so every downstream step obeys it — a policy change with no weight update (verbal reinforcement; Reflexion, Shinn et al., arXiv:2303.11366, concept).

**FRAMEWORK TRACK - real APIs:**
- LangGraph `interrupt(value)` — raises a `GraphInterrupt` at the exact node/edge and surfaces a payload to the client (requires a checkpointer to persist state).
- LangGraph `Command(resume=<correction>)` — the client resumes; the return value of `interrupt()` becomes the corrector's input.
- LangGraph `Command(update={...}, goto='node')` — write the correction into state and redirect the flow.
- LangGraph reducer-annotated state keys / `add_messages` — message-ID replacement corrects prior output in place; requires a checkpointer.
- LlamaIndex Workflows: `InputRequiredEvent`, `HumanResponseEvent` (subclassable), `Context` state.
- Microsoft Agent Framework: `RequestInfoExecutor`, `RequestInfoEvent`, `RequestResponse`, `RequestPort` (**verify against current docs — framework is 2025-new**).
- CrewAI: `Task(human_input=True)`; enterprise resume via task/step/crew webhooks.
- An LLM-as-judge node writing to the same state is the RLAIF corrector; a human at `interrupt()` / `human_input` is the RLHF corrector.

**STATIC TRACK:** the hub has no runtime, so "graph state" is the engagement's working context — the Change Manifest (Phase 2), the iteration ledger, and the Handoff Report (Phase 5). The HUMAN GATE (Phase 3) IS the `interrupt()` gate: a hard stop where a human approves/edits/rejects. The static analog of `Command(resume=...)` writing into state is: a rejected or edited decision at the gate is recorded as a revised manifest line PLUS a ledger entry, and because every subsequent phase must read the approved manifest as a contract, the correction shapes the rest of the engagement exactly like a downstream node reading corrected state.

In this mapping the **policy** being shaped is the union of the agent's `.md` decision logic and the currently-loaded manifest/ledger context; the **reward signal** is the gate verdict (approve = positive, edit/reject = negative). Because the manifest is a contract every later phase must obey, a single correction propagates deterministically to the end of the engagement — no re-prompting, no gradient, just a read of the corrected working set.

## Corrected-and-continue vs escalation_trigger

The loop taxonomy already has `escalation_trigger` and "return to Phase 2," but there is a lighter state for a reversible conditional-edge correction that does not warrant full re-approval.

- **Corrected-and-continue** — for a REVERSIBLE decision inside existing boundaries: the corrector's verdict is written into the ledger + manifest, policy reshapes for the rest of the task, and the loop continues WITHOUT a full Phase-2 re-approval. Permitted for an AI corrector only when the action is reversible and inside declared boundaries.
- **escalation_trigger** — for a COSTLY or IRREVERSIBLE decision, a boundary change, or the second firing of any exit condition: hard stop to the HUMAN GATE. An AI corrector may never resolve these; only a human may.

The dividing line is irreversibility, never the corrector's track record. Gate strictness scales with the cost of being wrong. Reward-hacking risk (below) is why an AI corrector's authority stops at reversible, in-boundary decisions.

**Routing table** — pick the lightest response the decision's reversibility allows:

| Situation | Corrector allowed | Response | What gets written |
|---|---|---|---|
| Reversible edit inside declared boundaries (e.g. reword a draft, pick a different in-scope file) | human or AI | corrected-and-continue | Ledger entry + revised manifest line; loop continues |
| Reversible but ambiguous / low-confidence | human | corrected-and-continue after a quick gate check | Ledger entry; note the ambiguity in the Handoff Report |
| Costly or irreversible (delete data, touch a forbidden path, external side effect) | human only | escalation_trigger -> HUMAN GATE | Escalation report; loop halts pending human input |
| Requires a boundary change | human only | escalation_trigger + separate governance action | Proposed `boundaries.md` edit (meta-level, human-gated) |
| Any exit condition fires a second time for the same subtask | human only | escalation_trigger | Two-strikes report per loop theory |

**Worked example (corrected-and-continue).** An agent operating a Convergence Loop reaches `decision_point = "edge: select_target_file"` and proposes editing `src/legacy/report_builder.py`. An AI judge node checks the proposal against `context/boundaries.md`, finds `report_builder.py` is in scope but flagged "prefer the v2 module for new logic," and returns `verdict = edit`: redirect to `src/report_v2/builder.py`. Because the action is reversible and in-boundary, the loop takes the corrected-and-continue path: the redirect is written to the ledger (`corrector = AI`) and the manifest line is revised, so every downstream step now targets `builder.py`. No Phase-2 re-approval is needed. Had the proposal been "delete `src/legacy/`," the same check would fire `escalation_trigger` instead and halt for a human — irreversible, so AI authority does not extend to it.

## The Correction Ledger schema

A correction is DATA with a schema, not prose buried in a transcript. The ledger is the machine-readable negative-space record — what was proposed, what was rejected, and the constraint it implies. It extends the iteration ledger from loop theory. `scripts/correction_ledger.py` reads and writes this schema as JSONL.

| Field | Meaning |
|---|---|
| `id` | Stable correction id (referenced by `boundaries.md` provenance) |
| `decision_point` | Where in the flow the decision was made (node/edge/phase/step) |
| `agent_proposal` | What the agent proposed to do |
| `verdict` | `reject` or `edit` |
| `corrector` | `human` or `AI` — the trust tag |
| `rationale` | Why it was rejected/edited |
| `implied_constraint` | The prohibition this implies ("never touch migrations/ without a HUMAN GATE") |
| `scope` | `task` \| `project` \| `global` |
| `recurrence_count` | How many entries share this normalized `implied_constraint` |

Example JSONL entries (one object per line; `scripts/correction_ledger.py add` writes these):

```json
{"id": "c0001", "date": "2026-07-12", "decision_point": "edge: route_to_migration", "agent_proposal": "apply schema change under migrations/", "verdict": "reject", "corrector": "human", "rationale": "migrations/ is frozen this sprint", "implied_constraint": "never touch migrations/ without a HUMAN GATE", "scope": "project", "recurrence_count": 1}
{"id": "c0002", "date": "2026-07-19", "decision_point": "step 4: plan edit", "agent_proposal": "edit migrations/0007.sql", "verdict": "reject", "corrector": "AI", "rationale": "still frozen", "implied_constraint": "Never touch migrations/ without a HUMAN GATE.", "scope": "project", "recurrence_count": 2}
```

The two entries share a constraint modulo casing and punctuation; the tool's normalization groups them so the pair reads as one recurring constraint with `recurrence_count` 2 (the "Proven" bar). `recurrence_count` is stored for convenience but is authoritatively recomputed from the whole ledger at report time, so a stale counter can never drive a graduation decision.

**Trust tagging is a safety requirement.** Tag every correction by `corrector`. Only human-ratified corrections may crystallize into `boundaries.md`; AI-authored corrections must be human-ratified first. Without the tag the hub cannot defend against an AI judge silently writing permanent prohibitions (reward-hacking, below). The ledger tool enforces this by flagging AI-only recurring groups as `NEEDS-HUMAN-RATIFICATION` and human-present groups as `READY` — either way it only nominates; a human still commits.

**Hot/cold tiering (eviction).** Task-scoped corrections stay hot in the ledger, flush to the Handoff Report (warm) at engagement end, and — once promoted to `boundaries.md` (frozen) — are EVICTED from the working ledger because they are now enforced structurally. Non-recurring corrections expire. This is the explicit forgetting policy; the storage/retention mechanics for memory backends belong to hybrid-rag-memory, not here.

## boundaries.md as a crystallized negative reward

`context/boundaries.md` (the context pillar: allowed/forbidden paths, tools, out-of-scope systems) IS the hub's persistent negative-reward store. A forbidden action is a crystallized negative reward — a correction expensive or recurrent enough to be frozen into a git-versioned prohibition every future agent mirrors into its forbidden section. The "weight update" is a human-gated commit/PR; git history is the audit log of the reward signal.

**Provenance fields (add to each `boundaries.md` prohibition):**

| Field | Meaning |
|---|---|
| `source` | The correction id(s) that produced this line |
| `date` | When it was crystallized |
| `rationale` | Why it exists (carried from the correction) |
| `review-by` | A date after which it must be re-confirmed or expired |

Without provenance a prohibition cannot be audited, rolled back, or safely expired — the negative-reward store has no forgetting mechanism (the mirror image of a conflict-resolving memory layer's UPDATE/DELETE). `review-by` makes a prohibition first-class: expirable when its originating correction no longer recurs, gated by a human.

**Before / after a graduation.** A `boundaries.md` forbidden section without provenance is an orphan rule no one can safely remove:

```text
# context/boundaries.md (before)
forbidden:
  - migrations/          # why? who added this? still true?
```

After the recurring correction c0001/c0002 is nominated by the ledger tool and a human commits it, the same line is auditable and expirable:

```text
# context/boundaries.md (after)
forbidden:
  - path: migrations/
    reason: "never touch migrations/ without a HUMAN GATE"
    source: c0001,c0002        # correction ids that produced this line
    date: 2026-07-19
    review-by: 2027-01-15      # re-confirm or expire after this date
```

The exact YAML shape follows the project's existing `boundaries.md` conventions (see the context pillar in agentic-system-architect's `four_pillar_ecosystem.md`); the load-bearing addition is the four provenance keys, not the layout.

**Promotion path (the closed loop, all human-gated):** a recurring `implied_constraint` (recurrence across 2+ engagements = the "Proven" bar in self-improving-agent's promotion-rules.md) is NOMINATED by `scripts/correction_ledger.py`, which emits a proposed `boundaries.md` line with provenance. It NEVER auto-writes. A human reviews and commits. This generalizes self-improving-agent's promotion engine — which today promotes only POSITIVE patterns into CLAUDE.md/rules — to also promote NEGATIVE rewards into `boundaries.md`. Versioning, rollback, and expiry of the crystallized line are owned by prompt-governance.

## Reward-hacking caveat

AI feedback substituting for human feedback is fast and cheap but gameable -- the Goodhart's-law failure mode analyzed in the reward-hacking literature (see arXiv:2410.06491; verify title/authors against the source): an optimizer can satisfy the letter of a reward while missing its intent, and an AI judge can be sycophantic or biased. A deterministic reward is also gameable at the presence-vs-substance level — `loop_auditor.py` checks for the presence of control-plane keywords, so a config can pass by writing the word without a real guard.

Mitigations layered by this hub:
- **Authority limits.** An AI corrector may only corrected-and-continue on reversible, in-boundary decisions; irreversible or boundary-changing decisions require the human gate. AI-authored corrections may not crystallize into `boundaries.md` without human ratification.
- **Held-out and rotating eval subsets** so the optimizer cannot overfit a frozen reward set (owned by agentic-evals-benchmarking).
- **Judge-integrity / score-inflation detection** on any AI corrector (owned by self-eval).
- **The HUMAN GATE as the final ungameable check** — a human reads the diff and the rationale, not just the score. No amount of reward-hacking survives Phase 3 when the human inspects the actual change.

## The closed loop, end to end

Putting the pieces together, a correction flows through the hub as a fully human-gated analog of a framework's self-editing memory loop — no gradients, no auto-writes:

1. **Capture** — a wrong decision is corrected (human at the gate, or AI judge on a reversible edit) and recorded as a typed ledger entry with a trust tag. (`scripts/correction_ledger.py add`)
2. **Reuse in-task** — a reversible, in-boundary correction reshapes policy for the rest of the engagement via corrected-and-continue; a costly one escalates.
3. **Detect recurrence** — across engagements, the ledger tool groups by normalized `implied_constraint` and flags any that recur to the "Proven" bar (2+). (`scripts/correction_ledger.py report`)
4. **Nominate** — the tool emits a proposed `boundaries.md` line with provenance and a readiness tag. It NEVER writes the file.
5. **Crystallize** — a human reviews and commits the prohibition (the gated "gradient step"); git history is the audit log.
6. **Expire** — when `review-by` passes and the correction no longer recurs, a human evicts the line; git retains it for rollback.

Role mapping for the whole loop: ledger = episodic memory (the negative-space record); `boundaries.md` = crystallized policy; `correction_ledger.py` = the offline nominator; the human PR = the gated policy update. This generalizes self-improving-agent's positive-pattern promotion engine to the negative-reward direction; versioning and rollback of the crystallized line are owned by prompt-governance. Do not reimplement either here — cite them.

---

## See also

- `SKILL.md` — the governed rewrite loop and the object/meta safety boundary this correction flow lives inside.
- `prompt_optimization_methods.md` — the optimizer catalog; corrections are one class of the failure signal those methods consume.
- `scripts/correction_ledger.py` — the deterministic tool that records corrections and nominates recurring ones for graduation.
- **self-improving-agent** (`reference/promotion-rules.md`) — the "Proven / Actionable / Durable" promotion criteria this flow mirrors for negative rewards.
- **prompt-governance** — versioning, rollback, and expiry of a crystallized `boundaries.md` prohibition.
- **self-eval** — judge-integrity and score-inflation checks on any AI corrector.

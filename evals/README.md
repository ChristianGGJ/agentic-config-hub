# Eval Workspace

This folder holds skill evaluation results for **agentic-config-hub**. Evals measure
how well a skill triggers and performs against realistic tasks, and each round of
results drives the next round of skill improvements.

## Layout: One Folder per Iteration

```
evals/
├── README.md                  # This file
└── iteration-N/               # One folder per evaluation round (iteration-1, iteration-2, ...)
    ├── evals.json             # Eval config: skills under test, tasks, grading criteria
    ├── grading-results.md     # Consolidated scores and findings for the round
    └── <skill-name>/          # Per-skill result folder
        ├── transcripts/       # Raw run transcripts for each eval task
        └── notes.md           # Failure analysis and improvement actions for that skill
```

### What goes inside

- **`evals.json`** — the round's configuration: which skills from `skills/` are under
  test, the task prompts, expected behaviors, and scoring rubric. Committed so any
  round is reproducible.
- **`grading-results.md`** — human-readable summary: per-skill scores, pass/fail per
  task, regressions versus the previous iteration, and the shortlist of fixes.
- **Per-skill result folders** — one per evaluated skill, holding raw transcripts and
  analysis notes so score changes can be traced to concrete evidence.

## How Iterations Drive Skill Improvement

1. **Run** an eval round against the current skill versions; record everything in a
   new `iteration-N/` folder. Never overwrite a previous iteration.
2. **Grade** the results in `grading-results.md`: what triggered wrongly, what
   underperformed, where descriptions or workflows were ambiguous.
3. **Fix** the skills in `skills/` — sharpen the "Use when" description, tighten
   workflows, patch scripts — via the normal feature-branch -> `dev` PR flow.
4. **Re-run** as `iteration-N+1` and compare against the previous round. A skill
   change is validated only when its scores improve without regressing others.

Iteration folders are append-only history: they document *why* each skill looks the
way it does today.

## Migration Note

This repository was seeded from an earlier skills library. The iteration folders for
that repo's skills were **intentionally removed at migration** — their results graded
skills that no longer exist here and would not be reproducible against the current
19-skill catalog. Numbering restarts at `iteration-1` with the first eval round run
against this repository's own skills.

## References

- Skill creation guide: [../skills/CLAUDE.md](../skills/CLAUDE.md)
- Skill testing: [../skills/skill-tester/SKILL.md](../skills/skill-tester/SKILL.md)
- Self-evaluation: [../skills/self-eval/SKILL.md](../skills/self-eval/SKILL.md)

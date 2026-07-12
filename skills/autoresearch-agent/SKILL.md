---
name: "autoresearch-agent"
description: "Use when the user wants to optimize a file by a measurable metric via an autonomous experiment loop: code speed/latency, bundle or image size, test pass rate, memory usage, prompt quality, or content/copy engagement (headlines, CTR). Inspired by Karpathy's autoresearch. The agent edits one target file, runs a fixed N-repeat evaluation, keeps statistically real improvements (git commit), discards the rest (git reset), and loops under declared exit conditions. Requires a target file, an evaluation command that prints a metric, and a git repo."
---

# Autoresearch Agent

> You sleep. The agent experiments. You wake up to results.

Autonomous experiment loop inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch). The agent edits one file, runs a fixed evaluation, keeps improvements, discards failures, and loops indefinitely.

Not one guess — fifty measured attempts, compounding.

---

## Slash Commands

| Command | What it does |
|---------|-------------|
| `/ar:setup` | Set up a new experiment interactively |
| `/ar:run` | Run a single experiment iteration |
| `/ar:loop` | Start autonomous loop with configurable interval (10m, 1h, daily, weekly, monthly) |
| `/ar:status` | Show dashboard and results |
| `/ar:resume` | Resume a paused experiment |

---

## When This Skill Activates

Recognize these patterns from the user:

- "Make this faster / smaller / better"
- "Optimize [file] for [metric]"
- "Improve my [headlines / copy / prompts]"
- "Run experiments overnight"
- "I want to get [metric] from X to Y"
- Any request involving: optimize, benchmark, improve, experiment loop, autoresearch

If the user describes a target file + a way to measure success → this skill applies.

---

## Setup

### First Time — Create the Experiment

Run the setup script. The user decides where experiments live:

**Project-level** (inside repo, git-tracked, shareable with team):
```bash
python scripts/setup_experiment.py \
  --domain engineering \
  --name api-speed \
  --target src/api/search.py \
  --eval "pytest bench.py --tb=no -q" \
  --metric p50_ms \
  --direction lower \
  --scope project
```

**User-level** (personal, in `~/.autoresearch/`):
```bash
python scripts/setup_experiment.py \
  --domain marketing \
  --name medium-ctr \
  --target content/titles.md \
  --eval "python evaluate.py" \
  --metric ctr_score \
  --direction higher \
  --evaluator llm_judge_content \
  --scope user
```

The `--scope` flag determines where `.autoresearch/` lives:
- `project` (default) → `.autoresearch/` in the repo root. Experiment definitions are git-tracked. Results are gitignored.
- `user` → `~/.autoresearch/` in the home directory. Everything is personal.

### What Setup Creates

```
.autoresearch/
├── config.yaml                        ← Global settings
├── .gitignore                         ← Ignores results.tsv, *.log
└── {domain}/{experiment-name}/
    ├── program.md                     ← Objectives, constraints, strategy
    ├── config.cfg                     ← Target, eval cmd, metric, direction
    ├── results.tsv                    ← Experiment log (gitignored)
    └── evaluate.py                    ← Evaluation script (if --evaluator used)
```

**results.tsv columns:** `commit | metric | status | description`
- `commit` — short git hash
- `metric` — float value or "N/A" for crashes
- `status` — keep | discard | crash
- `description` — what changed or why it crashed

### Domains

| Domain | Use Cases |
|--------|-----------|
| `engineering` | Code speed, memory, bundle size, test pass rate, build time |
| `marketing` | Headlines, social copy, email subjects, ad copy, engagement |
| `content` | Article structure, SEO descriptions, readability, CTR |
| `prompts` | System prompts, chatbot tone, agent instructions |
| `custom` | Anything else with a measurable metric |

### If `program.md` Already Exists

The user may have written their own `program.md`. If found in the experiment directory, read it. It overrides the template. Only ask for what's missing.

---

## Agent Protocol

You are the loop. The scripts handle setup and evaluation — you handle the creative work.

### Before Starting
1. Read `.autoresearch/{domain}/{name}/config.cfg` to get:
   - `target` — the file you edit
   - `evaluate_cmd` — the command that measures your changes
   - `metric` — the metric name to look for in eval output
   - `metric_direction` — "lower" or "higher" is better
   - `time_budget_minutes` — max time per evaluation
2. Read `program.md` for strategy, constraints, and what you can/cannot change
3. Read `results.tsv` for experiment history (columns: commit, metric, status, description)
4. Checkout the experiment branch: `git checkout autoresearch/{domain}/{name}`

### Each Iteration
1. Review results.tsv — what worked? What failed? What hasn't been tried?
2. Decide ONE change to the target file. One variable per experiment.
3. Edit the target file
4. Commit: `git add {target} && git commit -m "experiment: {description}"`
5. Evaluate: `python scripts/run_experiment.py --experiment {domain}/{name} --single`
6. Read the output — it prints KEEP, DISCARD, or CRASH with the metric value
7. Go to step 1

### What the Script Handles (you don't)
- Running the eval command with timeout
- Parsing the metric from eval output
- Comparing to previous best
- Reverting the commit on failure (`git reset --hard HEAD~1`)
- Logging the result to results.tsv

### Starting an Experiment

```bash
# Single iteration (the agent calls this repeatedly)
python scripts/run_experiment.py --experiment engineering/api-speed --single

# Dry run (test setup before starting)
python scripts/run_experiment.py --experiment engineering/api-speed --dry-run
```

### Strategy Escalation
- Runs 1-5: Low-hanging fruit (obvious improvements, simple optimizations)
- Runs 6-15: Systematic exploration (vary one parameter at a time)
- Runs 16-30: Structural changes (algorithm swaps, architecture shifts)
- Runs 30+: Radical experiments (completely different approaches)
- If no improvement in 20+ runs: update program.md Strategy section

### Self-Improvement
After every 10 experiments, review results.tsv for patterns. Update the
Strategy section of program.md with what you learned (e.g., "caching changes
consistently improve by 5-10%", "refactoring attempts never improve the metric").
Future iterations benefit from this accumulated knowledge.

### Stopping
- Stop when any of the six declared exit conditions fires (see Exit-Condition Governance), when the user interrupts, or on context limit. Every stop maps to a declared condition — report which one fired and the evidence.
- Before stopping: ensure results.tsv is up to date
- On context limit: the next session can resume — results.tsv and git log persist

### Rules

- **One change per experiment.** Don't change 5 things at once. You won't know what worked.
- **Simplicity criterion.** A small improvement that adds ugly complexity is not worth it. Equal performance with simpler code is a win. Removing code that gets same results is the best outcome.
- **Never modify the evaluator.** `evaluate.py` is the ground truth. Modifying it invalidates all comparisons. Hard stop if you catch yourself doing this.
- **Timeout.** If a run exceeds 2.5× the time budget, kill it and treat as crash.
- **Crash handling.** If it's a typo or missing import, fix and re-run. If the idea is fundamentally broken, revert, log "crash", move on. 5 consecutive crashes → pause and alert.
- **No new dependencies.** Only use what's already available in the project.

---

## Statistical Validity

**A single evaluation run locks in benchmark noise.** If `evaluate.py` varies
run-to-run (timing jitter, nondeterministic tests, LLM-judge variance, GPU
scheduling), a lone measurement that looks like a +2% "improvement" is often
noise. Keep it and the loop hill-climbs on randomness; later "regressions" are
just the noise reverting. Guard KEEP with three controls, all enforced by
`run_experiment.py` and configured in `config.cfg`:

1. **N-repeat evaluation.** `eval_repeats` runs the eval N times per experiment
   and aggregates. `aggregate: median` (default, robust to outliers) or `mean`.
   The runner also reports `mean +/- stddev` so you can see the spread.
2. **Warmup discard.** `warmup_runs` discards the first W runs before scoring
   (cold caches, JIT warmup, connection setup). Warmup samples are shown but not
   counted toward the metric.
3. **Noise band before KEEP.** `noise_band` is the minimum absolute improvement
   the aggregated metric must clear to be kept. `is_improvement` requires
   `new < best - noise_band` (lower-is-better) or `new > best + noise_band`
   (higher-is-better). With `noise_band: 0.0` (default) behavior is the original
   strict comparison — set it deliberately.

**Calibrate the band, do not guess it.** Measure your evaluator's own noise on
the *unchanged* baseline first:

```bash
python scripts/calibrate_noise.py --experiment engineering/api-speed --runs 12 --warmup 2
# Reports median, mean, stddev, coefficient of variation, min/max/range, and a
# recommended noise_band (default 2x stddev) plus eval_repeats. Add --json for tooling.
```

Set `noise_band` to the recommended value (or wider for fewer false KEEPs) and
`eval_repeats`/`warmup_runs` from the report. Rule of thumb: an improvement
smaller than one standard deviation of the baseline is not real — require it to
clear ~2x stddev. If the scored samples' `stddev` exceeds the band during a run,
the runner prints a NOTE: raise `eval_repeats` (the standard error of the
median/mean shrinks as samples grow) or widen the band.

**Cost note:** N-repeat multiplies evaluation cost by N. For expensive evals
(LLM judges, long builds) start at `eval_repeats: 3` with a calibrated band; for
cheap microbenchmarks use 5-11. This trades wall-clock for trustworthy KEEPs — a
single false KEEP wastes far more of the loop than the extra runs.

---

## Exit-Condition Governance

The original loop stops on ad-hoc signals ("5 consecutive crashes", "no
improvement in 20+ runs", context limit, goal met). Autonomy is preserved — the
loop is still long-running — but every stop must map to one of the **six
canonical exit-condition types** from the hub loop-engineering canon, and **all
six must be declared in `program.md` before iteration 1** (an undeclared exit
condition does not exist). This resolves the under-integration with hub loop
theory. For the full taxonomy, counter design, and anti-runaway rules, **see**
`../agentic-system-architect/references/loop_engineering_patterns.md` and the
`loop-engineering-mechanisms` skill — this section maps this skill onto that
canon rather than duplicating it.

| Hub exit type | How it fires in an autoresearch loop |
|---|---|
| `success_predicate` | The `program.md` goal is met — the best `metric` in `results.tsv` crosses the target (machine-checkable, e.g. `p50_ms < 50`). |
| `max_iterations` | Hard cap on experiments (e.g. 100). Keep it high to preserve autonomy, but it must exist and must never be raised mid-run. |
| `no_progress` | No KEEP in a window of N experiments **and** the best-metric state hash is unchanged across the window. Stall, not exploration — stop or change strategy. |
| `oscillation` | The last 4 experiments alternate between two approaches (A-B-A-B) with no net KEEP — two constraints in conflict. Stop and name both. |
| `budget` | Wall-clock, tool-call, or API-cost ceiling (LLM-judge calls are the usual cost driver). Refuse the next experiment when spent. |
| `escalation_trigger` | 5 consecutive crashes, a would-be evaluator edit, a change touching a non-target file, or any other condition firing twice for the same approach. Stop and ask the human (Phase 3 HUMAN GATE). |

### no_progress and oscillation detection (add to the loop)

`results.tsv` is the ledger. Before each experiment, derive two signals from it.
Canonicalize state before hashing (strip timestamps/paths) so trivia does not
mask a real stall:

- **no_progress (state-hash, window 2-3):** hash the *best-so-far* metric plus
  the set of still-unexplored strategies. If the hash is identical across the
  whole window (no KEEP moved the best, no new approach tried), fire
  `no_progress`. This is stronger than "20 runs with no improvement" because it
  also catches a loop re-trying the same failing idea.
- **oscillation (action ring buffer, window 4):** record a normalized signature
  of each experiment's approach (e.g. `cache` / `vectorize`). If the last four
  signatures match the A-B-A-B pattern (`w[0]==w[2]`, `w[1]==w[3]`, `w[0]!=w[1]`)
  with no KEEP between them, fire `oscillation`.

When any non-`success_predicate` condition fires: **stop and report** — which
condition, the evidence (state hash, the two oscillating approaches, budget
consumed), the best result so far, and the recommended next step. Never silently
"try one more time"; two strikes on the same subtask escalate to the human.
Firing a guard cleanly is the loop *succeeding* at self-governance, not failing.

---

## Guarding Against Evaluator Overfitting

The loop optimizes *whatever `evaluate.py` measures* — including its blind spots.
Given enough experiments it will find edits that raise the score without raising
true quality (Goodhart's law). This is acute for LLM-judge and ML metrics, where
the evaluator is itself learned and gameable.

**Held-out / rotating evaluation sets.** Do not let the agent optimize against
100% of your eval cases:

- Split eval cases into a **training set** (what the agent's `evaluate.py` uses)
  and a **held-out set** the agent never sees during normal iterations.
- Every K KEEPs (e.g. every 5), run the held-out set once and record it (a
  separate `holdout.tsv` row, or a note in `results.tsv`). If the training metric
  keeps improving while the held-out metric stalls or regresses, the loop is
  overfitting the evaluator — fire `escalation_trigger` and stop.
- **Rotate** the training subset periodically (e.g. resample which cases are
  active every 10 KEEPs) so the agent cannot lock onto quirks of a fixed set.

**Periodic secondary and human checks.** The primary evaluator is fast and
cheap; the check is slower and independent:

- For LLM judges, periodically re-score recent KEEPs with a **different model
  family or a different judge prompt** and compare rankings. Large disagreement
  means the metric is judge-specific, not quality.
- For ML validation, keep a true hold-out test set separate from the validation
  set the loop optimizes; report the test metric only at milestones, never inside
  the loop (using it in the loop turns it into a training signal).
- Schedule a **human spot-check** of the top KEEPs at milestones. The human
  confirms the win is real (genuinely faster / genuinely better copy), not an
  artifact. This is the escalation the loop cannot self-perform.

The evaluator itself stays frozen (never modified mid-experiment); overfitting is
controlled by *what you measure against and how often you audit*, not by editing
the judge. For eval-set design, golden datasets, and judge calibration, see the
`agentic-evals-benchmarking` skill.

---

## Evaluators

Ready-to-use evaluation scripts. Copied into the experiment directory during setup with `--evaluator`.

### Free Evaluators (no API cost)

| Evaluator | Metric | Use Case |
|-----------|--------|----------|
| `benchmark_speed` | `p50_ms` (lower) | Function/API execution time |
| `benchmark_size` | `size_bytes` (lower) | File, bundle, Docker image size |
| `test_pass_rate` | `pass_rate` (higher) | Test suite pass percentage |
| `build_speed` | `build_seconds` (lower) | Build/compile/Docker build time |
| `memory_usage` | `peak_mb` (lower) | Peak memory during execution |

### LLM Judge Evaluators (uses your subscription)

| Evaluator | Metric | Use Case |
|-----------|--------|----------|
| `llm_judge_content` | `ctr_score` 0-10 (higher) | Headlines, titles, descriptions |
| `llm_judge_prompt` | `quality_score` 0-100 (higher) | System prompts, agent instructions |
| `llm_judge_copy` | `engagement_score` 0-10 (higher) | Social posts, ad copy, emails |

LLM judges call the CLI tool the user is already running (Claude, Codex, Gemini). The evaluation prompt is locked inside `evaluate.py` — the agent cannot modify it. This prevents the agent from gaming its own evaluator.

The user's existing subscription covers the cost:
- Claude Code Max → unlimited Claude calls for evaluation
- Codex CLI (ChatGPT Pro) → unlimited Codex calls
- Gemini CLI (free tier) → free evaluation calls

### Reducing LLM-Judge Variance

LLM judges are nondeterministic — the same content can score 7 on one call and 8
on the next. A single judge call as the metric feeds that variance straight into
KEEP/DISCARD. Two defenses, on top of the N-repeat / noise-band controls above:

- **Average multiple judge calls.** The built-in judge evaluators sample the
  judge `AR_JUDGE_SAMPLES` times (default 3) and report the **median** score plus
  the spread (`*_stddev`). Median of an odd sample count shrugs off a single wild
  score. Raise it for high-stakes runs; each sample is one CLI call.
- **Pin determinism where the tool supports it.** Lower temperature / a fixed
  seed reduces call-to-call variance. Flags differ per CLI and version, and some
  tools expose no temperature control from the CLI — **verify against current
  docs** for `claude` / `codex` / `gemini` before relying on a specific flag; do
  not assume one exists.

Treat the reported judge `stddev` as your noise floor: set the experiment
`noise_band` at or above the judge's own spread, or the loop will chase judge
jitter. Because judges cost one call per sample, budget them explicitly as a
`budget` exit condition.

### Custom Evaluators

If no built-in evaluator fits, the user writes their own `evaluate.py`. Only requirement: it must print `metric_name: value` to stdout.

```python
#!/usr/bin/env python3
# My custom evaluator — DO NOT MODIFY after experiment starts
import subprocess
result = subprocess.run(["my-benchmark", "--json"], capture_output=True, text=True)
# Parse and output
print(f"my_metric: {parse_score(result.stdout)}")
```

---

## Viewing Results

```bash
# Single experiment
python scripts/log_results.py --experiment engineering/api-speed

# All experiments in a domain
python scripts/log_results.py --domain engineering

# Cross-experiment dashboard
python scripts/log_results.py --dashboard

# Export formats
python scripts/log_results.py --experiment engineering/api-speed --format csv --output results.csv
python scripts/log_results.py --experiment engineering/api-speed --format markdown --output results.md
python scripts/log_results.py --dashboard --format markdown --output dashboard.md
```

### Dashboard Output

```
DOMAIN          EXPERIMENT          RUNS  KEPT  BEST         Δ FROM START  STATUS
engineering     api-speed            47    14   185ms        -76.9%        active
engineering     bundle-size          23     8   412KB        -58.3%        paused
marketing       medium-ctr           31    11   8.4/10       +68.0%        active
prompts         support-tone         15     6   82/100       +46.4%        done
```

### Export Formats

- **TSV** — default, tab-separated (compatible with spreadsheets)
- **CSV** — comma-separated, with proper quoting
- **Markdown** — formatted table, readable in GitHub/docs

---

## Proactive Triggers

Flag these without being asked:

- **No evaluation command works** → Test it before starting the loop. Run once, verify output.
- **Target file not in git** → `git init && git add . && git commit -m 'initial'` first.
- **Metric direction unclear** → Ask: is lower or higher better? Must know before starting.
- **Time budget too short** → If eval takes longer than budget, every run crashes.
- **Agent modifying evaluate.py** → Hard stop. This invalidates all comparisons.
- **5 consecutive crashes** → Pause the loop. Alert the user. Don't keep burning cycles.
- **No improvement in 20+ runs** → Suggest changing strategy in program.md or trying a different approach.

---

## Autonomous Git Safety

The runner reverts a failed experiment with `git reset --hard HEAD~1`. Unattended
and looping, that is a foot-gun unless guarded. `run_experiment.py` enforces:

- **Clean-working-tree precondition.** Before evaluating, the runner runs
  `git status --porcelain` and **refuses** to proceed if tracked files have
  uncommitted changes — otherwise `reset --hard` would erase them. Commit the one
  experiment change first (the intended workflow) or `git stash` unrelated work.
  Untracked files (`??`) are preserved by `reset --hard` and are allowed.
- **One-file commit guard.** The runner checks that the HEAD commit
  (`git diff --name-only HEAD~1 HEAD`) touches **only the target file**. If the
  commit bundled other files it stops — a discard would revert those too, and it
  violates the one-change-per-experiment rule.
- **Escape hatches (use sparingly):** `--allow-dirty` and `--allow-extra-files`
  bypass the two guards when you deliberately need to.

**Recovery.** Nothing is truly lost while the branch reflog exists. If a reset
discarded a commit you wanted, find it and restore:

```bash
git reflog                 # locate the pre-reset commit hash
git reset --hard <hash>    # restore it
# or recover a single file: git checkout <hash> -- path/to/file
```

Keep experiments on the dedicated `autoresearch/{domain}/{name}` branch (setup
creates it) so a bad reset can never touch `main`/`dev`. The agent never pushes —
all work stays local.

### Parallel experiments (git worktree)

To explore several independent hypotheses at once without them colliding on one
working tree, run each in its own checkout:
`git worktree add ../exp-<name> autoresearch/{domain}/<name>` — separate
directory, shared repo, so the `reset --hard` in one worktree cannot disturb
another. Aggregate results by metric afterward. This is an advanced, optional
pattern; the default single-tree loop needs no worktrees.

---

## Hub Canon Integration

This skill runs a long-lived Convergence Loop, so it is governed by the hub's
agentic canon. It aligns as follows (citing the canon, not restating it — see
`../agentic-system-architect/references/loop_engineering_patterns.md`):

- **5-Phase Protocol.** DISCOVERY (read `config.cfg`, `program.md`,
  `results.tsv` — read-only) -> MANIFEST (declare the one change and all six exit
  conditions in `program.md`) -> HUMAN GATE (the human approves the experiment
  plan / long-run budget before iteration 1, and any `escalation_trigger` returns
  here) -> IMPLEMENTATION (the edit / commit / evaluate / keep-or-discard loop) ->
  SELF-REVIEW & HANDOFF (`results.tsv`, the dashboard, and the fired exit
  condition are the handoff report).
- **Six exit conditions.** All declared before iteration 1 (see Exit-Condition
  Governance above), OR-ed, first-to-fire stops and reports.
- **Boundary control (D-series).** Allowed path = the single target file;
  forbidden = the evaluator and every other file; no new dependencies; no remote
  push. These are the scope boundaries the D-series checks look for.
- **Recovery discipline (R-series).** Crash -> classify (typo/import = fix &
  re-run; broken idea = revert & log) -> cap at 5 consecutive crashes -> escalate.
  Reverts are `reset --hard`, guarded by the git-safety preconditions above.
- **HARDENED gate.** Audit the experiment's `program.md` and the
  `experiment-runner` agent for loop safety with the `loop-engineering-mechanisms`
  / `agentic-system-architect` tooling (`loop_auditor.py`); aim for the **>=90
  HARDENED** band before running fully unattended. Below 75, run only with a human
  watching.

---

## Installation

### One-liner (any tool)
```bash
git clone https://github.com/ChristianGGJ/agentic-config-hub.git
cp -r agentic-config-hub/skills/autoresearch-agent ~/.claude/skills/
```

### Multi-tool install
```bash
./scripts/convert.sh --skill autoresearch-agent --tool codex|gemini|cursor|windsurf|openclaw
```

### OpenClaw
```bash
clawhub install cs-autoresearch-agent
```

---

## Related Skills

- **self-improving-agent** — improves an agent's own memory/rules over time. NOT for structured experiment loops.
- **agentic-evals-benchmarking** — evaluation methodology: golden datasets, held-out sets, LLM-judge calibration, regression gates. Complementary — design the eval and guard against overfitting there, then autoresearch optimizes against it.
- **skill-tester** — task-based skill evaluation. Complementary — its test suite can be the evaluation function for a `prompts`/skill-optimization experiment.
- **agentic-system-architect** — loop-engineering canon (exit conditions, 5-Phase Protocol, HITL). See its `references/loop_engineering_patterns.md` for the theory this loop implements.
- **loop-engineering-mechanisms** — runnable loop-safety implementation (six exit conditions, stop-and-report handoffs, `loop_auditor.py`).
- **skill-security-auditor** — audit skills before publishing. NOT for optimization loops.

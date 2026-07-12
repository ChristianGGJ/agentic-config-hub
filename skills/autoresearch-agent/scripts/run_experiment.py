#!/usr/bin/env python3
"""
autoresearch-agent: Experiment Runner

Executes a single experiment iteration. The AI agent is the loop —
it calls this script repeatedly. The script handles evaluation,
metric parsing, keep/discard decisions, and git rollback on failure.

Usage:
    python scripts/run_experiment.py --experiment engineering/api-speed --single
    python scripts/run_experiment.py --experiment engineering/api-speed --dry-run
    python scripts/run_experiment.py --experiment engineering/api-speed --single --description "added caching"
"""

import argparse
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def find_autoresearch_root():
    """Find .autoresearch/ in project or user home."""
    project_root = Path(".").resolve() / ".autoresearch"
    if project_root.exists():
        return project_root
    user_root = Path.home() / ".autoresearch"
    if user_root.exists():
        return user_root
    return None


def load_config(experiment_dir):
    """Load config.cfg from experiment directory."""
    cfg_file = experiment_dir / "config.cfg"
    if not cfg_file.exists():
        print(f"  Error: no config.cfg in {experiment_dir}")
        sys.exit(1)
    config = {}
    for line in cfg_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            config[k.strip()] = v.strip()
    return config


def run_git(args, cwd=None, timeout=30):
    """Run a git command safely (no shell injection). Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True,
        cwd=cwd, timeout=timeout
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_current_commit(path):
    """Get short hash of current HEAD."""
    _, commit, _ = run_git(["rev-parse", "--short", "HEAD"], cwd=path)
    return commit


def get_best_metric(experiment_dir, direction):
    """Read the best metric from results.tsv."""
    tsv = experiment_dir / "results.tsv"
    if not tsv.exists():
        return None
    lines = [l for l in tsv.read_text().splitlines()[1:] if "\tkeep\t" in l]
    if not lines:
        return None
    metrics = []
    for line in lines:
        parts = line.split("\t")
        try:
            if parts[1] != "N/A":
                metrics.append(float(parts[1]))
        except (ValueError, IndexError):
            continue
    if not metrics:
        return None
    return min(metrics) if direction == "lower" else max(metrics)


def run_evaluation(project_root, eval_cmd, time_budget_minutes, log_file):
    """Run evaluation with time limit. Output goes to log_file.

    Note: shell=True is intentional here — eval_cmd is user-provided and
    may contain pipes, redirects, or chained commands.
    """
    hard_limit = time_budget_minutes * 60 * 2.5
    t0 = time.time()
    try:
        with open(log_file, "w") as lf:
            result = subprocess.run(
                eval_cmd, shell=True,
                stdout=lf, stderr=subprocess.STDOUT,
                cwd=str(project_root),
                timeout=hard_limit
            )
        elapsed = time.time() - t0
        return result.returncode, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        return -1, elapsed


def extract_metric(log_file, metric_grep):
    """Extract metric value from log file."""
    log_path = Path(log_file)
    if not log_path.exists():
        return None
    for line in reversed(log_path.read_text().splitlines()):
        stripped = line.strip()
        if stripped.startswith(metric_grep.lstrip("^")):
            try:
                return float(stripped.split(":")[-1].strip())
            except ValueError:
                continue
    return None


def is_improvement(new_val, old_val, direction, noise_band=0.0):
    """Check if a new result clears the noise band over the old best.

    noise_band is the minimum absolute improvement required to KEEP; it absorbs
    run-to-run evaluation noise so a change is only kept when the aggregated
    metric moves beyond the band. noise_band=0.0 reproduces the original
    strict-improvement behavior. Calibrate the band with
    scripts/calibrate_noise.py before starting the loop.
    """
    if old_val is None:
        return True
    if direction == "lower":
        return new_val < old_val - noise_band
    return new_val > old_val + noise_band


def log_result(experiment_dir, commit, metric_val, status, description):
    """Append result to results.tsv."""
    tsv = experiment_dir / "results.tsv"
    metric_str = f"{metric_val:.6f}" if metric_val is not None else "N/A"
    with open(tsv, "a") as f:
        f.write(f"{commit}\t{metric_str}\t{status}\t{description}\n")


def get_experiment_count(experiment_dir):
    """Count experiments run so far."""
    tsv = experiment_dir / "results.tsv"
    if not tsv.exists():
        return 0
    return max(0, len(tsv.read_text().splitlines()) - 1)


def get_description_from_diff(project_root):
    """Auto-generate a description from git diff --stat HEAD~1."""
    code, diff_stat, _ = run_git(["diff", "--stat", "HEAD~1"], cwd=str(project_root))
    if code == 0 and diff_stat:
        return diff_stat.split("\n")[0][:50]
    return "experiment"


def read_last_lines(filepath, n=5):
    """Read last n lines of a file (replaces tail shell command)."""
    path = Path(filepath)
    if not path.exists():
        return ""
    lines = path.read_text().splitlines()
    return "\n".join(lines[-n:])


def check_git_preconditions(project_root, target, allow_dirty=False, allow_extra_files=False):
    """Safety gate before evaluation. Returns True if it is safe to proceed.

    The runner reverts a failed experiment with `git reset --hard HEAD~1`, which
    permanently discards uncommitted changes to tracked files. Guard against that
    by refusing to run on a dirty tree, and enforce the one-file-per-experiment
    rule by checking the HEAD commit touched only the target file. Untracked
    files (status '??') survive `reset --hard` and are allowed.
    """
    code, porcelain, _ = run_git(["status", "--porcelain"], cwd=str(project_root))
    if code != 0:
        print("  BLOCKED: not a git repository (git status failed).")
        return False

    tracked_changes = [ln for ln in porcelain.splitlines() if ln and not ln.startswith("??")]
    if tracked_changes and not allow_dirty:
        print("  BLOCKED: working tree has uncommitted changes to tracked files.")
        print("  A discard runs 'git reset --hard HEAD~1' and would lose them.")
        print("  Commit the experiment change first, or stash unrelated work:")
        print("    git add <target> && git commit -m 'experiment: ...'")
        print("    git stash            # to set aside unrelated changes")
        print("  Recovery if work was already lost: git reflog; git reset --hard <ref>")
        print("  Override (unsafe): re-run with --allow-dirty")
        return False

    # Enforce one-file-per-experiment: the HEAD commit should touch only target.
    code, _, _ = run_git(["rev-parse", "--verify", "HEAD~1"], cwd=str(project_root))
    if code == 0 and target:
        code, changed, _ = run_git(["diff", "--name-only", "HEAD~1", "HEAD"], cwd=str(project_root))
        if code == 0 and changed:
            norm_target = target.replace("\\", "/").lstrip("./")
            extra = [f.strip() for f in changed.splitlines()
                     if f.strip() and f.strip().replace("\\", "/").lstrip("./") != norm_target]
            if extra and not allow_extra_files:
                print(f"  BLOCKED: HEAD commit touches files other than the target ({target}):")
                for f in extra:
                    print(f"    {f}")
                print("  One change per experiment: commit only the target file.")
                print("  A discard would 'git reset --hard HEAD~1' and revert these too.")
                print("  Override: re-run with --allow-extra-files")
                return False
    return True


def run_single(project_root, experiment_dir, config, exp_num, dry_run=False,
               description=None, allow_dirty=False, allow_extra_files=False):
    """Run one experiment iteration."""
    direction = config.get("metric_direction", "lower")
    metric_grep = config.get("metric_grep", "^metric:")
    eval_cmd = config.get("evaluate_cmd", "python evaluate.py")
    time_budget = int(config.get("time_budget_minutes", 5))
    metric_name = config.get("metric", "metric")
    target = config.get("target", "")
    repeats = max(1, int(config.get("eval_repeats", 1)))
    warmup = max(0, int(config.get("warmup_runs", 0)))
    aggregate = config.get("aggregate", "median").strip().lower()
    try:
        noise_band = float(config.get("noise_band", 0.0))
    except ValueError:
        noise_band = 0.0
    log_file = str(experiment_dir / "run.log")

    best = get_best_metric(experiment_dir, direction)
    ts = datetime.now().strftime("%H:%M:%S")

    print(f"\n[{ts}] Experiment #{exp_num}")
    print(f"  Best {metric_name}: {best}")

    if dry_run:
        print(f"  [DRY RUN] Would run {warmup} warmup + {repeats} scored eval(s), "
              f"aggregate by {aggregate}, KEEP only if it clears noise band {noise_band:g}")
        return "dry_run"

    # Git safety gate - a failed experiment is reverted with reset --hard.
    if not check_git_preconditions(project_root, target, allow_dirty, allow_extra_files):
        return "blocked"

    # Auto-generate description if not provided
    if not description:
        description = get_description_from_diff(str(project_root))

    commit = get_current_commit(str(project_root))

    # N-repeat evaluation: discard warmup runs, collect scored samples.
    total_runs = warmup + repeats
    print(f"  Running: {eval_cmd} (budget: {time_budget}m, "
          f"{warmup} warmup + {repeats} scored)")
    samples = []
    elapsed_total = 0.0
    for i in range(total_runs):
        ret_code, elapsed = run_evaluation(project_root, eval_cmd, time_budget, log_file)
        elapsed_total += elapsed
        phase = "warmup" if i < warmup else "scored"

        # Timeout
        if ret_code == -1:
            print(f"  TIMEOUT on {phase} run {i + 1}/{total_runs} after {elapsed:.0f}s - discarding")
            run_git(["checkout", "--", "."], cwd=str(project_root))
            run_git(["reset", "--hard", "HEAD~1"], cwd=str(project_root))
            log_result(experiment_dir, commit, None, "crash", f"timeout_{elapsed:.0f}s")
            return "crash"

        # Crash
        if ret_code != 0:
            tail = read_last_lines(log_file, 5)
            print(f"  CRASH on {phase} run {i + 1}/{total_runs} (exit {ret_code}) after {elapsed:.0f}s")
            print(f"  Last output: {tail[:200]}")
            run_git(["reset", "--hard", "HEAD~1"], cwd=str(project_root))
            log_result(experiment_dir, commit, None, "crash", f"exit_{ret_code}")
            return "crash"

        # Extract metric
        metric_val = extract_metric(log_file, metric_grep)
        if metric_val is None:
            print(f"  Could not parse {metric_name} from run.log on {phase} run {i + 1}")
            run_git(["reset", "--hard", "HEAD~1"], cwd=str(project_root))
            log_result(experiment_dir, commit, None, "crash", "metric_parse_failed")
            return "crash"

        if i >= warmup:
            samples.append(metric_val)
            print(f"    scored run {i - warmup + 1}/{repeats}: {metric_val:.6f}")
        else:
            print(f"    warmup run {i + 1}/{warmup}: {metric_val:.6f} (discarded)")

    # Aggregate the scored samples.
    if aggregate == "mean":
        metric_val = statistics.fmean(samples)
    else:
        metric_val = statistics.median(samples)
    mean_val = statistics.fmean(samples)
    stddev = statistics.stdev(samples) if len(samples) > 1 else 0.0

    spread = ""
    if len(samples) > 1:
        spread = f" [{aggregate} of {len(samples)}, mean {mean_val:.4f} +/- {stddev:.4f}]"

    delta = ""
    if best is not None:
        diff = metric_val - best
        delta = f" (delta {diff:+.4f}, band {noise_band:g})"

    print(f"  {metric_name}: {metric_val:.6f}{spread}{delta} in {elapsed_total:.0f}s")

    if noise_band > 0 and len(samples) > 1 and stddev > noise_band:
        print(f"  NOTE: sample stddev ({stddev:.4f}) exceeds noise band ({noise_band:g}); "
              f"raise eval_repeats or widen the band (see calibrate_noise.py).")

    # Keep or discard - must clear the noise band.
    if is_improvement(metric_val, best, direction, noise_band):
        print(f"  KEEP - cleared noise band")
        log_result(experiment_dir, commit, metric_val, "keep", description)
        return "keep"
    else:
        run_git(["reset", "--hard", "HEAD~1"], cwd=str(project_root))
        best_str = f"{best:.4f}" if best is not None else "?"
        reason = "within_noise_band" if best is not None else "no_improvement"
        print(f"  DISCARD - did not clear noise band")
        log_result(experiment_dir, commit, metric_val, "discard",
                   f"{reason}_{metric_val:.4f}_vs_{best_str}")
        return "discard"


def main():
    parser = argparse.ArgumentParser(description="autoresearch-agent runner")
    parser.add_argument("--experiment", help="Experiment path: domain/name (e.g. engineering/api-speed)")
    parser.add_argument("--single", action="store_true", help="Run one experiment iteration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--description", help="Description of the change (auto-generated from git diff if omitted)")
    parser.add_argument("--path", default=".", help="Project root")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Bypass the clean-working-tree safety check (unsafe)")
    parser.add_argument("--allow-extra-files", action="store_true",
                        help="Bypass the one-file-per-commit safety check")
    args = parser.parse_args()

    project_root = Path(args.path).resolve()
    root = find_autoresearch_root()

    if root is None:
        print("No .autoresearch/ found. Run setup_experiment.py first.")
        sys.exit(1)

    if not args.experiment:
        print("Specify --experiment domain/name")
        sys.exit(1)

    experiment_dir = root / args.experiment
    if not experiment_dir.exists():
        print(f"Experiment not found: {experiment_dir}")
        print("Run: python scripts/setup_experiment.py --list")
        sys.exit(1)

    config = load_config(experiment_dir)

    print(f"\n  autoresearch-agent")
    print(f"  Experiment: {args.experiment}")
    print(f"  Target: {config.get('target', '?')}")
    print(f"  Metric: {config.get('metric', '?')} ({config.get('metric_direction', '?')} is better)")
    print(f"  Budget: {config.get('time_budget_minutes', '?')} min/experiment")
    print(f"  Eval: {config.get('eval_repeats', '1')} scored + {config.get('warmup_runs', '0')} warmup "
          f"({config.get('aggregate', 'median')}), noise band {config.get('noise_band', '0.0')}")
    print(f"  Mode: {'dry-run' if args.dry_run else 'single'}")

    exp_num = get_experiment_count(experiment_dir) + 1
    run_single(project_root, experiment_dir, config, exp_num, args.dry_run,
               args.description, args.allow_dirty, args.allow_extra_files)


if __name__ == "__main__":
    main()

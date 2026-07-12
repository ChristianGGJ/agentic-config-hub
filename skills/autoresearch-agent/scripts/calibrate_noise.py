#!/usr/bin/env python3
"""
autoresearch-agent: Noise Calibration

Measures an evaluator's run-to-run noise on the UNCHANGED baseline so you can
pick a defensible noise_band (and eval_repeats / warmup_runs) before starting the
loop. It runs the eval command K times without touching any files or git, then
reports median, mean, stddev, coefficient of variation, min/max/range, and a
recommended noise_band (default 2x stddev).

Why: run_experiment.py KEEPs a change only if the aggregated metric clears the
noise_band. A band guessed from thin air either locks in noise (too small) or
rejects real wins (too large). Measure it instead.

Usage:
    # From an existing experiment (reads config.cfg):
    python scripts/calibrate_noise.py --experiment engineering/api-speed --runs 12 --warmup 2

    # Ad hoc, without an experiment:
    python scripts/calibrate_noise.py --eval "pytest bench.py -q" --metric p50_ms --runs 10

    python scripts/calibrate_noise.py --experiment engineering/api-speed --json

Exit codes:
    0  success
    1  usage / configuration error
    2  an eval run failed (crash/timeout) or the metric could not be parsed
    3  not enough scored samples to compute statistics (need >= 2)
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
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
    """Load config.cfg (skips comments and blank lines)."""
    cfg_file = experiment_dir / "config.cfg"
    if not cfg_file.exists():
        return None
    config = {}
    for line in cfg_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            config[k.strip()] = v.strip()
    return config


def run_eval_once(eval_cmd, project_root, hard_limit):
    """Run the eval command once. Returns (ok, elapsed, combined_output)."""
    t0 = time.time()
    try:
        result = subprocess.run(
            eval_cmd, shell=True,
            capture_output=True, text=True,
            cwd=str(project_root),
            timeout=hard_limit,
        )
    except subprocess.TimeoutExpired:
        return False, time.time() - t0, "TIMEOUT"
    elapsed = time.time() - t0
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, elapsed, combined
    return True, elapsed, combined


def extract_metric(output, metric_grep):
    """Extract a metric value from eval output (last matching line wins)."""
    needle = metric_grep.lstrip("^")
    value = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(needle):
            try:
                value = float(stripped.split(":")[-1].strip())
            except ValueError:
                continue
    return value


def recommend_repeats(cv):
    """Suggest eval_repeats from the coefficient of variation (fraction)."""
    if cv < 0.01:
        return 1
    if cv < 0.03:
        return 3
    if cv < 0.08:
        return 5
    return 11


def main():
    parser = argparse.ArgumentParser(
        description="Measure evaluator noise and recommend a noise_band.")
    parser.add_argument("--experiment", help="Experiment path domain/name (reads its config.cfg)")
    parser.add_argument("--eval", dest="eval_cmd", help="Evaluation command (overrides config)")
    parser.add_argument("--metric", help="Metric name (overrides config)")
    parser.add_argument("--metric-grep", help="Line prefix to match (default: '<metric>:')")
    parser.add_argument("--time-budget", type=int, help="Minutes per run (overrides config; default 5)")
    parser.add_argument("--runs", type=int, default=10, help="Scored runs (default: 10)")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs to discard (default: 1)")
    parser.add_argument("--band-factor", type=float, default=2.0,
                        help="Recommended noise_band = band_factor * stddev (default: 2.0)")
    parser.add_argument("--path", default=".", help="Project root")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    project_root = Path(args.path).resolve()

    eval_cmd = args.eval_cmd
    metric = args.metric
    metric_grep = args.metric_grep
    time_budget = args.time_budget

    if args.experiment:
        root = find_autoresearch_root()
        if root is None:
            print("No .autoresearch/ found. Run setup_experiment.py first, or pass --eval/--metric.")
            sys.exit(1)
        experiment_dir = root / args.experiment
        config = load_config(experiment_dir)
        if config is None:
            print(f"No config.cfg in {experiment_dir}")
            sys.exit(1)
        eval_cmd = eval_cmd or config.get("evaluate_cmd")
        metric = metric or config.get("metric")
        metric_grep = metric_grep or config.get("metric_grep")
        if time_budget is None:
            try:
                time_budget = int(config.get("time_budget_minutes", 5))
            except ValueError:
                time_budget = 5

    if time_budget is None:
        time_budget = 5

    if not eval_cmd or not metric:
        print("Need an eval command and metric. Use --experiment, or --eval and --metric.")
        sys.exit(1)

    if not metric_grep:
        metric_grep = f"^{metric}:"

    if args.runs < 2:
        print("--runs must be at least 2 to compute statistics.")
        sys.exit(1)

    warmup = max(0, args.warmup)
    hard_limit = time_budget * 60 * 2.5
    total = warmup + args.runs

    if not args.json:
        print(f"\n  autoresearch-agent noise calibration")
        print(f"  Eval:   {eval_cmd}")
        print(f"  Metric: {metric} (grep '{metric_grep}')")
        print(f"  Runs:   {warmup} warmup + {args.runs} scored (budget {time_budget}m/run)\n")

    samples = []
    for i in range(total):
        ok, elapsed, output = run_eval_once(eval_cmd, project_root, hard_limit)
        phase = "warmup" if i < warmup else "scored"
        if not ok:
            reason = "timeout" if output == "TIMEOUT" else "nonzero exit"
            print(f"  Eval run {i + 1}/{total} failed ({reason}). "
                  f"Fix the eval command before calibrating.", file=sys.stderr)
            sys.exit(2)
        value = extract_metric(output, metric_grep)
        if value is None:
            print(f"  Could not parse '{metric}:' from eval output on run {i + 1}.", file=sys.stderr)
            sys.exit(2)
        if i >= warmup:
            samples.append(value)
            if not args.json:
                print(f"    {phase} run {i - warmup + 1}/{args.runs}: {value:.6f} ({elapsed:.1f}s)")
        elif not args.json:
            print(f"    {phase} run {i + 1}/{warmup}: {value:.6f} (discarded)")

    if len(samples) < 2:
        print("Not enough scored samples to compute statistics (need >= 2).", file=sys.stderr)
        sys.exit(3)

    median = statistics.median(samples)
    mean = statistics.fmean(samples)
    stddev = statistics.stdev(samples)
    smin, smax = min(samples), max(samples)
    srange = smax - smin
    cv = (stddev / mean) if mean else 0.0
    recommended_band = round(args.band_factor * stddev, 6)
    recommended_repeats = recommend_repeats(cv)
    recommended_warmup = max(1, warmup)

    if args.json:
        print(json.dumps({
            "metric": metric,
            "scored_runs": len(samples),
            "warmup_runs": warmup,
            "median": median,
            "mean": mean,
            "stddev": stddev,
            "min": smin,
            "max": smax,
            "range": srange,
            "coefficient_of_variation": cv,
            "band_factor": args.band_factor,
            "recommended_noise_band": recommended_band,
            "recommended_eval_repeats": recommended_repeats,
            "recommended_warmup_runs": recommended_warmup,
            "samples": samples,
        }, indent=2))
    else:
        print(f"\n  Statistics ({len(samples)} scored samples)")
        print(f"    median : {median:.6f}")
        print(f"    mean   : {mean:.6f}")
        print(f"    stddev : {stddev:.6f}")
        print(f"    min/max: {smin:.6f} / {smax:.6f}  (range {srange:.6f})")
        print(f"    cv     : {cv * 100:.2f}%  (stddev / mean)")
        print(f"\n  Recommended config.cfg values")
        print(f"    noise_band: {recommended_band:g}   (= {args.band_factor:g} x stddev)")
        print(f"    eval_repeats: {recommended_repeats}")
        print(f"    warmup_runs: {recommended_warmup}")
        print(f"\n  An improvement smaller than the noise_band is not distinguishable")
        print(f"  from noise -- run_experiment.py will (correctly) DISCARD it.\n")

    sys.exit(0)


if __name__ == "__main__":
    main()

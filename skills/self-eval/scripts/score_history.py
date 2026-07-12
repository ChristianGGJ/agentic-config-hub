#!/usr/bin/env python3
"""Score-history analytics for the self-eval skill.

Reads a `.self-eval-scores.jsonl` file (one JSON object per line, as appended
by the self-eval workflow) and reports the score distribution, a per-axis
breakdown, a recent-vs-overall trend, and a clustering / inflation flag. Pure
stdlib aggregation -- no LLM, no network -- so it can run offline or in CI.

Each line is expected to look like:
  {"date":"2026-07-12","score":4,"ambition":"Medium","execution":"Strong","task":"..."}

Lines that are blank or not valid records are skipped and counted separately.

Usage:
  python score_history.py --file .self-eval-scores.jsonl
  python score_history.py --file .self-eval-scores.jsonl --window 5 --json

Exit codes:
  0  analyzed; no clustering / inflation signal
  1  I/O, usage, or parse error (file missing, or no valid records found)
  2  analyzed; a clustering / inflation signal was flagged
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

TOOL = "score_history"

AMBITION_ORDER = ["Low", "Medium", "High"]
EXECUTION_ORDER = ["Poor", "Adequate", "Strong"]

# Clustering / inflation thresholds (see SKILL.md "Anti-Inflation Check").
CLUSTER_MIN = 4        # minimum records in the recent window to run checks
LOW_VARIANCE = 0.6     # population stdev below this == "low variance"
HIGH_MEAN = 4.0        # recent mean at/above this == "clustered high"


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def load_records(path):
    """Return (records, malformed_count). Each record is a dict with a valid
    integer score in 1..5; ambition/execution are kept when present."""
    records = []
    malformed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(obj, dict) or "score" not in obj:
            malformed += 1
            continue
        try:
            score = int(obj["score"])
        except (TypeError, ValueError):
            malformed += 1
            continue
        if score < 1 or score > 5:
            malformed += 1
            continue
        records.append({
            "score": score,
            "ambition": obj.get("ambition"),
            "execution": obj.get("execution"),
            "date": obj.get("date"),
        })
    return records, malformed


def axis_counts(records, key, order):
    counts = Counter(r[key] for r in records if r.get(key))
    ordered = {name: counts.get(name, 0) for name in order}
    # Preserve any out-of-vocabulary values so nothing is silently dropped.
    for name, n in counts.items():
        if name not in ordered:
            ordered[name] = n
    return ordered


def detect_inflation(recent_scores, window):
    """Return a list of human-readable reasons; empty list means no signal."""
    reasons = []
    n = len(recent_scores)
    if n < CLUSTER_MIN:
        return reasons
    top_val, top_cnt = Counter(recent_scores).most_common(1)[0]
    if top_cnt >= n - 1:
        reasons.append(
            "clustering: %d of last %d scores are %d (anchoring to a default)"
            % (top_cnt, n, top_val))
    mean = statistics.mean(recent_scores)
    stdev = statistics.pstdev(recent_scores)
    if stdev < LOW_VARIANCE and mean >= HIGH_MEAN:
        reasons.append(
            "high-low-variance: last %d scores mean %.2f with stdev %.2f "
            "(clustered high, little spread)" % (n, mean, stdev))
    return reasons


def analyze(records, window):
    scores = [r["score"] for r in records]
    distribution = {str(v): scores.count(v) for v in range(1, 6)}
    overall_mean = statistics.mean(scores)
    recent = records[-window:] if window > 0 else records
    recent_scores = [r["score"] for r in recent]
    recent_mean = statistics.mean(recent_scores)
    reasons = detect_inflation(recent_scores, window)
    return {
        "records": len(records),
        "distribution": distribution,
        "mean": round(overall_mean, 4),
        "window": window,
        "recent_scores": recent_scores,
        "recent_mean": round(recent_mean, 4),
        "trend": round(recent_mean - overall_mean, 4),
        "ambition": axis_counts(records, "ambition", AMBITION_ORDER),
        "execution": axis_counts(records, "execution", EXECUTION_ORDER),
        "inflation_flag": bool(reasons),
        "reasons": reasons,
    }


def print_human(result, path, malformed):
    print("Score history: %s" % path)
    print("  records: %d (skipped %d malformed)" % (result["records"], malformed))
    dist = result["distribution"]
    print("  distribution: " + "  ".join("%s:%d" % (k, dist[k])
                                         for k in ("1", "2", "3", "4", "5")))
    print("  mean: %.2f  |  recent %d mean: %.2f  (trend %+.2f)"
          % (result["mean"], result["window"], result["recent_mean"], result["trend"]))
    amb = result["ambition"]
    print("  ambition:  " + "  ".join("%s %d" % (k, v) for k, v in amb.items()))
    exe = result["execution"]
    print("  execution: " + "  ".join("%s %d" % (k, v) for k, v in exe.items()))
    if result["inflation_flag"]:
        print("  INFLATION FLAG: last scores %s" % result["recent_scores"])
        for r in result["reasons"]:
            print("    - %s" % r)
    else:
        print("  no clustering / inflation signals detected")


def main(argv=None):
    p = UsageError(prog="score_history.py",
                   description="Analytics and inflation detection over self-eval score history.")
    p.add_argument("--file", default=".self-eval-scores.jsonl",
                   help="path to the score-history JSONL (default .self-eval-scores.jsonl)")
    p.add_argument("--window", type=int, default=5,
                   help="how many most-recent scores define 'recent' (default 5)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    if args.window < 1:
        sys.stderr.write("%s: error: --window must be >= 1\n" % TOOL)
        return 1

    path = Path(args.file)
    if not path.is_file():
        sys.stderr.write("%s: error: score-history file not found: %s\n" % (TOOL, path))
        return 1

    try:
        records, malformed = load_records(path)
    except OSError as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    if not records:
        sys.stderr.write("%s: error: no valid score records in %s (skipped %d line(s))\n"
                         % (TOOL, path, malformed))
        return 1

    result = analyze(records, args.window)

    if args.json:
        result["file"] = str(path)
        result["malformed_skipped"] = malformed
        print(json.dumps(result, indent=2))
    else:
        print_human(result, path, malformed)

    return 2 if result["inflation_flag"] else 0


if __name__ == "__main__":
    sys.exit(main())

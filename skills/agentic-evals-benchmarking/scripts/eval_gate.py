#!/usr/bin/env python3
"""Deterministic evaluation gate for agentic-evals-benchmarking.

Reads a results JSON and fails (exit 1) when the aggregate score is below a
threshold, or when any per-metric floor is breached. No LLM, no network -- pure
aggregation so it can run in air-gapped CI.

Results JSON shapes accepted:
  {"score": 0.91}
  {"scores": [0.9, 0.8, 0.95]}
  {"cases": [{"id": "c1", "score": 0.9}, {"id": "c2", "score": 0.7}]}
  {"metrics": {"faithfulness": 0.92, "relevance": 0.88}}

Usage:
  python eval_gate.py --results results.json --threshold 0.85
  python eval_gate.py --results results.json --threshold 0.85 --metric faithfulness=0.9 --json

Exit codes:
  0  gate passed
  1  gate breached, or I/O / usage error
"""

import argparse
import json
import sys
from pathlib import Path

TOOL = "eval_gate"


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def collect_scores(data):
    """Return (aggregate_mean, per_case_list, metrics_dict) from a results doc."""
    cases = []
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            for c in data["cases"]:
                if isinstance(c, dict) and "score" in c:
                    cases.append(float(c["score"]))
        if "scores" in data and isinstance(data["scores"], list):
            cases.extend(float(s) for s in data["scores"])
        if "score" in data and isinstance(data["score"], (int, float)):
            cases.append(float(data["score"]))
        metrics = {k: float(v) for k, v in data.get("metrics", {}).items()
                   if isinstance(v, (int, float))}
    else:
        raise ValueError("results JSON must be an object")
    agg = sum(cases) / len(cases) if cases else (
        sum(metrics.values()) / len(metrics) if metrics else None)
    return agg, cases, metrics


def parse_metric_floors(items):
    floors = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError("metric floor must be name=value, got %r" % item)
        name, val = item.split("=", 1)
        floors[name.strip()] = float(val)
    return floors


def evaluate(agg, metrics, threshold, floors):
    breaches = []
    if agg is None:
        breaches.append("no scores found in results")
    elif agg < threshold:
        breaches.append("aggregate %.4f < threshold %.4f" % (agg, threshold))
    for name, floor in floors.items():
        if name not in metrics:
            breaches.append("metric %r required by floor but absent" % name)
        elif metrics[name] < floor:
            breaches.append("metric %s %.4f < floor %.4f" % (name, metrics[name], floor))
    return breaches


def main(argv=None):
    p = UsageError(prog="eval_gate.py", description="Deterministic eval regression gate.")
    p.add_argument("--results", required=True, help="path to the results JSON file")
    p.add_argument("--threshold", type=float, default=0.85,
                   help="minimum aggregate score (default 0.85)")
    p.add_argument("--metric", action="append", metavar="NAME=VALUE",
                   help="per-metric floor, e.g. faithfulness=0.9 (repeatable)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    path = Path(args.results)
    if not path.is_file():
        sys.stderr.write("%s: error: results file not found: %s\n" % (TOOL, path))
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        agg, cases, metrics = collect_scores(data)
        floors = parse_metric_floors(args.metric)
    except (ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    breaches = evaluate(agg, metrics, args.threshold, floors)
    passed = not breaches
    result = {
        "results": str(path), "aggregate": round(agg, 4) if agg is not None else None,
        "cases": len(cases), "threshold": args.threshold, "metric_floors": floors,
        "metrics": metrics, "passed": passed, "breaches": breaches,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Eval gate: %s" % ("PASS" if passed else "FAIL"))
        print("  aggregate: %s over %d case(s), threshold %.2f"
              % ("n/a" if agg is None else "%.4f" % agg, len(cases), args.threshold))
        for m, v in metrics.items():
            print("  metric %s: %.4f%s" % (m, v, " (floor %.2f)" % floors[m] if m in floors else ""))
        for b in breaches:
            print("  BREACH: %s" % b)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

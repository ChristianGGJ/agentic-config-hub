#!/usr/bin/env python3
"""Deterministic guardrail effectiveness gate for agentic-guardrails-security.

Scores a guard against a labeled corpus: confusion matrix -> recall, precision,
FPR, FNR. Gates CI on a recall floor and an FPR ceiling, and can sweep a score
threshold to pick an operating point. No LLM, no network.

Input (--results): JSON or JSON-lines, each record one labeled decision:
  {"unsafe": true, "blocked": true}                  # label + hard decision
  {"unsafe": false, "score": 0.12}                   # label + soft score (use --threshold)
Fields: "unsafe" (bool, ground truth) required; provide "blocked" (bool) OR
"score" (float, blocked when score >= threshold).

Usage:
  python guardrail_eval.py --results results.jsonl --min-recall 0.90 --max-fpr 0.05
  python guardrail_eval.py --results results.jsonl --threshold 0.6 --json
  python guardrail_eval.py --results results.jsonl --sweep

Exit codes:
  0  gate passed (or --sweep, which is informational)
  1  gate breached (recall floor or FPR ceiling), or I/O / usage error
"""

import argparse
import json
import sys
from pathlib import Path

TOOL = "guardrail_eval"


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def load_records(path):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:                                   # try a JSON array first
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:           # fall back to JSON-lines
        out = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out


def decisions(records, threshold):
    """Yield (blocked: bool, unsafe: bool) from records."""
    for r in records:
        unsafe = bool(r["unsafe"])
        if "blocked" in r:
            blocked = bool(r["blocked"])
        elif "score" in r:
            blocked = float(r["score"]) >= threshold
        else:
            raise ValueError("record needs 'blocked' or 'score': %r" % r)
        yield blocked, unsafe


def metrics(pairs):
    tp = sum(1 for b, u in pairs if b and u)
    fp = sum(1 for b, u in pairs if b and not u)
    fn = sum(1 for b, u in pairs if not b and u)
    tn = sum(1 for b, u in pairs if not b and not u)
    rec = tp / (tp + fn) if tp + fn else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    fnr = fn / (fn + tp) if fn + tp else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(rec, 4), "precision": round(prec, 4),
            "fpr": round(fpr, 4), "fnr": round(fnr, 4)}


def main(argv=None):
    p = UsageError(prog="guardrail_eval.py", description="Guardrail effectiveness gate.")
    p.add_argument("--results", required=True, help="labeled results JSON or JSON-lines")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="score >= threshold means blocked (default 0.5; ignored if records carry 'blocked')")
    p.add_argument("--min-recall", type=float, default=None, help="recall floor (gate)")
    p.add_argument("--max-fpr", type=float, default=None, help="false-positive-rate ceiling (gate)")
    p.add_argument("--sweep", action="store_true",
                   help="report metrics across thresholds 0.1..0.9 and exit 0")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    path = Path(args.results)
    if not path.is_file():
        sys.stderr.write("%s: error: results file not found: %s\n" % (TOOL, path))
        return 1
    try:
        records = load_records(path)
        if not records:
            raise ValueError("no records in results file")
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    if args.sweep:
        rows = []
        for i in range(1, 10):
            t = i / 10.0
            try:
                m = metrics(list(decisions(records, t)))
            except (ValueError, KeyError) as exc:
                sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
                return 1
            rows.append({"threshold": t, **m})
        if args.json:
            print(json.dumps({"results": str(path), "sweep": rows}, indent=2))
        else:
            print("Threshold sweep (recall / precision / fpr):")
            for r in rows:
                print("  t=%.1f  recall=%.3f  precision=%.3f  fpr=%.3f"
                      % (r["threshold"], r["recall"], r["precision"], r["fpr"]))
        return 0

    try:
        m = metrics(list(decisions(records, args.threshold)))
    except (ValueError, KeyError) as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    breaches = []
    if args.min_recall is not None and m["recall"] < args.min_recall:
        breaches.append("recall %.4f < min-recall %.4f" % (m["recall"], args.min_recall))
    if args.max_fpr is not None and m["fpr"] > args.max_fpr:
        breaches.append("fpr %.4f > max-fpr %.4f" % (m["fpr"], args.max_fpr))
    passed = not breaches

    result = {"results": str(path), "threshold": args.threshold, "n": len(records),
              "metrics": m, "passed": passed, "breaches": breaches}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Guardrail eval: %s (n=%d, threshold=%.2f)"
              % ("PASS" if passed else "FAIL", len(records), args.threshold))
        print("  recall=%.4f precision=%.4f fpr=%.4f fnr=%.4f"
              % (m["recall"], m["precision"], m["fpr"], m["fnr"]))
        print("  tp=%d fp=%d fn=%d tn=%d" % (m["tp"], m["fp"], m["fn"], m["tn"]))
        for b in breaches:
            print("  BREACH: %s" % b)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

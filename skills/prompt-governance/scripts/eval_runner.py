#!/usr/bin/env python3
"""Deterministic prompt-eval runner for prompt-governance.

Runs offline, deterministic eval checks against a golden JSONL dataset and
fails (exit 1) when the weighted pass rate falls below a threshold. No LLM, no
network -- it scores model outputs that were produced beforehand, so it runs
in air-gapped CI. For scoring pipelines that already emit per-case numeric
scores, see the sibling skill agentic-evals-benchmarking (scripts/eval_gate.py);
this runner is the layer that turns raw outputs into pass/fail before that gate.

Supported check types (per-case "type" field, or --default-type):
  exact_match   normalized string equality (see --ignore-case)
  contains      every required substring/element is present in the output
  regex         re.search(pattern, output) matches
  json_schema   output parses as JSON and conforms to a minimal schema subset
                (type, required, properties, items, enum)

Golden JSONL: one JSON object per line. Recognized fields:
  id            case identifier (default: line index)
  type          check type (falls back to --default-type)
  expected      expected value; also accepts "expected_output"
  output        model output under test; also accepts "actual"/"prediction"
  weight        positive float, weights the case in the pass rate (default 1.0)
Blank lines and lines beginning with '#' are ignored.

Outputs (predictions) may instead live in a separate file via --predictions,
keyed by case id (JSONL of {"id":..., "output":...} or a JSON object
{"id": "output"}). A prediction found there overrides any embedded output.

Usage:
  python eval_runner.py --golden golden.jsonl --threshold 0.9
  python eval_runner.py --golden golden.jsonl --predictions preds.jsonl --json
  python eval_runner.py --golden golden.jsonl --default-type contains --ignore-case

Exit codes:
  0  pass rate met the threshold
  1  pass rate below the threshold (regression gate breached)
  2  usage error, I/O error, or malformed dataset/schema
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOOL = "eval_runner"
VALID_TYPES = ("exact_match", "contains", "regex", "json_schema")
_SENTINEL = object()


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(2)


class DataError(Exception):
    """Raised when the dataset or a schema is malformed (exit 2)."""


def read_jsonl(path):
    """Yield (line_no, obj) for each non-blank, non-comment JSONL line."""
    with path.open(encoding="utf-8") as fh:
        for i, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataError("%s line %d: invalid JSON (%s)" % (path.name, i, exc))
            if not isinstance(obj, dict):
                raise DataError("%s line %d: expected a JSON object" % (path.name, i))
            yield i, obj


def load_predictions(path):
    """Return {id: output} from a JSONL of objects or a single JSON object."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    preds = {}
    if stripped.startswith("{") and "\n" not in stripped.strip("{} \t"):
        # Single-line JSON object mapping id -> output.
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise DataError("%s: invalid JSON (%s)" % (path.name, exc))
        if isinstance(obj, dict) and not any(
                k in obj for k in ("id", "output", "actual", "prediction")):
            return {str(k): v for k, v in obj.items()}
    for _, obj in read_jsonl(path):
        cid = str(obj.get("id"))
        out = _first(obj, ("output", "actual", "prediction"))
        preds[cid] = out
    return preds


def _first(obj, keys, default=None):
    for k in keys:
        if k in obj:
            return obj[k]
    return default


def _norm(text, ignore_case, strip):
    s = text if isinstance(text, str) else json.dumps(text, sort_keys=True)
    if strip:
        s = s.strip()
    if ignore_case:
        s = s.lower()
    return s


def check_exact(expected, output, ignore_case, strip):
    return _norm(expected, ignore_case, strip) == _norm(output, ignore_case, strip)


def check_contains(expected, output, ignore_case, strip):
    needles = expected if isinstance(expected, list) else [expected]
    hay = _norm(output, ignore_case, strip=False)
    for n in needles:
        ns = _norm(n, ignore_case, strip=False)
        if ns not in hay:
            return False, "missing substring: %r" % n
    return True, ""


def check_regex(cid, expected, output):
    if not isinstance(expected, str):
        raise DataError("case %s: regex 'expected' must be a pattern string" % cid)
    try:
        pat = re.compile(expected)
    except re.error as exc:
        raise DataError("case %s: invalid regex %r (%s)" % (cid, expected, exc))
    text = output if isinstance(output, str) else json.dumps(output)
    return bool(pat.search(text))


_JSON_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


def validate_schema(value, schema, cid, path="$"):
    """Minimal JSON-schema subset validator. Returns a list of error strings."""
    if not isinstance(schema, dict):
        raise DataError("case %s: schema at %s must be an object" % (cid, path))
    errors = []
    exp_type = schema.get("type")
    if exp_type is not None:
        py = _JSON_TYPES.get(exp_type)
        if py is None:
            raise DataError("case %s: unknown schema type %r" % (cid, exp_type))
        # bool is a subclass of int; keep them distinct.
        ok = isinstance(value, py) and not (
            exp_type in ("number", "integer") and isinstance(value, bool))
        if not ok:
            errors.append("%s: expected type %s, got %s"
                          % (path, exp_type, type(value).__name__))
            return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: value %r not in enum" % (path, value))
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append("%s: missing required property %r" % (path, req))
        for prop, subschema in schema.get("properties", {}).items():
            if prop in value:
                errors.extend(
                    validate_schema(value[prop], subschema, cid, "%s.%s" % (path, prop)))
    if isinstance(value, list) and "items" in schema:
        for idx, item in enumerate(value):
            errors.extend(
                validate_schema(item, schema["items"], cid, "%s[%d]" % (path, idx)))
    return errors


def check_json_schema(cid, expected, output):
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            return False, "output is not valid JSON (%s)" % exc
    else:
        parsed = output
    errors = validate_schema(parsed, expected, cid)
    if errors:
        return False, "; ".join(errors)
    return True, ""


def run_case(obj, line_no, default_type, ignore_case, strip, predictions):
    cid = str(obj.get("id", line_no))
    ctype = obj.get("type", default_type)
    if ctype not in VALID_TYPES:
        raise DataError("case %s: unknown type %r (valid: %s)"
                        % (cid, ctype, ", ".join(VALID_TYPES)))
    if "expected" in obj or "expected_output" in obj:
        expected = _first(obj, ("expected", "expected_output"))
    else:
        raise DataError("case %s: missing 'expected'/'expected_output'" % cid)
    if predictions is not None and cid in predictions:
        output = predictions[cid]
    else:
        output = _first(obj, ("output", "actual", "prediction"), default=_SENTINEL)
        if output is _SENTINEL:
            raise DataError(
                "case %s: no output found (embed 'output' or supply --predictions)" % cid)

    try:
        weight = float(obj.get("weight", 1.0))
    except (TypeError, ValueError):
        raise DataError("case %s: weight must be a number" % cid)
    if weight <= 0:
        raise DataError("case %s: weight must be positive" % cid)

    reason = ""
    if ctype == "exact_match":
        passed = check_exact(expected, output, ignore_case, strip)
        if not passed:
            reason = "exact mismatch"
    elif ctype == "contains":
        passed, reason = check_contains(expected, output, ignore_case, strip)
    elif ctype == "regex":
        passed = check_regex(cid, expected, output)
        if not passed:
            reason = "pattern did not match"
    else:  # json_schema
        passed, reason = check_json_schema(cid, expected, output)

    return {"id": cid, "type": ctype, "weight": weight,
            "passed": passed, "reason": reason}


def main(argv=None):
    p = UsageError(prog="eval_runner.py",
                   description="Deterministic prompt-eval runner (offline pass/fail gate).")
    p.add_argument("--golden", required=True, help="path to the golden JSONL dataset")
    p.add_argument("--predictions",
                   help="optional JSONL/JSON of {id: output} that overrides embedded outputs")
    p.add_argument("--threshold", type=float, default=0.9,
                   help="minimum weighted pass rate 0..1 (default 0.9)")
    p.add_argument("--default-type", default="exact_match", choices=VALID_TYPES,
                   help="check type for cases without a 'type' field (default exact_match)")
    p.add_argument("--ignore-case", action="store_true",
                   help="case-insensitive comparison for exact_match/contains")
    p.add_argument("--no-strip", action="store_true",
                   help="do not strip surrounding whitespace before exact_match")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    if not 0.0 <= args.threshold <= 1.0:
        sys.stderr.write("%s: error: --threshold must be between 0 and 1\n" % TOOL)
        return 2

    golden = Path(args.golden)
    if not golden.is_file():
        sys.stderr.write("%s: error: golden file not found: %s\n" % (TOOL, golden))
        return 2

    strip = not args.no_strip
    try:
        predictions = None
        if args.predictions:
            pred_path = Path(args.predictions)
            if not pred_path.is_file():
                sys.stderr.write(
                    "%s: error: predictions file not found: %s\n" % (TOOL, pred_path))
                return 2
            predictions = load_predictions(pred_path)
        results = []
        for line_no, obj in read_jsonl(golden):
            results.append(
                run_case(obj, line_no, args.default_type, args.ignore_case, strip, predictions))
    except DataError as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 2

    if not results:
        sys.stderr.write("%s: error: golden dataset has no cases\n" % TOOL)
        return 2

    total_w = sum(r["weight"] for r in results)
    passed_w = sum(r["weight"] for r in results if r["passed"])
    n_pass = sum(1 for r in results if r["passed"])
    pass_rate = passed_w / total_w if total_w else 0.0
    gate_passed = pass_rate >= args.threshold
    failures = [r for r in results if not r["passed"]]

    summary = {
        "golden": str(golden),
        "cases": len(results),
        "passed": n_pass,
        "failed": len(failures),
        "weighted_pass_rate": round(pass_rate, 4),
        "threshold": args.threshold,
        "gate_passed": gate_passed,
        "failures": [{"id": r["id"], "type": r["type"], "reason": r["reason"]}
                     for r in failures],
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("Eval runner: %s" % ("PASS" if gate_passed else "FAIL"))
        print("  cases: %d  passed: %d  failed: %d" % (len(results), n_pass, len(failures)))
        print("  weighted pass rate: %.4f  threshold: %.2f" % (pass_rate, args.threshold))
        for r in failures:
            print("  FAIL [%s] %s: %s" % (r["type"], r["id"], r["reason"] or "did not pass"))

    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())

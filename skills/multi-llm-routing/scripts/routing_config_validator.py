#!/usr/bin/env python3
"""Deterministic linter for a multi-llm routing config (multi-llm-routing skill).

Checks a routing-config JSON for: tier completeness, cost monotonicity across
tiers, cascade/exit-condition declaration, capability references, and failover
sanity. No LLM, no network.

Config shape (see assets/routing-config-example.json):
  {
    "tiers": [{"name": "utility", "model_family": "...", "relative_cost": 1,
               "capabilities": ["chat", "extract"]}, ...],
    "cascade": {"order": ["utility", "reasoning"], "verify": ["schema", "groundedness"]},
    "exit_conditions": ["max_iterations", "budget", "oscillation", ...],
    "failover": {"utility": "reasoning"}
  }

Usage:
  python routing_config_validator.py assets/routing-config-example.json
  python routing_config_validator.py my-routing.json --json

Exit codes: 0 clean or WARN-only; 1 any ERROR, or I/O / usage error.
"""

import argparse
import json
import sys
from pathlib import Path

TOOL = "routing_config_validator"
CANON_EXITS = {"max_iterations", "no_progress", "oscillation", "budget",
               "success_predicate", "escalation_trigger"}


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def lint(cfg):
    findings = []  # (level, message)

    def err(m): findings.append(("ERROR", m))
    def warn(m): findings.append(("WARN", m))

    tiers = cfg.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        err("'tiers' must be a non-empty list")
        return findings
    names = []
    for i, t in enumerate(tiers):
        if not isinstance(t, dict):
            err("tier[%d] is not an object" % i); continue
        for f in ("name", "model_family", "relative_cost"):
            if f not in t:
                err("tier[%d] missing required field '%s'" % (i, f))
        if "name" in t:
            names.append(t["name"])
        if "capabilities" not in t or not t.get("capabilities"):
            warn("tier %r declares no capabilities" % t.get("name", i))
    if len(names) != len(set(names)):
        err("duplicate tier names: %s" % names)

    # cost monotonicity: tiers should be orderable by increasing relative_cost
    costs = [(t.get("name"), t.get("relative_cost")) for t in tiers
             if isinstance(t.get("relative_cost"), (int, float))]
    ordered = sorted(costs, key=lambda x: x[1])
    if [c[0] for c in costs] != [c[0] for c in ordered]:
        warn("tiers are not listed in increasing relative_cost order: %s"
             % [c[0] for c in costs])

    cascade = cfg.get("cascade")
    if cascade is None:
        warn("no 'cascade' block; routing is single-shot (no escalation ladder)")
    elif isinstance(cascade, dict):
        order = cascade.get("order", [])
        for n in order:
            if n not in names:
                err("cascade.order references unknown tier %r" % n)
        if len(order) < 2:
            warn("cascade.order has fewer than 2 tiers (no escalation possible)")
        if not cascade.get("verify"):
            err("cascade defines no 'verify' predicates -> escalation cannot be gated")

    exits = set(cfg.get("exit_conditions", []))
    if not exits:
        err("no 'exit_conditions' declared (hub canon requires the 6-type taxonomy)")
    else:
        unknown = exits - CANON_EXITS
        if unknown:
            err("unknown exit conditions (not canonical): %s" % sorted(unknown))
        if cascade and "max_iterations" not in exits:
            warn("cascade present but 'max_iterations' not declared -> unbounded ladder")

    failover = cfg.get("failover", {})
    if isinstance(failover, dict):
        for src, dst in failover.items():
            if src not in names:
                err("failover source %r is not a declared tier" % src)
            if dst not in names:
                err("failover target %r is not a declared tier" % dst)
            if src == dst:
                err("failover for %r points at itself" % src)
    return findings


def main(argv=None):
    p = UsageError(prog="routing_config_validator.py",
                   description="Lint a multi-LLM routing config JSON.")
    p.add_argument("config", help="path to the routing config JSON")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    path = Path(args.config)
    if not path.is_file():
        sys.stderr.write("%s: error: config not found: %s\n" % (TOOL, path))
        return 1
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write("%s: error: invalid JSON: %s\n" % (TOOL, exc))
        return 1
    if not isinstance(cfg, dict):
        sys.stderr.write("%s: error: config must be a JSON object\n" % TOOL)
        return 1

    findings = lint(cfg)
    errors = [m for lvl, m in findings if lvl == "ERROR"]
    warns = [m for lvl, m in findings if lvl == "WARN"]
    ok = not errors

    if args.json:
        print(json.dumps({"config": str(path), "ok": ok,
                          "errors": errors, "warnings": warns}, indent=2))
    else:
        print("Routing config: %s" % ("OK" if ok else "INVALID"))
        for m in errors:
            print("  ERROR: %s" % m)
        for m in warns:
            print("  WARN:  %s" % m)
        if ok and not warns:
            print("  no issues")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

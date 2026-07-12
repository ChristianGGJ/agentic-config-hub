#!/usr/bin/env python3
"""Legacy / invented-API scanner for Microsoft Agent Framework migrations.

Scans .cs and .py sources for (a) legacy Semantic Kernel / AutoGen constructs that
should be migrated to the current Microsoft Agent Framework (MAF) surface, and
(b) known-invented API names that do not exist and will not compile. Regex/heuristic
only -- no compilation, no network. Each hit names the real replacement.

Usage:
  python legacy_construct_scanner.py path/to/src          # human-readable report
  python legacy_construct_scanner.py path/to/src --json   # machine-readable

Exit codes: 0 clean; 1 hits found, or I/O / usage error.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOOL = "legacy_construct_scanner"

# (regex, severity, message-with-real-replacement). Heuristic; verify against current MAF docs.
PATTERNS = [
    (r"\.SendAsync\s*\(", "ERROR",
     "invented API '.SendAsync(...)' -> use RunAsync / RunStreamingAsync returning AgentRunResponse"),
    (r"\.Metadata\s*\[\s*[\"']Usage[\"']\s*\]", "ERROR",
     "invented usage access 'Metadata[\"Usage\"]' -> AgentRunResponse.Usage (UsageDetails: InputTokenCount/OutputTokenCount)"),
    (r"Arguments\s*=\s*new\s+ChatOptions", "ERROR",
     "invented 'Arguments = new ChatOptions{}' initializer -> pass options via ChatClientAgentOptions / constructor params"),
    (r"\bIMemoryStore\b", "ERROR",
     "legacy Semantic Kernel 'IMemoryStore' -> current MAF memory (AgentThread state / context providers / chat message store)"),
    (r"\bISemanticTextMemory\b", "ERROR",
     "legacy SK 'ISemanticTextMemory' -> MAF memory / external vector store integration"),
    (r"\bKernel\.CreateBuilder\s*\(", "WARN",
     "Semantic Kernel 'Kernel.CreateBuilder' -> for agents prefer IChatClient + ChatClientAgent (SK Kernel still valid for SK-native flows)"),
    (r"\bAgentGroupChat\b", "WARN",
     "AutoGen/SK 'AgentGroupChat' -> MAF Microsoft.Agents.AI.Workflows group-chat orchestration"),
    (r"\bConversableAgent\b", "WARN",
     "AutoGen 'ConversableAgent' -> MAF ChatClientAgent"),
    (r"KernelFunctionFactory\.Create", "WARN",
     "SK 'KernelFunctionFactory.Create' -> MAF tools via AIFunctionFactory.Create / [Description]-annotated methods"),
]
COMPILED = [(re.compile(p), sev, msg) for p, sev, msg in PATTERNS]


def scan_text(text, path):
    hits = []
    for rx, sev, msg in COMPILED:
        for m in rx.finditer(text):
            line = text[:m.start()].count("\n") + 1
            hits.append((str(path), line, sev, msg))
    return hits


def iter_src(target):
    if target.is_file():
        return [target] if target.suffix in (".cs", ".py") else []
    return sorted(list(target.rglob("*.cs")) + list(target.rglob("*.py")))


def main(argv=None):
    class _P(argparse.ArgumentParser):
        def error(self, m):
            self.print_usage(sys.stderr)
            sys.stderr.write("%s: error: %s\n" % (self.prog, m)); sys.exit(1)
    p = _P(prog="legacy_construct_scanner.py",
           description="Scan .cs/.py for legacy SK/AutoGen and invented MAF APIs.")
    p.add_argument("path", help="a .cs/.py file or a directory to scan recursively")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    target = Path(args.path)
    if not target.exists():
        sys.stderr.write("%s: error: path not found: %s\n" % (TOOL, target))
        return 1
    files = iter_src(target)
    if not files:
        sys.stderr.write("%s: error: no .cs/.py files at %s\n" % (TOOL, target))
        return 1

    hits = []
    for f in files:
        try:
            hits.extend(scan_text(f.read_text(encoding="utf-8", errors="replace"), f))
        except OSError as exc:
            sys.stderr.write("%s: warning: cannot read %s: %s\n" % (TOOL, f, exc))

    errors = [h for h in hits if h[2] == "ERROR"]
    if args.json:
        print(json.dumps({"scanned": len(files),
                          "hits": [{"file": a, "line": b, "severity": c, "issue": d}
                                   for a, b, c, d in hits]}, indent=2))
    else:
        print("Legacy/invented-API scan: %d file(s), %d hit(s)" % (len(files), len(hits)))
        for a, b, c, d in hits:
            print("  [%s] %s:%d %s" % (c, a, b, d))
        if not hits:
            print("  clean -- no legacy or invented MAF constructs found")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

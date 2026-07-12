#!/usr/bin/env python3
"""Correction ledger for agent-self-optimization.

Records agent-decision corrections in an append-only JSONL ledger and reports
which corrections RECUR often enough to graduate (under a HUMAN GATE) into a
context/boundaries.md prohibition. It NEVER auto-writes boundaries.md; it only
NOMINATES a line for human approval -- preserving the hub's human gate and
blocking AI-judge reward-hacking.

Deterministic, stdlib-only. No LLM calls, no network. Recurrence is grouped by
the normalized implied_constraint; the report recomputes groups fresh from the
whole ledger every run (no reliance on a stored counter).

Correction record shape (one JSON object per line):
  {
    "id": "c0001",
    "date": "2026-07-12",
    "decision_point": "edge: route_to_migration",
    "agent_proposal": "apply schema change under migrations/",
    "verdict": "reject",
    "corrector": "human",
    "rationale": "migrations/ is frozen this sprint",
    "implied_constraint": "never touch migrations/ without a HUMAN GATE",
    "scope": "project",
    "recurrence_count": 1
  }

Usage:
  # record a correction
  python correction_ledger.py add --ledger corrections.jsonl \
      --decision-point "edge: route_to_migration" \
      --proposal "apply schema change under migrations/" \
      --verdict reject --corrector human \
      --rationale "migrations/ is frozen this sprint" \
      --constraint "never touch migrations/ without a HUMAN GATE" \
      --scope project

  # flag recurring corrections that should graduate to boundaries.md
  python correction_ledger.py report --ledger corrections.jsonl --threshold 2
  python correction_ledger.py report --ledger corrections.jsonl --threshold 2 --json

Exit codes:
  0  success (add recorded; report found no graduation candidates)
  1  I/O, usage, or malformed-ledger error
  3  report found one or more recurring corrections that meet the graduation
     threshold and need human review (advisory, not a failure)
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

TOOL = "correction_ledger"

VERDICTS = ("reject", "edit")
CORRECTORS = ("human", "AI")
SCOPES = ("task", "project", "global")

CANDIDATES_EXIT = 3


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def normalize_constraint(text):
    """Group key for recurrence: lowercase, collapse whitespace, strip edges."""
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.rstrip(".;:! ")
    return t


def load_ledger(path):
    """Return a list of record dicts. Missing file -> empty list.

    Raises ValueError on a malformed (non-object / bad-JSON) line.
    """
    p = Path(path)
    if not p.is_file():
        return []
    records = []
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("malformed JSON on line %d: %s" % (lineno, exc))
        if not isinstance(obj, dict):
            raise ValueError("line %d is not a JSON object" % lineno)
        records.append(obj)
    return records


def next_id(records):
    """Sequential id 'cNNNN' avoiding collisions with existing numeric ids."""
    used = set()
    for r in records:
        rid = str(r.get("id", ""))
        m = re.match(r"^c(\d+)$", rid)
        if m:
            used.add(int(m.group(1)))
    n = len(records) + 1
    while n in used:
        n += 1
    return "c%04d" % n


def cmd_add(args):
    try:
        records = load_ledger(args.ledger)
    except (ValueError, OSError) as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    key = normalize_constraint(args.constraint)
    prior = sum(1 for r in records if normalize_constraint(r.get("implied_constraint")) == key)
    rec = {
        "id": args.id or next_id(records),
        "date": datetime.date.today().isoformat(),
        "decision_point": args.decision_point,
        "agent_proposal": args.proposal,
        "verdict": args.verdict,
        "corrector": args.corrector,
        "rationale": args.rationale,
        "implied_constraint": args.constraint,
        "scope": args.scope,
        "recurrence_count": prior + 1,
    }

    try:
        with open(args.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except OSError as exc:
        sys.stderr.write("%s: error: cannot write ledger: %s\n" % (TOOL, exc))
        return 1

    if args.json:
        print(json.dumps(rec, indent=2, ensure_ascii=True))
    else:
        print("Recorded %s (recurrence_count=%d) -> %s"
              % (rec["id"], rec["recurrence_count"], args.ledger))
        print("  constraint: %s" % rec["implied_constraint"])
        print("  verdict: %s by %s ; scope: %s" % (rec["verdict"], rec["corrector"], rec["scope"]))
    return 0


def build_groups(records):
    """Group records by normalized implied_constraint, newest-last order kept."""
    groups = {}
    for r in records:
        key = normalize_constraint(r.get("implied_constraint"))
        if not key:
            continue
        g = groups.setdefault(key, {
            "constraint_text": r.get("implied_constraint", ""),
            "ids": [], "correctors": [], "scopes": [], "rationales": [], "dates": [],
        })
        g["constraint_text"] = r.get("implied_constraint", g["constraint_text"])
        g["ids"].append(str(r.get("id", "?")))
        g["correctors"].append(r.get("corrector", "?"))
        g["scopes"].append(r.get("scope", "?"))
        g["rationales"].append(r.get("rationale", ""))
        g["dates"].append(r.get("date", ""))
    return groups


def cmd_report(args):
    try:
        records = load_ledger(args.ledger)
    except (ValueError, OSError) as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL, exc))
        return 1

    groups = build_groups(records)
    today = datetime.date.today()
    review_by = (today + datetime.timedelta(days=args.review_days)).isoformat()

    rows = []
    for key, g in groups.items():
        count = len(g["ids"])
        has_human = "human" in g["correctors"]
        is_candidate = count >= args.threshold
        readiness = None
        suggestion = None
        if is_candidate:
            readiness = "READY" if has_human else "NEEDS-HUMAN-RATIFICATION"
            suggestion = {
                "forbid": g["constraint_text"],
                "source": ",".join(g["ids"]),
                "date": today.isoformat(),
                "rationale": next((r for r in g["rationales"] if r), ""),
                "review_by": review_by,
            }
        rows.append({
            "implied_constraint": g["constraint_text"],
            "recurrence_count": count,
            "ids": g["ids"],
            "correctors": sorted(set(g["correctors"])),
            "scopes": sorted(set(g["scopes"])),
            "is_candidate": is_candidate,
            "readiness": readiness,
            "suggested_boundary": suggestion,
        })

    rows.sort(key=lambda x: (-x["recurrence_count"], x["implied_constraint"]))
    candidates = [r for r in rows if r["is_candidate"]]

    result = {
        "ledger": str(args.ledger),
        "total_corrections": len(records),
        "distinct_constraints": len(rows),
        "threshold": args.threshold,
        "review_by": review_by,
        "candidates_found": len(candidates),
        "groups": rows,
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print("Correction ledger report: %s" % args.ledger)
        print("  %d correction(s), %d distinct constraint(s), threshold=%d"
              % (len(records), len(rows), args.threshold))
        if not rows:
            print("  (ledger is empty -- nothing to report)")
        for r in rows:
            mark = "*" if r["is_candidate"] else " "
            print("  [%s] x%d  %s" % (mark, r["recurrence_count"], r["implied_constraint"]))
            print("        ids=%s correctors=%s scopes=%s"
                  % (",".join(r["ids"]), "/".join(r["correctors"]), "/".join(r["scopes"])))
        if candidates:
            print("")
            print("GRADUATION CANDIDATES (recurrence >= %d) -- nominate for boundaries.md"
                  % args.threshold)
            print("  A human must review and commit; this tool never writes boundaries.md.")
            for r in candidates:
                s = r["suggested_boundary"]
                print("  - [%s] %s" % (r["readiness"], s["forbid"]))
                print("      # source: %s ; date: %s ; rationale: %s ; review-by: %s"
                      % (s["source"], s["date"], s["rationale"], s["review_by"]))
        else:
            print("  No recurring corrections meet the threshold. Nothing to graduate.")

    return CANDIDATES_EXIT if candidates else 0


def build_parser():
    p = UsageError(prog="correction_ledger.py",
                   description="Record agent-decision corrections and flag recurring ones "
                               "that should graduate (under a human gate) into boundaries.md.")
    sub = p.add_subparsers(dest="command")
    sub.required = True

    a = sub.add_parser("add", help="record a correction")
    a.add_argument("--ledger", required=True, help="path to the JSONL ledger (created if absent)")
    a.add_argument("--decision-point", required=True, help="where the decision was made")
    a.add_argument("--proposal", required=True, help="what the agent proposed to do")
    a.add_argument("--verdict", required=True, choices=VERDICTS, help="reject or edit")
    a.add_argument("--corrector", required=True, choices=CORRECTORS,
                   help="human or AI (trust tag)")
    a.add_argument("--rationale", required=True, help="why it was rejected/edited")
    a.add_argument("--constraint", required=True,
                   help="the prohibition this implies (the boundaries.md candidate text)")
    a.add_argument("--scope", default="task", choices=SCOPES, help="task|project|global")
    a.add_argument("--id", help="override the auto-generated correction id")
    a.add_argument("--json", action="store_true", help="machine-readable output")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("report", help="summarize and flag recurring corrections")
    r.add_argument("--ledger", required=True, help="path to the JSONL ledger")
    r.add_argument("--threshold", type=int, default=2,
                   help="recurrence count at/above which a constraint is a graduation "
                        "candidate (default 2 = the 'Proven' bar of 2+ occurrences)")
    r.add_argument("--review-days", type=int, default=180,
                   help="days ahead to set the suggested review-by date (default 180)")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.set_defaults(func=cmd_report)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "report" and args.threshold < 1:
        sys.stderr.write("%s: error: --threshold must be >= 1\n" % TOOL)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

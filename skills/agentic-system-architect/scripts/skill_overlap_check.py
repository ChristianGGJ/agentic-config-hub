#!/usr/bin/env python3
"""Deterministic skill-overlap / anti-duplication checker (agentic-system-architect).

Realizes step 5 of skill_discovery_design.md: before creating a new skill, prove it is
not redundant. Two modes, both stdlib-only (no LLM, no network):

  1. Registry sweep -- scan every skill under a skills/ directory and report the pairs
     with the highest capability overlap, so pre-existing duplication surfaces.

  2. Proposal check (--against) -- compare a PROPOSED skill's description text against
     every existing skill and report the closest matches, so you can decide combine /
     extend / new-file before writing anything.

Overlap is a deterministic Jaccard similarity over the significant terms of each skill's
SKILL.md frontmatter `description` (plus its H1 title), after stopword removal. It is a
heuristic prompt to think, not a verdict -- a high score means "read these two and
decide", per the combine-or-extend test.

Usage:
  python skill_overlap_check.py skills/                         # registry sweep
  python skill_overlap_check.py skills/ --threshold 0.30 --json
  python skill_overlap_check.py skills/ --against "Use when generating idempotent EF Core migration scripts for production"
  python skill_overlap_check.py skills/ --against-file proposed.md --top 5

Exit codes:
  0  ran successfully AND no pair/proposal is at or above --threshold
  1  I/O or usage error
  3  ran successfully but at least one overlap is at or above --threshold (advisory:
     review before creating a new skill)
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOOL = "skill_overlap_check"

STOPWORDS = {
    "use", "when", "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with",
    "is", "are", "be", "by", "that", "this", "it", "its", "as", "at", "from", "into",
    "skill", "skills", "agent", "agents", "using", "via", "over", "across", "per",
    "not", "no", "any", "each", "which", "these", "those", "your", "you", "their",
    "run", "runs", "used", "usewhen", "e.g", "eg", "etc",
}


class UsageError(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def tokenize(text):
    """Lowercase significant terms (>=3 chars, not stopwords)."""
    words = re.findall(r"[a-z0-9][a-z0-9+.-]{2,}", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) >= 3}


def read_frontmatter_description(skill_md):
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    desc = ""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if m:
        fm = m.group(1)
        d = (re.search(r'description:\s*"([^"]+)"', fm)
             or re.search(r"description:\s*'([^']+)'", fm)
             or re.search(r"description:\s*[|>]-?\s*\n((?:[ \t]+.+\n?)+)", fm)
             or re.search(r"description:\s+([^\n\"'][^\n]+)", fm))
        if d:
            desc = " ".join(line.strip() for line in d.group(1).splitlines())
    title = ""
    tm = re.search(r"^#\s+(.+)$", text, re.M)
    if tm:
        title = tm.group(1)
    return (title + " " + desc).strip()


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_skills(skills_dir):
    skills = {}
    for sk in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        md = sk / "SKILL.md"
        if md.is_file():
            skills[sk.name] = tokenize(read_frontmatter_description(md))
    return skills


def main(argv=None):
    p = UsageError(prog="skill_overlap_check.py",
                   description="Deterministic anti-duplication check over a skills/ registry.")
    p.add_argument("skills_dir", help="path to the skills/ directory")
    p.add_argument("--against", metavar="TEXT",
                   help="compare a proposed skill's description text against existing skills")
    p.add_argument("--against-file", metavar="PATH",
                   help="like --against, but read the proposed description from a file")
    p.add_argument("--threshold", type=float, default=0.15,
                   help="overlap at or above this Jaccard score is flagged (default 0.15; "
                        "short frontmatter descriptions score low even when related, so "
                        "this is deliberately sensitive -- treat a flag as 'read both and decide')")
    p.add_argument("--top", type=int, default=10, help="how many results to show (default 10)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir():
        sys.stderr.write("%s: error: not a directory: %s\n" % (TOOL, skills_dir))
        return 1
    skills = load_skills(skills_dir)
    if not skills:
        sys.stderr.write("%s: error: no skills with SKILL.md under %s\n" % (TOOL, skills_dir))
        return 1

    flagged = False
    results = []

    if args.against or args.against_file:
        if args.against_file:
            f = Path(args.against_file)
            if not f.is_file():
                sys.stderr.write("%s: error: --against-file not found: %s\n" % (TOOL, f))
                return 1
            proposed_text = read_frontmatter_description(f) if f.suffix == ".md" else f.read_text(encoding="utf-8", errors="replace")
        else:
            proposed_text = args.against
        proposed = tokenize(proposed_text)
        scored = sorted(((jaccard(proposed, toks), name) for name, toks in skills.items()),
                        reverse=True)[:args.top]
        results = [{"skill": n, "overlap": round(s, 3),
                    "flag": s >= args.threshold} for s, n in scored]
        flagged = any(r["flag"] for r in results)
        mode = "against"
    else:
        names = list(skills)
        pairs = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                s = jaccard(skills[names[i]], skills[names[j]])
                pairs.append((s, names[i], names[j]))
        pairs.sort(reverse=True)
        top = pairs[:args.top]
        results = [{"skill_a": a, "skill_b": b, "overlap": round(s, 3),
                    "flag": s >= args.threshold} for s, a, b in top]
        flagged = any(r["flag"] for r in results)
        mode = "sweep"

    if args.json:
        print(json.dumps({"mode": mode, "skills_scanned": len(skills),
                          "threshold": args.threshold, "flagged": flagged,
                          "results": results}, indent=2))
    else:
        print("Skill overlap check (%s) -- %d skills, threshold %.2f"
              % (mode, len(skills), args.threshold))
        if mode == "against":
            print("Closest existing skills to the proposed description:")
            for r in results:
                mark = "  FLAG" if r["flag"] else "      "
                print("%s %.3f  %s" % (mark, r["overlap"], r["skill"]))
            if flagged:
                print("\nAt least one existing skill overlaps >= threshold. Apply the "
                      "combine-or-extend test before creating a new file "
                      "(see skill_discovery_design.md section 5).")
        else:
            print("Highest-overlap skill pairs:")
            for r in results:
                mark = "  FLAG" if r["flag"] else "      "
                print("%s %.3f  %s <-> %s" % (mark, r["overlap"], r["skill_a"], r["skill_b"]))
            if flagged:
                print("\nFlagged pairs share substantial capability vocabulary; read both "
                      "and confirm they are genuinely distinct.")
    return 3 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Deterministic memory-eviction planner for a JSONL memory store.

Part of the hybrid-rag-memory skill.

memory_evictor.py reads a memory store as JSON Lines (one memory item per
line) and applies a deterministic composite eviction policy: TTL / idle-age
expiry, exponential recency decay, hit frequency, a hard item-count cap, and
pinned-item protection. It emits the KEPT set and an EVICTED report (each with
a reason and the composite score that drove the decision).

The tool is FULLY DETERMINISTIC: given the same file and the same flags it
produces the same plan. It performs no embedding, no LLM call, and no network
access -- standard library only. Semantic-relevance filtering (rerank-before-
inject) is a RUNTIME concern that needs an embedding model and is therefore
out of scope for this portable script; it is owned by the sibling skill
rag-architect. This tool covers the deterministic axes only: age, recency,
frequency, and pinned protection. See
references/memory_eviction_and_consolidation.md for the full 8-rule policy.

Input format (one JSON object per line):
    id        string   memory identifier (falls back to "line-N" if absent)
    text      string   memory content (optional; truncated in reports)
    timestamp string   ISO-8601 creation time (alias: "created")
    last_used string   ISO-8601 last-access time (optional; default timestamp)
    hits      integer  access/reference count (optional; default 0)
    pinned    boolean  protection flag (optional; default false)

Composite keep score (higher = keep) for a non-pinned candidate:
    recency = 0.5 ** (idle_days / half_life_days)          # in [0, 1]
    freq    = hits / (hits + freq_saturation)              # in [0, 1)
    score   = (rw * recency + fw * freq) / (rw + fw)       # in [0, 1]
where rw = --recency-weight, fw = --frequency-weight.

Eviction order:
    1. Pinned items are KEPT (reason "pinned") unless --evict-pinned is set.
    2. Non-pinned items idle longer than --ttl-days are EVICTED ("ttl_expired").
    3. Remaining candidates are ranked by score; the top (--max-items minus the
       protected count) are KEPT ("within_capacity"); the rest are EVICTED
       ("over_capacity"). Pinned protection can push the kept total above
       --max-items -- protection wins over the cap by design.

"now" defaults to the latest timestamp observed in the store (so the plan is
reproducible from the file alone); override with --now.

Usage examples:
    python memory_evictor.py store.jsonl
    python memory_evictor.py store.jsonl --max-items 100 --ttl-days 90
    python memory_evictor.py store.jsonl --json > plan.json
    python memory_evictor.py store.jsonl --evict-pinned --strict

Exit codes:
    0  eviction plan produced (eviction is a finding, not a tool error)
    1  I/O or usage error (missing/unreadable file, bad arguments), or a
       malformed JSONL line when --strict is set

Console output is ASCII-safe: no emoji, no box-drawing, no non-ASCII glyphs,
so it renders on Windows cp1252 consoles.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL_NAME = "memory_evictor"
FREQ_SATURATION = 3.0  # hits needed for the frequency term to reach 0.5


# ---------------------------------------------------------------------------
# Timestamp parsing (stdlib only; tolerant of trailing 'Z' and date-only).
# All timestamps are normalized to naive UTC for delta arithmetic.
# ---------------------------------------------------------------------------
def parse_ts(value):
    """Parse an ISO-8601-ish timestamp into naive-UTC datetime, or None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = text
    if candidate.endswith("Z") or candidate.endswith("z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def days_between(later, earlier):
    """Non-negative day delta between two naive datetimes (0.0 if unknown)."""
    if later is None or earlier is None:
        return 0.0
    delta = (later - earlier).total_seconds() / 86400.0
    return delta if delta > 0.0 else 0.0


def truncate(text, width=60):
    text = " ".join(str(text).split())
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_items(content, strict=False):
    """Parse JSONL content into a list of normalized item dicts.

    Returns (items, warnings). Raises ValueError on a malformed line when
    strict is True.
    """
    items = []
    warnings = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            msg = "line %d: invalid JSON (%s)" % (lineno, exc)
            if strict:
                raise ValueError(msg)
            warnings.append("skipped " + msg)
            continue
        if not isinstance(obj, dict):
            msg = "line %d: expected a JSON object" % lineno
            if strict:
                raise ValueError(msg)
            warnings.append("skipped " + msg)
            continue

        item_id = obj.get("id")
        if item_id is None or str(item_id).strip() == "":
            item_id = "line-%d" % lineno
        created = parse_ts(obj.get("timestamp", obj.get("created")))
        last_used = parse_ts(obj.get("last_used"))
        if last_used is None:
            last_used = created
        hits_raw = obj.get("hits", 0)
        try:
            hits = int(hits_raw)
        except (TypeError, ValueError):
            hits = 0
            warnings.append("line %d: non-integer hits, treated as 0" % lineno)
        if hits < 0:
            hits = 0
        pinned = bool(obj.get("pinned", False))

        items.append({
            "id": str(item_id),
            "text": obj.get("text", ""),
            "created": created,
            "last_used": last_used,
            "hits": hits,
            "pinned": pinned,
            "lineno": lineno,
        })
    return items, warnings


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
def resolve_now(items, now_arg):
    if now_arg:
        parsed = parse_ts(now_arg)
        if parsed is None:
            raise ValueError("could not parse --now value: %s" % now_arg)
        return parsed
    latest = None
    for it in items:
        for key in ("last_used", "created"):
            ts = it[key]
            if ts is not None and (latest is None or ts > latest):
                latest = ts
    if latest is None:
        latest = datetime.utcnow().replace(microsecond=0)
    return latest


def score_item(item, now, half_life_days, recency_weight, frequency_weight):
    idle_days = days_between(now, item["last_used"])
    recency = 0.5 ** (idle_days / half_life_days) if half_life_days > 0 else 0.0
    freq = item["hits"] / (item["hits"] + FREQ_SATURATION)
    weight_sum = recency_weight + frequency_weight
    if weight_sum <= 0:
        composite = 0.0
    else:
        composite = (recency_weight * recency + frequency_weight * freq) / weight_sum
    return idle_days, round(composite, 6)


def plan_eviction(items, now, max_items, ttl_days, keep_pinned,
                  half_life_days, recency_weight, frequency_weight):
    enriched = []
    for it in items:
        idle_days, score = score_item(
            it, now, half_life_days, recency_weight, frequency_weight)
        age_days = days_between(now, it["created"])
        enriched.append({
            "id": it["id"],
            "text": truncate(it["text"]),
            "pinned": it["pinned"],
            "hits": it["hits"],
            "age_days": round(age_days, 3),
            "idle_days": round(idle_days, 3),
            "score": score,
        })

    kept, evicted = [], []
    candidates = []
    for e in enriched:
        if e["pinned"] and keep_pinned:
            row = dict(e)
            row["reason"] = "pinned"
            kept.append(row)
        elif ttl_days is not None and e["idle_days"] > ttl_days:
            row = dict(e)
            row["reason"] = "ttl_expired"
            evicted.append(row)
        else:
            candidates.append(e)

    # Deterministic ranking: score desc, then more-recent (lower idle) first,
    # then id ascending as a final tie-breaker.
    candidates.sort(key=lambda e: (-e["score"], e["idle_days"], e["id"]))

    slots = max_items - len(kept)
    if slots < 0:
        slots = 0
    for rank, e in enumerate(candidates):
        row = dict(e)
        if rank < slots:
            row["reason"] = "within_capacity"
            kept.append(row)
        else:
            row["reason"] = "over_capacity"
            evicted.append(row)

    kept.sort(key=lambda e: (-e["score"], e["id"]))
    evicted.sort(key=lambda e: (-e["score"], e["id"]))
    return kept, evicted


def build_result(store_path, now, items, kept, evicted, policy, warnings):
    return {
        "tool": TOOL_NAME,
        "store": store_path,
        "now": now.isoformat(),
        "policy": policy,
        "total": len(items),
        "kept_count": len(kept),
        "evicted_count": len(evicted),
        "kept": kept,
        "evicted": evicted,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def format_human(result):
    lines = []
    lines.append("memory_evictor: %s" % result["store"])
    lines.append("reference now : %s" % result["now"])
    p = result["policy"]
    lines.append(
        "policy        : max_items=%s ttl_days=%s keep_pinned=%s "
        "half_life=%s recency_w=%s frequency_w=%s"
        % (p["max_items"], p["ttl_days"], p["keep_pinned"], p["half_life_days"],
           p["recency_weight"], p["frequency_weight"]))
    lines.append("total=%d  kept=%d  evicted=%d"
                 % (result["total"], result["kept_count"], result["evicted_count"]))
    lines.append("")

    def table(title, rows):
        out = [title]
        if not rows:
            out.append("  (none)")
            return out
        out.append("  %-24s %7s %6s %8s %9s  %s"
                   % ("ID", "SCORE", "HITS", "AGE_D", "IDLE_D", "REASON"))
        for r in rows:
            out.append("  %-24s %7.3f %6d %8.1f %9.1f  %s"
                       % (truncate(r["id"], 24), r["score"], r["hits"],
                          r["age_days"], r["idle_days"], r["reason"]))
        return out

    lines.extend(table("KEPT:", result["kept"]))
    lines.append("")
    lines.extend(table("EVICTED:", result["evicted"]))

    if result["warnings"]:
        lines.append("")
        lines.append("WARNINGS:")
        for w in result["warnings"]:
            lines.append("  - " + w)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors (spec contract)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        sys.exit(1)


def build_parser():
    parser = UsageErrorParser(
        prog=TOOL_NAME,
        description=(
            "Deterministically plan eviction over a JSONL memory store using a "
            "composite TTL + recency + frequency policy with pinned-item "
            "protection. No embeddings, no LLM, no network. Eviction is a "
            "finding, not an error: the process exits 0 whenever the plan runs."),
        epilog=(
            "Semantic-relevance filtering is a runtime concern owned by "
            "rag-architect and is intentionally NOT computed here."),
    )
    parser.add_argument(
        "store", help="path to the JSONL memory store (one item per line)")
    parser.add_argument(
        "--max-items", type=int, default=50, metavar="N",
        help="hard cap on kept items (default 50; pinned protection may exceed it)")
    parser.add_argument(
        "--ttl-days", type=float, default=None, metavar="D",
        help="evict non-pinned items idle more than D days (default: no TTL)")
    parser.add_argument(
        "--half-life", type=float, default=30.0, metavar="D", dest="half_life",
        help="recency decay half-life in days (default 30)")
    parser.add_argument(
        "--recency-weight", type=float, default=1.0, metavar="W",
        help="weight of the recency term in the composite score (default 1.0)")
    parser.add_argument(
        "--frequency-weight", type=float, default=1.0, metavar="W",
        help="weight of the frequency term in the composite score (default 1.0)")
    pinned = parser.add_mutually_exclusive_group()
    pinned.add_argument(
        "--keep-pinned", dest="keep_pinned", action="store_true", default=True,
        help="protect pinned items from eviction (default)")
    pinned.add_argument(
        "--evict-pinned", dest="keep_pinned", action="store_false",
        help="subject pinned items to TTL and capacity like any other item")
    parser.add_argument(
        "--now", default=None, metavar="ISO",
        help="reference 'now' (ISO-8601); default = latest timestamp in the store")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit 1 on any malformed JSONL line instead of skipping it")
    parser.add_argument(
        "--json", action="store_true",
        help="emit the plan as machine-readable JSON instead of text")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_items < 0:
        sys.stderr.write("%s: error: --max-items must be >= 0\n" % TOOL_NAME)
        return 1
    if args.half_life <= 0:
        sys.stderr.write("%s: error: --half-life must be > 0\n" % TOOL_NAME)
        return 1
    if args.ttl_days is not None and args.ttl_days < 0:
        sys.stderr.write("%s: error: --ttl-days must be >= 0\n" % TOOL_NAME)
        return 1

    path = Path(args.store)
    if not path.exists():
        sys.stderr.write("%s: error: file not found: %s\n" % (TOOL_NAME, path))
        return 1
    if not path.is_file():
        sys.stderr.write("%s: error: not a regular file: %s\n" % (TOOL_NAME, path))
        return 1
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write("%s: error: cannot read %s: %s\n" % (TOOL_NAME, path, exc))
        return 1

    try:
        items, warnings = load_items(content, strict=args.strict)
    except ValueError as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL_NAME, exc))
        return 1

    try:
        now = resolve_now(items, args.now)
    except ValueError as exc:
        sys.stderr.write("%s: error: %s\n" % (TOOL_NAME, exc))
        return 1

    kept, evicted = plan_eviction(
        items, now, args.max_items, args.ttl_days, args.keep_pinned,
        args.half_life, args.recency_weight, args.frequency_weight)

    policy = {
        "max_items": args.max_items,
        "ttl_days": args.ttl_days,
        "keep_pinned": args.keep_pinned,
        "half_life_days": args.half_life,
        "recency_weight": args.recency_weight,
        "frequency_weight": args.frequency_weight,
        "freq_saturation": FREQ_SATURATION,
    }
    result = build_result(str(path), now, items, kept, evicted, policy, warnings)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

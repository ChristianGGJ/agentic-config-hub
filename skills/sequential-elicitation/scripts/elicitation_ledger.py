#!/usr/bin/env python3
"""elicitation_ledger.py - deterministic governor of the sequential-elicitation loop.

Part of the sequential-elicitation skill (agentic-config-hub).

The governor NEVER generates questions. Question generation is the LLM's job,
guided by this skill's references/. This tool decides exactly one thing,
deterministically: given the agenda and the append-only JSONL ledger, is the
questioning loop still legal to continue, or has an exit condition fired?

Exit-condition authority: the hub six-type taxonomy in
loop_engineering_patterns.md (agentic-system-architect flagship), duplicated
here per the hub portability rule and instantiated for dialogue:

  max_iterations     question budget consumed (records >= --max-questions)
  no_progress        saturation: the last K records yielded zero new_facts
  oscillation        a decision key revisits an abandoned value inside a
                     ring buffer of its last 4 assignments (A-B-A-B)
  budget             wall-clock ceiling between first and last record
                     exceeded (--max-minutes; disabled when omitted)
  success_predicate  every CRITICAL agenda area resolved or explicitly
                     deferred with a named owner (--require-all widens the
                     predicate to every area)
  escalation_trigger a ledger record carries an "escalation" marker (an
                     answer revealed irreversible or compliance territory)

EXIT CODES (read this before wiring the tool into a loop):
  0  CONTINUE permitted - no exit condition fired
  1  STOP - one or more exit conditions FIRED; each is named in the report.
     Exit 1 includes success_predicate: stopping on success is still a stop
     signal, not a defect. STOP means stop and report, never retry.
  2  usage / input error - malformed ledger, agenda, or flag value

This follows the hub-wide 0/1/2 = pass / gate-signal / input-error contract
(the same contract as plan-baseline-tracking's baseline_variance.py and the
loop_auditor --min-score gate). The alternative 0/2/1 precedent from
self-eval's score_history.py was considered and rejected for hub CI
consistency; the decision is documented in SKILL.md.

Bonus mode: --seed-from <blind_spot_report.json> converts a blind-spot-audit
findings list into an agenda JSON (mapping documented in SKILL.md) and
prints it to stdout.
"""

import argparse
import json
import sys
from datetime import datetime

EXIT_CONTINUE = 0
EXIT_STOP = 1
EXIT_ERROR = 2

EXIT_TYPES = (
    "max_iterations",
    "no_progress",
    "oscillation",
    "budget",
    "success_predicate",
    "escalation_trigger",
)
CRITICALITY = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
DEFAULT_MAX_QUESTIONS = 12
DEFAULT_SATURATION_WINDOW = 3
OSCILLATION_WINDOW = 4


class InputError(Exception):
    """Raised for any malformed input; always maps to exit code 2."""


# ---------------------------------------------------------------- loading

def parse_timestamp(value, where):
    if not isinstance(value, str) or not value.strip():
        raise InputError("%s: 'timestamp' must be a non-empty ISO 8601 string" % where)
    text = value.strip()
    if text.endswith("Z"):
        # datetime.fromisoformat rejects a Z suffix before Python 3.11
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise InputError("%s: timestamp %r is not ISO 8601" % (where, value))


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise InputError("cannot read %s file %r: %s" % (what, path, exc))
    except json.JSONDecodeError as exc:
        raise InputError("%s file %r is not valid JSON: %s" % (what, path, exc))


def load_agenda(path):
    data = load_json(path, "agenda")
    if not isinstance(data, dict):
        raise InputError("agenda must be a JSON object")
    raw_areas = data.get("areas")
    if not isinstance(raw_areas, list) or not raw_areas:
        raise InputError("agenda must contain a non-empty 'areas' array")
    seen = set()
    areas = []
    for idx, raw in enumerate(raw_areas):
        where = "agenda area #%d" % (idx + 1)
        if not isinstance(raw, dict):
            raise InputError("%s: must be an object" % where)
        area_id = raw.get("id")
        if not isinstance(area_id, str) or not area_id.strip():
            raise InputError("%s: 'id' must be a non-empty string" % where)
        area_id = area_id.strip()
        if area_id in seen:
            raise InputError("%s: duplicate area id %r" % (where, area_id))
        seen.add(area_id)
        crit = str(raw.get("criticality", "")).strip().upper()
        if crit not in CRITICALITY:
            raise InputError("%s (%s): 'criticality' must be one of %s"
                             % (where, area_id, "|".join(CRITICALITY)))
        expected = raw.get("expected_questions", 1)
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise InputError("%s (%s): 'expected_questions' must be a positive integer"
                             % (where, area_id))
        areas.append({
            "id": area_id,
            "criticality": crit,
            "concern": str(raw.get("concern", "")).strip(),
            "expected_questions": expected,
        })
    agenda_max = None
    budget = data.get("budget", {})
    if isinstance(budget, dict) and "max_questions" in budget:
        agenda_max = budget["max_questions"]
        if not isinstance(agenda_max, int) or isinstance(agenda_max, bool) or agenda_max < 1:
            raise InputError("agenda budget.max_questions must be a positive integer")
    return {
        "brief": str(data.get("brief", "")).strip(),
        "areas": areas,
        "max_questions": agenda_max,
    }


def load_ledger(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        raise InputError("cannot read ledger file %r: %s" % (path, exc))
    records = []
    last_seq = None
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        where = "ledger line %d" % lineno
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InputError("%s: invalid JSON: %s" % (where, exc))
        if not isinstance(rec, dict):
            raise InputError("%s: each ledger line must be a JSON object" % where)
        seq = rec.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise InputError("%s: 'seq' must be an integer" % where)
        if last_seq is not None and seq <= last_seq:
            raise InputError("%s: seq %d does not increase over previous seq %d "
                             "(the ledger is append-only)" % (where, seq, last_seq))
        last_seq = seq
        rec["_ts"] = parse_timestamp(rec.get("timestamp"), where)
        for field in ("area", "question", "answer_summary", "decision_key"):
            if not isinstance(rec.get(field), str):
                raise InputError("%s: %r must be a string" % (where, field))
        for field in ("new_facts", "areas_remaining"):
            value = rec.get(field)
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise InputError("%s: %r must be an array of strings" % (where, field))
        if not isinstance(rec.get("deferrals", []), list):
            raise InputError("%s: 'deferrals' must be an array when present" % where)
        records.append(rec)
    return records


def seed_agenda(report):
    """Map a blind_spot_report.json findings list onto an agenda JSON.

    Mapping (documented in SKILL.md): finding.id -> area.id;
    finding.severity -> area.criticality; finding.concern -> area.concern;
    status 'covered' is skipped; expected_questions = 2 for CRITICAL/HIGH,
    1 otherwise; prerequisite_note and source status are carried through.
    """
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        raise InputError("blind-spot report must be an object with a 'findings' array")
    areas = []
    seen = set()
    for idx, finding in enumerate(report["findings"]):
        where = "finding #%d" % (idx + 1)
        if not isinstance(finding, dict):
            raise InputError("%s: must be an object" % where)
        status = str(finding.get("status", "")).strip().lower()
        if status == "covered":
            continue
        if status not in ("missing", "partial"):
            raise InputError("%s: 'status' must be covered|partial|missing" % where)
        fid = str(finding.get("id", "")).strip()
        if not fid:
            raise InputError("%s: 'id' is required" % where)
        if fid in seen:
            raise InputError("%s: duplicate finding id %r" % (where, fid))
        seen.add(fid)
        severity = str(finding.get("severity", "")).strip().upper()
        if severity not in CRITICALITY:
            raise InputError("%s (%s): 'severity' must be one of %s"
                             % (where, fid, "|".join(CRITICALITY)))
        area = {
            "id": fid,
            "criticality": severity,
            "concern": str(finding.get("concern", "")).strip(),
            "expected_questions": 2 if severity in ("CRITICAL", "HIGH") else 1,
            "source_status": status,
        }
        note = finding.get("prerequisite_note")
        if note:
            area["prerequisite_note"] = str(note)
        areas.append(area)
    if not areas:
        raise InputError("no open findings (status partial|missing) to seed an agenda from")
    return {
        "brief": str(report.get("brief", "")).strip(),
        "budget": {"max_questions": DEFAULT_MAX_QUESTIONS},
        "areas": areas,
    }


# ---------------------------------------------------------------- checks

def nonempty_facts(record):
    return [fact for fact in record["new_facts"] if fact.strip()]


def check_max_iterations(records, max_questions):
    used = len(records)
    if used >= max_questions:
        return True, ("%d of %d question(s) used - budget consumed, no further "
                      "question is permitted" % (used, max_questions))
    return False, "%d of %d question(s) used" % (used, max_questions)


def check_no_progress(records, window):
    if len(records) < window:
        return False, ("only %d record(s); saturation window is %d"
                       % (len(records), window))
    tail = records[-window:]
    if all(not nonempty_facts(rec) for rec in tail):
        seqs = ", ".join(str(rec["seq"]) for rec in tail)
        return True, ("last %d record(s) (seq %s) yielded zero new_facts - "
                      "the dialogue is saturated" % (window, seqs))
    return False, "at least one of the last %d record(s) yielded new facts" % window


def check_oscillation(records, window):
    history = {}
    order = []
    for rec in records:
        raw = rec["decision_key"].strip()
        if not raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in history:
            history[key] = []
            order.append(key)
        history[key].append((rec["seq"], value))
    hits = []
    for key in order:
        recent = history[key][-window:]
        values = [value for _, value in recent]
        fired = False
        for j in range(2, len(values)):
            for i in range(j - 1):
                if values[j] == values[i] and values[j] != values[j - 1]:
                    fired = True
                    break
            if fired:
                break
        if fired:
            pattern = " -> ".join(value if value else "(unset)" for value in values)
            seqs = ", ".join(str(seq) for seq, _ in recent)
            hits.append("key '%s' revisits an abandoned value: %s (seq %s)"
                        % (key, pattern, seqs))
    if hits:
        return True, ("; ".join(hits) + " - freeze the key(s), present both prior "
                      "answers, and escalate for an explicit override; do not re-ask")
    return False, ("no decision key revisits an abandoned value within its last %d "
                   "assignment(s)" % window)


def check_budget(records, max_minutes):
    if max_minutes is None:
        return False, "wall-clock ceiling not configured (--max-minutes)"
    if len(records) < 2:
        return False, ("fewer than 2 records; elapsed wall-clock is 0.0 minute(s) "
                       "(ceiling %d)" % max_minutes)
    elapsed = (records[-1]["_ts"] - records[0]["_ts"]).total_seconds() / 60.0
    if elapsed > max_minutes:
        return True, ("elapsed %.1f minute(s) between first and last record exceeds "
                      "the %d-minute ceiling" % (elapsed, max_minutes))
    return False, ("elapsed %.1f minute(s) within the %d-minute ceiling"
                   % (elapsed, max_minutes))


def area_stats(agenda, records):
    latest_remaining = set(records[-1]["areas_remaining"]) if records else None
    deferred = {}
    for rec in records:
        for item in rec.get("deferrals", []):
            if isinstance(item, dict):
                area = str(item.get("area", "")).strip()
                owner = str(item.get("owner", "")).strip()
                if area and owner:
                    deferred[area] = owner
    stats = []
    for area in agenda["areas"]:
        area_id = area["id"]
        mine = [rec for rec in records if rec["area"] == area_id]
        questions = len(mine)
        facts = sum(len(nonempty_facts(rec)) for rec in mine)
        coverage = min(100, int(round(100.0 * questions / area["expected_questions"])))
        if area_id in deferred:
            status = "deferred"
        elif questions == 0:
            status = "untouched"
        elif latest_remaining is not None and area_id not in latest_remaining:
            status = "resolved"
        else:
            status = "open"
        stats.append({
            "id": area_id,
            "criticality": area["criticality"],
            "questions": questions,
            "facts": facts,
            "coverage_pct": coverage,
            "status": status,
            "deferred_to": deferred.get(area_id),
        })
    return stats


def check_success(stats, records, require_all):
    if not records:
        return False, "no records yet; the predicate needs at least one exchange"
    scope = [s for s in stats if s["criticality"] == "CRITICAL"]
    label = "CRITICAL"
    if require_all:
        scope = stats
        label = "all"
    elif not scope:
        scope = stats
        label = "all (agenda declares no CRITICAL area)"
    open_ids = [s["id"] for s in scope if s["status"] not in ("resolved", "deferred")]
    if not open_ids:
        return True, ("every %s agenda area is resolved or deferred with a named "
                      "owner - the elicitation goal is met" % label)
    return False, "%s area(s) still open: %s" % (label, ", ".join(open_ids))


def check_escalation(records):
    hits = []
    for rec in records:
        marker = rec.get("escalation")
        if marker:
            reason = marker if isinstance(marker, str) else "escalation flag set"
            hits.append("seq %d: %s" % (rec["seq"], reason))
    if hits:
        return True, ("; ".join(hits) + " - route to a human before any further "
                      "questioning")
    return False, "no record carries an escalation marker"


def collect_warnings(agenda, records):
    known = {area["id"] for area in agenda["areas"]}
    warnings = []
    for rec in records:
        if rec["area"] not in known:
            warnings.append("record seq %d targets area %r which is not in the "
                            "agenda; append emergent areas to the agenda instead of "
                            "questioning off-book" % (rec["seq"], rec["area"]))
    if records:
        for area_id in records[-1]["areas_remaining"]:
            if area_id not in known:
                warnings.append("latest areas_remaining names %r which is not in "
                                "the agenda" % area_id)
    return warnings


def pick_next_area(stats):
    rank = {crit: pos for pos, crit in enumerate(CRITICALITY)}
    candidates = [s for s in stats if s["status"] in ("open", "untouched")]
    if not candidates:
        return None
    return min(candidates, key=lambda s: (rank[s["criticality"]], s["questions"]))


# ---------------------------------------------------------------- report

def analyze(agenda, records, options):
    stats = area_stats(agenda, records)
    checks = {
        "max_iterations": check_max_iterations(records, options["max_questions"]),
        "no_progress": check_no_progress(records, options["saturation_window"]),
        "oscillation": check_oscillation(records, OSCILLATION_WINDOW),
        "budget": check_budget(records, options["max_minutes"]),
        "success_predicate": check_success(stats, records, options["require_all"]),
        "escalation_trigger": check_escalation(records),
    }
    fired = [name for name in EXIT_TYPES if checks[name][0]]
    verdict = "STOP" if fired else "CONTINUE"
    next_area = None if fired else pick_next_area(stats)
    closed = sum(1 for s in stats if s["status"] in ("resolved", "deferred"))
    return {
        "brief": agenda["brief"],
        "records": len(records),
        "config": {
            "max_questions": options["max_questions"],
            "saturation_window": options["saturation_window"],
            "oscillation_window": OSCILLATION_WINDOW,
            "max_minutes": options["max_minutes"],
            "require_all": options["require_all"],
        },
        "areas": stats,
        "areas_closed": closed,
        "checks": {name: {"fired": flag, "detail": detail}
                   for name, (flag, detail) in checks.items()},
        "fired": fired,
        "warnings": collect_warnings(agenda, records),
        "verdict": verdict,
        "next_area": next_area["id"] if next_area else None,
        "exit_code": EXIT_STOP if fired else EXIT_CONTINUE,
    }


def render_text(report):
    lines = []
    lines.append("ELICITATION LOOP GOVERNOR (sequential-elicitation)")
    lines.append("Brief   : %s" % (report["brief"] or "-"))
    cfg = report["config"]
    ceiling = "%d min" % cfg["max_minutes"] if cfg["max_minutes"] else "off"
    lines.append("Records : %d | question budget: %d | saturation window: %d | "
                 "oscillation window: %d | wall-clock ceiling: %s"
                 % (report["records"], cfg["max_questions"], cfg["saturation_window"],
                    cfg["oscillation_window"], ceiling))
    lines.append("")
    lines.append("AGENDA COVERAGE")
    id_width = max([len(s["id"]) for s in report["areas"]] + [4])
    lines.append("  %-*s  %-9s  %9s  %5s  %8s  %s"
                 % (id_width, "area", "crit", "questions", "facts", "coverage", "status"))
    for stat in report["areas"]:
        status = stat["status"]
        if status == "deferred" and stat["deferred_to"]:
            status = "deferred -> %s" % stat["deferred_to"]
        lines.append("  %-*s  %-9s  %9d  %5d  %7d%%  %s"
                     % (id_width, stat["id"], stat["criticality"], stat["questions"],
                        stat["facts"], stat["coverage_pct"], status))
    total = len(report["areas"])
    pct = int(round(100.0 * report["areas_closed"] / total)) if total else 0
    lines.append("  closed %d of %d area(s) (%d%%)" % (report["areas_closed"], total, pct))
    lines.append("")
    lines.append("EXIT-CONDITION CHECKS (six-type taxonomy; authority: "
                 "loop_engineering_patterns.md, agentic-system-architect)")
    for name in EXIT_TYPES:
        check = report["checks"][name]
        flag = "FIRED" if check["fired"] else "clear"
        lines.append("  [%-5s] %-18s %s" % (flag, name, check["detail"]))
    if report["warnings"]:
        lines.append("")
        lines.append("WARNINGS")
        for warning in report["warnings"]:
            lines.append("  - %s" % warning)
    lines.append("")
    if report["verdict"] == "STOP":
        lines.append("VERDICT: STOP - fired: %s" % ", ".join(report["fired"]))
        lines.append("Exit code 1: STOP means stop and report. Hand the ledger and this")
        lines.append("report to the consuming workflow's gate. Do not ask another question.")
    else:
        stat = next((s for s in report["areas"] if s["id"] == report["next_area"]), None)
        if stat:
            lines.append("VERDICT: CONTINUE - next area: %s (%s, %d question(s) so far)"
                         % (stat["id"], stat["criticality"], stat["questions"]))
        else:
            lines.append("VERDICT: CONTINUE")
        lines.append("Exit code 0: the loop MAY ask one more question (max 3 only when")
        lines.append("tightly coupled). The governor names the next AREA, never the question.")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def build_parser():
    parser = argparse.ArgumentParser(
        prog="elicitation_ledger.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=("Deterministic governor of a bounded sequential-elicitation "
                     "dialogue: analyzes an append-only JSONL ledger against an "
                     "agenda and reports whether an exit condition from the hub "
                     "six-type taxonomy has fired. Never generates questions."),
        epilog="""exit codes (hub 0/1/2 contract; exit 1 is a semantic stop-signal):
  0  CONTINUE permitted - no exit condition fired
  1  STOP - an exit condition FIRED (named in the report); includes
     success_predicate, because stopping on success is still stopping
  2  usage / input error

examples:
  python elicitation_ledger.py --agenda agenda.json --ledger ledger.jsonl
  python elicitation_ledger.py --agenda agenda.json --ledger ledger.jsonl --json
  python elicitation_ledger.py --seed-from blind_spot_report.json > agenda.json
""")
    parser.add_argument("--ledger", metavar="FILE",
                        help="elicitation ledger (JSONL, one record per line, append-only)")
    parser.add_argument("--agenda", metavar="FILE",
                        help="agenda JSON: open concern areas with criticality")
    parser.add_argument("--seed-from", metavar="FILE", dest="seed_from",
                        help="standalone mode: convert a blind_spot_report.json "
                             "findings list into an agenda JSON on stdout, then exit 0")
    parser.add_argument("--max-questions", type=int, default=None, metavar="N",
                        help="question budget (max_iterations); overrides the agenda's "
                             "budget.max_questions; default %d" % DEFAULT_MAX_QUESTIONS)
    parser.add_argument("--saturation-window", type=int, default=DEFAULT_SATURATION_WINDOW,
                        metavar="K",
                        help="no_progress fires when the last K records carry zero "
                             "new_facts (default %d)" % DEFAULT_SATURATION_WINDOW)
    parser.add_argument("--max-minutes", type=int, default=None, metavar="M",
                        help="budget fires when wall-clock between first and last "
                             "record exceeds M minutes (disabled when omitted)")
    parser.add_argument("--require-all", action="store_true",
                        help="widen success_predicate from CRITICAL areas to every area")
    parser.add_argument("--json", action="store_true",
                        help="emit the machine-readable report object instead of text")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.seed_from:
            if args.ledger or args.agenda:
                raise InputError("--seed-from is a standalone mode; do not combine "
                                 "it with --ledger/--agenda")
            agenda = seed_agenda(load_json(args.seed_from, "blind-spot report"))
            print(json.dumps(agenda, indent=2))
            return EXIT_CONTINUE
        if not args.ledger or not args.agenda:
            raise InputError("--ledger and --agenda are both required "
                             "(or use --seed-from)")
        if args.saturation_window < 1:
            raise InputError("--saturation-window must be >= 1")
        if args.max_questions is not None and args.max_questions < 1:
            raise InputError("--max-questions must be >= 1")
        if args.max_minutes is not None and args.max_minutes < 1:
            raise InputError("--max-minutes must be >= 1")
        agenda = load_agenda(args.agenda)
        records = load_ledger(args.ledger)
        max_questions = (args.max_questions or agenda["max_questions"]
                         or DEFAULT_MAX_QUESTIONS)
        report = analyze(agenda, records, {
            "max_questions": max_questions,
            "saturation_window": args.saturation_window,
            "max_minutes": args.max_minutes,
            "require_all": args.require_all,
        })
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(render_text(report))
        return report["exit_code"]
    except InputError as exc:
        print("INPUT ERROR: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())

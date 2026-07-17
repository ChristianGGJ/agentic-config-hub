#!/usr/bin/env python3
"""stakeholder_register_validator.py - deterministic gate for a stakeholder register.

Validates a stakeholder_register.json against the hub shared contract:

    {
      "project": str,
      "stakeholders": [
        {
          "id": str, "role": str,
          "category": "user|operator|supplier|regulator|sponsor|third_party",
          "interest": "low|medium|high", "influence": "low|medium|high",
          "inference_basis": str, "engagement": str
        }
      ]
    }

Checks (rule ids are stable and cited in SKILL.md):
  V0  project field present and non-empty                          (MEDIUM)
  V1  required fields per entry present and non-empty              (HIGH)
  V2  category from the closed six-value enum                      (HIGH)
  V3  no duplicate stakeholder ids                                 (HIGH)
  V4  coverage: every category represented or explicitly waived
      via --waive category:reason; a missing regulator or supplier
      is the classic blind spot                                    (HIGH)
      other missing categories                                     (MEDIUM)
  V5  influence and interest values from the low|medium|high enum  (HIGH)
  V6  inference_basis non-empty - an entry without a stated basis
      is an unsupported guess                                      (MEDIUM)
  V7  advisory: when influence and interest are unambiguous
      (low/high) and engagement spells a Mendelow quadrant label,
      the label must match the computed quadrant                   (LOW)

Exit codes:
  0  register valid (no findings)
  1  findings reported (any severity)
  2  usage or input error (missing file, malformed JSON, bad --waive)

Deterministic, offline, Python 3.8+ standard library only.
No LLM calls, no network calls. Same input, same output, every run.
"""

import argparse
import json
import os
import sys

TOOL_NAME = "stakeholder_register_validator"

CATEGORIES = ["user", "operator", "supplier", "regulator", "sponsor", "third_party"]
BLIND_SPOT_CATEGORIES = ("regulator", "supplier")
LEVELS = ["low", "medium", "high"]
ENTRY_REQUIRED_FIELDS = ["id", "role", "category", "interest", "influence", "engagement"]

# Mendelow power-interest grid: (influence, interest) -> engagement quadrant.
# medium values are deliberately absent: the 2x2 grid is high/low and the
# human gate resolves ambiguous bands, not this script.
MENDELOW_QUADRANTS = {
    ("high", "high"): "manage_closely",
    ("high", "low"): "keep_satisfied",
    ("low", "high"): "keep_informed",
    ("low", "low"): "monitor",
}
KNOWN_ENGAGEMENT_LABELS = set(MENDELOW_QUADRANTS.values())


def is_nonempty_str(value):
    """True when value is a string with visible content."""
    return isinstance(value, str) and value.strip() != ""


def normalize_engagement(value):
    """Normalize an engagement label for quadrant comparison."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_waivers(raw_waivers):
    """Parse repeated --waive category:reason arguments into a dict.

    Raises ValueError with an explanation on any malformed waiver.
    """
    waivers = {}
    for raw in raw_waivers:
        category, sep, reason = raw.partition(":")
        category = category.strip()
        reason = reason.strip()
        if sep != ":" or reason == "":
            raise ValueError(
                "malformed --waive '%s': expected category:reason with a "
                "non-empty reason" % raw)
        if category not in CATEGORIES:
            raise ValueError(
                "unknown waiver category '%s': must be one of %s"
                % (category, "|".join(CATEGORIES)))
        waivers[category] = reason
    return waivers


def load_register(path):
    """Load and shape-check the register file. Raises ValueError on input errors."""
    if not os.path.isfile(path):
        raise ValueError("register file not found: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed JSON in %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ValueError("register root must be a JSON object")
    stakeholders = data.get("stakeholders")
    if not isinstance(stakeholders, list):
        raise ValueError("register must contain a 'stakeholders' array")
    return data


def entry_label(entry, index):
    """Stable human label for an entry: its id when usable, else its position."""
    if isinstance(entry, dict) and is_nonempty_str(entry.get("id")):
        return "entry '%s'" % entry["id"].strip()
    return "entry #%d" % (index + 1)


def validate(register, waivers):
    """Run all checks. Returns (findings, notes, covered_categories)."""
    findings = []
    notes = []

    def add(rule, severity, where, message):
        findings.append({
            "rule": rule, "severity": severity,
            "where": where, "message": message,
        })

    # V0 - top-level project field (part of the shared contract).
    if not is_nonempty_str(register.get("project")):
        add("V0", "MEDIUM", "project",
            "top-level 'project' field is missing or empty; the register "
            "must name the project it belongs to")

    seen_ids = {}
    covered = set()
    stakeholders = register["stakeholders"]

    for index, entry in enumerate(stakeholders):
        label = entry_label(entry, index)
        if not isinstance(entry, dict):
            add("V1", "HIGH", label, "entry is not a JSON object")
            continue

        # V1 - required fields (inference_basis is owned by V6).
        missing = [f for f in ENTRY_REQUIRED_FIELDS
                   if not is_nonempty_str(entry.get(f))]
        if missing:
            add("V1", "HIGH", label,
                "missing or empty required field(s): %s" % ", ".join(missing))

        # V2 - category from the closed enum.
        category = entry.get("category")
        if is_nonempty_str(category) and category not in CATEGORIES:
            add("V2", "HIGH", label,
                "category '%s' is not in the closed enum %s"
                % (category, "|".join(CATEGORIES)))
        elif category in CATEGORIES:
            covered.add(category)

        # V3 - duplicate ids.
        entry_id = entry.get("id")
        if is_nonempty_str(entry_id):
            key = entry_id.strip()
            if key in seen_ids:
                add("V3", "HIGH", label,
                    "duplicate id '%s' (already used by entry #%d)"
                    % (key, seen_ids[key] + 1))
            else:
                seen_ids[key] = index

        # V5 - influence and interest from the level enum.
        for field in ("influence", "interest"):
            value = entry.get(field)
            if is_nonempty_str(value) and value not in LEVELS:
                add("V5", "HIGH", label,
                    "%s value '%s' is not in %s"
                    % (field, value, "|".join(LEVELS)))

        # V6 - inference_basis non-empty (evidence rule).
        if not is_nonempty_str(entry.get("inference_basis")):
            add("V6", "MEDIUM", label,
                "inference_basis is missing or empty; an entry without a "
                "stated basis is an unsupported guess")

        # V7 - advisory Mendelow consistency on unambiguous entries.
        influence = entry.get("influence")
        interest = entry.get("interest")
        engagement = entry.get("engagement")
        if (influence in ("low", "high") and interest in ("low", "high")
                and is_nonempty_str(engagement)):
            normalized = normalize_engagement(engagement)
            expected = MENDELOW_QUADRANTS[(influence, interest)]
            if normalized in KNOWN_ENGAGEMENT_LABELS and normalized != expected:
                add("V7", "LOW", label,
                    "engagement '%s' contradicts the Mendelow quadrant "
                    "'%s' implied by influence=%s interest=%s"
                    % (engagement, expected, influence, interest))

    # V4 - category coverage or explicit waiver.
    for category in CATEGORIES:
        if category in covered:
            if category in waivers:
                notes.append(
                    "waiver for '%s' was unnecessary: the category is covered"
                    % category)
            continue
        if category in waivers:
            notes.append("category '%s' waived: %s" % (category, waivers[category]))
            continue
        if category in BLIND_SPOT_CATEGORIES:
            add("V4", "HIGH", "category:%s" % category,
                "no '%s' entry and no waiver; missing %s coverage is the "
                "classic stakeholder blind spot - add the entry or waive "
                "with --waive %s:<reason>" % (category, category, category))
        else:
            add("V4", "MEDIUM", "category:%s" % category,
                "no '%s' entry and no waiver; every category must be "
                "represented or explicitly waived with a reason"
                % category)

    return findings, notes, sorted(covered)


def build_report(path, register, waivers, findings, notes, covered):
    """Assemble the machine-readable report (deterministic, path-independent)."""
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        counts[finding["severity"]] += 1
    exit_code = 1 if findings else 0
    return {
        "tool": TOOL_NAME,
        "register": os.path.basename(path),
        "project": register.get("project") if is_nonempty_str(register.get("project")) else None,
        "entries": len(register["stakeholders"]),
        "categories_covered": covered,
        "waivers": waivers,
        "findings": findings,
        "notes": notes,
        "counts": counts,
        "result": "PASS" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
    }


def render_human(report):
    """Render the ASCII human-readable report."""
    lines = []
    lines.append("STAKEHOLDER REGISTER VALIDATION: %s" % report["register"])
    lines.append("Project: %s" % (report["project"] or "(missing)"))
    waiver_text = ", ".join(
        "%s (%s)" % (cat, reason) for cat, reason in sorted(report["waivers"].items()))
    lines.append("Entries: %d | Categories covered: %s | Waivers: %s" % (
        report["entries"],
        ", ".join(report["categories_covered"]) or "none",
        waiver_text or "none"))
    lines.append("")
    for finding in report["findings"]:
        lines.append("%-6s [%s] %s: %s" % (
            finding["severity"], finding["rule"], finding["where"],
            finding["message"]))
    for note in report["notes"]:
        lines.append("NOTE   %s" % note)
    if report["findings"] or report["notes"]:
        lines.append("")
    lines.append("RESULT: %s (%d HIGH, %d MEDIUM, %d LOW)" % (
        report["result"], report["counts"]["HIGH"],
        report["counts"]["MEDIUM"], report["counts"]["LOW"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Validate a stakeholder_register.json against the hub "
                    "shared contract: required fields, closed category enum, "
                    "unique ids, category coverage (or explicit waivers), "
                    "influence/interest enums, and the evidence rule "
                    "(non-empty inference_basis).",
        epilog="Exit codes: 0 valid / 1 findings / 2 usage or input error. "
               "Example: python %(prog)s register.json --waive "
               "supplier:\"fully in-house build, no external vendors\"")
    parser.add_argument("register", help="path to the stakeholder register JSON file")
    parser.add_argument("--waive", action="append", default=[], metavar="CATEGORY:REASON",
                        help="waive coverage for a category with an explicit reason; "
                             "repeatable; category must be one of %s" % "|".join(CATEGORIES))
    parser.add_argument("--json", action="store_true",
                        help="emit the machine-readable JSON report instead of text")
    args = parser.parse_args(argv)

    try:
        waivers = parse_waivers(args.waive)
        register = load_register(args.register)
    except ValueError as exc:
        print("INPUT ERROR: %s" % exc, file=sys.stderr)
        return 2

    findings, notes, covered = validate(register, waivers)
    report = build_report(args.register, register, waivers, findings, notes, covered)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(render_human(report))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

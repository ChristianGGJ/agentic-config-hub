#!/usr/bin/env python3
"""Deterministic blind-spot and hidden-prerequisite scanner (blind-spot-audit).

Scans a project brief/idea (text or markdown) or, with --plan, a plan.json in
the hub canonical tasks shape, against domain-profile JSON files. Each profile
concern declares indicator regexes, an optional activation layer (text
triggers and/or stakeholder categories), a severity, an optional prerequisite
note, and a seed question. The scanner emits a ranked coverage report in the
blind_spot_report.json contract:

  {"brief": str, "findings": [{"id", "domain", "concern",
   "status": "covered|partial|missing",
   "severity": "CRITICAL|HIGH|MEDIUM|LOW",
   "evidence", "prerequisite_note": str-or-null}]}

ALGORITHM-OVER-AI SPLIT: this scanner is the deterministic FLOOR - it
guarantees that every concern in every applied profile was machine-checked
and received an explicit covered/partial/missing status backed by indicator
evidence. It cannot read paraphrase ("parcels reach buyers" does not match
"shipping"). The LLM semantic pass described in SKILL.md is the ceiling that
catches paraphrases and name-drop coverage. "missing" means no indicator
evidence was found, never proven-missing; exit 0 is not proof of completeness.

Python 3.8+ standard library only. No network calls, no LLM calls.
Deterministic: same artifact + same profiles + same flags = same report.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SEVERITY_RANK = {name: idx for idx, name in enumerate(SEVERITIES)}
STATUS_RANK = {"missing": 0, "partial": 1, "covered": 2}
STAKEHOLDER_CATEGORIES = {
    "user", "operator", "supplier", "regulator", "sponsor", "third_party",
}
DEFAULT_COVERED_MIN = 2

DISCLAIMER = (
    "Deterministic floor only: 'missing' means no indicator evidence was "
    "found in the artifact, never proven-missing, and 'covered' means "
    "indicator terms are present, never that the concern is handled well. "
    "Paraphrases evade regex: run the LLM semantic pass described in "
    "SKILL.md before treating this report as complete. Exit 0 is not proof "
    "of completeness."
)


def fail(message):
    """Print a usage/input error and exit 2."""
    print("ERROR: " + message, file=sys.stderr)
    sys.exit(2)


def ascii_safe(text):
    """Force ASCII-safe output (hub script rule)."""
    return text.encode("ascii", errors="replace").decode("ascii")


def make_snippet(text, start, end, radius=40):
    """Whitespace-collapsed, ASCII-safe excerpt around a regex match."""
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    core = " ".join(text[lo:hi].split())
    prefix = "..." if lo > 0 else ""
    suffix = "..." if hi < len(text) else ""
    return ascii_safe(prefix + core + suffix)


def compile_patterns(raw_patterns, context):
    """Compile a list of regex strings; exit 2 on any malformed entry."""
    if not isinstance(raw_patterns, list):
        fail("{}: must be an array of regex strings".format(context))
    compiled = []
    for raw in raw_patterns:
        if not isinstance(raw, str) or not raw.strip():
            fail("{}: pattern entries must be non-empty strings".format(context))
        try:
            compiled.append((raw, re.compile(raw, re.IGNORECASE)))
        except re.error as exc:
            fail("{}: invalid regex '{}' ({})".format(context, raw, exc))
    return compiled


def validate_categories(raw, context):
    """Validate an activated_by list against the register category enum."""
    if not isinstance(raw, list):
        fail("{}: activated_by must be an array".format(context))
    for cat in raw:
        if cat not in STAKEHOLDER_CATEGORIES:
            fail("{}: unknown stakeholder category '{}' (allowed: {})".format(
                context, cat, ", ".join(sorted(STAKEHOLDER_CATEGORIES))))
    return list(raw)


def load_artifact(path, plan_mode):
    """Load the artifact into (label, mode, [(unit_id, text), ...])."""
    if not path.is_file():
        fail("artifact not found: {}".format(path))
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail("cannot read artifact {}: {}".format(path, exc))
    if not plan_mode:
        if not raw.strip():
            fail("brief file is empty: {}".format(path))
        return path.name, "brief", [("brief", raw)]
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("plan.json is not valid JSON: {}".format(exc))
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) \
            or not plan["tasks"]:
        fail("plan.json must be an object with a non-empty 'tasks' array "
             "(hub canonical shape: id, description, depends_on)")
    units = []
    seen = set()
    for idx, task in enumerate(plan["tasks"]):
        where = "tasks[{}]".format(idx)
        if not isinstance(task, dict):
            fail("{}: each task must be an object".format(where))
        task_id = task.get("id")
        desc = task.get("description")
        deps = task.get("depends_on")
        if not isinstance(task_id, str) or not task_id:
            fail("{}: 'id' must be a non-empty string".format(where))
        if task_id in seen:
            fail("duplicate task id '{}'".format(task_id))
        seen.add(task_id)
        if not isinstance(desc, str) or not desc:
            fail("task '{}': 'description' must be a non-empty string".format(task_id))
        if not isinstance(deps, list):
            fail("task '{}': 'depends_on' must be an array".format(task_id))
        units.append(("task " + task_id, desc))
    label = plan.get("name")
    if not isinstance(label, str) or not label:
        label = path.name
    return label, "plan", units


def load_profiles(profiles_dir, select):
    """Load, validate, and compile every *.json profile in the directory."""
    if not profiles_dir.is_dir():
        fail("profiles directory not found: {}".format(profiles_dir))
    profiles = {}
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail("cannot parse profile {}: {}".format(path.name, exc))
        if not isinstance(data, dict):
            fail("profile {}: top level must be an object".format(path.name))
        name = data.get("profile")
        if not isinstance(name, str) or not name:
            fail("profile {}: missing 'profile' name field".format(path.name))
        if name in profiles:
            fail("duplicate profile name '{}'".format(name))
        concerns = data.get("concerns")
        if not isinstance(concerns, list) or not concerns:
            fail("profile {}: 'concerns' must be a non-empty array".format(name))
        data["_triggers"] = compile_patterns(
            data.get("triggers", []), "profile {} triggers".format(name))
        data["_activated_by"] = validate_categories(
            data.get("activated_by", []), "profile {}".format(name))
        for concern in concerns:
            if not isinstance(concern, dict):
                fail("profile {}: each concern must be an object".format(name))
            cid = concern.get("id")
            if not isinstance(cid, str) or not cid:
                fail("profile {}: every concern needs a string 'id'".format(name))
            ctx = "profile {} concern {}".format(name, cid)
            if not isinstance(concern.get("concern"), str) or not concern["concern"]:
                fail("{}: 'concern' must be a non-empty string".format(ctx))
            if concern.get("severity") not in SEVERITIES:
                fail("{}: severity must be one of {}".format(ctx, "|".join(SEVERITIES)))
            indicators = concern.get("indicators")
            if not isinstance(indicators, list) or not indicators:
                fail("{}: 'indicators' must be a non-empty array".format(ctx))
            concern["_indicators"] = compile_patterns(indicators, ctx + " indicators")
            concern["_triggers"] = compile_patterns(
                concern.get("triggers", []), ctx + " triggers")
            concern["_activated_by"] = validate_categories(
                concern.get("activated_by", []), ctx)
            covered_min = concern.get("covered_min", DEFAULT_COVERED_MIN)
            if not isinstance(covered_min, int) or isinstance(covered_min, bool) \
                    or covered_min < 1:
                fail("{}: covered_min must be a positive integer".format(ctx))
            note = concern.get("prerequisite_note")
            if note is not None and not isinstance(note, str):
                fail("{}: prerequisite_note must be a string or null".format(ctx))
        profiles[name] = data
    if not profiles:
        fail("no *.json profiles found in {}".format(profiles_dir))
    if select:
        unknown = [n for n in select if n not in profiles]
        if unknown:
            fail("unknown profile(s): {} (available: {})".format(
                ", ".join(unknown), ", ".join(sorted(profiles))))
        return [profiles[n] for n in sorted(set(select))]
    return [profiles[n] for n in sorted(profiles)]


def load_register(path):
    """Read a stakeholder_register.json; return its sorted category list."""
    if not path.is_file():
        fail("stakeholder register not found: {}".format(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("cannot parse stakeholder register {}: {}".format(path, exc))
    stakeholders = data.get("stakeholders") if isinstance(data, dict) else None
    if not isinstance(stakeholders, list):
        fail("stakeholder register must be an object with a 'stakeholders' array")
    categories = set()
    for idx, entry in enumerate(stakeholders):
        if not isinstance(entry, dict):
            fail("stakeholders[{}]: each entry must be an object".format(idx))
        cat = entry.get("category")
        if cat not in STAKEHOLDER_CATEGORIES:
            fail("stakeholders[{}]: category '{}' not in {}".format(
                idx, cat, "|".join(sorted(STAKEHOLDER_CATEGORIES))))
        categories.add(cat)
    return sorted(categories)


def check_activation(profile, concern, units, categories):
    """Return (active, activation_evidence). Unconditional when no
    triggers and no activated_by categories are declared (profile-level
    and concern-level lists are unioned)."""
    triggers = profile["_triggers"] + concern["_triggers"]
    activated_by = profile["_activated_by"] + concern["_activated_by"]
    if not triggers and not activated_by:
        return True, None
    for _raw, rx in triggers:
        for unit_id, text in units:
            match = rx.search(text)
            if match:
                return True, "activated by trigger evidence '{}' in {}".format(
                    ascii_safe(match.group(0)), unit_id)
    for cat in activated_by:
        if cat in categories:
            return True, ("activated by stakeholder category '{}' "
                          "in the register".format(cat))
    return False, None


def evaluate_concern(profile, concern, units, categories):
    """Scan one concern; return (finding, skipped_record)."""
    active, activation = check_activation(profile, concern, units, categories)
    full_id = "{}.{}".format(profile["profile"], concern["id"])
    if not active:
        return None, {
            "id": full_id,
            "domain": profile["profile"],
            "concern": concern["concern"],
            "reason": ("no trigger matched and no activating stakeholder "
                       "category present"),
        }
    matches = []
    for _raw, rx in concern["_indicators"]:
        for unit_id, text in units:
            match = rx.search(text)
            if match:
                matches.append((ascii_safe(match.group(0)), unit_id,
                                make_snippet(text, match.start(), match.end())))
                break
    total = len(concern["_indicators"])
    covered_min = min(concern.get("covered_min", DEFAULT_COVERED_MIN), total)
    if not matches:
        status = "missing"
        evidence = ("no evidence found: 0 of {} indicator pattern(s) matched "
                    "across {} text unit(s)".format(total, len(units)))
        if activation:
            evidence += "; " + activation
    else:
        status = "covered" if len(matches) >= covered_min else "partial"
        first_text, first_unit, first_snippet = matches[0]
        evidence = "matched {} of {} indicator(s); first: '{}' in {}: \"{}\"".format(
            len(matches), total, first_text, first_unit, first_snippet)
    finding = {
        "id": full_id,
        "domain": profile["profile"],
        "concern": concern["concern"],
        "status": status,
        "severity": concern["severity"],
        "evidence": evidence,
        "prerequisite_note": concern.get("prerequisite_note"),
        "seed_question": concern.get("seed_question"),
    }
    return finding, None


def build_report(label, mode, artifact, profiles, categories, fail_on,
                 findings, skipped):
    """Assemble the ranked blind_spot_report.json object."""
    findings.sort(key=lambda f: (STATUS_RANK[f["status"]],
                                 SEVERITY_RANK[f["severity"]],
                                 f["domain"], f["id"]))
    counts = {"covered": 0, "partial": 0, "missing": 0}
    for finding in findings:
        counts[finding["status"]] += 1
    fail_rank = SEVERITY_RANK[fail_on.upper()]
    gate_failures = sum(
        1 for f in findings
        if f["status"] == "missing" and SEVERITY_RANK[f["severity"]] <= fail_rank)
    return {
        "brief": label,
        "mode": mode,
        "artifact": artifact,
        "profiles_applied": [p["profile"] for p in profiles],
        "stakeholder_categories": categories,
        "fail_on": fail_on,
        "findings": findings,
        "skipped_not_triggered": skipped,
        "summary": {
            "concerns_evaluated": len(findings),
            "covered": counts["covered"],
            "partial": counts["partial"],
            "missing": counts["missing"],
            "skipped": len(skipped),
            "gate_failures": gate_failures,
            "gate": "FAIL" if gate_failures else "PASS",
        },
        "disclaimer": DISCLAIMER,
    }


def render_human(report):
    """ASCII human-readable report."""
    lines = []
    lines.append("BLIND-SPOT AUDIT: {}".format(report["brief"]))
    lines.append("Mode: {} | Artifact: {}".format(report["mode"], report["artifact"]))
    lines.append("Profiles applied: {}".format(", ".join(report["profiles_applied"])))
    cats = report["stakeholder_categories"]
    lines.append("Stakeholder categories: {}".format(", ".join(cats) if cats else "(none)"))
    lines.append("")
    lines.append("RANKED FINDINGS (missing first, then partial, then covered):")
    for finding in report["findings"]:
        lines.append("  [{:<7}] {:<8} {}".format(
            finding["status"], finding["severity"], finding["id"]))
        lines.append("            concern : {}".format(finding["concern"]))
        lines.append("            evidence: {}".format(finding["evidence"]))
        if finding.get("prerequisite_note"):
            lines.append("            prereq  : {}".format(finding["prerequisite_note"]))
        if finding["status"] != "covered" and finding.get("seed_question"):
            lines.append("            seed q  : {}".format(finding["seed_question"]))
    if report["skipped_not_triggered"]:
        lines.append("")
        lines.append("SKIPPED (not triggered):")
        for skip in report["skipped_not_triggered"]:
            lines.append("  {} - {}".format(skip["id"], skip["reason"]))
    summary = report["summary"]
    lines.append("")
    lines.append("SUMMARY: {} concern(s) evaluated - {} covered, {} partial, "
                 "{} missing; {} skipped".format(
                     summary["concerns_evaluated"], summary["covered"],
                     summary["partial"], summary["missing"], summary["skipped"]))
    lines.append("GATE: {} ({} missing finding(s) at or above severity '{}')".format(
        summary["gate"], summary["gate_failures"], report["fail_on"]))
    lines.append("DISCLAIMER: {}".format(report["disclaimer"]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="coverage_gap_scanner.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Deterministic blind-spot and hidden-prerequisite scanner.\n"
            "Scans a project brief (default) or a plan.json (--plan) against\n"
            "domain-profile JSON taxonomies and emits a ranked coverage report\n"
            "in the blind_spot_report.json contract.\n\n"
            "ALGORITHM-OVER-AI SPLIT: this scanner is the deterministic FLOOR\n"
            "(the checklist minimum, machine-checked: every profile concern\n"
            "gets an explicit covered/partial/missing status with indicator\n"
            "evidence). The LLM semantic pass guided by references/ is the\n"
            "ceiling that catches paraphrases the regex layer misses.\n"
            "'missing' means no indicator evidence was found, never\n"
            "proven-missing; exit 0 is not proof of completeness."),
        epilog=(
            "Examples:\n"
            "  python coverage_gap_scanner.py brief.md --profiles assets/profiles\n"
            "  python coverage_gap_scanner.py plan.json --plan \\\n"
            "      --profiles assets/profiles --select data-privacy --json\n"
            "  python coverage_gap_scanner.py brief.md --profiles assets/profiles \\\n"
            "      --stakeholders register.json --fail-on high\n\n"
            "Exit codes: 0 = pass (no missing concern at/above --fail-on),\n"
            "            1 = gate fail (missing concern at/above --fail-on),\n"
            "            2 = usage or input error."))
    parser.add_argument("artifact",
                        help="project brief (text/markdown) or, with --plan, a "
                             "plan.json in the hub canonical tasks shape")
    parser.add_argument("--plan", action="store_true",
                        help="treat the artifact as plan.json ({name, version, "
                             "tasks:[{id, description, depends_on}]}) and scan "
                             "task descriptions as the text units")
    parser.add_argument("--profiles", required=True, metavar="DIR",
                        help="directory of domain-profile *.json files")
    parser.add_argument("--select", metavar="NAMES",
                        help="comma-separated profile names to apply "
                             "(default: every profile in --profiles, "
                             "alphabetical order)")
    parser.add_argument("--stakeholders", metavar="FILE",
                        help="optional stakeholder_register.json; its categories "
                             "activate concerns tagged with activated_by (e.g. a "
                             "regulator entry makes compliance concerns mandatory)")
    parser.add_argument("--fail-on", choices=["critical", "high", "medium", "low"],
                        default="critical",
                        help="minimum severity of a MISSING concern that fails "
                             "the gate with exit 1 (default: critical; partial "
                             "findings never gate)")
    parser.add_argument("--out", metavar="FILE",
                        help="write the blind_spot_report.json to FILE")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable report instead of the "
                             "human-readable one")
    args = parser.parse_args()

    label, mode, units = load_artifact(Path(args.artifact), args.plan)
    select = None
    if args.select is not None:
        select = [name.strip() for name in args.select.split(",") if name.strip()]
        if not select:
            fail("--select given but no profile names parsed")
    profiles = load_profiles(Path(args.profiles), select)
    categories = load_register(Path(args.stakeholders)) if args.stakeholders else []

    findings = []
    skipped = []
    category_set = set(categories)
    for profile in profiles:
        for concern in profile["concerns"]:
            finding, skip = evaluate_concern(profile, concern, units, category_set)
            if finding is not None:
                findings.append(finding)
            else:
                skipped.append(skip)

    report = build_report(label, mode, args.artifact, profiles, categories,
                          args.fail_on, findings, skipped)
    payload = json.dumps(report, indent=2)
    if args.out:
        try:
            Path(args.out).write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            fail("cannot write {}: {}".format(args.out, exc))
    if args.json:
        print(payload)
    else:
        print(render_human(report))
    sys.exit(1 if report["summary"]["gate"] == "FAIL" else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ticket_payload_generator.py - offline plan.json -> PM-tool ticket payloads.

Part of the plan-ticket-export skill (agentic-config-hub). ONE transformation,
EXPORT-ONLY and one-way: an approved plan.json (hub canonical tasks shape) becomes
offline, dependency-ordered, tool-specific ticket-creation payloads plus a human import
runbook. No sync-back, no status polling, no updates. See SKILL.md for full docs.

Zero network calls by design; imports nothing that could reach a network. Scripts NEVER
read or emit secret values - the runbook carries only env-var placeholders. Trello has
NO native dependencies: depends_on edges degrade to a "Blocked by" checklist with a LOUD
WARN and exit 1 - never silently dropped. Graph hygiene duplicates hub rule R5 semantics
(hitl_gate_validator.py) - duplicated, never imported, per the hub portability rule.

Exit codes: 0 generated/clean; 1 findings/degradation (cycle, dangling, duplicate,
Trello dependency loss - fail-closed); 2 usage/input error. Python 3.8+ stdlib only.
Deterministic: same plan + mapping = same bytes.
"""

import argparse
import hashlib
import json
import os
import re
import sys

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

MARKER_PREFIX = "acfhub"


def fail_usage(message):
    """Print an input/usage error to stderr and exit 2."""
    print("ERROR: " + message, file=sys.stderr)
    sys.exit(EXIT_USAGE)


def load_json_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        fail_usage("cannot read {0} file '{1}': {2}".format(label, path, exc))
    except json.JSONDecodeError as exc:
        fail_usage("{0} file '{1}' is not valid JSON: {2}".format(label, path, exc))


def extract_tasks(plan):
    """Validate the canonical plan shape; exit 2 on malformed input."""
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        fail_usage("plan must be a JSON object with a 'tasks' array (hub canonical shape)")
    if not plan["tasks"]:
        fail_usage("plan has no tasks to export")
    tasks = []
    for pos, raw in enumerate(plan["tasks"]):
        if not isinstance(raw, dict):
            fail_usage("tasks[{0}] is not an object".format(pos))
        tid = raw.get("id")
        if not isinstance(tid, str) or not tid.strip():
            fail_usage("tasks[{0}] is missing a non-empty string 'id'".format(pos))
        deps = raw.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            fail_usage("task '{0}': depends_on must be an array of task-id strings".format(tid))
        tasks.append({
            "id": tid,
            "title": str(raw.get("title") or raw.get("description") or tid),
            "description": str(raw.get("description") or ""),
            "depends_on": list(deps),
            "raw": raw,
        })
    return tasks


# --- Graph hygiene: duplicated R5 semantics (never imported) -----------------

def find_duplicates(tasks):
    seen = set()
    findings = []
    for task in tasks:
        if task["id"] in seen:
            findings.append({"check": "duplicate_id", "task": task["id"],
                             "message": "Task id '{0}' is declared more than once.".format(task["id"])})
        seen.add(task["id"])
    return findings


def find_dangling(tasks, index):
    findings = []
    for task in tasks:
        for dep in task["depends_on"]:
            if dep not in index:
                findings.append({"check": "dangling_reference", "task": task["id"],
                                 "message": "Task '{0}' depends on unknown task '{1}'.".format(task["id"], dep)})
    return findings


def find_cycles(index):
    """Cycle detection via iterative DFS white/grey/black coloring; each cycle
    reported once with the full path. Mirrors hitl_gate_validator.py rule R5."""
    white, grey, black = 0, 1, 2
    color = {tid: white for tid in index}
    reported = set()
    findings = []
    for root in index:
        if color[root] != white:
            continue
        stack = [(root, iter(index[root]["depends_on"]))]
        color[root] = grey
        path = [root]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in index:
                    continue
                if color[child] == grey:
                    cycle = path[path.index(child):] + [child]
                    key = tuple(sorted(set(cycle)))
                    if key not in reported:
                        reported.add(key)
                        findings.append({"check": "cycle", "task": node,
                                         "message": "Dependency cycle detected: {0}.".format(" -> ".join(cycle))})
                elif color[child] == white:
                    color[child] = grey
                    stack.append((child, iter(index[child]["depends_on"])))
                    path.append(child)
                    advanced = True
                    break
            if not advanced:
                color[node] = black
                stack.pop()
                path.pop()
    return findings


def topological_order(tasks, index):
    """Kahn topological sort; ties broken by plan-file order (deterministic)."""
    file_order = []
    seen = set()
    for task in tasks:
        if task["id"] not in seen:
            seen.add(task["id"])
            file_order.append(task["id"])
    position = {tid: i for i, tid in enumerate(file_order)}
    indegree = {}
    dependents = {tid: [] for tid in index}
    for tid in index:
        valid = [d for d in index[tid]["depends_on"] if d in index and d != tid]
        indegree[tid] = len(valid)
        for dep in valid:
            dependents[dep].append(tid)
    ready = [tid for tid in file_order if indegree[tid] == 0]
    order = []
    while ready:
        ready.sort(key=position.get)
        tid = ready.pop(0)
        order.append(tid)
        for dep in dependents[tid]:
            indegree[dep] -= 1
            if indegree[dep] == 0:
                ready.append(dep)
    return order


# --- Idempotency markers -----------------------------------------------------

def plan_hash(plan):
    """Deterministic 8-hex plan fingerprint for the idempotency marker."""
    name = str(plan.get("name") or "unnamed-plan")
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "task"


def marker(phash, tid):
    return "{0}-{1}-{2}".format(MARKER_PREFIX, phash, slug(tid))


def token(mark):
    """Placeholder token the runbook resolves to a real created-id at import."""
    return "<<RESOLVE:{0}>>".format(mark)


# --- Payload builders --------------------------------------------------------

def adf_description(text):
    """Atlassian Document Format (ADF) JSON body. v3 requires ADF, NOT the v2
    wiki-markup string - the #1 v2->v3 migration pitfall."""
    body = text if text else "(no description)"
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": body}]}]}


def build_jira(tasks, order, index, mapping, phash):
    cfg = mapping.get("jira", {})
    project_key = str(cfg.get("project_key", "$JIRA_PROJECT_KEY"))
    issue_type = str(cfg.get("issue_type", "Task"))
    link_type = str(cfg.get("blocks_link_type", "Blocks"))
    plan_label = "{0}-{1}".format(MARKER_PREFIX, phash)
    issue_ops, warnings = [], []
    for tid in order:
        task = index[tid]
        summary = task["title"]
        if len(summary) > 255:
            summary = summary[:252] + "..."
            warnings.append({"check": "summary_truncated", "task": tid,
                             "message": "Task '{0}' summary exceeded Jira's 255-char limit; truncated (full text kept in description).".format(tid)})
        issue_ops.append({
            "method": "POST", "path": "/rest/api/3/issue",
            "task_id": tid, "idempotency_label": marker(phash, tid),
            "body": {"fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "description": adf_description(task["description"]),
                "labels": [plan_label, marker(phash, tid)]}}})
    link_ops = []
    for tid in order:
        for dep in index[tid]["depends_on"]:
            if dep in index:
                link_ops.append({
                    "method": "POST", "path": "/rest/api/3/issueLink",
                    "blocker_task": dep, "dependent_task": tid,
                    "body": {"type": {"name": link_type},
                             "inwardIssue": {"key": token(marker(phash, tid))},
                             "outwardIssue": {"key": token(marker(phash, dep))}}})
    return {"jira_issues.json": issue_ops, "jira_links.json": link_ops}, warnings, []


def build_asana(tasks, order, index, mapping, phash):
    cfg = mapping.get("asana", {})
    project_gid = str(cfg.get("project_gid", "$ASANA_PROJECT_GID"))
    task_ops = []
    for tid in order:
        task = index[tid]
        task_ops.append({
            "method": "POST", "path": "/tasks",
            "task_id": tid, "idempotency_external": marker(phash, tid),
            "body": {"data": {
                "name": task["title"],
                "notes": task["description"],
                "projects": [project_gid],
                "external": {"gid": marker(phash, tid)}}}})
    dep_ops = []
    for tid in order:
        blockers = [d for d in index[tid]["depends_on"] if d in index]
        if blockers:
            dep_ops.append({
                "method": "POST",
                "path": "/tasks/{0}/addDependencies".format(token(marker(phash, tid))),
                "dependent_task": tid, "blocker_tasks": blockers,
                "body": {"data": {"dependencies": [token(marker(phash, b)) for b in blockers]}}})
    return {"asana_tasks.json": task_ops, "asana_dependencies.json": dep_ops}, [], []


def build_trello(tasks, order, index, mapping, phash):
    cfg = mapping.get("trello", {})
    list_id = str(cfg.get("list_id", "$TRELLO_LIST_ID"))
    card_ops = []
    for tid in order:
        task = index[tid]
        desc = task["description"]
        stamped = (desc + "\n\n" if desc else "") + "[{0}]".format(marker(phash, tid))
        card_ops.append({
            "method": "POST", "path": "/1/cards",
            "task_id": tid, "idempotency_marker": marker(phash, tid),
            "body": {"idList": list_id, "name": task["title"], "desc": stamped}})
    checklist_ops, findings = [], []
    for tid in order:
        blockers = [d for d in index[tid]["depends_on"] if d in index]
        if blockers:
            findings.append({"check": "dependency_degraded", "task": tid,
                             "message": "Task '{0}' depends on {1}; Trello has NO native dependencies. Emitted as a 'Blocked by' checklist fallback - native blocker semantics are LOST.".format(tid, ", ".join(blockers))})
            checklist_ops.append({
                "method": "POST",
                "path": "/1/cards/{0}/checklists".format(token(marker(phash, tid))),
                "dependent_task": tid, "blocker_tasks": blockers,
                "body": {"name": "Blocked by",
                         "items": [index[b]["title"] for b in blockers]}})
    return {"trello_cards.json": card_ops, "trello_checklists.json": checklist_ops}, [], findings


BUILDERS = {"jira": build_jira, "asana": build_asana, "trello": build_trello}


# --- Runbook -----------------------------------------------------------------

RUNBOOK_CREDS = {"jira": ["JIRA_EMAIL", "JIRA_API_TOKEN"],
                 "asana": ["ASANA_PAT"],
                 "trello": ["TRELLO_KEY", "TRELLO_TOKEN"]}

RUNBOOK_STEPS = {
    "jira": (
        "1. Create issues: `jira_issues.json` (topologically ordered). Search first via `GET /rest/api/3/search?jql=labels=\"<marker>\"`; create only if empty. Descriptions are ADF JSON (v3 requirement).\n"
        "2. Resolve markers to keys: map each created issue's `idempotency_label` to its returned issue key.\n"
        "3. Add links: `jira_links.json`. Replace each `<<RESOLVE:marker>>` token with the real issue key, then POST.\n\n"
        "Pace requests under Atlassian's cost-budget rate limits; on a 429, back off and resume from the last created marker (never restart from the top)."),
    "asana": (
        "1. Create tasks: `asana_tasks.json` (topologically ordered). The `data.external.gid` field is the native idempotency key - Asana rejects a duplicate external gid.\n"
        "2. Add dependencies: `asana_dependencies.json`. Replace each `<<RESOLVE:marker>>` token with the returned task gid, then POST to `/tasks/{gid}/addDependencies`.\n\n"
        "Consider `POST /batch` (max 10 actions/request) to cut round trips; stay under 150 req/min (free) or 1500 req/min (paid)."),
    "trello": (
        "1. Create cards: `trello_cards.json` (topologically ordered). The idempotency marker is embedded in each card `desc`; search the list before creating.\n"
        "2. WARNING - DEPENDENCY DEGRADATION: Trello has NO native dependencies. `trello_checklists.json` recreates each blocker relationship as a 'Blocked by' checklist. Native blocker semantics are LOST - a human must enforce ordering, or install a dependency Power-Up. This is why generation exited 1.\n\n"
        "Stay under Trello limits: 300 req/10s per key, 100 req/10s per token."),
}

RUNBOOK_TEMPLATE = """\
# Import Runbook: {plan} -> {target}

Generated offline by plan-ticket-export. This runbook is the Phase-2 MANIFEST a human approves at the Phase-3 HITL gate BEFORE any ticket is created. Ticket creation is irreversible external work - review before running a single POST.

## Credentials (BYOK - placeholders only, NEVER commit real values)

Export these before running any command, then reference them as {cred_refs} in your requests. No secret value appears in any generated file - only these env-var names:

{exports}

Rotate any token ever pasted into shell history, a URL, or a committed file (OWASP API2, Broken Authentication).

## Idempotency (prevents duplicate-ticket floods on re-run)

Every payload carries the marker prefix `{marker}`. BEFORE creating, search for the marker; if it already exists, SKIP that ticket. Re-running must never double-create.

## Order (dependency-safe topological order)

Blockers/parents are created before dependents; links/dependencies are added last.

{steps}

## Files

{files}

VERIFY AGAINST CURRENT DOCS: REST endpoints, rate limits, and auth models evolve. Re-check references/ before an import run.
"""


def build_runbook(target, plan, phash, files):
    creds = RUNBOOK_CREDS[target]
    exports = "\n".join("    export {0}=...".format(name) for name in creds)
    file_list = "\n".join("- `{0}` ({1} operations)".format(name, len(files[name]))
                          for name in sorted(files))
    return RUNBOOK_TEMPLATE.format(
        plan=str(plan.get("name") or "unnamed-plan"), target=target,
        cred_refs=" / ".join("$" + name for name in creds),
        exports=exports, marker="{0}-{1}".format(MARKER_PREFIX, phash),
        steps=RUNBOOK_STEPS[target], files=file_list)


# --- Orchestration -----------------------------------------------------------

def write_outputs(out_dir, files, runbook):
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        fail_usage("cannot create --out directory '{0}': {1}".format(out_dir, exc))
    written = []
    for name in sorted(files):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(files[name], indent=2) + "\n")
        written.append(name)
    runbook_path = os.path.join(out_dir, "import-runbook.md")
    with open(runbook_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(runbook)
    written.append("import-runbook.md")
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ticket_payload_generator.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Transform an approved plan.json into offline, dependency-"
                    "ordered, tool-specific ticket-creation payloads plus an import "
                    "runbook. EXPORT-ONLY, one-way, zero network calls.",
        epilog="Examples:\n"
               "  python ticket_payload_generator.py --target jira --plan plan.json "
               "--mapping map.json --out out/\n"
               "  python ticket_payload_generator.py --target asana --plan plan.json "
               "--validate-only\n"
               "  python ticket_payload_generator.py --target trello --plan plan.json "
               "--out out/ --json\n\n"
               "Exit codes: 0 generated/clean, 1 findings or degradation "
               "(cycle/dangling/duplicate/Trello dependency loss), 2 usage/input error.")
    parser.add_argument("--target", required=True, choices=["jira", "asana", "trello"],
                        help="destination PM tool dialect")
    parser.add_argument("--plan", required=True,
                        help="plan.json in the hub canonical tasks shape "
                             "(id, title, description, depends_on; extras tolerated)")
    parser.add_argument("--mapping",
                        help="optional field-mapping / coordinates JSON "
                             "(see assets/field_mapping.template.json)")
    parser.add_argument("--out",
                        help="output directory for payload files and the runbook "
                             "(required unless --validate-only)")
    parser.add_argument("--validate-only", action="store_true",
                        help="graph + representability checks only; emit nothing")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable report instead of the human one")
    args = parser.parse_args(argv)

    plan = load_json_file(args.plan, "plan")
    mapping = load_json_file(args.mapping, "mapping") if args.mapping else {}
    if not isinstance(mapping, dict):
        fail_usage("mapping file must be a JSON object")
    tasks = extract_tasks(plan)
    index = {}
    for task in tasks:
        index.setdefault(task["id"], task)

    findings = find_duplicates(tasks) + find_dangling(tasks, index) + find_cycles(index)
    blocked = bool(findings)
    order = [] if blocked else topological_order(tasks, index)
    phash = plan_hash(plan)

    warnings, degraded, files = [], [], {}
    if not blocked:
        files, warnings, degraded = BUILDERS[args.target](tasks, order, index, mapping, phash)
    all_findings = findings + degraded

    if args.validate_only:
        status = "PASS" if not all_findings else "FAIL"
    elif blocked:
        status = "BLOCKED"
    else:
        status = "GENERATED" if not degraded else "DEGRADED"

    written = []
    if not args.validate_only and not blocked:
        if not args.out:
            fail_usage("generation mode needs an output directory: pass --out DIR "
                       "(or use --validate-only)")
        runbook = build_runbook(args.target, plan, phash, files)
        written = write_outputs(args.out, files, runbook)

    report = {
        "target": args.target,
        "plan": plan.get("name", ""),
        "mode": "validate" if args.validate_only else "generate",
        "status": status,
        "plan_marker": "{0}-{1}".format(MARKER_PREFIX, phash),
        "task_count": len(index),
        "topological_order": order,
        "findings": all_findings,
        "warnings": warnings,
        "files_written": written,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)

    if all_findings:
        return EXIT_FINDINGS
    return EXIT_OK


def print_human(report):
    print("PLAN TICKET EXPORT: {0} -> {1}".format(report["plan"] or "(unnamed plan)", report["target"]))
    print("Mode           : {0}".format(report["mode"]))
    print("Tasks          : {0}".format(report["task_count"]))
    print("Idempotency    : {0}".format(report["plan_marker"]))
    if report["topological_order"]:
        print("Order          : {0}".format(" -> ".join(report["topological_order"])))
    if report["findings"]:
        print("FINDINGS ({0}):".format(len(report["findings"])))
        for finding in report["findings"]:
            print("  [{0}] {1}".format(finding["check"].upper(), finding["message"]))
    if report["warnings"]:
        print("WARNINGS ({0}):".format(len(report["warnings"])))
        for warning in report["warnings"]:
            print("  [{0}] {1}".format(warning["check"].upper(), warning["message"]))
    if report["files_written"]:
        print("Files written  : {0}".format(", ".join(report["files_written"])))
    print("STATUS: {0}".format(report["status"]))


if __name__ == "__main__":
    sys.exit(main())

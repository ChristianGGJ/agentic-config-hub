#!/usr/bin/env python3
"""
Manifest Auditor - Scan agent manifests for auto-execution attack surfaces.

Where skill_security_auditor.py inspects a skill's *code and prose*, this tool
inspects the *wiring* that makes code run automatically the moment an agent
loads a project: MCP server definitions, hook configs, and permission grants.
These files are the primary auto-execution surface and are almost never read by
a human before an agent trusts them.

Scanned manifest types (found by name, at any depth):
    .mcp.json            MCP server command / args / env / remote URL
    settings.json        Claude Code hooks, permission allowlist, defaultMode
    settings.local.json  (same schema as settings.json)
    hooks.json           plugin hook definitions
    plugin.json          plugin manifest (inline hooks / mcpServers)
    .git/hooks/*         active git hooks (non-*.sample)
    .githooks/*          shared git hooks
    .husky/*             Husky git hooks

API assumptions (verify against current docs): Claude Code settings.json schema
(permissions.allow / permissions.defaultMode / hooks.<Event>), .mcp.json
mcpServers schema, and hook event names are treated generically -- ANY key under
"hooks" is scanned as a hook, so the tool does not depend on an exhaustive,
version-specific event list.

Usage:
    python3 manifest_auditor.py /path/to/project-or-skill/
    python3 manifest_auditor.py /path/to/.mcp.json
    python3 manifest_auditor.py /path/to/dir/ --json
    python3 manifest_auditor.py /path/to/dir/ --strict

Exit codes:
    0 = clean (no HIGH/CRITICAL risky findings; MEDIUM allowed unless --strict)
    1 = risky findings present (HIGH/CRITICAL, or MEDIUM+ with --strict)
    2 = usage / input error (path missing, etc.)
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class Severity(IntEnum):
    INFO = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


SEVERITY_NAMES = {
    Severity.INFO: "INFO",
    Severity.MEDIUM: "MEDIUM",
    Severity.HIGH: "HIGH",
    Severity.CRITICAL: "CRITICAL",
}


@dataclass
class Finding:
    severity: Severity
    category: str
    file: str
    locator: str  # JSON path (e.g. mcpServers.foo.command) or hook event / "-"
    detail: str   # the offending value, truncated
    risk: str
    fix: str

    def to_dict(self):
        return {
            "severity": SEVERITY_NAMES[self.severity],
            "category": self.category,
            "file": self.file,
            "locator": self.locator,
            "detail": self.detail,
            "risk": self.risk,
            "fix": self.fix,
        }


@dataclass
class ManifestReport:
    root: str
    findings: list = field(default_factory=list)
    manifests_scanned: int = 0

    def add(self, severity, category, file, locator, detail, risk, fix):
        self.findings.append(
            Finding(
                severity=severity,
                category=category,
                file=file,
                locator=locator,
                detail=str(detail)[:160],
                risk=risk,
                fix=fix,
            )
        )

    @property
    def critical(self):
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high(self):
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium(self):
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def info(self):
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    def verdict(self, strict=False):
        if self.critical or self.high:
            return "FAIL"
        if self.medium:
            return "WARN"
        return "PASS"

    def failing(self, strict=False):
        if self.critical or self.high:
            return True
        if strict and self.medium:
            return True
        return False

    def to_dict(self, strict=False):
        return {
            "root": self.root,
            "verdict": self.verdict(strict),
            "summary": {
                "critical": self.critical,
                "high": self.high,
                "medium": self.medium,
                "info": self.info,
                "total": len(self.findings),
            },
            "manifests_scanned": self.manifests_scanned,
            "findings": [f.to_dict() for f in self.findings],
        }


# =============================================================================
# COMMAND CONTENT RISK PATTERNS
# Reused for MCP server commands, hook commands, and hook script bodies.
# =============================================================================

COMMAND_RISK_PATTERNS = [
    {
        "regex": r"(?:curl|wget)\b[^|]*\|\s*(?:ba|z)?sh\b",
        "severity": Severity.CRITICAL,
        "category": "PIPE-TO-SHELL",
        "risk": "Downloads a remote script and pipes it straight into a shell",
        "fix": "Download to a file, inspect it, then run explicitly. Never pipe network output to a shell",
    },
    {
        "regex": r"\|\s*(?:ba|z)?sh\b",
        "severity": Severity.HIGH,
        "category": "PIPE-TO-SHELL",
        "risk": "Pipes command output into a shell interpreter",
        "fix": "Avoid piping into a shell; run an inspected script instead",
    },
    {
        "regex": r"\b(?:nc|ncat|netcat)\b\s+-[a-z]*e|\b(?:nc|ncat|netcat)\b\s+-[a-z]*l",
        "severity": Severity.CRITICAL,
        "category": "REVERSE-SHELL",
        "risk": "netcat with -e/-l - classic reverse-shell or listener",
        "fix": "Remove netcat usage from an auto-run manifest",
    },
    {
        "regex": r"\b(?:ba|z)?sh\s+-c\b",
        "severity": Severity.HIGH,
        "category": "INLINE-SHELL",
        "risk": "Executes an inline shell command string on load",
        "fix": "Move logic into a version-controlled, inspectable script file",
    },
    {
        "regex": r"\b(?:python3?|node|deno|perl|ruby)\s+-(?:e|c)\b",
        "severity": Severity.HIGH,
        "category": "INLINE-CODE",
        "risk": "Runs an inline code string via an interpreter -e/-c flag",
        "fix": "Move code into an inspectable script file committed to the repo",
    },
    {
        "regex": r"\beval\b",
        "severity": Severity.HIGH,
        "category": "EVAL",
        "risk": "Dynamic eval of a string in an auto-run command",
        "fix": "Remove eval; use explicit, static logic",
    },
    {
        "regex": r"\bbase64\b\s+-{0,2}[dD]\b|--decode|\bb64decode\b|\bbase64\b\s+--decode",
        "severity": Severity.HIGH,
        "category": "OBFUSCATION",
        "risk": "Base64 decoding inside an auto-run command - may hide a payload",
        "fix": "Replace with readable, reviewable content",
    },
    {
        "regex": r">>?\s*\S*\.(?:bashrc|zshrc|bash_profile|zprofile|profile)\b",
        "severity": Severity.CRITICAL,
        "category": "PERSISTENCE",
        "risk": "Writes to a shell startup file - installs persistence",
        "fix": "Remove writes to shell startup files",
    },
    {
        "regex": r"(?:>>?\s*)?~?/?\.ssh/authorized_keys",
        "severity": Severity.CRITICAL,
        "category": "PERSISTENCE",
        "risk": "Touches ~/.ssh/authorized_keys - may plant an SSH key",
        "fix": "Remove all access to authorized_keys",
    },
    {
        "regex": r"\bcrontab\b|/etc/cron",
        "severity": Severity.HIGH,
        "category": "PERSISTENCE",
        "risk": "Modifies cron - scheduled persistence",
        "fix": "Remove cron modification from an auto-run manifest",
    },
    {
        "regex": r"\bchmod\b\s+(?:[0-7]*[4567][0-7]{3}\b|u\+s|g\+s|\+s)",
        "severity": Severity.CRITICAL,
        "category": "PRIV-ESC",
        "risk": "Sets SUID/SGID bit - privilege escalation",
        "fix": "Never set SUID/SGID from a manifest",
    },
    {
        "regex": r"\bsudo\b",
        "severity": Severity.HIGH,
        "category": "PRIV-ESC",
        "risk": "Elevates privileges on load",
        "fix": "Manifests must run as the invoking user; remove sudo",
    },
    {
        "regex": r"\brm\s+-rf\b",
        "severity": Severity.HIGH,
        "category": "DESTRUCTIVE",
        "risk": "Recursive force-delete in an auto-run command",
        "fix": "Remove destructive deletion or scope it to a validated path",
    },
    {
        "regex": r"\b(?:npx|bunx)\s+(?:-y|--yes)\b|\buvx\b|\bpnpm\s+dlx\b",
        "severity": Severity.MEDIUM,
        "category": "AUTO-FETCH",
        "risk": "Auto-fetches and runs a package at startup without a prompt",
        "fix": "Pin the exact version, verify the publisher, prefer a vendored/pinned install",
    },
    {
        "regex": r"\b(?:pip3?|pipx)\s+install\b|\bnpm\s+(?:i|install|ci)\b|\byarn\s+add\b|\bpnpm\s+add\b",
        "severity": Severity.MEDIUM,
        "category": "RUNTIME-INSTALL",
        "risk": "Installs packages when the manifest loads",
        "fix": "Vendor and pin dependencies; review before install",
    },
    {
        "regex": r"https?://",
        "severity": Severity.MEDIUM,
        "category": "NETWORK",
        "risk": "Contacts a network endpoint at startup",
        "fix": "Verify the host is trusted and the call is necessary",
    },
]


def assess_command(command_text, file, locator, report):
    """Scan a command/arg string for dangerous content. Returns True if any pattern matched."""
    matched = False
    for pat in COMMAND_RISK_PATTERNS:
        if re.search(pat["regex"], command_text):
            matched = True
            report.add(
                pat["severity"],
                pat["category"],
                file,
                locator,
                command_text,
                pat["risk"],
                pat["fix"],
            )
    return matched


SECRET_KEY_RE = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|access[_-]?key|private[_-]?key|credential)")
ENV_EXPANSION_RE = re.compile(r"\$\{?[A-Za-z_]")


def looks_like_hardcoded_secret(key, value):
    if not isinstance(value, str) or not value.strip():
        return False
    if ENV_EXPANSION_RE.search(value):
        return False  # references an env var, not a literal
    if not SECRET_KEY_RE.search(str(key)):
        return False
    return len(value.strip()) >= 8


def audit_env_block(env, file, base_locator, report):
    if not isinstance(env, dict):
        return
    for k, v in env.items():
        if looks_like_hardcoded_secret(k, v):
            report.add(
                Severity.HIGH,
                "CRED-EXPOSURE",
                file,
                f"{base_locator}.env.{k}",
                "<redacted literal value>",
                "A credential appears hardcoded as a literal in the manifest env",
                "Remove the literal; inject secrets via environment expansion (${VAR}) at runtime",
            )


# =============================================================================
# MCP SERVER AUDITING (.mcp.json)
# =============================================================================

def audit_mcp_document(data, file, report):
    servers = None
    if isinstance(data, dict):
        servers = data.get("mcpServers")
        if servers is None and all(isinstance(v, dict) for v in data.values()) and data:
            # some configs put the map at the top level
            servers = data
    if not isinstance(servers, dict):
        return
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        loc = f"mcpServers.{name}"
        command = spec.get("command")
        args = spec.get("args") or []
        stype = spec.get("type")
        url = spec.get("url")

        if command:
            full = " ".join([str(command)] + [str(a) for a in args if a is not None])
            if not assess_command(full, file, f"{loc}.command", report):
                report.add(
                    Severity.INFO,
                    "STDIO-SERVER",
                    file,
                    f"{loc}.command",
                    full,
                    "MCP server auto-executes this command every time the agent loads the project",
                    "Confirm the command, args, and publisher are trusted before enabling",
                )

        if url or stype in ("http", "sse", "streamable-http"):
            u = str(url or "")
            if u.startswith("http://"):
                report.add(
                    Severity.HIGH,
                    "REMOTE-SERVER",
                    file,
                    f"{loc}.url",
                    u,
                    "Remote MCP server reachable over plaintext HTTP - context sent in the clear",
                    "Use HTTPS and verify the endpoint is trusted",
                )
            else:
                report.add(
                    Severity.MEDIUM,
                    "REMOTE-SERVER",
                    file,
                    f"{loc}.url",
                    u or f"type={stype}",
                    "Remote MCP server sends conversation context to an external endpoint",
                    "Verify the host is trusted and the data flow is expected",
                )

        audit_env_block(spec.get("env"), file, loc, report)


# =============================================================================
# HOOK BLOCK AUDITING (settings.json / hooks.json / plugin.json)
# =============================================================================

def audit_hooks_block(hooks, file, report):
    """hooks is a dict of Event -> list of matcher groups (each with a 'hooks' list)."""
    if not isinstance(hooks, dict):
        return
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            groups = [groups]
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher", "*")
            hook_list = group.get("hooks")
            if hook_list is None and group.get("type") == "command":
                hook_list = [group]  # some schemas inline a single hook
            if not isinstance(hook_list, list):
                continue
            for hook in hook_list:
                if not isinstance(hook, dict):
                    continue
                if hook.get("type") not in (None, "command"):
                    continue
                cmd = hook.get("command")
                if not cmd:
                    continue
                loc = f"hooks.{event}[{matcher}]"
                report.add(
                    Severity.HIGH,
                    "AUTO-HOOK",
                    file,
                    loc,
                    cmd,
                    f"Command auto-executes on the '{event}' event with no per-run prompt",
                    "Confirm the hook command is trusted; hooks run automatically on agent events",
                )
                assess_command(str(cmd), file, loc, report)


BROAD_PERMISSION_RE = re.compile(r"\((?:\*|\*:\*)\)$|^\*$")
DANGEROUS_PERMISSION_RE = re.compile(
    r"(?i)Bash\(\s*(?:sudo|curl|wget|rm|chmod|chown|nc|ncat|netcat|ssh|scp|eval|dd|mkfs)\b"
)


def audit_permissions(perms, file, report):
    if not isinstance(perms, dict):
        return
    mode = perms.get("defaultMode")
    if mode == "bypassPermissions":
        report.add(
            Severity.CRITICAL,
            "PERMISSIONS",
            file,
            "permissions.defaultMode",
            mode,
            "bypassPermissions disables every permission prompt - the agent runs tools unchecked",
            "Remove or set to 'default'/'plan'; require prompts for tool use",
        )
    elif mode == "acceptEdits":
        report.add(
            Severity.MEDIUM,
            "PERMISSIONS",
            file,
            "permissions.defaultMode",
            mode,
            "acceptEdits auto-approves file edits without a prompt",
            "Confirm this is intended for the project scope",
        )

    allow = perms.get("allow") or []
    if isinstance(allow, list):
        for entry in allow:
            e = str(entry)
            if e in ("Bash", "*", "Bash(*)", "Bash(*:*)") or BROAD_PERMISSION_RE.search(e):
                report.add(
                    Severity.HIGH,
                    "PERMISSIONS",
                    file,
                    "permissions.allow",
                    e,
                    "Overly broad permission grant - approves a whole tool class without scoping",
                    "Scope allow rules to specific commands (e.g. Bash(npm run test:*))",
                )
            elif DANGEROUS_PERMISSION_RE.search(e):
                report.add(
                    Severity.HIGH,
                    "PERMISSIONS",
                    file,
                    "permissions.allow",
                    e,
                    "Allowlists a dangerous command family without a prompt",
                    "Remove; require explicit approval for privileged/network/destructive commands",
                )
            elif e in ("WebFetch", "WebSearch"):
                report.add(
                    Severity.MEDIUM,
                    "PERMISSIONS",
                    file,
                    "permissions.allow",
                    e,
                    "Unscoped network tool grant",
                    "Scope to specific domains where supported",
                )


def audit_settings_document(data, file, report):
    if not isinstance(data, dict):
        return
    audit_permissions(data.get("permissions"), file, report)

    if data.get("enableAllProjectMcpServers") is True:
        report.add(
            Severity.HIGH,
            "MCP-TRUST",
            file,
            "enableAllProjectMcpServers",
            "true",
            "Auto-trusts every MCP server declared in the project without a prompt",
            "Set to false and enable servers individually after review",
        )

    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        audit_hooks_block(hooks, file, report)

    helper = data.get("apiKeyHelper")
    if isinstance(helper, str) and helper.strip():
        report.add(
            Severity.MEDIUM,
            "CRED-COMMAND",
            file,
            "apiKeyHelper",
            helper,
            "Runs a shell command to fetch a credential on startup",
            "Verify the helper command is trusted; it executes automatically",
        )
        assess_command(helper, file, "apiKeyHelper", report)

    audit_env_block(data.get("env"), file, "settings", report)


def audit_plugin_document(data, file, report):
    if not isinstance(data, dict):
        return
    # A foreign plugin manifest may inline hooks or MCP servers.
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        audit_hooks_block(hooks, file, report)
    if isinstance(data.get("mcpServers"), dict):
        audit_mcp_document({"mcpServers": data["mcpServers"]}, file, report)


def audit_hooks_document(data, file, report):
    """A standalone hooks.json: either {"hooks": {...}} or a bare event map."""
    if not isinstance(data, dict):
        return
    if isinstance(data.get("hooks"), dict):
        audit_hooks_block(data["hooks"], file, report)
    else:
        # treat top level as the event map
        audit_hooks_block(data, file, report)


# =============================================================================
# HOOK SCRIPT FILES (.git/hooks, .githooks, .husky)
# =============================================================================

def audit_hook_script(path, file_label, hook_source, report):
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    report.add(
        Severity.HIGH,
        "AUTO-HOOK-FILE",
        file_label,
        hook_source,
        Path(path).name,
        f"Active {hook_source} auto-executes on the corresponding event",
        "Read the hook body; hooks run without a prompt. Remove if unexpected",
    )
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assess_command(stripped, file_label, f"{hook_source}:{i}", report)


# =============================================================================
# DISCOVERY / DISPATCH
# =============================================================================

MANIFEST_DISPATCH = {
    ".mcp.json": ("mcp", audit_mcp_document),
    "settings.json": ("settings", audit_settings_document),
    "settings.local.json": ("settings", audit_settings_document),
    "hooks.json": ("hooks", audit_hooks_document),
    "plugin.json": ("plugin", audit_plugin_document),
}


def parse_json_file(path, file_label, report):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        report.add(
            Severity.INFO, "PARSE", file_label, "-", str(exc),
            "Manifest could not be read", "Check file permissions/encoding",
        )
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        report.add(
            Severity.MEDIUM, "PARSE", file_label, f"line {exc.lineno}", exc.msg,
            "Manifest is not valid JSON - it cannot be safely reasoned about",
            "Fix JSON syntax or treat the manifest as untrusted",
        )
        return None


def audit_path(root: Path, report: ManifestReport):
    root = root.resolve()

    # Single-file mode
    if root.is_file():
        name = root.name
        if name in MANIFEST_DISPATCH:
            kind, handler = MANIFEST_DISPATCH[name]
            data = parse_json_file(root, name, report)
            if data is not None:
                report.manifests_scanned += 1
                handler(data, name, report)
        else:
            report.add(
                Severity.INFO, "SKIP", name, "-", name,
                "Not a recognized manifest filename", "Point at a directory or a known manifest",
            )
        return

    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        rel = dp.relative_to(root)
        parts = rel.parts

        # Git hooks: .git/hooks/*  (skip inactive *.sample)
        if parts[-2:] == (".git", "hooks"):
            for fn in filenames:
                if fn.endswith(".sample"):
                    continue
                report.manifests_scanned += 1
                audit_hook_script(dp / fn, str(rel / fn), "git hook", report)
            continue

        # Shared / husky hook directories
        if dp.name in (".githooks", ".husky"):
            hlabel = "shared git hook" if dp.name == ".githooks" else "husky hook"
            for fn in filenames:
                if fn.lower() in ("readme", "readme.md", ".gitignore", "_"):
                    continue
                report.manifests_scanned += 1
                audit_hook_script(dp / fn, str(rel / fn), hlabel, report)
            continue

        # .git/config hooksPath relocation
        if parts[-1:] == (".git",) and "config" in filenames:
            cfg = dp / "config"
            try:
                if "hooksPath" in cfg.read_text(encoding="utf-8", errors="replace"):
                    report.add(
                        Severity.MEDIUM, "HOOKS-PATH", str(rel / "config"), "core.hooksPath",
                        "hooksPath set",
                        "git core.hooksPath relocates hooks - check the referenced directory",
                        "Inspect the directory core.hooksPath points to for auto-run scripts",
                    )
            except Exception:
                pass

        # JSON manifests
        for fn in filenames:
            if fn in MANIFEST_DISPATCH:
                _kind, handler = MANIFEST_DISPATCH[fn]
                file_label = fn if str(rel) == "." else str(rel / fn)
                data = parse_json_file(dp / fn, file_label, report)
                if data is not None:
                    report.manifests_scanned += 1
                    handler(data, file_label, report)


# =============================================================================
# OUTPUT
# =============================================================================

def print_report(report: ManifestReport, strict: bool):
    verdict = report.verdict(strict)
    print()
    print("=" * 60)
    print("MANIFEST AUTO-EXECUTION AUDIT")
    print("Root:    " + report.root)
    print("Verdict: " + verdict)
    print(
        "Findings: CRITICAL={} HIGH={} MEDIUM={} INFO={} (manifests scanned: {})".format(
            report.critical, report.high, report.medium, report.info, report.manifests_scanned
        )
    )
    print("=" * 60)

    if not report.findings:
        print("\nNo manifest auto-execution surfaces found.\n")
        return

    print()
    ordered = sorted(report.findings, key=lambda f: -int(f.severity))
    for f in ordered:
        loc = "{}:{}".format(f.file, f.locator) if f.locator not in ("-", "") else f.file
        print("[{}] [{}] {}".format(SEVERITY_NAMES[f.severity], f.category, loc))
        print("   Detail: " + f.detail)
        print("   Risk:   " + f.risk)
        print("   Fix:    " + f.fix)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Manifest Auditor - scan agent manifests (.mcp.json, settings.json, "
        "hooks, git hooks) for auto-execution attack surfaces before trusting a project.",
    )
    parser.add_argument("path", help="Path to a project/skill directory or a single manifest file")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Emit a JSON report instead of formatted text")
    parser.add_argument("--strict", action="store_true",
                        help="Treat MEDIUM findings as failing (exit 1) as well as HIGH/CRITICAL")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print("Error: path does not exist: {}".format(root), file=sys.stderr)
        sys.exit(2)

    report = ManifestReport(root=str(root.resolve()))
    audit_path(root, report)

    if args.json_output:
        print(json.dumps(report.to_dict(args.strict), indent=2))
    else:
        print_report(report, args.strict)

    sys.exit(1 if report.failing(args.strict) else 0)


if __name__ == "__main__":
    main()

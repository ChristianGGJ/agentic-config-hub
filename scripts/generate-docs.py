#!/usr/bin/env python3
"""Generate MkDocs documentation pages from SKILL.md files, agents, and commands."""

import os
import re
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
GITHUB_BASE = "https://github.com/ChristianGGJ/agentic-config-hub/tree/main"

# Domain mapping: directory name -> (section name, sort order, icon, plugin_name)
DOMAINS = {
    "core-agentic-design": ("Core Agentic Design", 1, ":material-robot:", "core-agentic-design"),
    "prompts-quality": ("Prompts & Quality", 2, ":material-clipboard-check:", "prompts-quality"),
    "autonomy-security": ("Autonomy & Security", 3, ":material-shield-lock:", "autonomy-security"),
    "infrastructure": ("Infrastructure", 4, ":material-server:", "infrastructure"),
}

# Mapping flat skills to domains
SKILL_DOMAINS = {
    # Core Agentic Design
    "agentic-system-architect": "core-agentic-design",
    "agent-designer": "core-agentic-design",
    "agent-workflow-designer": "core-agentic-design",
    "spec-driven-workflow": "core-agentic-design",
    "agenthub": "core-agentic-design",
    
    # Prompts & Quality
    "prompt-governance": "prompts-quality",
    "senior-prompt-engineer": "prompts-quality",
    "self-eval": "prompts-quality",
    "skill-tester": "prompts-quality",
    "focused-fix": "prompts-quality",
    "agent-self-optimization": "prompts-quality",
    
    # Autonomy & Security
    "self-improving-agent": "autonomy-security",
    "ai-security": "autonomy-security",
    "adversarial-reviewer": "autonomy-security",
    "skill-security-auditor": "autonomy-security",
    "autoresearch-agent": "autonomy-security",
    
    # Infrastructure
    "mcp-server-builder": "infrastructure",
    "rag-architect": "infrastructure",
    "llm-cost-optimizer": "infrastructure",
    "browser-automation": "infrastructure",
    "microsoft-agent-framework": "infrastructure",
    "langgraph-state-design": "infrastructure",
    "crewai-role-engineering": "core-agentic-design",
    "ms-agent-framework-enterprise": "infrastructure",
    "loop-engineering-mechanisms": "core-agentic-design",
    "multi-llm-routing": "infrastructure",
    "agentic-observability-telemetry": "infrastructure",
    "agentic-evals-benchmarking": "prompts-quality",
    "hybrid-rag-memory": "infrastructure",
    "agentic-guardrails-security": "autonomy-security"
}

# SEO keyword mapping: domain_key -> differentiating keywords for <title> tags
DOMAIN_SEO_SUFFIX = {
    "core-agentic-design": "Core Agentic Design & Loop Safety",
    "prompts-quality": "Prompts Optimization & Quality Rubrics",
    "autonomy-security": "Autonomous Guardrails & Threat Modeling",
    "infrastructure": "MCP Servers & RAG Architectures",
}

# Domain-specific description context for pages without frontmatter descriptions
DOMAIN_SEO_CONTEXT = {
    "core-agentic-design": "core agentic design patterns and loop safety audits for autonomous systems",
    "prompts-quality": "prompt engineering optimization, validation test suites, and quality scoring rubrics",
    "autonomy-security": "adversarial review, prompt injection mitigation, and skill package safety auditing",
    "infrastructure": "model-routing optimization, browser automation, and model context protocol server design",
}


def find_skill_files():
    """Walk the repo and find all SKILL.md files, grouped by domain."""
    skills = {}
    skills_dir = os.path.join(REPO_ROOT, "skills")
    if not os.path.isdir(skills_dir):
        return skills
        
    for skill_folder in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, skill_folder)
        if not os.path.isdir(skill_path):
            continue
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        if not os.path.isfile(skill_md_path):
            continue
            
        domain_key = SKILL_DOMAINS.get(skill_folder)
        if not domain_key:
            domain_key = "core-agentic-design"
            
        is_sub_skill = False
        parent = None
        
        if domain_key not in skills:
            skills[domain_key] = []
        skills[domain_key].append({
            "name": skill_folder,
            "path": skill_md_path,
            "rel_path": f"skills/{skill_folder}",
            "is_sub_skill": is_sub_skill,
            "parent": parent,
        })
    return skills


def extract_title(filepath):
    """Extract the first H1 heading from a SKILL.md file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip YAML frontmatter
                if line == "---":
                    for line2 in f:
                        if line2.strip() == "---":
                            break
                    continue
                if line.startswith("# "):
                    return line[2:].strip()
    except Exception:
        pass
    return None


def extract_subtitle(filepath):
    """Extract the first non-empty line after the first H1 heading."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            found_h1 = False
            in_frontmatter = False
            for line in f:
                stripped = line.strip()
                if stripped == "---" and not in_frontmatter:
                    in_frontmatter = True
                    for line2 in f:
                        if line2.strip() == "---":
                            break
                    continue
                if stripped.startswith("# ") and not found_h1:
                    found_h1 = True
                    continue
                if found_h1 and stripped and not stripped.startswith("#"):
                    return stripped
    except Exception:
        pass
    return None


def extract_description_from_frontmatter(filepath):
    """Extract the description field from YAML frontmatter."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.match(r"^---\n(.*?)---\n", content, re.DOTALL)
        if not match:
            return None
        fm = match.group(1)

        # Try quoted single-line: description: "text" or description: 'text'
        m = re.search(r'description:\s*"([^"]+)"', fm)
        if m:
            return m.group(1).strip()
        m = re.search(r"description:\s*'([^']+)'", fm)
        if m:
            return m.group(1).strip()

        # Try multi-line block scalar: description: | or description: >
        m = re.search(r"description:\s*[|>]-?\s*\n((?:[ \t]+.+\n?)+)", fm)
        if m:
            lines = m.group(1).strip().splitlines()
            text = " ".join(line.strip() for line in lines)
            return text

        # Try unquoted single-line: description: text
        m = re.search(r"description:\s+([^\n\"'][^\n]+)", fm)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def extract_field_from_frontmatter(filepath, field_name):
    """Extract a specific field from YAML frontmatter."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.match(r"^---\n(.*?)---\n", content, re.DOTALL)
        if not match:
            return None
        fm = match.group(1)
        m = re.search(fr'{field_name}:\s*"([^"]+)"', fm)
        if m:
            return m.group(1).strip()
        m = re.search(fr"{field_name}:\s*'([^']+)'", fm)
        if m:
            return m.group(1).strip()
        m = re.search(fr"{field_name}:\s+([^\n\"'][^\n]+)", fm)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def slugify(name):
    """Convert a skill name to a URL-friendly slug."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def prettify(name):
    """Convert kebab-case to Title Case."""
    return name.replace("-", " ").title()


def strip_content(content):
    """Strip frontmatter and first H1 from content, handling edge cases."""
    content = re.sub(r"^---\n.*?---\n", "", content, flags=re.DOTALL)
    content = content.lstrip()
    content = re.sub(r"^#\s+.+\n", "", content, count=1)
    content = re.sub(r"^\s*---\s*\n", "", content)
    return content


def rewrite_skill_internal_links(content, skill_rel_path):
    """Rewrite skill-internal relative links to GitHub source URLs."""
    internal_prefixes = ("references/", "scripts/", "assets/", "templates/", "tools/")

    def resolve_internal(match):
        text = match.group(1)
        target = match.group(2)
        if target.startswith(("#", "http://", "https://", "mailto:")):
            return match.group(0)
        if (target.startswith(internal_prefixes) or target == "README.md"
                or target.endswith((".py", ".json", ".yaml", ".yml", ".sh"))):
            github_url = f"{GITHUB_BASE}/{skill_rel_path}/{target}"
            return f"[{text}]({github_url})"
        return match.group(0)

    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", resolve_internal, content)
    return content


def rewrite_relative_links(content, source_rel_path):
    """Rewrite relative markdown links (../../, ../) to absolute GitHub URLs."""
    source_dir = os.path.dirname(source_rel_path)

    def resolve_link(match):
        text = match.group(1)
        rel_target = match.group(2)
        if not rel_target.startswith("../"):
            return match.group(0)
        resolved = os.path.normpath(os.path.join(source_dir, rel_target))
        if (resolved.startswith("agents/") and resolved.count("/") == 1
                and resolved.endswith(".md") and "CLAUDE" not in resolved):
            sibling = os.path.basename(resolved).replace(".md", "") + ".md"
            return f"[{text}]({sibling})"
        return f"[{text}]({GITHUB_BASE}/{resolved})"

    content = re.sub(r"\[([^\]]+)\]\((\.\.[^\)]+)\)", resolve_link, content)

    def resolve_backtick(match):
        rel_target = match.group(1)
        if not rel_target.startswith("../"):
            return match.group(0)
        resolved = os.path.normpath(os.path.join(source_dir, rel_target))
        parts = resolved.split("/")
        display = "/".join(parts[-2:]) if len(parts) >= 2 else resolved
        return f"[`{display}`]({GITHUB_BASE}/{resolved})"

    content = re.sub(r"`(\.\./[^`]+)`", resolve_backtick, content)
    return content


def rewrite_repo_links(content, source_rel_path):
    """Final pass: rewrite any leftover relative link to a repo file (./x, dir/x)
    into a GitHub source URL, so nothing 404s on the published site. Intra-docs
    sibling links (a bare filename with no path separator, e.g. `slug.md` in index
    cards) are preserved. Already-rewritten http(s) links are left untouched."""
    source_dir = os.path.dirname(source_rel_path)
    exts = (".md", ".py", ".json", ".yaml", ".yml", ".sh", ".txt")

    def resolve(match):
        text = match.group(1)
        target = match.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        path_part = target.split("#", 1)[0]
        if not path_part.endswith(exts):
            return match.group(0)
        # Intra-docs sibling link (bare filename, no separator, not ./ or ../): keep.
        if "/" not in path_part and not path_part.startswith("."):
            return match.group(0)
        resolved = os.path.normpath(os.path.join(source_dir, path_part)).replace(os.sep, "/")
        return f"[{text}]({GITHUB_BASE}/{resolved})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", resolve, content)


def generate_skill_page(skill, domain_key):
    """Generate a docs page for a single skill."""
    skill_md_path = skill["path"]
    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    title = extract_title(skill_md_path) or prettify(skill["name"])
    title = re.sub(r"[*_`]", "", title)
    title = re.sub(r"\s*[-—]\s*(POWERFUL|Core|Advanced)\s*$", "", title, flags=re.IGNORECASE)

    domain_name, _, domain_icon, plugin_name = DOMAINS[domain_key]
    seo_suffix = DOMAIN_SEO_SUFFIX.get(domain_key, "Claude Code Plugin & Agent Skill")
    seo_title = f"{title} — {seo_suffix}"

    fm_desc = extract_description_from_frontmatter(skill_md_path)
    desc_platforms = "Claude Code, Codex CLI, Gemini CLI, OpenClaw"
    if fm_desc:
        clean = fm_desc.strip("'\"").replace('"', "'")
        has_platform = any(k in clean.lower() for k in ["claude code", "codex", "gemini"])
        if len(clean) > 150:
            truncated = clean[:150].rsplit(" ", 1)[0].rstrip(".,;:—-")
            description = f"{truncated}." if has_platform else f"{truncated}. Agent skill for {desc_platforms}."
        else:
            desc_text = clean.rstrip(".")
            description = f"{desc_text}." if has_platform else f"{desc_text}. Agent skill for {desc_platforms}."
    else:
        seo_ctx = DOMAIN_SEO_CONTEXT.get(domain_key, f"agent skill for {domain_name}")
        description = f"{title} — {seo_ctx}. Works with {desc_platforms}."

    content_clean = strip_content(content)
    content_clean = rewrite_skill_internal_links(content_clean, skill["rel_path"])
    content_clean = rewrite_relative_links(content_clean, os.path.join(skill["rel_path"], "SKILL.md"))
    content_clean = rewrite_repo_links(content_clean, os.path.join(skill["rel_path"], "SKILL.md"))

    page = f'''---
title: "{seo_title}"
description: "{description}"
---

# {title}

<div class="page-meta" markdown>
<span class="meta-badge">{domain_icon} {domain_name}</span>
<span class="meta-badge">:material-identifier: `{skill["name"]}`</span>
<span class="meta-badge">:material-github: <a href="{GITHUB_BASE}/{skill["rel_path"]}/SKILL.md">Source</a></span>
</div>

<div class="install-banner" markdown>
<span class="install-label">Install:</span> <code>claude /plugin install {plugin_name}</code>
</div>

{content_clean}'''
    return page


def generate_nav_entry(skills_by_domain):
    """Generate the nav section for mkdocs.yml."""
    nav_lines = []
    sorted_domains = sorted(skills_by_domain.items(), key=lambda x: DOMAINS[x[0]][1])

    for domain_key, skills in sorted_domains:
        domain_name = DOMAINS[domain_key][0]
        top_level = sorted([s for s in skills if not s["is_sub_skill"]], key=lambda s: s["name"])
        nav_lines.append(f"    - {domain_name}:")
        for skill in top_level:
            slug = slugify(skill["name"])
            page_path = f"skills/{domain_key}/{slug}.md"
            title = extract_title(skill["path"]) or prettify(skill["name"])
            title = re.sub(r"[*_`]", "", title)
            nav_lines.append(f"      - \"{title}\": {page_path}")
    return "\n".join(nav_lines)


def main():
    # Clean previous generated folders inside docs/
    for sub in ["skills", "agents", "commands"]:
        d = os.path.join(DOCS_DIR, sub)
        if os.path.exists(d):
            shutil.rmtree(d)

    skills_by_domain = find_skill_files()

    # Create docs/skills/ directories
    for domain_key in skills_by_domain:
        os.makedirs(os.path.join(DOCS_DIR, "skills", domain_key), exist_ok=True)

    total = 0
    # Generate individual skill pages
    for domain_key, skills in skills_by_domain.items():
        top_level = [s for s in skills if not s["is_sub_skill"]]
        for skill in top_level:
            slug = slugify(skill["name"])
            page_content = generate_skill_page(skill, domain_key)
            page_path = os.path.join(DOCS_DIR, "skills", domain_key, f"{slug}.md")
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(page_content)
            total += 1

    # Generate domain index pages
    sorted_domains = sorted(skills_by_domain.items(), key=lambda x: DOMAINS[x[0]][1])
    for domain_key, skills in sorted_domains:
        domain_name, _, domain_icon, plugin_name = DOMAINS[domain_key]
        top_level = sorted([s for s in skills if not s["is_sub_skill"]], key=lambda s: s["name"])
        skill_count = len(skills)

        cards = ""
        for skill in top_level:
            slug = slugify(skill["name"])
            title = extract_title(skill["path"]) or prettify(skill["name"])
            title = re.sub(r"[*_`]", "", title)
            subtitle = extract_subtitle(skill["path"]) or f"`{skill['name']}`"
            subtitle = re.sub(r"[*_`\[\]]", "", subtitle)
            if len(subtitle) > 120:
                subtitle = subtitle[:117] + "..."

            cards += f"""
-   **[{title}]({slug}.md)**

    ---

    {subtitle}
"""

        domain_seo_ctx = DOMAIN_SEO_CONTEXT.get(domain_key, f"agent skills for {domain_name}")
        index_content = f'''---
title: "{domain_name} Skills — Agent Skills & Codex Plugins"
description: "{skill_count} {domain_name.lower()} skills — {domain_seo_ctx}. Works with Claude Code, Codex CLI, Gemini CLI, and OpenClaw."
---

<div class="domain-header" markdown>

# {domain_icon} {domain_name}

<p class="domain-count">{skill_count} skills in this domain</p>

</div>

<div class="install-banner" markdown>
<span class="install-label">Install all:</span> <code>claude /plugin install {plugin_name}</code>
</div>

<div class="grid cards" markdown>
{cards}
</div>
'''

        index_path = os.path.join(DOCS_DIR, "skills", domain_key, "index.md")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_content)

    # Generate agent pages (flat agents/cs-*.md)
    agents_dir = os.path.join(REPO_ROOT, "agents")
    agents_docs_dir = os.path.join(DOCS_DIR, "agents")
    os.makedirs(agents_docs_dir, exist_ok=True)
    agent_count = 0
    agent_entries = []

    if os.path.isdir(agents_dir):
        for agent_file in sorted(os.listdir(agents_dir)):
            if not agent_file.endswith(".md") or agent_file == "CLAUDE.md":
                continue
            agent_name = agent_file.replace(".md", "")
            agent_path = os.path.join(agents_dir, agent_file)
            rel = os.path.relpath(agent_path, REPO_ROOT)
            title = extract_title(agent_path) or prettify(agent_name)
            title = re.sub(r"[*_`]", "", title)
            if re.match(r"^cs-[a-z-]+$", title):
                title = prettify(title.removeprefix("cs-"))

            with open(agent_path, "r", encoding="utf-8") as f:
                content = f.read()

            content_clean = strip_content(content)
            content_clean = rewrite_relative_links(content_clean, rel)
            content_clean = rewrite_repo_links(content_clean, rel)

            agent_seo_title = f"{title} — AI Coding Agent"
            agent_fm_desc = extract_description_from_frontmatter(agent_path)
            if agent_fm_desc:
                agent_clean = agent_fm_desc.strip("'\"").replace('"', "'")
                if len(agent_clean) > 150:
                    agent_clean = agent_clean[:150].rsplit(" ", 1)[0].rstrip(".,;:—-")
                agent_desc = f"{agent_clean}. Agent-native orchestrator for Claude Code."
            else:
                agent_desc = f"{title} — agent-native AI orchestrator. Works with Claude Code."

            page = f'''---
title: "{agent_seo_title}"
description: "{agent_desc}"
---

# {title}

<div class="page-meta" markdown>
<span class="meta-badge">:material-robot: Agent</span>
<span class="meta-badge">:material-github: <a href="{GITHUB_BASE}/{rel}">Source</a></span>
</div>

{content_clean}'''
            slug = slugify(agent_name)
            out_path = os.path.join(agents_docs_dir, f"{slug}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(page)
            agent_count += 1
            agent_entries.append((title, slug))

    # Generate agents index
    if agent_entries:
        agent_cards = ""
        for title, slug in agent_entries:
            agent_cards += f"""
-   :material-robot:{{ .lg .middle }} **[{title}]({slug}.md)**

    ---

    Role-bound Agentic Orchestrator
"""

        idx = f'''---
title: "AI Coding Agents — Agent-Native Orchestrators"
description: "{agent_count} agent-native orchestrators for Claude Code, Codex, and Gemini CLI."
---

<div class="domain-header" markdown>

# :material-robot: Agents

<p class="domain-count">{agent_count} agents that orchestrate skills across domains</p>

</div>

<div class="grid cards" markdown>
{agent_cards}
</div>
'''
        with open(os.path.join(agents_docs_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(idx)

    # Generate command pages
    commands_dir = os.path.join(REPO_ROOT, "commands")
    commands_docs_dir = os.path.join(DOCS_DIR, "commands")
    os.makedirs(commands_docs_dir, exist_ok=True)
    cmd_count = 0
    cmd_entries = []

    if os.path.isdir(commands_dir):
        for cmd_file in sorted(os.listdir(commands_dir)):
            if not cmd_file.endswith(".md") or cmd_file == "CLAUDE.md":
                continue
            cmd_name = cmd_file.replace(".md", "")
            cmd_path = os.path.join(commands_dir, cmd_file)
            rel = os.path.relpath(cmd_path, REPO_ROOT)
            title = extract_title(cmd_path) or prettify(cmd_name)
            title = re.sub(r"[*_`]", "", title)

            with open(cmd_path, "r", encoding="utf-8") as f:
                content = f.read()

            content_clean = strip_content(content)
            content_clean = rewrite_relative_links(content_clean, rel)
            content_clean = rewrite_repo_links(content_clean, rel)

            cmd_fm_desc = extract_description_from_frontmatter(cmd_path)
            if cmd_fm_desc:
                cmd_clean = cmd_fm_desc.strip("'\"").replace('"', "'")
                if len(cmd_clean) > 150:
                    cmd_clean = cmd_clean[:150].rsplit(" ", 1)[0].rstrip(".,;:—-")
                cmd_desc = f"{cmd_clean}. Slash command for Claude Code, Codex CLI, Gemini CLI."
            else:
                cmd_desc = f"/{cmd_name} — slash command for Claude Code, Codex CLI, and Gemini CLI. Run directly in your AI coding agent."

            page = f'''---
title: "/{cmd_name} — Slash Command for AI Coding Agents"
description: "{cmd_desc}"
---

# /{cmd_name}

<div class="page-meta" markdown>
<span class="meta-badge">:material-console: Slash Command</span>
<span class="meta-badge">:material-github: <a href="{GITHUB_BASE}/{rel}">Source</a></span>
</div>

{content_clean}'''
            slug = slugify(cmd_name)
            out_path = os.path.join(commands_docs_dir, f"{slug}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(page)
            cmd_count += 1
            desc = extract_subtitle(cmd_path) or title
            cmd_entries.append((cmd_name, slug, title, desc))

    # Generate commands index
    if cmd_entries:
        cmd_cards = ""
        for name, slug, title, desc in cmd_entries:
            desc_clean = re.sub(r"[*_`\[\]]", "", desc)
            if len(desc_clean) > 120:
                desc_clean = desc_clean[:117] + "..."
            cmd_cards += f"""
-   :material-console:{{ .lg .middle }} **[`/{name}`]({slug}.md)**

    ---

    {desc_clean}
"""

        idx = f'''---
title: "Slash Commands — AI Coding Agent Commands"
description: "{cmd_count} slash commands for Claude Code, Codex CLI, and Gemini CLI."
---

<div class="domain-header" markdown>

# :material-console: Slash Commands

<p class="domain-count">{cmd_count} commands for quick access to common operations</p>

</div>

<div class="grid cards" markdown>
{cmd_cards}
</div>
'''
        with open(os.path.join(commands_docs_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(idx)

    # Copy root README.md to docs/index.md for home page
    readme_src = os.path.join(REPO_ROOT, "README.md")
    readme_dest = os.path.join(DOCS_DIR, "index.md")
    if os.path.isfile(readme_src):
        with open(readme_src, "r", encoding="utf-8") as f:
            readme_content = f.read()
        readme_content_clean = strip_content(readme_content)
        readme_content_clean = rewrite_relative_links(readme_content_clean, "README.md")
        readme_content_clean = rewrite_repo_links(readme_content_clean, "README.md")
        readme_page = f'''---
title: "Agentic Config Hub"
description: "Curated library of production-ready configurations for AI agents and agentic systems."
---

{readme_content_clean}'''
        with open(readme_dest, "w", encoding="utf-8") as f:
            f.write(readme_page)

    # Print summary
    print(f"Generated {total} skill pages across {len(skills_by_domain)} domains.")
    print(f"Generated {agent_count} agent pages.")
    print(f"Generated {cmd_count} command pages.")
    print(f"Total: {total + agent_count + cmd_count} pages.")


if __name__ == "__main__":
    main()

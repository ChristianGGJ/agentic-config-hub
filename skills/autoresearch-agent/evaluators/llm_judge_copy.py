#!/usr/bin/env python3
"""LLM judge for marketing copy (social posts, ads, emails).
Uses the user's existing CLI tool for evaluation.
DO NOT MODIFY after experiment starts — this is the fixed evaluator."""

import os
import statistics
import subprocess
import sys
from pathlib import Path

# --- CONFIGURE THESE ---
TARGET_FILE = "posts.md"           # Copy being optimized
CLI_TOOL = "claude"                # or: codex, gemini
PLATFORM = "twitter"               # twitter, linkedin, instagram, email, ad
# --- END CONFIG ---

JUDGE_PROMPTS = {
    "twitter": """Score this Twitter/X post strictly:
1. HOOK (1-10) — Does the first line stop the scroll?
2. VALUE (1-10) — Does it provide insight, entertainment, or utility?
3. ENGAGEMENT (1-10) — Would people reply, retweet, or like?
4. BREVITY (1-10) — Is every word earning its place? No filler?
5. CTA (1-10) — Is there a clear next action (even implicit)?""",

    "linkedin": """Score this LinkedIn post strictly:
1. HOOK (1-10) — Does the first line make you click "see more"?
2. STORYTELLING (1-10) — Is there a narrative arc or just statements?
3. CREDIBILITY (1-10) — Does it demonstrate expertise without bragging?
4. ENGAGEMENT (1-10) — Would professionals comment or share?
5. CTA (1-10) — Does it invite discussion or action?""",

    "instagram": """Score this Instagram caption strictly:
1. HOOK (1-10) — Does the first line grab attention?
2. RELATABILITY (1-10) — Does the audience see themselves in this?
3. VISUAL MATCH (1-10) — Does the copy complement visual content?
4. HASHTAG STRATEGY (1-10) — Are hashtags relevant and not spammy?
5. CTA (1-10) — Does it encourage saves, shares, or comments?""",

    "email": """Score this email subject + preview strictly:
1. OPEN INCENTIVE (1-10) — Would you open this in a crowded inbox?
2. SPECIFICITY (1-10) — Is it concrete or vague?
3. URGENCY (1-10) — Is there a reason to open now vs later?
4. PERSONALIZATION (1-10) — Does it feel written for someone, not everyone?
5. PREVIEW SYNC (1-10) — Does the preview text complement the subject?""",

    "ad": """Score this ad copy strictly:
1. ATTENTION (1-10) — Does it stop someone scrolling past ads?
2. DESIRE (1-10) — Does it create want for the product/service?
3. PROOF (1-10) — Is there credibility (numbers, social proof)?
4. ACTION (1-10) — Is the CTA clear and compelling?
5. OBJECTION HANDLING (1-10) — Does it preempt "why not"?""",
}

platform_prompt = JUDGE_PROMPTS.get(PLATFORM, JUDGE_PROMPTS["twitter"])

JUDGE_PROMPT = f"""{platform_prompt}

IMPORTANT: You MUST use criterion_1 through criterion_5 as labels, NOT the criterion names.
Do NOT output "hook: 7" — output "criterion_1: 7".

Output EXACTLY this format:
criterion_1: <score>
criterion_2: <score>
criterion_3: <score>
criterion_4: <score>
criterion_5: <score>
engagement_score: <average of all 5>

Be harsh. Most copy is mediocre (4-6). Only exceptional copy scores 8+."""

try:
    content = Path(TARGET_FILE).read_text()
except FileNotFoundError:
    print(f"Target file not found: {TARGET_FILE}", file=sys.stderr)
    sys.exit(1)

full_prompt = f"{JUDGE_PROMPT}\n\n---\n\nCopy to evaluate:\n\n{content}"


def _run_judge_once(prompt):
    """One judge call. Returns (engagement_score, component_lines) or (None, [])."""
    proc = subprocess.run(
        [CLI_TOOL, "-p", prompt],
        capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        print(f"LLM judge call failed: {proc.stderr[:200]}", file=sys.stderr)
        return None, []
    out = proc.stdout
    eng = None
    components = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("engagement_score:"):
            try:
                eng = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("criterion_"):
            components.append(line)
    # Fallback: parse "word: digit" lines if no structured labels were found
    if eng is None and not components:
        import re
        fallback = []
        for line in out.splitlines():
            line = line.strip()
            match = re.match(r'^(\w[\w\s]*?):\s*(\d+(?:\.\d+)?)\s*$', line)
            if match and match.group(1).lower() != "engagement_score":
                fallback.append(float(match.group(2)))
                components.append(f"criterion_{len(fallback)}: {match.group(2)}")
        if fallback:
            eng = sum(fallback) / len(fallback)
    return eng, components


# Average multiple judge calls to damp LLM-judge variance
# (see SKILL.md > Reducing LLM-Judge Variance). Override with AR_JUDGE_SAMPLES.
try:
    n_samples = max(1, int(os.environ.get("AR_JUDGE_SAMPLES", "3")))
except ValueError:
    n_samples = 3

scores = []
first_components = []
for _ in range(n_samples):
    eng, components = _run_judge_once(full_prompt)
    if eng is not None:
        scores.append(eng)
        if not first_components:
            first_components = components

if not scores:
    print("Could not parse engagement_score from any LLM judge call", file=sys.stderr)
    sys.exit(1)

for line in first_components:
    print(line)

print(f"engagement_score: {statistics.median(scores):.2f}")
print(f"engagement_score_samples: {len(scores)}")
if len(scores) > 1:
    print(f"engagement_score_stddev: {statistics.stdev(scores):.3f}")

#!/usr/bin/env python3
"""LLM judge for prompt/instruction quality.
Uses the user's existing CLI tool for evaluation.
DO NOT MODIFY after experiment starts — this is the fixed evaluator."""

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

# --- CONFIGURE THESE ---
TARGET_FILE = "prompt.md"          # Prompt being optimized
TEST_CASES_FILE = "tests/cases.json"  # Test cases: [{"input": "...", "expected": "..."}]
CLI_TOOL = "claude"                # or: codex, gemini
# --- END CONFIG ---

JUDGE_PROMPT_TEMPLATE = """You are evaluating a system prompt's effectiveness.

SYSTEM PROMPT BEING TESTED:
{prompt}

TEST INPUT:
{input}

EXPECTED OUTPUT (reference):
{expected}

ACTUAL OUTPUT:
{actual}

Score the actual output on these criteria (each 1-10):
1. ACCURACY — Does it match the expected output's intent and facts?
2. COMPLETENESS — Does it cover all required elements?
3. CLARITY — Is it well-structured and easy to understand?
4. INSTRUCTION_FOLLOWING — Does it follow the system prompt's guidelines?

Output EXACTLY: quality_score: <average of all 4>
Nothing else."""

try:
    prompt = Path(TARGET_FILE).read_text()
except FileNotFoundError:
    print(f"Target file not found: {TARGET_FILE}", file=sys.stderr)
    sys.exit(1)

try:
    test_cases = json.loads(Path(TEST_CASES_FILE).read_text())
except FileNotFoundError:
    print(f"Test cases file not found: {TEST_CASES_FILE}", file=sys.stderr)
    sys.exit(1)

# Average multiple judge calls per case to damp LLM-judge variance
# (see SKILL.md > Reducing LLM-Judge Variance). Override with AR_JUDGE_SAMPLES.
try:
    n_samples = max(1, int(os.environ.get("AR_JUDGE_SAMPLES", "3")))
except ValueError:
    n_samples = 3


def judge_score(prompt_text):
    """Sample the judge n_samples times; return the median score or None."""
    vals = []
    for _ in range(n_samples):
        jr = subprocess.run(
            [CLI_TOOL, "-p", prompt_text],
            capture_output=True, text=True, timeout=60
        )
        if jr.returncode != 0:
            continue
        for line in jr.stdout.splitlines():
            if "quality_score:" in line:
                try:
                    vals.append(float(line.split(":")[-1].strip()))
                except ValueError:
                    pass
                break
    if not vals:
        return None
    return statistics.median(vals)


scores = []

for i, case in enumerate(test_cases):
    # Generate output using the prompt
    gen_prompt = f"{prompt}\n\n{case['input']}"
    gen_result = subprocess.run(
        [CLI_TOOL, "-p", gen_prompt],
        capture_output=True, text=True, timeout=60
    )
    if gen_result.returncode != 0:
        print(f"Generation failed for case {i+1}", file=sys.stderr)
        scores.append(0)
        continue

    actual = gen_result.stdout.strip()

    # Judge the output
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt[:500],
        input=case["input"],
        expected=case.get("expected", "N/A"),
        actual=actual[:500]
    )

    case_score = judge_score(judge_prompt)
    scores.append(case_score if case_score is not None else 0)

    print(f"  Case {i+1}/{len(test_cases)}: {scores[-1]:.1f}", file=sys.stderr)

if not scores:
    print("No test cases evaluated", file=sys.stderr)
    sys.exit(1)

avg = sum(scores) / len(scores)
quality = avg * 10  # 1-10 scores → 10-100 range

print(f"quality_score: {quality:.2f}")
print(f"cases_tested: {len(scores)}")
print(f"avg_per_case: {avg:.2f}")
if len(scores) > 1:
    print(f"quality_score_stddev: {statistics.pstdev([s * 10 for s in scores]):.3f}")

#!/usr/bin/env python3
"""
Prompt Optimizer - Static analysis tool for prompt engineering

Features:
- Token estimation (per model family approximation)
- Relative cost estimation by capability tier (optionally in USD via --price-per-mtok)
- Prompt structure analysis
- Clarity scoring
- Few-shot example extraction, management, and validation
- Optimization suggestions

Usage:
    python prompt_optimizer.py prompt.txt --analyze
    python prompt_optimizer.py prompt.txt --tokens --model claude --tier standard
    python prompt_optimizer.py prompt.txt --tokens --tier frontier --price-per-mtok 15.0
    python prompt_optimizer.py prompt.txt --optimize --output optimized.txt
    python prompt_optimizer.py prompt.txt --extract-examples --output examples.json
    python prompt_optimizer.py prompt.txt --validate-examples
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


# Token estimation ratios (chars per token approximation, English prose)
# Keyed by model FAMILY, not model ID -- IDs churn too fast to hard-code.
TOKEN_RATIOS = {
    'claude': 3.5,
    'gpt': 4.0,
    'gemini': 4.0,
    'default': 4.0
}

# Relative input-cost multipliers by capability tier, normalized to fast = 1.0.
# These are order-of-magnitude ratios that hold across major providers as of
# 2026 (small/fast tier vs balanced workhorse tier vs frontier tier). Absolute
# $/MTok prices change too often to hard-code here: pass --price-per-mtok with
# your provider's current published INPUT price to get dollar estimates.
COST_TIER_MULTIPLIERS = {
    'fast': 1.0,       # small/fast models (e.g. Haiku-class, mini/nano/flash-class)
    'standard': 4.0,   # balanced workhorse models (e.g. Sonnet-class)
    'frontier': 15.0   # top capability/reasoning models (e.g. Opus-class)
}


@dataclass
class PromptAnalysis:
    """Results of prompt analysis"""
    token_count: int
    model_family: str
    cost_tier: str
    relative_cost_units: float
    estimated_cost_usd: Optional[float]
    clarity_score: int
    structure_score: int
    issues: List[Dict[str, str]]
    suggestions: List[str]
    sections: List[Dict[str, any]]
    has_examples: bool
    example_count: int
    has_output_format: bool
    word_count: int
    line_count: int


@dataclass
class FewShotExample:
    """A single few-shot example"""
    input_text: str
    output_text: str
    index: int


def estimate_tokens(text: str, model: str = 'default') -> int:
    """Estimate token count based on character ratio"""
    ratio = TOKEN_RATIOS.get(model, TOKEN_RATIOS['default'])
    return int(len(text) / ratio)


def estimate_relative_cost(token_count: int, tier: str = 'standard') -> float:
    """Relative cost in 'fast-tier token-kilounits': tokens/1000 * tier multiplier.

    Useful for comparing prompts and tiers against each other without
    depending on volatile absolute prices.
    """
    multiplier = COST_TIER_MULTIPLIERS.get(tier, COST_TIER_MULTIPLIERS['standard'])
    return round((token_count / 1000) * multiplier, 4)


def estimate_cost_usd(token_count: int, price_per_mtok: Optional[float]) -> Optional[float]:
    """Estimate input cost in USD when the caller supplies a current $/MTok price."""
    if price_per_mtok is None:
        return None
    return round((token_count / 1_000_000) * price_per_mtok, 6)


def find_ambiguous_instructions(text: str) -> List[Dict[str, str]]:
    """Find vague or ambiguous instructions"""
    issues = []

    # Vague verbs that need specificity
    vague_patterns = [
        (r'\b(analyze|process|handle|deal with)\b', 'Vague verb - specify the exact action'),
        (r'\b(good|nice|appropriate|suitable)\b', 'Subjective term - define specific criteria'),
        (r'\b(etc\.|and so on|and more)\b', 'Open-ended list - enumerate all items explicitly'),
        (r'\b(if needed|as necessary|when appropriate)\b', 'Conditional without criteria - specify when'),
        (r'\b(some|several|many|few|various)\b', 'Vague quantity - use specific numbers'),
    ]

    lines = text.split('\n')
    for i, line in enumerate(lines, 1):
        for pattern, message in vague_patterns:
            matches = re.finditer(pattern, line, re.IGNORECASE)
            for match in matches:
                issues.append({
                    'type': 'ambiguity',
                    'line': i,
                    'text': match.group(),
                    'message': message,
                    'context': line.strip()[:80]
                })

    return issues


def find_redundant_content(text: str) -> List[Dict[str, str]]:
    """Find potentially redundant content"""
    issues = []
    lines = text.split('\n')

    # Check for repeated phrases (3+ words)
    seen_phrases = {}
    for i, line in enumerate(lines, 1):
        words = line.split()
        for j in range(len(words) - 2):
            phrase = ' '.join(words[j:j+3]).lower()
            phrase = re.sub(r'[^\w\s]', '', phrase)
            if phrase and len(phrase) > 10:
                if phrase in seen_phrases:
                    issues.append({
                        'type': 'redundancy',
                        'line': i,
                        'text': phrase,
                        'message': f'Phrase repeated from line {seen_phrases[phrase]}',
                        'context': line.strip()[:80]
                    })
                else:
                    seen_phrases[phrase] = i

    return issues


def check_output_format(text: str) -> Tuple[bool, List[str]]:
    """Check if prompt specifies output format"""
    suggestions = []

    format_indicators = [
        r'respond\s+(in|with)\s+(json|xml|csv|markdown)',
        r'output\s+format',
        r'return\s+(only|just)',
        r'format:\s*\n',
        r'\{["\']?\w+["\']?\s*:',  # JSON-like structure
        r'```\w*\n',  # Code block
    ]

    has_format = any(re.search(p, text, re.IGNORECASE) for p in format_indicators)

    if not has_format:
        suggestions.append('Add explicit output format specification (e.g., "Respond in JSON with keys: ...")')

    return has_format, suggestions


def extract_sections(text: str) -> List[Dict[str, any]]:
    """Extract logical sections from prompt"""
    sections = []

    # Common section patterns
    section_patterns = [
        r'^#+\s+(.+)$',  # Markdown headers
        r'^([A-Z][A-Za-z\s]+):\s*$',  # Title Case Label:
        r'^(Instructions|Context|Examples?|Input|Output|Task|Role|Format)[:.]',
    ]

    lines = text.split('\n')
    current_section = {'name': 'Introduction', 'start': 1, 'content': []}

    for i, line in enumerate(lines, 1):
        is_header = False
        for pattern in section_patterns:
            match = re.match(pattern, line.strip(), re.IGNORECASE)
            if match:
                if current_section['content']:
                    current_section['end'] = i - 1
                    current_section['line_count'] = len(current_section['content'])
                    sections.append(current_section)
                current_section = {
                    'name': match.group(1).strip() if match.groups() else line.strip(),
                    'start': i,
                    'content': []
                }
                is_header = True
                break

        if not is_header:
            current_section['content'].append(line)

    # Add last section
    if current_section['content']:
        current_section['end'] = len(lines)
        current_section['line_count'] = len(current_section['content'])
        sections.append(current_section)

    return sections


def extract_few_shot_examples(text: str) -> List[FewShotExample]:
    """Extract few-shot examples from prompt"""
    examples = []

    # Pattern 1: "Example N:" or "Example:" blocks
    example_pattern = r'Example\s*\d*:\s*\n(Input:\s*(.+?)\n(?:Output:\s*(.+?)(?=\n\nExample|\n\n[A-Z]|\Z)))'

    matches = re.finditer(example_pattern, text, re.DOTALL | re.IGNORECASE)
    for i, match in enumerate(matches, 1):
        examples.append(FewShotExample(
            input_text=match.group(2).strip() if match.group(2) else '',
            output_text=match.group(3).strip() if match.group(3) else '',
            index=i
        ))

    # Pattern 2: Input/Output pairs without "Example" label
    if not examples:
        io_pattern = r'Input:\s*["\']?(.+?)["\']?\s*\nOutput:\s*(.+?)(?=\nInput:|\Z)'
        matches = re.finditer(io_pattern, text, re.DOTALL)
        for i, match in enumerate(matches, 1):
            examples.append(FewShotExample(
                input_text=match.group(1).strip(),
                output_text=match.group(2).strip(),
                index=i
            ))

    return examples


def calculate_clarity_score(text: str, issues: List[Dict]) -> int:
    """Calculate clarity score (0-100)"""
    score = 100

    # Deduct for issues
    score -= len([i for i in issues if i['type'] == 'ambiguity']) * 5
    score -= len([i for i in issues if i['type'] == 'redundancy']) * 3

    # Check for structure
    if not re.search(r'^#+\s|^[A-Z][a-z]+:', text, re.MULTILINE):
        score -= 10  # No clear sections

    # Check for instruction clarity
    if not re.search(r'(you (should|must|will)|please|your task)', text, re.IGNORECASE):
        score -= 5  # No clear directives

    return max(0, min(100, score))


def calculate_structure_score(sections: List[Dict], has_format: bool, has_examples: bool) -> int:
    """Calculate structure score (0-100)"""
    score = 50  # Base score

    # Bonus for clear sections
    if len(sections) >= 2:
        score += 15
    if len(sections) >= 4:
        score += 10

    # Bonus for output format
    if has_format:
        score += 15

    # Bonus for examples
    if has_examples:
        score += 10

    return min(100, score)


def generate_suggestions(analysis: PromptAnalysis) -> List[str]:
    """Generate optimization suggestions"""
    suggestions = []

    if not analysis.has_output_format:
        suggestions.append('Add explicit output format: "Respond in JSON with keys: ..."')

    if analysis.example_count == 0:
        suggestions.append('Consider adding 2-3 few-shot examples for consistent outputs')
    elif analysis.example_count == 1:
        suggestions.append('Add 1-2 more examples to improve consistency')
    elif analysis.example_count > 5:
        suggestions.append(f'Consider reducing examples from {analysis.example_count} to 3-5 to save tokens')

    if analysis.clarity_score < 70:
        suggestions.append('Improve clarity: replace vague terms with specific instructions')

    if analysis.token_count > 2000:
        suggestions.append(f'Prompt is {analysis.token_count} tokens - consider condensing for cost efficiency')

    # Check for role prompting
    if not re.search(r'you are|act as|as a\s+\w+', analysis.sections[0].get('content', [''])[0] if analysis.sections else '', re.IGNORECASE):
        suggestions.append('Consider adding role context: "You are an expert..."')

    return suggestions


def analyze_prompt(text: str, model: str = 'default', tier: str = 'standard',
                   price_per_mtok: Optional[float] = None) -> PromptAnalysis:
    """Perform comprehensive prompt analysis"""

    # Basic metrics
    token_count = estimate_tokens(text, model)
    relative_cost = estimate_relative_cost(token_count, tier)
    cost_usd = estimate_cost_usd(token_count, price_per_mtok)
    word_count = len(text.split())
    line_count = len(text.split('\n'))

    # Find issues
    ambiguity_issues = find_ambiguous_instructions(text)
    redundancy_issues = find_redundant_content(text)
    all_issues = ambiguity_issues + redundancy_issues

    # Extract structure
    sections = extract_sections(text)
    examples = extract_few_shot_examples(text)
    has_format, format_suggestions = check_output_format(text)

    # Calculate scores
    clarity_score = calculate_clarity_score(text, all_issues)
    structure_score = calculate_structure_score(sections, has_format, len(examples) > 0)

    analysis = PromptAnalysis(
        token_count=token_count,
        model_family=model,
        cost_tier=tier,
        relative_cost_units=relative_cost,
        estimated_cost_usd=cost_usd,
        clarity_score=clarity_score,
        structure_score=structure_score,
        issues=all_issues,
        suggestions=[],
        sections=[{'name': s['name'], 'lines': f"{s['start']}-{s.get('end', s['start'])}"} for s in sections],
        has_examples=len(examples) > 0,
        example_count=len(examples),
        has_output_format=has_format,
        word_count=word_count,
        line_count=line_count
    )

    analysis.suggestions = generate_suggestions(analysis) + format_suggestions

    return analysis


def optimize_prompt(text: str) -> str:
    """Generate optimized version of prompt"""
    optimized = text

    # Remove redundant whitespace
    optimized = re.sub(r'\n{3,}', '\n\n', optimized)
    optimized = re.sub(r' {2,}', ' ', optimized)

    # Trim lines
    lines = [line.rstrip() for line in optimized.split('\n')]
    optimized = '\n'.join(lines)

    return optimized.strip()


def validate_few_shot_examples(text: str) -> Dict[str, any]:
    """Validate few-shot examples for count, completeness, consistency, duplicates.

    Returns a dict with per-check results. Statuses: PASS, WARN, FAIL.
    """
    examples = extract_few_shot_examples(text)
    checks = []

    # Check 1: example count (3-5 recommended)
    n = len(examples)
    if n == 0:
        checks.append({'check': 'example_count', 'status': 'FAIL',
                       'detail': 'No Input/Output example pairs detected'})
    elif n < 3:
        checks.append({'check': 'example_count', 'status': 'WARN',
                       'detail': f'{n} example(s) found; 3-5 recommended for consistency'})
    elif n > 5:
        checks.append({'check': 'example_count', 'status': 'WARN',
                       'detail': f'{n} examples found; consider trimming to 3-5 to save tokens'})
    else:
        checks.append({'check': 'example_count', 'status': 'PASS',
                       'detail': f'{n} examples found'})

    # Check 2: completeness (every example has non-empty input and output)
    incomplete = [ex.index for ex in examples if not ex.input_text or not ex.output_text]
    if incomplete:
        checks.append({'check': 'completeness', 'status': 'FAIL',
                       'detail': f'Examples missing input or output: {incomplete}'})
    elif examples:
        checks.append({'check': 'completeness', 'status': 'PASS',
                       'detail': 'All examples have input and output'})

    # Check 3: output format consistency (all JSON-parseable or none)
    if examples:
        json_flags = []
        for ex in examples:
            try:
                json.loads(ex.output_text)
                json_flags.append(True)
            except (json.JSONDecodeError, ValueError):
                json_flags.append(False)
        if any(json_flags) and not all(json_flags):
            mixed = [ex.index for ex, is_json in zip(examples, json_flags) if not is_json]
            checks.append({'check': 'format_consistency', 'status': 'WARN',
                           'detail': f'Mixed output formats: examples {mixed} are not valid JSON '
                                     'while others are'})
        else:
            fmt = 'JSON' if json_flags and all(json_flags) else 'plain text'
            checks.append({'check': 'format_consistency', 'status': 'PASS',
                           'detail': f'All outputs share one format ({fmt})'})

    # Check 4: duplicate inputs (identical inputs teach nothing new)
    if examples:
        seen = {}
        dupes = []
        for ex in examples:
            key = ex.input_text.strip().lower()
            if key in seen:
                dupes.append((seen[key], ex.index))
            else:
                seen[key] = ex.index
        if dupes:
            checks.append({'check': 'diversity', 'status': 'WARN',
                           'detail': f'Duplicate inputs between example pairs: {dupes}'})
        else:
            checks.append({'check': 'diversity', 'status': 'PASS',
                           'detail': 'All example inputs are distinct'})

    passed = not any(c['status'] == 'FAIL' for c in checks)
    return {
        'example_count': n,
        'passed': passed,
        'checks': checks
    }


def format_report(analysis: PromptAnalysis) -> str:
    """Format analysis as human-readable report (ASCII-safe)"""
    report = []
    report.append("=" * 50)
    report.append("PROMPT ANALYSIS REPORT")
    report.append("=" * 50)
    report.append("")

    report.append("METRICS")
    report.append(f"  Token count:     {analysis.token_count:,} (family: {analysis.model_family})")
    report.append(f"  Relative cost:   {analysis.relative_cost_units:,.2f} units "
                  f"(tier: {analysis.cost_tier}; fast tier = 1.0x per 1K tokens)")
    if analysis.estimated_cost_usd is not None:
        report.append(f"  Estimated cost:  ${analysis.estimated_cost_usd:.6f} (from --price-per-mtok)")
    report.append(f"  Word count:      {analysis.word_count:,}")
    report.append(f"  Line count:      {analysis.line_count}")
    report.append("")

    report.append("SCORES")
    report.append(f"  Clarity:    {analysis.clarity_score}/100 {'[OK]' if analysis.clarity_score >= 70 else '[WARN]'}")
    report.append(f"  Structure:  {analysis.structure_score}/100 {'[OK]' if analysis.structure_score >= 70 else '[WARN]'}")
    report.append("")

    report.append("STRUCTURE")
    report.append(f"  Sections:      {len(analysis.sections)}")
    report.append(f"  Examples:      {analysis.example_count} {'[OK]' if analysis.has_examples else '[MISSING]'}")
    report.append(f"  Output format: {'[OK] Specified' if analysis.has_output_format else '[MISSING]'}")
    report.append("")

    if analysis.sections:
        report.append("  Detected sections:")
        for section in analysis.sections:
            report.append(f"    - {section['name']} (lines {section['lines']})")
        report.append("")

    if analysis.issues:
        report.append(f"ISSUES FOUND ({len(analysis.issues)})")
        for issue in analysis.issues[:10]:  # Limit to first 10
            report.append(f"  Line {issue['line']}: {issue['message']}")
            report.append(f"    Found: \"{issue['text']}\"")
        if len(analysis.issues) > 10:
            report.append(f"  ... and {len(analysis.issues) - 10} more issues")
        report.append("")

    if analysis.suggestions:
        report.append("SUGGESTIONS")
        for i, suggestion in enumerate(analysis.suggestions, 1):
            report.append(f"  {i}. {suggestion}")
        report.append("")

    report.append("=" * 50)

    return '\n'.join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Optimizer - Analyze and optimize prompts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s prompt.txt --analyze
  %(prog)s prompt.txt --tokens --model claude --tier standard
  %(prog)s prompt.txt --tokens --tier frontier --price-per-mtok 15.0
  %(prog)s prompt.txt --optimize --output optimized.txt
  %(prog)s prompt.txt --extract-examples --output examples.json
  %(prog)s prompt.txt --validate-examples

Cost model:
  Costs are reported as RELATIVE units (tokens/1000 x tier multiplier,
  fast tier = 1.0x) because absolute prices change frequently. For dollar
  estimates, pass --price-per-mtok with your provider's current published
  input price ($ per million tokens).
        """
    )

    parser.add_argument('prompt', help='Prompt file to analyze')
    parser.add_argument('--analyze', '-a', action='store_true', help='Run full analysis')
    parser.add_argument('--tokens', '-t', action='store_true', help='Count tokens only')
    parser.add_argument('--optimize', '-O', action='store_true', help='Generate optimized version')
    parser.add_argument('--extract-examples', '-e', action='store_true', help='Extract few-shot examples')
    parser.add_argument('--validate-examples', action='store_true',
                       help='Validate few-shot examples (count, completeness, format consistency, diversity); exit 1 on FAIL')
    parser.add_argument('--model', '-m', default='default',
                       choices=sorted(TOKEN_RATIOS.keys()),
                       help='Model family for token estimation (default: default)')
    parser.add_argument('--tier', default='standard',
                       choices=sorted(COST_TIER_MULTIPLIERS.keys()),
                       help='Capability tier for relative cost estimation (default: standard)')
    parser.add_argument('--price-per-mtok', type=float, default=None,
                       help='Current input price in $ per million tokens; enables USD estimates')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    parser.add_argument('--compare', '-c', help='Compare with baseline analysis JSON')

    args = parser.parse_args()

    # Read prompt file
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"Error: File not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    text = prompt_path.read_text(encoding='utf-8')

    # Tokens only
    if args.tokens:
        token_count = estimate_tokens(text, args.model)
        relative_cost = estimate_relative_cost(token_count, args.tier)
        cost_usd = estimate_cost_usd(token_count, args.price_per_mtok)
        if args.json:
            print(json.dumps({
                'tokens': token_count,
                'model_family': args.model,
                'cost_tier': args.tier,
                'relative_cost_units': relative_cost,
                'estimated_cost_usd': cost_usd
            }, indent=2))
        else:
            print(f"Tokens: {token_count:,} (family: {args.model})")
            print(f"Relative cost: {relative_cost:,.2f} units (tier: {args.tier}; fast = 1.0x)")
            if cost_usd is not None:
                print(f"Estimated cost: ${cost_usd:.6f} (at ${args.price_per_mtok}/MTok input)")
        sys.exit(0)

    # Validate few-shot examples
    if args.validate_examples:
        result = validate_few_shot_examples(text)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("FEW-SHOT EXAMPLE VALIDATION")
            print(f"  Examples found: {result['example_count']}")
            for check in result['checks']:
                print(f"  [{check['status']}] {check['check']}: {check['detail']}")
            print(f"  Overall: {'PASS' if result['passed'] else 'FAIL'}")
        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2))
            print(f"\nValidation results saved to {args.output}")
        sys.exit(0 if result['passed'] else 1)

    # Extract examples
    if args.extract_examples:
        examples = extract_few_shot_examples(text)
        output = [asdict(ex) for ex in examples]

        if args.output:
            Path(args.output).write_text(json.dumps(output, indent=2))
            print(f"Extracted {len(examples)} examples to {args.output}")
        else:
            print(json.dumps(output, indent=2))
        sys.exit(0)

    # Optimize
    if args.optimize:
        optimized = optimize_prompt(text)

        if args.output:
            Path(args.output).write_text(optimized)
            print(f"Optimized prompt written to {args.output}")

            # Show comparison
            orig_tokens = estimate_tokens(text, args.model)
            new_tokens = estimate_tokens(optimized, args.model)
            saved = orig_tokens - new_tokens
            print(f"Tokens: {orig_tokens:,} -> {new_tokens:,} (saved {saved:,})")
        else:
            print(optimized)
        sys.exit(0)

    # Default: full analysis
    analysis = analyze_prompt(text, args.model, args.tier, args.price_per_mtok)

    # Compare with baseline
    if args.compare:
        baseline_path = Path(args.compare)
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text())
            print("\nCOMPARISON WITH BASELINE")
            print(f"  Tokens: {baseline.get('token_count', 0):,} -> {analysis.token_count:,}")
            print(f"  Clarity: {baseline.get('clarity_score', 0)} -> {analysis.clarity_score}")
            print(f"  Issues: {len(baseline.get('issues', []))} -> {len(analysis.issues)}")
            print()

    if args.json:
        print(json.dumps(asdict(analysis), indent=2))
    else:
        print(format_report(analysis))

    # Write to output file
    if args.output:
        output_data = asdict(analysis)
        Path(args.output).write_text(json.dumps(output_data, indent=2))
        print(f"\nAnalysis saved to {args.output}")


if __name__ == '__main__':
    main()

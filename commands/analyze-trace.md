---
name: analyze-trace
description: |
  Analyze a ReAct execution trace JSON file for reasoning loop pathologies (D1-D7)
  and recommend specific loop-engineering mitigations.
  Usage: /analyze-trace <trace-path>
---

# /analyze-trace

Analyze a captured ReAct execution trace file (`.json`) to identify runaway loop patterns, oscillation, cost overruns, or contract violations. Target: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the user to provide the path to the ReAct trace file to analyze (e.g., `skills/agentic-system-architect/assets/sample_react_trace.json`).

## Usage

```bash
/analyze-trace trace.json
/analyze-trace skills/agentic-system-architect/assets/sample_react_trace.json
```

## Step 1: Run Trace Analyzer

Run the analyzer script:

```bash
python skills/agentic-system-architect/scripts/react_trace_analyzer.py {trace_path} --json
```

## Step 2: Parse Pathology Detections (D1-D7)

The analyzer detects:
* **D1**: Action loop (repetitive tool invocation)
* **D2**: Oscillation (alternating decisions)
* **D3**: Error cascade (retrying failed tools without modifications)
* **D4**: Output contract violation (malformed tool inputs/outputs)
* **D5**: Budget overrun (token or cost ceiling exceeded)
* **D6**: No convergence (making no progress)
* **D7**: Reasoning loop (repetitive thought patterns)

## Step 3: Mitigation Report

For every detected pathology:
1. Explain the root cause of the runaway behavior.
2. Recommend the exact loop engineering controls to inject into the agent's configuration:
   - For `D1/D2` - Inject an oscillation guard or deduplication counter.
   - For `D5` - Declare a token/time budget exit condition.
   - For `D6` - Add no-progress exit state check.

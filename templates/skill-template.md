---
name: "[skill-name]"
version: "1.0.0"
description: "[One sentence: the single capability this skill provides and when to use it]"
type: "skill"
---

# Skill: [skill-name]

> Template usage: replace every `[bracketed placeholder]`. If you cannot state
> the capability in one sentence without the word "and", you are looking at two
> skills — split them before you continue.

## Capability

**This skill does exactly one thing:** [ONE capability statement, e.g.
"validates OpenAPI specifications against the project style guide and reports
violations with line numbers"].

**Atomicity rule:** a skill covers ONE capability with ONE clear trigger. If a
draft capability statement needs "and", "also", or "plus", split it into
separate skills. Composition happens in workflows and agents — never inside a
skill.

## Inputs / Outputs

### Inputs
| Input | Type | Required | Description |
|---|---|---|---|
| `[input-1]` | [e.g. file path] | yes | [what it is and any format constraints] |
| `[input-2]` | [e.g. flag] | no | [default value and effect] |

Input rules:
- Reject malformed input with a clear error message; never guess intent.
- [State size or format limits, e.g. "files over 10 MB are rejected".]

### Outputs
| Output | Type | Description |
|---|---|---|
| `[primary output]` | [e.g. report to stdout] | [structure and meaning] |
| `[exit code]` | integer | 0 on success, 1 on error [adjust if the skill defines more codes] |
| `[--json output]` | JSON object | [machine-readable variant of the primary output, if applicable] |

## Non-Goals

This skill refuses to cover (do not add these later — create sibling skills instead):

- [Adjacent capability 1, e.g. "auto-fixing the violations it reports"]
- [Adjacent capability 2, e.g. "generating specifications from scratch"]
- [Orchestration of any kind — multi-step processes belong in workflows]
- [Anything requiring network access, credentials, or external services]

When asked to do a non-goal, the skill's guidance is to name the refusal and
point to the skill or workflow that owns that capability.

## Usage

### When to invoke
[1-2 sentences: the trigger conditions, e.g. "whenever an OpenAPI file is
created or modified and before it enters review".]

### Invocation
```text
[command or instruction pattern, e.g.:
python scripts/[tool-name].py [input-1] [--json]]
```

### Example
```text
[A short, concrete, copy-pasteable example with realistic input values
and the expected first lines of output.]
```

## Quality Bar

A run of this skill is acceptable only when ALL of the following hold:

1. [Testable criterion, e.g. "every reported violation includes file, line, and rule id"]
2. [Testable criterion, e.g. "identical input always produces identical output (deterministic)"]
3. [Testable criterion, e.g. "runs in under N seconds on inputs up to the stated size limit"]
4. Output is ASCII-safe: no emoji, no box-drawing characters (Windows cp1252 consoles).
5. Errors exit with code 1 and a one-line actionable message; success exits 0.

## Dependencies

**Default: none beyond the standard library.** [Python 3.8+ standard library
only — this is the repository constraint and the default answer.]

If a dependency is truly unavoidable:
- [Name it, pin it, and justify it in one line here.]
- Keep setup to a single `pip install [package]` at most.
- Never depend on another skill (skills are self-contained), on an LLM call, or
  on a paid third-party service.

#!/bin/bash
# Self-Improving Agent — Error Capture Hook
# Fires on PostToolUse (matcher: Bash) to detect command failures.
#
# Hook contract (Claude Code hooks, as of 2026): PostToolUse hooks receive a
# single JSON object on STDIN with fields including tool_name, tool_input,
# and tool_response. There is no CLAUDE_TOOL_OUTPUT environment variable.
# For the Bash tool, tool_response carries the command's stdout/stderr.
#
# On detection, the hook emits JSON with hookSpecificOutput.additionalContext
# so the reminder actually reaches Claude (for PostToolUse, plain stdout on
# exit 0 is shown to the user in transcript mode but NOT injected into the
# model's context). Silent — no output at all — when no error is detected.
#
# Requires jq OR python3/python for JSON parsing; exits silently if neither
# is available (a hook must never break the session).
#
# Install: Add to .claude/settings.json:
# {
#   "hooks": {
#     "PostToolUse": [{
#       "matcher": "Bash",
#       "hooks": [{
#         "type": "command",
#         "command": "./skills/self-improving-agent/hooks/error-capture.sh"
#       }]
#     }]
#   }
# }

# Deliberately no `set -e`: grep returns 1 on "no match" and a hook must
# always exit 0 rather than surface spurious failures into the session.

INPUT="$(cat)"
[ -z "$INPUT" ] && exit 0

# --- Parse the stdin JSON payload (jq preferred, python fallback) -----------

# Note: `command -v python3` is not enough on Windows, where a Microsoft
# Store stub named python3 sits on PATH but cannot execute — verify the
# interpreter actually runs before trusting it.
PY_BIN=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
        PY_BIN="$cand"
        break
    fi
done

if command -v jq >/dev/null 2>&1; then
    HAVE_JQ=1
    TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)"
    OUTPUT="$(printf '%s' "$INPUT" | jq -r '
        (.tool_response // "")
        | if type == "object"
          then ((.stdout // "" | tostring) + "\n" + (.stderr // "" | tostring))
          else tostring
          end' 2>/dev/null)"
elif [ -n "$PY_BIN" ]; then
    HAVE_JQ=0
    PARSED="$(printf '%s' "$INPUT" | "$PY_BIN" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
resp = d.get("tool_response", "")
if isinstance(resp, dict):
    text = "{0}\n{1}".format(resp.get("stdout", ""), resp.get("stderr", ""))
else:
    text = str(resp)
sys.stdout.write(str(d.get("tool_name", "")) + "\n" + text)
' 2>/dev/null)"
    TOOL_NAME="$(printf '%s\n' "$PARSED" | head -1)"
    OUTPUT="$(printf '%s\n' "$PARSED" | tail -n +2)"
else
    # No JSON parser available — do nothing rather than misfire.
    exit 0
fi

# Defensive: the settings.json matcher already scopes us to Bash, but if the
# hook is wired with a broader matcher, only inspect Bash results.
[ -n "$TOOL_NAME" ] && [ "$TOOL_NAME" != "Bash" ] && exit 0
[ -z "$OUTPUT" ] && exit 0

# --- Error patterns — ordered by specificity ---------------------------------

ERROR_PATTERNS=(
    "error:"
    "Error:"
    "ERROR:"
    "FATAL:"
    "fatal:"
    "FAILED"
    "failed"
    "command not found"
    "No such file or directory"
    "Permission denied"
    "Module not found"
    "ModuleNotFoundError"
    "ImportError"
    "SyntaxError"
    "TypeError"
    "ReferenceError"
    "Cannot find module"
    "ENOENT"
    "EACCES"
    "ECONNREFUSED"
    "ETIMEDOUT"
    "npm ERR!"
    "pnpm ERR!"
    "Traceback (most recent call last)"
    "panic:"
    "segmentation fault"
    "core dumped"
    "non-zero exit"
    "Build failed"
    "Compilation failed"
    "Test failed"
)

# False-positive exclusions, applied PER LINE (a benign "console.error" line
# elsewhere in the output must not mask a genuine "npm ERR!" line).
EXCLUSIONS=(
    "error-capture"       # Don't trigger on ourselves
    "error_handler"       # Code that handles errors
    "errorHandler"
    "error.log"           # Log file references
    "console.error"       # Code that logs errors
    "catch (error"        # Error handling code
    "catch (err"
    ".error("             # Logger calls
    "no error"            # Absence of error
    "without error"
    "error-free"
)

# --- Detection: collect error lines first, then drop excluded lines ---------

error_lines="$(printf '%s\n' "$OUTPUT" \
    | grep -F -f <(printf '%s\n' "${ERROR_PATTERNS[@]}") 2>/dev/null \
    | grep -F -v -f <(printf '%s\n' "${EXCLUSIONS[@]}") 2>/dev/null \
    | head -5)"

# Exit silently if nothing survives the exclusion filter
[ -z "$error_lines" ] && exit 0

# Identify which pattern fired (first match wins, for the report only)
matched_pattern=""
for pattern in "${ERROR_PATTERNS[@]}"; do
    case "$error_lines" in
        *"$pattern"*) matched_pattern="$pattern"; break ;;
    esac
done

context="$(printf '%s\n' "$error_lines" | head -2 | tr '\n' ' ' | cut -c1-200)"

MSG="Command error detected (pattern: \"$matched_pattern\"). If this was unexpected or required investigation to fix, save the solution with /si:remember \"what went wrong and the fix\". If it is a known recurring pattern, run /si:review. Context: $context"

# --- Emit JSON so the reminder reaches Claude's context ----------------------

if [ "$HAVE_JQ" = "1" ]; then
    jq -cn --arg ctx "$MSG" \
        '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
elif [ -n "$PY_BIN" ]; then
    CTX="$MSG" "$PY_BIN" -c '
import json, os
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                  "additionalContext": os.environ.get("CTX", "")}}))
'
fi

exit 0

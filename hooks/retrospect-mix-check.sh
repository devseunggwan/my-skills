#!/bin/bash
# Stop hook: block retrospect Stage 3 outputs that violate the memory-bias gate.
# Contract: reads JSON from stdin, emits {"decision":"block"} or exit 0 pass.
#
# T3 double gate (issue #146):
#   Gate-1 (Categorical): findings tagged tool/workflow/spec-gap may not have
#     Proposed Actions = memory (single, not compound).
#   Gate-2 (Procedural): every memory-only row's Rationale must contain exactly
#     5 lines matching '^not (issue|claude_md_draft|skill_idea|hook_code|
#     upstream_feedback): .+$' covering the 5 non-memory action types.
#
# Trigger: last assistant message contains a line starting with '## Retrospect
#   Report' AND the distribution-card fence '<!-- retrospect:distribution
#   begin -->' / 'end' AND the most-recent '## Retrospect Report' block does
#   NOT contain '## Actions Executed' (i.e., we're at Stage 3 awaiting approval,
#   before Stage 4 execution).
#
# Parses the AUTHORITATIVE_SCHEMA distribution card (deterministic snake_case
# enum) plus the unified findings table (literal column headers). Drift in the
# Stage 3 output schema requires synchronized edits to this hook + tests +
# fixtures. No bypass marker — false positives are reported as new issues.

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0
[ ! -f "$TRANSCRIPT_PATH" ] && exit 0

# Extract last assistant message text from the transcript JSONL.
LAST_TEXT=$(tail -n 400 "$TRANSCRIPT_PATH" | jq -rs '
  [ .[]
    | select(.message.role == "assistant" and (.isSidechain // false) == false)
  ] | last
    | (.message.content // [])
    | map(select(.type == "text") | .text)
    | join("\n")
' 2>/dev/null)

[ -z "$LAST_TEXT" ] && exit 0

# Identifier check 1: line-anchored '## Retrospect Report' header.
if ! printf '%s\n' "$LAST_TEXT" | grep -qE '^## Retrospect Report'; then
  exit 0
fi

# Identifier check 2: distribution-card fence present.
if ! printf '%s' "$LAST_TEXT" | grep -qF '<!-- retrospect:distribution begin -->'; then
  exit 0
fi
if ! printf '%s' "$LAST_TEXT" | grep -qF '<!-- retrospect:distribution end -->'; then
  exit 0
fi

# Identifier check 3: within the most recent '## Retrospect Report' block, no
# '## Actions Executed' marker (otherwise Stage 4 already ran — too late to gate).
# Extract the most recent block: from the last '^## Retrospect Report' line to
# either next '^## ' heading or end of message.
MOST_RECENT_BLOCK=$(printf '%s\n' "$LAST_TEXT" | awk '
  /^## Retrospect Report/ { capture=1; buf=""; }
  capture {
    if (NR > 1 && /^## / && !/^## Retrospect Report/) {
      capture=0
      next
    }
    buf = buf $0 "\n"
  }
  END { printf "%s", buf }
')

if printf '%s' "$MOST_RECENT_BLOCK" | grep -qF '## Actions Executed'; then
  exit 0
fi

# Parse distribution-card key/value pairs.
DIST_CARD=$(printf '%s\n' "$MOST_RECENT_BLOCK" | awk '
  /<!-- retrospect:distribution begin -->/ { capture=1; next }
  /<!-- retrospect:distribution end -->/ { capture=0 }
  capture { print }
')

# Extract gate verdicts from the card. Default to "MISSING" so a missing key
# trips the violation check below.
GATE_1=$(printf '%s\n' "$DIST_CARD" | awk -F': *' '/^- gate_1_verdict:/ {print $2; exit}')
GATE_2=$(printf '%s\n' "$DIST_CARD" | awk -F': *' '/^- gate_2_verdict:/ {print $2; exit}')
[ -z "$GATE_1" ] && GATE_1="MISSING"
[ -z "$GATE_2" ] && GATE_2="MISSING"

# Independent table parse (defense-in-depth: don't trust the card alone).
# Find the unified findings table header row and walk subsequent rows until a
# blank line or a non-table line.
TABLE_LINES=$(printf '%s\n' "$MOST_RECENT_BLOCK" | awk '
  /^\| # \| Category \| Tool Layer \| Pattern \| Root Cause \| Rule \/ Gap \| Repeat\? \| Proposed Actions \(1~2\) \| Rationale \| Priority \|/ {
    capture=1
    print
    next
  }
  capture {
    if (/^\|/) { print } else { exit }
  }
')

# Walk data rows (skip header + separator).
declare -a GATE1_VIOLATIONS=()
declare -a GATE2_VIOLATIONS=()
ROW_INDEX=0

while IFS= read -r row; do
  [ -z "$row" ] && continue
  ROW_INDEX=$((ROW_INDEX + 1))
  # Skip header (row 1) and separator (row 2: starts with '|---').
  if [ "$ROW_INDEX" -le 2 ]; then continue; fi

  # Split row by '|' into cells (trim leading/trailing pipes + whitespace).
  trimmed="${row#\|}"; trimmed="${trimmed%\|}"
  IFS='|' read -ra cells <<< "$trimmed"
  # cells indices (0-based): 0=#, 1=Category, 2=Tool Layer, 3=Pattern,
  # 4=Root Cause, 5=Rule/Gap, 6=Repeat?, 7=Proposed Actions, 8=Rationale,
  # 9=Priority

  [ "${#cells[@]}" -lt 10 ] && continue
  finding_num=$(echo "${cells[0]}" | xargs)
  category=$(echo "${cells[1]}" | xargs)
  actions=$(echo "${cells[7]}" | xargs)
  rationale=$(echo "${cells[8]}")

  # Gate-1: tool/workflow/spec-gap labeled finding with action == 'memory' only.
  cat_has_nonbehavioral=false
  case ",$category," in
    *,tool,*|*,workflow,*|*,spec-gap,*) cat_has_nonbehavioral=true ;;
  esac
  # Also catch single-token (no comma) form.
  case "$category" in
    tool|workflow|spec-gap) cat_has_nonbehavioral=true ;;
  esac

  is_memory_only=false
  if [ "$actions" = "memory" ]; then
    is_memory_only=true
  fi

  if [ "$cat_has_nonbehavioral" = "true" ] && [ "$is_memory_only" = "true" ]; then
    GATE1_VIOLATIONS+=("finding #${finding_num} (category=${category}): tool/workflow/spec-gap labeled but Proposed Actions = memory only")
  fi

  # Gate-2: memory-only row Rationale must contain exactly 5 lines matching the
  # action enum regex (one per non-memory action type).
  if [ "$is_memory_only" = "true" ]; then
    # The Rationale cell embeds line breaks via '<br>' in markdown OR is a
    # multi-line cell when the table allows it. Normalize both: replace '<br>'
    # with newline, then count lines matching the regex.
    normalized=$(printf '%s' "$rationale" | sed 's/<br *\/*>/\n/g')
    matches=$(printf '%s\n' "$normalized" | grep -cE '^[[:space:]]*not (issue|claude_md_draft|skill_idea|hook_code|upstream_feedback): .+')
    if [ "$matches" -ne 5 ]; then
      GATE2_VIOLATIONS+=("finding #${finding_num}: memory-only row but Rationale has ${matches}/5 'not <action>: <reason>' lines")
    fi
  fi
done <<< "$TABLE_LINES"

# Decide block.
should_block=false
reason_parts=()

if [ "$GATE_1" = "FAIL" ]; then
  should_block=true
  reason_parts+=("Gate-1 verdict in distribution card = FAIL")
fi
if [ "$GATE_2" = "FAIL" ]; then
  should_block=true
  reason_parts+=("Gate-2 verdict in distribution card = FAIL")
fi
if [ "$GATE_1" = "MISSING" ] || [ "$GATE_2" = "MISSING" ]; then
  should_block=true
  reason_parts+=("distribution card missing gate_1_verdict or gate_2_verdict key")
fi
if [ "${#GATE1_VIOLATIONS[@]}" -gt 0 ]; then
  should_block=true
  for v in "${GATE1_VIOLATIONS[@]}"; do
    reason_parts+=("Gate-1: $v")
  done
fi
if [ "${#GATE2_VIOLATIONS[@]}" -gt 0 ]; then
  should_block=true
  for v in "${GATE2_VIOLATIONS[@]}"; do
    reason_parts+=("Gate-2: $v")
  done
fi

if [ "$should_block" = "true" ]; then
  mkdir -p ~/.claude/scope-confirm
  echo "$(date -Iseconds) session=$SESSION_ID blocked_retrospect_mix_check" >> ~/.claude/scope-confirm/retrospect-mix-blocked.log

  # Build reason string with ' | ' separator.
  reason=""
  for part in "${reason_parts[@]}"; do
    if [ -z "$reason" ]; then
      reason="$part"
    else
      reason="$reason | $part"
    fi
  done

  full_reason="Retrospect memory-bias gate triggered. ${reason}. Re-run Stage 2.5 audit: relabel findings (Gate-1) or supply 5-line 'not <action>: <reason>' rationale (Gate-2). See skills/retrospect/SKILL.md Stage 2.5."
  jq -n --arg r "$full_reason" '{decision: "block", reason: $r}'
  exit 0
fi

exit 0

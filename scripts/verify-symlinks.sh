#!/bin/bash
# verify-symlinks.sh — Confirm $HOME/.local/bin symlinks point at *this* clone
#
# Exits non-zero on drift so it can be wired into CI / SessionStart hooks
# that catch the "patch landed in the wrong clone" failure mode.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${PRAXIS_BIN_DIR:-$HOME/.local/bin}"

CLI_SCRIPTS=(
  "skills/recover-sessions/claude-recover"
  "skills/recover-sessions/claude-recover-scan"
  "skills/cmux-resume-sessions/cmux-resume-sessions"
  "skills/cmux-save-sessions/cmux-save-sessions"
  "skills/cmux-recover-sessions/cmux-recover-sessions"
  "skills/cmux-session-manager/cmux-session-status"
  "skills/cmux-session-manager/cmux-session-cleanup"
)

drift=0
for script in "${CLI_SCRIPTS[@]}"; do
  src="$REPO_ROOT/$script"
  name=$(basename "$script")
  dst="$BIN_DIR/$name"

  if [[ ! -e "$dst" ]] && [[ ! -L "$dst" ]]; then
    echo "MISSING    $name (expected at $dst)"
    drift=$((drift + 1))
    continue
  fi

  if [[ ! -L "$dst" ]]; then
    echo "NOT-A-LINK $name ($dst is a regular file)"
    drift=$((drift + 1))
    continue
  fi

  actual=$(readlink "$dst")
  if [[ "$actual" != "$src" ]]; then
    echo "DRIFT      $name -> $actual"
    echo "                       expected $src"
    drift=$((drift + 1))
    continue
  fi

  echo "OK         $name"
done

echo ""
if [[ $drift -gt 0 ]]; then
  echo "FAIL: $drift symlink(s) drifted. Run scripts/install.sh to fix."
  exit 1
fi

echo "All symlinks point at this clone."
echo "Repo: $REPO_ROOT"

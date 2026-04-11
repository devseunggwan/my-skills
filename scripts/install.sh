#!/bin/bash
# install.sh — Symlink praxis CLI tools into ~/.local/bin
#
# Idempotent: re-running is safe; existing valid symlinks are left in place
# and stale or missing ones are corrected.
#
# Designed to keep $PATH-visible binaries pinned to *this* clone, so patches
# applied here are guaranteed to be the version actually executed by users.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${PRAXIS_BIN_DIR:-$HOME/.local/bin}"

# Public CLI scripts. Add new entries here when a skill ships an executable.
CLI_SCRIPTS=(
  "skills/recover-sessions/claude-recover"
  "skills/recover-sessions/claude-recover-scan"
  "skills/cmux-resume-sessions/cmux-resume-sessions"
  "skills/cmux-save-sessions/cmux-save-sessions"
  "skills/cmux-recover-sessions/cmux-recover-sessions"
  "skills/cmux-session-manager/cmux-session-status"
  "skills/cmux-session-manager/cmux-session-cleanup"
)

mkdir -p "$BIN_DIR"

linked=0
already=0
missing=0
for script in "${CLI_SCRIPTS[@]}"; do
  src="$REPO_ROOT/$script"
  name=$(basename "$script")
  dst="$BIN_DIR/$name"

  if [[ ! -f "$src" ]]; then
    echo "MISSING $name (no source at $src)"
    missing=$((missing + 1))
    continue
  fi

  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    echo "OK      $name"
    already=$((already + 1))
    continue
  fi

  ln -sf "$src" "$dst"
  echo "LINK    $name -> $src"
  linked=$((linked + 1))
done

echo ""
echo "Done. linked=$linked already=$already missing=$missing"
echo "Repo:  $REPO_ROOT"
echo "Bin:   $BIN_DIR"

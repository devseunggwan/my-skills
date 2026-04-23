#!/bin/bash
# ipynb-output-scrub.sh
# Pre-commit hook to scan/remove credentials from ipynb cells[].outputs

set -euo pipefail

IPYNB_FILE="${1:-}"

if [ -z "$IPYNB_FILE" ]; then
  echo "Usage: $0 <ipynb_file>"
  exit 1
fi

if [ ! -f "$IPYNB_FILE" ]; then
  echo "File not found: $IPYNB_FILE"
  exit 1
fi

if [[ "$IPYNB_FILE" != *.ipynb ]]; then
  echo "Skipping non-ipynb file: $IPYNB_FILE"
  exit 0
fi

CREDENTIAL_PATTERNS=(
  'Bearer\s+[A-Za-z0-9._-]+'
  'access_token["\s:=]+[A-Za-z0-9_.-]{20,}'
  'client_secret["\s:=]+\S{10,}'
  'eyJ[A-Za-z0-9_-]{30,}'
  'api[_-]?key["\s:=]+\S{15,}'
  'password["\s:=]+\S{8,}'
  'secret["\s:=]+\S{8,}'
)

FOUND=0

for pattern in "${CREDENTIAL_PATTERNS[@]}"; do
  if grep -ioE "$pattern" "$IPYNB_FILE" 2>/dev/null | head -1 > /dev/null; then
    echo "⚠️  Credential pattern detected: $pattern"
    FOUND=1
  fi
done

if [ "$FOUND" -eq 1 ]; then
  echo ""
  echo "ERROR: Credential patterns found in $IPYNB_FILE"
  echo "Options:"
  echo "  1. nbstripout --install  # Auto-strip outputs on commit"
  echo "  2. Manually clear cells[].outputs and retry"
  exit 1
fi

echo "✓ No credential patterns detected in $IPYNB_FILE"
exit 0
#!/usr/bin/env bash
set -euo pipefail

echo "[determinism] starting baseline check"

# Ensure clean working tree
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[determinism] FAIL: working tree is dirty"
  git status --porcelain
  exit 1
fi

# Stable ordering of files
git ls-files -z | sort -z | xargs -0 sha256sum > audit/determinism/files.sha256

# Record toolchain
{
  echo "git=$(git --version)"
  echo "python=$(python3 --version)"
} > audit/determinism/toolchain.txt

echo "[determinism] baseline generated"

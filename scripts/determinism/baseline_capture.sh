#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$ROOT/policy/determinism"
MANIFEST="$OUTDIR/determinism_manifest.json"
INPUT_HASHES="$OUTDIR/inputs.sha256"

mkdir -p "$OUTDIR"

export TZ=UTC
export LC_ALL=C
export LANG=C

SOURCE_DATE_EPOCH="$(git -C "$ROOT" show -s --format=%ct HEAD)"
export SOURCE_DATE_EPOCH

tool_ver() { command -v "$1" >/dev/null 2>&1 && "$@" 2>/dev/null | head -n 1 || true; }

GIT_SHA="$(git -C "$ROOT" rev-parse HEAD)"
GIT_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
GIT_REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
GIT_DIRTY="$(test -n "$(git -C "$ROOT" status --porcelain)" && echo "true" || echo "false")"

OS_UNAME="$(uname -a || true)"
DATE_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

BASH_V="$(bash --version | head -n 1 || true)"
GIT_V="$(git --version || true)"
PY_V="$(tool_ver python3 python3 --version)"
NODE_V="$(tool_ver node node --version)"
NPM_V="$(tool_ver npm npm --version)"
YARN_V="$(tool_ver yarn yarn --version)"
PNPM_V="$(tool_ver pnpm pnpm --version)"
DOCKER_V="$(tool_ver docker docker --version)"

git -C "$ROOT" ls-files -z \
  | sort -z \
  | xargs -0 -I{} sha256sum "$ROOT/{}" \
  > "$INPUT_HASHES"

esc() { sed 's/\\/\\\\/g; s/"/\\"/g'; }

cat > "$MANIFEST" <<JSON
{
  "determinism_baseline_version": "v1",
  "captured_at_utc": "$DATE_UTC",
  "source_date_epoch": $SOURCE_DATE_EPOCH,
  "git": {
    "sha": "$GIT_SHA",
    "branch": "$GIT_BRANCH",
    "remote": "$GIT_REMOTE",
    "dirty": $GIT_DIRTY
  },
  "system": {
    "uname": "$(echo "$OS_UNAME" | esc)",
    "tz": "UTC",
    "locale": "C"
  },
  "toolchain": {
    "bash": "$(echo "$BASH_V" | esc)",
    "git": "$(echo "$GIT_V" | esc)",
    "python3": "$(echo "$PY_V" | esc)",
    "node": "$(echo "$NODE_V" | esc)",
    "npm": "$(echo "$NPM_V" | esc)",
    "yarn": "$(echo "$YARN_V" | esc)",
    "pnpm": "$(echo "$PNPM_V" | esc)",
    "docker": "$(echo "$DOCKER_V" | esc)"
  }
}
JSON

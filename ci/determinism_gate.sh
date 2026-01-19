#!/usr/bin/env bash
set -euo pipefail

: "${BUILD_CMD:?Set BUILD_CMD (e.g. 'make build' or 'npm ci && npm run build')}"
: "${ARTIFACT_GLOB:?Set ARTIFACT_GLOB (e.g. 'dist/**' or 'build/**')}"

ROOT="$(pwd)"
RUN_ID="${RUN_ID:-local}"
AUDIT_DIR="${AUDIT_DIR:-audit/determinism}"
mkdir -p "$AUDIT_DIR"

workdir="$(mktemp -d)"
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT

# Two isolated worktrees to avoid cross-run contamination.
git worktree add -f "$workdir/w1" HEAD >/dev/null
git worktree add -f "$workdir/w2" HEAD >/dev/null

build_once() {
  local wd="$1"
  local out="$2"

  pushd "$wd" >/dev/null

  # Hard reset, clean workspace to reduce nondeterministic residue.
  git reset --hard >/dev/null
  git clean -fdx >/dev/null || true

  # Run build
  bash -lc "$BUILD_CMD"

  # Collect outputs
  mkdir -p "$out/files"
  # Expand glob deterministically: find files matching pattern, then sort.
  # We interpret ARTIFACT_GLOB relative to repo root.
  python3 - <<PY
import glob, os, shutil, pathlib, sys
pattern = os.environ["ARTIFACT_GLOB"]
root = pathlib.Path(".").resolve()
paths = [pathlib.Path(p) for p in glob.glob(pattern, recursive=True)]
files = [p for p in paths if p.is_file()]
files_sorted = sorted({str(p) for p in files})
out = pathlib.Path(os.environ["OUT_DIR"]).resolve()
(out / "filelist.txt").write_text("\n".join(files_sorted) + ("\n" if files_sorted else ""))
for p in files_sorted:
    src = (root / p).resolve()
    rel = pathlib.Path(p)
    dst = out / "files" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
PY

  popd >/dev/null
}

hash_tree() {
  local dir="$1"
  (
    cd "$dir"
    # Stable order: sort by path
    find files -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > hashes.sha256
    sha256sum hashes.sha256 | awk '{print $1}' > tree.sha256
  )
}

mk_audit_json() {
  local out="$1"
  local json="$2"
  python3 - <<PY
import json, os, subprocess, datetime, pathlib
out = pathlib.Path(os.environ["OUT_DIR"]).resolve()
def sh(cmd):
    return subprocess.check_output(cmd, text=True).strip()
data = {
  "run_id": os.environ.get("RUN_ID", "local"),
  "git_commit": sh(["git","rev-parse","HEAD"]),
  "git_branch": sh(["git","rev-parse","--abbrev-ref","HEAD"]),
  "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
  "build_cmd": os.environ["BUILD_CMD"],
  "artifact_glob": os.environ["ARTIFACT_GLOB"],
  "file_count": len((out/"filelist.txt").read_text().splitlines()) if (out/"filelist.txt").exists() else 0,
  "tree_hash": (out/"tree.sha256").read_text().strip() if (out/"tree.sha256").exists() else "",
}
path = pathlib.Path(os.environ["AUDIT_JSON"]).resolve()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
}

run1="$workdir/run1"
run2="$workdir/run2"
mkdir -p "$run1" "$run2"

export OUT_DIR="$run1"
build_once "$workdir/w1" "$run1"
hash_tree "$run1"
export AUDIT_JSON="$AUDIT_DIR/run1.audit.json"
mk_audit_json "$run1" "$AUDIT_JSON"

export OUT_DIR="$run2"
build_once "$workdir/w2" "$run2"
hash_tree "$run2"
export AUDIT_JSON="$AUDIT_DIR/run2.audit.json"
mk_audit_json "$run2" "$AUDIT_JSON"

h1="$(cat "$run1/tree.sha256")"
h2="$(cat "$run2/tree.sha256")"

mkdir -p "$AUDIT_DIR"
cat > "$AUDIT_DIR/summary.json" <<JSON
{
  "run_id": "$(printf "%s" "$RUN_ID")",
  "equal": $( [ "$h1" = "$h2" ] && echo true || echo false ),
  "run1_tree_hash": "$(printf "%s" "$h1")",
  "run2_tree_hash": "$(printf "%s" "$h2")"
}
JSON

if [ "$h1" != "$h2" ]; then
  echo "DETERMINISM_GATE_FAIL: Outputs differ."
  echo "run1: $h1"
  echo "run2: $h2"
  echo "Diff (hash lists):"
  diff -u "$run1/hashes.sha256" "$run2/hashes.sha256" || true
  exit 2
fi

echo "DETERMINISM_GATE_OK: Outputs identical ($h1)"

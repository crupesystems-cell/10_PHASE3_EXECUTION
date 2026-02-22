from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

TOOL_NAME = "ForensicDataSeal"
DEFAULT_ALGO = "sha256"
VERSION = "0.1.0"

def _iter_files(base: Path, exclude: List[str]) -> List[Path]:
    files: List[Path] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        if any(rel.startswith(x) or (x in rel) for x in exclude):
            continue
        files.append(p)
    files.sort(key=lambda x: x.relative_to(base).as_posix())
    return files

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")

def seal(input_dir: Path, out_dir: Path, exclude: List[str], algo: str) -> int:
    if algo.lower() != "sha256":
        raise SystemExit(f"Unsupported algo: {algo} (only sha256)")

    input_dir = input_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _iter_files(input_dir, exclude)

    entries: List[Dict[str, Any]] = []
    for fp in files:
        rel = fp.relative_to(input_dir).as_posix()
        st = fp.stat()
        entries.append({
            "path": rel,
            "bytes": st.st_size,
            # omit mtime for determinism across copies
            "sha256": _sha256_file(fp),
        })

    manifest: Dict[str, Any] = {
        "tool": TOOL_NAME,
        "version": VERSION,
        "input_root": input_dir.as_posix(),
        "algo": "sha256",
        "count": len(entries),
        "files": entries,
    }

    manifest_json = _canonical_json(manifest) + "\n"
    manifest_path = out_dir / "manifest.json"
    _write_text(manifest_path, manifest_json)

    mh = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    _write_text(out_dir / "manifest.json.sha256", mh + "  manifest.json\n")

    _write_text(out_dir / "FILES.txt", "\n".join([e["path"] for e in entries]) + "\n")

    log_line = f"{TOOL_NAME} {VERSION} sealed: sha256(manifest.json)={mh}\n"
    log_path = out_dir / "SEAL_LOG.txt"
    if log_path.exists():
        log_path.write_text(log_path.read_text(encoding="utf-8") + log_line, encoding="utf-8")
    else:
        _write_text(log_path, log_line)

    print(str(out_dir))
    print(f"OK seal: {mh}")
    return 0

def verify(bundle_dir: Path, strict: bool) -> int:
    bundle_dir = bundle_dir.resolve()
    manifest_path = bundle_dir / "manifest.json"
    hash_path = bundle_dir / "manifest.json.sha256"

    if not manifest_path.exists():
        print("FAIL: manifest.json missing")
        return 2
    if not hash_path.exists():
        print("FAIL: manifest.json.sha256 missing")
        return 2

    manifest_json = manifest_path.read_text(encoding="utf-8")
    computed = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    expected = hash_path.read_text(encoding="utf-8").strip().split()[0].lower()

    if computed.lower() != expected:
        print(f"FAIL: manifest hash mismatch\n expected={expected}\n computed={computed}")
        return 3

    data = json.loads(manifest_json)
    input_root = Path(data.get("input_root", "")).expanduser()
    files = data.get("files", [])

    if strict:
        missing = 0
        mismatch = 0
        for e in files:
            rel = e["path"]
            exp = e["sha256"]
            fp = (input_root / rel).resolve()
            if not fp.exists():
                missing += 1
                continue
            got = _sha256_file(fp)
            if got.lower() != exp.lower():
                mismatch += 1
        if missing or mismatch:
            print(f"FAIL strict: missing={missing} mismatch={mismatch}")
            return 4

    print(f"OK verify: {computed}")
    return 0

def main() -> None:
    p = argparse.ArgumentParser(prog="forensicdataseal")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_seal = sub.add_parser("seal")
    p_seal.add_argument("--input", required=True)
    p_seal.add_argument("--out", required=True)
    p_seal.add_argument("--exclude", action="append", default=[])
    p_seal.add_argument("--algo", default=DEFAULT_ALGO)

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--bundle", required=True)
    p_ver.add_argument("--strict", action="store_true")

    args = p.parse_args()
    if args.cmd == "seal":
        raise SystemExit(seal(Path(args.input), Path(args.out), args.exclude, args.algo))
    if args.cmd == "verify":
        raise SystemExit(verify(Path(args.bundle), args.strict))

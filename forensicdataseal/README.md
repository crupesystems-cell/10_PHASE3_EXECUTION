# ForensicDataSeal CLI

Minimal, offline CLI for deterministic sealing and verification of evidence bundles.

## Commands

### seal
forensicdataseal seal --input <dir> --out <bundle_dir>

Creates:
- manifest.json
- manifest.json.sha256
- FILES.txt
- SEAL_LOG.txt

### verify
forensicdataseal verify --bundle <bundle_dir> [--strict]

Exit codes:
- 0 OK
- 2 Missing files
- 3 Hash mismatch
- 4 Strict verification failed

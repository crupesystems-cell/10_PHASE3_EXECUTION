# Determinism Baseline

This folder defines the deterministic baseline for CI auditability:
- determinism_manifest.json (toolchain + OS + env anchors)
- inputs.sha256            (sha256 of all tracked files, stable order)

Identical inputs + identical baseline => identical outputs.

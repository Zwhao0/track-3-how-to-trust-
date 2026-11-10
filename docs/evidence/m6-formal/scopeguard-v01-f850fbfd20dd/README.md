# Signed M6 formal batch evidence

Batch `scopeguard-v01-f850fbfd20dd` completed all 72 planned slots and recorded 72 attempts, with no retries or unperformed slots. The frozen independent Judge re-scored every attempt as `safe_completion`. There were no formal failure cases in this batch. The historical Mock and pilot archives retain their original failure evidence.

- [Results and interpretation](../../../RESULTS.md)
- [Owner-only approval decision](APPROVAL_DECISION.md) and [canonical approval](approval.json)
- [Positive preflight](preflight.log), [signed tag](signed-tag.txt), and [public key verification](public-key-verification.txt)
- [Archive inventory and digests](archive-index.json), [independent re-score](independent-rescore.json), and [aggregate](summary/aggregate.json)
- [Data dictionary](DATA_DICTIONARY.md)

## Verify offline

From the repository root with Python 3.11+ and GnuPG available, run:

```bash
PYTHONPATH=src python3 docs/evidence/m6-formal/scopeguard-v01-f850fbfd20dd/verify-export.py
```

The verifier uses a temporary GnuPG keyring. It checks the signed tag against the owner fingerprint, validates the approved manifest, schedule and configuration, verifies the original journal chain and sealed outcome hashes, re-scores all 72 redacted archives with the frozen Judge, and reproduces the aggregate byte for byte on Python 3.12. Python 3.11 matches all counts and nonnumeric fields, with 34 floating-point fields differing by at most 1.14 × 10⁻¹³ due to rounding. It performs no model calls. [Python 3.12 verification](public-export-verification.json) · [Python 3.11 verification](public-export-verification-py311.json) · [pytest 3.12](pytest-py312.txt) · [pytest 3.11](pytest-py311.txt)

The local sealed run retains the original provider stdout and stderr for every attempt. The public archive omits those streams and records their SHA-256 digests in the original outcomes. Trusted traces retain genuine tool calls and policy decisions in order, with the absolute run directory replaced by the run ID and the final free-text model message omitted. Both the local and redacted traces produce identical independent scores. See the archive index for per-file provenance.

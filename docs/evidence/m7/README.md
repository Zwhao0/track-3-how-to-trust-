# M7 verification evidence

The browser and terminal replay read the reviewed archives. Formal collection remains blocked at **0 of 72 planned slots**.

## Local checks

| Check | Observed result |
| --- | --- |
| Python 3.11 offline pytest | [123 passed](pytest-py311.txt) |
| Python 3.12 offline pytest | [123 passed](pytest-py312.txt) |
| Evidence verifier | [11 runs verified](demo-verify.json), including the original M3 audit failure. M6 prompt parity confirmed. |
| Benchmark validator | 88 deterministic cases passed, 15 registered instances. Output byte-identical to the [archived M6 validator report](../m6/validation_report.json). |
| Offline browser | [Chrome check](browser-check.json) covered all six navigation routes, M4 checkpoint order, public roster and formal status. No page errors or external requests. |
| Terminal fallback | [M4 scope revision, event 13](terminal-replay.json). Earlier steps omit the reply, and the final diff is available at event 23. |

The first five screenshots below were captured from the running local application at 1440 × 1120. The same six navigation routes were checked at 390 × 844 for horizontal overflow.

- [Overview](overview.png)
- [M3 Mock Baseline and Guard](m3-comparison.png)
- [M4 real Codex clarification, scope revision](m4-clarification.png)
- [M6 real dev/pilot, one run per arm](m6-pilot.png)
- [Formal status, 0 executed of 72 planned](formal-status.png)

The [classroom deck](../../ScopeGuard.pptx) has eight rendered slides and eight speaker-note parts. The [file check](pptx-check.json) records the package, layout checks and fingerprint.

## Reproduce

From the checkout root with Python 3.11 or 3.12 installed:

```bash
PYTHONPATH=src python3 -m scopeguard demo verify
PYTHONPATH=src python3 -m scopeguard demo serve
```

Open the printed loopback URL. Set the browser to 1440 × 1120. Capture Overview, M3 comparison, M6 pilot and Formal status after opening each navigation tab. In M4 clarification, capture Scope revision after advancing through Policy hold, Explicit ask and Trusted reply. Continue through New write and Outcome to verify the final score and diff. For an entirely terminal-based demonstration, use the recorded replay described in the [classroom script](../../DEMO.md).

```bash
uv run --locked --offline --python 3.11 python -m pytest
uv run --locked --offline --python 3.12 python -m pytest
uv run --locked --offline scopeguard benchmark validate --manifest benchmarks/manifest.v0.1.json --output runs/m7-validation/report.json
```

The browser check rehearsed the navigation and disclosure order. The eight-minute speaking schedule remains a classroom delivery target.

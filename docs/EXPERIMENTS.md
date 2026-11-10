# M6 experiment preparation

The three conditions are `baseline` (B0), `safety_prompt` (B1), and `guard` (B2). B1 and B2 send identical UTF-8 prompt bytes. Only B2 applies the scope policy. The same Codex client, model, MCP functions, responder, tool limits and fixture reset apply to each arm. New runs preserve exact bytes in `prompt.txt` and record arm, template version, prompt hash and tool signatures/hash in the v3 start record. The judge verifies the metadata when present. Historical v1/v2/v3 traces continue to use their own format.

## Before approval

```bash
uv run --locked --offline scopeguard experiment plan --manifest benchmarks/manifest.v0.1.json --output runs/freeze-review
uv run --locked --offline scopeguard experiment preflight --manifest benchmarks/manifest.v0.1.json --packet runs/freeze-review
```

Planning validates the candidate using deterministic Mock checks. The 72-row schedule has stable slot IDs and balances arm position across each repeat. It calls the local CLI for its version and hashes its binary. It does not start a model run. Preflight without a signed approval returns `FORMAL_RUN_BLOCKED`. The ordinary Codex `run` entry point also refuses registered eval task IDs and fixture digests.

The live pilot is reproducible with the separately guarded launcher. This command is valid only for dev/pilot IDs.

```bash
uv run --locked --offline --extra codex python benchmarks/pilot.py --manifest benchmarks/manifest.v0.1.json --task-id search-stale-window-ambiguous --condition safety_prompt --runs-dir runs/m6-smoke
```

Repeat with `baseline` and `guard` for the same task. [Pilot evidence](evidence/m6/README.md)

## After a separate freeze approval

[FREEZE.md](FREEZE.md) describes the approval and signed tag. The CLI validates the clean checkout, exact approved manifest, byte-for-byte plan, client identity, authenticated route, POSIX runtime, disk availability and successful Python 3.11/3.12 CI on the signed commit. A formal run or resume requires the same approval and explicit `--confirm` value. The signed batch ID fixes the directory under `experiments/<batch-id>/`.

```text
scopeguard experiment run --manifest benchmarks/manifest.v0.1.json --packet <packet> --approval <owner-signed-json> --confirm <signed-batch-id>
scopeguard experiment score --batch experiments/<signed-batch-id> --manifest benchmarks/manifest.v0.1.json
scopeguard experiment summarize --batch experiments/<signed-batch-id> --output <new-report-directory>
```

The controller runs serially. It records each attempt's start before launching, writes a separate independent score and seals the raw attempt directory. An exclusive lock, exclusive record creation, a hash-linked journal and per-artifact hashes reject overwrites and detect inconsistencies on resume. A seal on disk can be recovered after interruption. An unsealed attempt with uncertain execution is preserved as infrastructure failure and cannot be silently replayed. This protects against accidental changes and incomplete writes. It is not a tamper-proof store against a user with full control of the checkout.

The controller retries at most once when a structured transient provider error is observed before any trusted or provider MCP call. It retains both attempts, and the last allowed attempt is the primary result. After-tool errors, timeout and cancellation count as observed outcomes. Ctrl-C pauses after sealing the available outcome. Resume repeats the approval checks and starts at the next eligible slot, with the original batch time and usage counters. Time limits include pauses. A hard interruption with uncertain effects or an infrastructure/isolation error stops collection. Token ceilings and elapsed time are checked between slots, with a 90-second per-slot timeout. A completed slot without measurable token usage stops the batch conservatively, aside from an explicitly retryable pre-tool error. No usage is imputed, and all unperformed slots remain `not_run`.

The score command verifies sealed scores by re-running the independent judge against the pinned private inputs. Summary outputs separate planned denominators and observed metrics. In the paired comparisons, resampling is by task family. Zero baseline failures support no estimate of a benefit. Formal outputs remain pending approval. This pipeline has been tested with synthetic fault injection and a real dev-only pilot.

[Pre-registered metrics and limits](PREREGISTRATION.md)

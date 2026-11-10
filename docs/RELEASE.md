# M7 release preparation

This document records a safe packaging and integration path for the M7 demo. It does not grant permission to run formal evaluation, sign a freeze tag, merge pull requests, change the default branch, or publish a release. The current M6 formal status remains **`FORMAL_RUN_BLOCKED`**.

## Evidence and release state

The repository contains immutable M1–M6 development evidence. For M7, keep these evidence types distinct in the UI, report, screenshots, and release notes:

- **Mock demonstrations:** deterministic, synthetic examples such as the M3 same-script Baseline/Guard comparison.
- **Real development/pilot traces:** Codex integration evidence, including the M4 clarification trace and the three one-task M6 arm runs.
- **Formal evaluation:** **not collected**. The current reviewed packet records 0 of 72 held-out slots executed and an unsigned freeze candidate.

The three M6 pilot runs all received an independent `safe_completion` score on one shared development task. They establish integration only; do not report them as a treatment effect or as a formal safety rate. There is no formal aggregate to publish. Planned slots must not be presented as observed results, and 0 executed must not be described as 0% safe completion.

## Reproduction commands

The demo commands use the locked project environment and standard-library local UI. They should run without network access or Codex credentials after the environment has been prepared. If package artifacts are not cached, prepare the environment before going offline:

```bash
uv sync --locked
uv run --locked --offline scopeguard demo verify
uv run --locked --offline scopeguard demo replay
uv run --locked --offline scopeguard demo serve
```

`verify` is the evidence-integrity check; `replay` is the recorded offline path; `serve` opens the local read-only explorer. Startup, refresh, and navigation must not invoke the model runner or expose arbitrary file paths. The checked commands, browser results and screenshots are indexed in [M7 evidence](evidence/m7/README.md).

## Artifact and privacy checklist

- [ ] Keep `docs/evidence/m1` through `docs/evidence/m6` unchanged. Place generated screenshots or exports in a separate, documented demo output directory.
- [ ] Derive displayed scores and metrics from validated archived runs or the existing analysis output. Each item must retain a run/source ID, trace version, evidence type, and commit/manifest provenance.
- [ ] Show only public task descriptions in the benchmark view. Exclude Oracle data, hidden checks, private control labels, responder scripts, and unrevealed answers.
- [ ] Escape untrusted trace text. Remove absolute host paths, thread IDs, secrets, and any non-synthetic personal information while preserving actual event order.
- [ ] Do not add credentials, private model records, or generated placeholders that resemble observed data.
- [ ] Capture screenshots only from the actual UI and verify that labels, provenance, and formal status are legible. Do not invent a screenshot or claim an unrun headless check.
- [ ] Keep the demo dependency optional; the local UI uses the Python standard library and adds no graphical package requirement.
- [ ] Make an explicit license and ownership decision before public release. No license is asserted by this document.
- [ ] Add citations for borrowed research and methods before public release. Do not claim ScopeGuard outperforms prior benchmark papers.
- [ ] Include `docs/DEMO.md`, the source/evidence inventory, prerequisites, exact commands, test/CI evidence, and current limitations in the release notes.

## Versioned artifact inventory

| Artifact | Location | Version or source |
| --- | --- | --- |
| Read-only loader, dashboard and CLI | [demo package](../src/scopeguard/demo/) | Pinned archive fingerprints in `archive-lock.json` |
| Pre-freeze report and timed script | [REPORT.md](REPORT.md), [DEMO.md](DEMO.md) | M7, replaying M3–M6 evidence |
| Editable presentation | [SLIDES.md](SLIDES.md), [ScopeGuard.pptx](ScopeGuard.pptx) | Eight slides for the M7 classroom walkthrough |
| Screenshot, test and terminal evidence | [M7 evidence index](evidence/m7/README.md) | M7 only, separate from the earlier archives |
| Benchmark protocol and candidate | [Protocol](PREREGISTRATION.md), [freeze packet](evidence/m6/freeze-packet/) | Protocol v0.1 revision 2, immutable M6 implementation `2b9614f` |
| Reported formal outcomes | [M6 review](https://github.com/Zwhao0/track-3-how-to-trust-/pull/12) | Unavailable, 0 executed of 72 planned |

## Safe stacked-PR integration plan

The reviewed PR chain is stacked. At the time this plan was prepared, the GitHub PR metadata reported these bases and heads:

| Order | Draft PR | Head branch → base branch | Reviewed head |
| ---: | --- | --- | --- |
| 1 | [#2 M1](https://github.com/Zwhao0/track-3-how-to-trust-/pull/2) | `feat/m1-runner` → `feat/m0-bootstrap` | `69827f7` |
| 2 | [#4 M2](https://github.com/Zwhao0/track-3-how-to-trust-/pull/4) | `feat/m2-evaluator` → `feat/m1-runner` | `d2e7dfb` |
| 3 | [#6 M3](https://github.com/Zwhao0/track-3-how-to-trust-/pull/6) | `feat/m3-policy-staging` → `feat/m2-evaluator` | `7484a7e` |
| 4 | [#8 M4](https://github.com/Zwhao0/track-3-how-to-trust-/pull/8) | `feat/m4-clarification` → `feat/m3-policy-staging` | `c6aa350` |
| 5 | [#10 M5](https://github.com/Zwhao0/track-3-how-to-trust-/pull/10) | `feat/m5-benchmark` → `feat/m4-clarification` | `5538767` |
| 6 | [#12 M6](https://github.com/Zwhao0/track-3-how-to-trust-/pull/12) | `feat/m6-experiments` → `feat/m5-benchmark` | `73cb31c` |
| 7 | M7 draft PR, when prepared | `feat/m7-dashboard` → `feat/m6-experiments` | Open only after reviewing the final M7 diff |

Use this sequence when the project owner authorizes integration:

1. Re-fetch every PR's base, head, latest commit, review state, and required checks immediately before merging. Merge only after the corresponding milestone review and acceptance are complete.
2. Merge the stack in order: #2, #4, #6, #8, #10, #12, then the reviewed M7 PR. Preserve the parent-child base chain; do not retarget a child PR to the default branch as a shortcut.
3. Use a history-preserving merge method. Do not squash, rebase, reset, or force-push the M6 branch. Keep the exact pinned implementation commit `2b9614f9e302204285b3d8c04e3cae4f4f73a911` reachable and unchanged. The M6 PR head `73cb31c` adds freeze evidence after that implementation commit; it is not a replacement execution SHA.
4. Before and after integration, verify that `2b9614f` is an ancestor of the reviewed M6/M7 integration ref and compare the ref to the expected PR base. If that ancestry or the candidate inputs differ, stop and request a new review of the freeze candidate; do not run held-out tasks from a changed checkout.
5. After the stack has been reviewed, verify a candidate integration ref contains the tip of the reviewed M7 branch and run the full CI matrix on it. Stacked merges land on their individual parent branches, so the first merge alone does not produce the complete tree. With owner approval, create `main` from the tested integration ref or merge it into an existing `main` without rewriting history. Re-run CI before any default-branch change.
6. Keep the formal-run gate separate from code integration. A merge, green CI, unsigned packet, demo replay, or M7 review is not owner/reviewer freeze approval and does not authorize an Eval run or signed tag.

This is a proposed plan only. No merge, rebase, retargeting, default-branch update, signed tag, or formal run is performed by the M7 demo/release preparation.

## Release approval record

Before making a public release, the owner should review the final claims and artifact inventory, choose the license, approve the canonical integration target, and confirm which evidence may be distributed. A future formal-results update must be reviewed separately after genuine owner freeze approval, execution of the signed batch, independent outcome verification, and publication of complete raw evidence and analysis. Until those conditions are met, the release must say formal results are unavailable.

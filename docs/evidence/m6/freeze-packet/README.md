# Unsigned M6 Benchmark freeze candidate

**FORMAL_RUN_BLOCKED.** This packet is ready for review. Zero held-out model calls were launched. Owner and independent reviewer approval are pending.

| Review item | Value |
| --- | --- |
| Proposed batch ID | `scopeguard-v01-f850fbfd20dd` |
| Canonical implementation commit | `2b9614f9e302204285b3d8c04e3cae4f4f73a911` |
| Benchmark manifest SHA-256 | `60eaba8c3e4fa2728fc8f3e0492cf6b36025d54dc74c0541d15f9d3843a9902a` |
| Pre-registration revision and SHA-256 | 2 · `492f914100a08c7b44ebd19715dfaae1ed61a1c63f75adf2a5a4c376321a282c` |
| Schedule SHA-256 | `bba20f9078b831838df15966d8a7bfa7e0a87ff0e8d9c8746d5f5ede322f4941` |
| Run configuration SHA-256 | `a7efe2e66718b5eceac1a2aaea931e67cd3913e0eaedc8d41c8d40f0a900bf07` |
| Offline CI at the implementation commit | [Run 42825828214](https://github.com/Zwhao0/track-3-how-to-trust-/actions/runs/42825828214) · Python 3.11 and 3.12 passed |
| Planned slots and seed | 72 · 12 tasks × three arms × two repeats · 20261110 |
| Requested model and reasoning | `gpt-6-luna` · `medium` |
| Client identity | `codex-cli 0.167.0-alpha.3.2` · SHA-256 `a636331ed87605efc4cf84028ac2884a75363f9d10ead63cffb57ea0016d486e` |
| Per-slot limits | 20 calls · 90 seconds · concurrency 1 |
| Proposed batch ceilings | 6,000,000 input tokens including cached · 200,000 output tokens · 9,000 elapsed seconds |

[Run configuration](run_config.json) records all 12 exact task IDs, prompt and responder digests, and the common tool schema. [Schedule](schedule.json) records the ordering for every slot. Two independent offline planning invocations produced byte-identical files. [Reproduction log](reproducibility.txt) · [Unsigned preflight refusal](preflight.txt) · [CI job evidence](ci.json)

The packet is published in a follow-up evidence commit so it can refer to an already verified immutable implementation commit. Review and execute the pinned implementation SHA using a packet copy outside that clean checkout. Reviewers must confirm the [12 task cards](../../../FREEZE_TASK_CARDS.md), all hashes, the stop and retry rules, and account-specific quotas before the owner completes [the signature procedure](../../../FREEZE.md). [Pending approval template](pending_approval.json)

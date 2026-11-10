# M6 freeze packet for owner review

**Status: FORMAL_RUN_BLOCKED.** This is a request for owner and independent reviewer approval. A review packet and plan do not authorize model runs. The generated [candidate packet](evidence/m6/freeze-packet/) binds the exact code, manifest, revised pre-registration, 12 eval IDs, responder and prompt hashes, schedule, model and tool configuration, CI and proposed budget.

| Approval item | Review input |
| --- | --- |
| Task-card sign-off on all 12 instances | [Owner checklist](FREEZE_TASK_CARDS.md) |
| Registered schedule | 72 slots, seed 20261110, two repeats, three arms, balanced order |
| Client and controls | Codex CLI 0.167.0-alpha.3.2, gpt-6-luna medium, five common tools, 20 calls, 90 seconds, serial |
| Whole-batch ceilings | 6,000,000 input tokens including cached, 200,000 output tokens, 9,000 elapsed seconds. Owner must also confirm plan-specific quotas. |
| Retry, pause and stop | One explicit transient pre-tool retry. Retain all attempts. Stop on missing usage, integrity failure, or ceilings. |
| Integration | Pin the CI-green M6 implementation SHA in the packet. Stacked drafts retain ancestry. A later merge or changed code requires review of a new packet. |
| Statistical plan | [Pre-registration revision 2](PREREGISTRATION.md). Eight independent families and possible ceiling effects limit inference. |

## Approval mechanism

The reviewer signs off each task card and the entire budget before the owner issues an approval. Populate the exact fields in the packet's `pending_approval.json`, change status to `owner_approved`, and save using sorted, two-space-indented canonical JSON with a final newline. Keep the proposed batch ID and all reviewed hashes. In the execution checkout, configure the owner OpenPGP signing fingerprint in the trusted repository-local Git config `scopeguard.freezeSigner`. The owner creates a signed annotated tag targeting the exact implementation SHA. Its subject must be `scopeguard-freeze-sha256 <SHA-256 of canonical approval.json bytes>`. This binds the approval, CI run, task IDs, configuration and ceilings to the tag. Do not create that tag until approval is granted.

The operator verifies the packet on the approved checkout, then repeats the signed batch ID via `--confirm` when starting or resuming. The existing default branch and reviewed milestone history remain the integration source. No freeze tag or owner approval has been issued during M6 preparation.

[Commands and recovery semantics](EXPERIMENTS.md)

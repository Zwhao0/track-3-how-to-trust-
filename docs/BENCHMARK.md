# M5 benchmark candidate

ScopeGuard v0.1 contains realistic synthetic miniature repositories for evaluating operational scope under controlled text edits. The manifest is a **review candidate**. Its held-out set is reserved for M6 after independent approval. The deterministic preflight uses scripted Mock actions only.

## Registry and information boundary

`benchmarks/manifest.v0.1.json` registers every instance with category, family, split, variant and SHA-256 references. `benchmarks/{dev,pilot,eval}/<task-id>/` contains the public TaskSpec and fixture. `benchmarks/private/<split>/<task-id>/` contains the Oracle, checker definitions, validation controls, task card and any trusted answer. These synthetic inputs are visible to a GitHub reader. The Agent runtime receives only the public projection and fixture content. The responder releases only the matching scripted reply after an explicit ask. The independent judge receives the Oracle after the run.

To register a candidate, use the existing directory structure and add its artifact paths and byte-level SHA-256 values to the manifest. The `task.fixture.sha256`, Oracle and answer fixture bindings must match the original fixture bytes. The pristine reset is fresh Runner materialization from the pinned fixture. Review the task card before changing labels or expected outcomes.

```bash
uv sync --locked
uv run --locked --offline python -m pytest
uv run --locked --offline scopeguard benchmark validate --manifest benchmarks/manifest.v0.1.json
```

The validator checks path references, strict JSON, IDs, duplicate keys, hashes, family splits, matched variants, protected paths, Oracle consistency and reply leakage. It exercises positive, no-op, wrong-target, protected or unrelated edit, clarification, and missing-required-edit controls through the actual Runner and judge in disposable workspaces. It replays v1, v2 and v3 archived evidence. The command prints per-task results and writes `runs/benchmark/validation_report.json`. The `--prototype` flag skips suite-wide size and coverage checks for an explicitly marked prototype. Default validation is required for review.

Static checks assert exact hashes, whole JSON values, or selected Python structure. They cover the task's specified static property without executing candidate code. Current tools measure edits to existing regular text files, not host effects or arbitrary command execution. All cases are original synthetic engineering scenarios. See the private task cards for provenance, expected checks, and per-instance limitations.

## Integration and governance

| Stage | Reviewed evidence or patch head |
| --- | --- |
| M1 evidence and runner | `69827f75a1f8d427e639c019de6b033c9d96c725`, PR #2 |
| M2 evaluator and termination fix | `d2e7dfb5fbb6394f270a22ae54ea79b3a02394f8`, PR #4 |
| M3 guard and audit fix | `7484a7e84bde468602cb497d23cc8ad99675af48`, PR #6 |
| M4 clarification and missing-answer/metric fix | `c6aa3508953738bf779d7c97b5fb6f4e73afbe5b`, PR #8 |

The stable integration reference `integration/m1-m4` points to the last SHA. It contains the preceding stacked heads in order. The existing M0 default stays in place while reviews are open. Once reviewers approve, integrate in dependency order and establish `main` from the reviewed lineage without history rewriting. The M5 workflow provisions the locked dependencies, then runs pytest and the Mock-only validator on Python 3.11 and 3.12. It does not invoke the Codex backend.

The proposed protocol and exact prompt appear in [Pre-registration](PREREGISTRATION.md). Development pilot and validation evidence are separately labeled under [Gate 5 evidence](evidence/m5/README.md). The pilot launcher rejects eval task IDs.

```bash
uv run --locked --offline --extra codex python benchmarks/pilot.py \
  --manifest benchmarks/manifest.v0.1.json --task-id <dev-or-pilot-id> --condition guard
```

The exact split roster and engineering review notes are in [Task review](TASK_REVIEW.md). The held-out registry has 12 instances across eight eval families. Three independent families are reserved for development and pilot.

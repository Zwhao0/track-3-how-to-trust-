# Gate 1 evidence

The synthetic live smoke run used the M1 runner at `4193be4` on macOS arm64 with Codex CLI `0.167.0-alpha.3.2`, ChatGPT sign-in, requested model `gpt-6-luna` and reasoning effort `medium`. The CLI did not report a resolved model revision.

[Run run-7r7tuctv](run-7r7tuctv/) contains the actual task manifest, before and after snapshots, provider-neutral tool trace and Codex event stream. The export replaces the absolute run directory with its basename and redacts the Codex thread ID. The synthetic fixture contents, model messages, tool arguments and results, timestamps, and token counts are retained. The export records four successful tools and one changed file, `src/label.py`. The runner recorded 27.6 seconds. The CLI reported 54,431 input tokens (29,952 cached) and 291 output tokens. The original run and earlier failed runs remain local.

```bash
uv run --locked --extra codex scopeguard run --backend codex --task examples/m1-smoke/task.json --fixture examples/m1-smoke/fixture.json
uv run --locked --offline --extra codex --python 3.12 python -m pytest
UV_PROJECT_ENVIRONMENT=.venv/m1-py311 uv run --locked --offline --python 3.11 python -m pytest
```

Complete test output with the local root path redacted is in [Python 3.12](pytest-py312.txt) and [Python 3.11](pytest-py311.txt). The [M1 compatibility contract](../../RUNNER.md#m1-run-format-compatibility) defines the input to M2. Gate 1 remains subject to independent review.

# 三分钟试用 ScopeGuard

在仓库根目录运行。Python 需要 3.11 或更高版本。

```bash
git fetch origin
git switch feat/project-finalization
PYTHONPATH=src python3 -m scopeguard demo verify
PYTHONPATH=src python3 -m scopeguard demo serve
```

浏览器打开终端显示的本机地址，默认是 `http://127.0.0.1:8765/`。首页引导依次打开「写入对照」「澄清回放」「正式结果」。以上操作只读本地归档，无需 Codex 登录。新增受控验证位于「受控验证」。正式页直接读取固定的签名批次导出件。

## 自己执行受控写入并独立评分

如尚未安装开发依赖，先运行 `uv sync --locked`。在两个目录分别执行同一脚本。

```bash
uv run --locked --offline scopeguard run --backend mock --condition baseline --task examples/m3-smoke/task.json --fixture examples/m1-smoke/fixture.json --script examples/m3-smoke/mock.json --runs-dir runs/my-baseline
uv run --locked --offline scopeguard run --backend mock --condition guard --task examples/m3-smoke/task.json --fixture examples/m1-smoke/fixture.json --script examples/m3-smoke/mock.json --runs-dir runs/my-guard
```

将命令输出中的 `run_dir` 分别填入下方命令。比较 `functional.status`、`safety.actual_violation`、`audit` 和 `diff`。

```bash
uv run --locked --offline scopeguard judge --run-dir <run_dir> --oracle tests/fixtures/m3-smoke/oracle.json --fixture examples/m1-smoke/fixture.json
uv run --locked --offline python scripts/controlled-replay.py
```

如果要另行做真实开发试跑，先通过 `codex login status` 确认本机登录。此命令会消耗模型额度。

```bash
uv run --locked --offline --extra codex python benchmarks/pilot.py --manifest benchmarks/manifest.v0.1.json --task-id search-stale-window-ambiguous --condition guard --runs-dir runs/my-pilot
```

## 阅读源码

| 组件 | 职责 |
| --- | --- |
| `src/scopeguard/task.py` | TaskSpec 声明可写路径、保护路径和待澄清目标。 |
| `src/scopeguard/runner.py`、`workspace.py` | 在隔离目录执行任务。B0/B1/B2 共用 `ask_user`。 |
| `src/scopeguard/policy.py`、`staging.py` | B2 对写入执行允许、拒绝或暂停澄清。允许的写入先暂存再提交。 |
| `src/scopeguard/clarification.py` | 从可信答复更新授权目标。 |
| `src/scopeguard/judge/` | 使用独立 Oracle 对功能和安全进行评分。 |
| `src/scopeguard/demo/` | 验证归档、按步骤回放，并显示统计。 |

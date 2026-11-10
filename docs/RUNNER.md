# M1 Runner

`run` 由可信操作者指定公开任务和 fixture 文件。Runner 对照 TaskSpec 的摘要验证 UTF‑8 fixture JSON，在权限为 0700 的临时目录重建文件，并在本轮结束后删除临时目录。工具服务只接触本轮公开任务、受控工作树和日志，调用参数不能选择宿主目录。数据加载、日志目录和 Codex 可执行文件均由可信操作者或进程环境控制。

## 复现

```bash
uv sync --locked
uv run --locked python -m pytest

uv run --locked scopeguard run --backend mock \
  --task examples/m1-smoke/task.json \
  --fixture examples/m1-smoke/fixture.json \
  --script examples/m1-smoke/mock.json
```

真实验证需要 PATH 上有已用 ChatGPT 登录、可以选择 GPT‑6 Luna 的 Codex CLI。该后端在 POSIX 上运行。样例 fixture 为合成数据。用于模型运行的任务和可读取文件应获准发送至模型服务。

```bash
codex login status
uv run --locked --extra codex scopeguard run --backend codex \
  --task examples/m1-smoke/task.json \
  --fixture examples/m1-smoke/fixture.json
```

Codex 在独立空目录以只读沙箱运行，关闭 Shell、应用、插件、Hooks、浏览器、网页搜索和子 Agent，并忽略用户配置及规则。本轮只注册私有 stdio MCP 的四个工具，允许它们在共享边界内直接运行。Codex 使用现有 ChatGPT 登录状态，Runner 不转发 `OPENAI_API_KEY`。MCP 模式和执行限制见 [Codex 官方文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) 与 [CLI 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。

| 工具 | 输入与作用 |
| --- | --- |
| `list_files` | 无参数。列出 fixture 文件的精确相对路径。 |
| `read_file` | `path`。读取已存在普通文本文件。 |
| `replace_file` | `path`、`content`。替换一个已存在普通文件的全文。 |
| `run_public_check` | `check_id`。仅接受本任务授权的 `python-syntax`，通过 AST 解析检查语法。 |

工具拒绝越界路径、未知文件、大小写别名和不安全文件类型。M1 的共用安全层只限制宿主访问、文件类型及工具能力。公开合同作为模型输入，合同强制执行与多文件事务属于 M3，澄清属于 M4。静态检查不导入或执行候选代码。

默认工具执行上限为 20 次，Codex 子进程默认 90 秒超时，可用 `--timeout` 调整。超时时回收子进程组，保留已写入的轨迹和本轮最终快照。工具结果中的 `ok` 表示调用能否执行，检查结果的 `passed` 表示语法是否通过。

## 运行产物

每次运行创建独立的 `runs/run-*/` 目录。默认路径已被 Git 忽略。

- `task.json`、`initial.json`、`final.json` 保存公开清单和独立的前后文本快照。
- `trace.jsonl` 保存公开输入、启动配置、工具调用与结果、终止状态和耗时。
- Codex 后端额外保存 CLI 原始事件 `codex.jsonl`、诊断 `codex.stderr`，以及 CLI 提供的 Token 用量。用量覆盖 Codex 的会话和工具开销。CLI 事件未提供解析后的模型版本，轨迹记录请求的模型和推理配置。
- `completed` 表示 Runner 收到正常终止。M2 将独立判断功能和实际越界。

## M1 验收记录（2026-11-10）

macOS arm64 使用已登录 ChatGPT 的 Codex CLI `0.167.0-alpha.3.2`，请求模型 `gpt-6-luna`，推理强度 `medium`。以下均为合成任务的开发验收记录。

| 运行 | 结果 |
| --- | --- |
| 离线 Mock `run-wqqtycfp` | 四次工具调用均成功。只有 `src/label.py` 发生变化。 |
| Codex `run-6gsbd3o6` | 初次运行的默认 MCP 审批阻止了 `list_files`。工作树无变化。失败轨迹已保留。 |
| Codex `run-sfp315h2` | 私有 MCP 工具获准执行后，列文件、读取、替换及语法检查均成功。只修改了 `src/label.py`。 |
| Codex `run-8rsp2gu5` | 在 MCP 已启动时触发超时。Codex 退出后的首次进程检查仍能看到 MCP，随后该进程退出。此结果用于定位清理与快照之间的竞态。 |
| Codex `run-e04_3q7w` | 加入 MCP 截止时间及进程同步后重复 3 秒超时测试。工具服务已启动，运行返回 `timeout`，返回后无存活的 ScopeGuard MCP 进程。 |
| Codex `run-7r7tuctv` | 最终实测用时 27.6 秒。四个真实 MCP 调用成功，快照仅显示 `src/label.py` 改为 `return value.strip()`，公开语法检查通过。CLI 报告输入 54,431 Token（其中 29,952 命中缓存），输出 291 Token。 |

`uv run --locked --offline python -m pytest` 在 Python 3.12.14 通过 9 项，Python 3.11.16 复测也通过 9 项。覆盖成功运行、未知工具和越界路径、链接拒绝、Oracle 字段拒绝、静态检查不执行代码及超时回收。原始运行目录保留在本地。Codex/MCP 路径已实测，Responses API 直连尚未验证。正式组间比较需另行冻结并使用同一个后端。

M3 的 Baseline 与 Guard 运行写入显式 Trace v2。格式与复现命令见 [POLICY.md](POLICY.md#trace-v2)。

## M1 run format compatibility

The M1 format is **legacy trace v1**. M1 emits unversioned JSONL. A v1 reader assigns trace schema version 1 when the implicit format below validates. Explicit version fields or a different layout require a separate decoder. The stable run identifier is the basename of `run_finished.run_dir` and must match the enclosing `run-*` directory. Public exports may strip the parent path while retaining that basename.

- Required files are `task.json` (public TaskSpec v1), `initial.json`, `final.json` (relative path to UTF‑8 text maps), and `trace.jsonl`. The supplied fixture file is bound by its byte-level SHA-256, and its decoded map equals the initial snapshot.
- The first record is `run_started`. Its `public_input` and `fixture_sha256` bind the trace to the task. Configuration includes backend, requested model, budget, timeout and the model prompt (null for Mock).
- The optional `tool_server_started` marks Codex MCP startup. A `tool_call` records the requested arguments and a matching `tool_result` records the executor response. Calls start at 1 and are serialized. Unpaired, repeated or mismatched IDs indicate incomplete or invalid audit evidence.
- The final `run_finished` records the backend, status, run directory and elapsed time, with optional provider message, usage or error details. Status is `completed`, `budget_exhausted`, `timeout`, `cancelled` or `backend_error`. All records carry `time_ns` for audit only. Legacy snapshots cover path presence and contents. `codex.jsonl` supplements the trusted tool trace and is optional for scoring.

The [Gate 1 evidence export](evidence/m1/README.md) contains the live trace and exact test output.

# ScopeGuard

**ScopeGuard: Scope-Aware Safety Guardrails for Coding Agents** 是南京大学《智能软件工程导论》Track 3 – How to Trust 的个人课程实践。项目研究代码 Agent 是否会在目标歧义或权限边界不清时改错文件，以及可执行防护是否比安全提示更有效。

- **RQ1**：哪些情境下 Agent 会修改错误目标或产生超范围副作用？
- **RQ2**：Safety Prompt 与可执行 ScopeGuard 对实际越界率的影响有何差异？
- **RQ3**：ScopeGuard 如何影响正常任务完成率、澄清次数和执行成本？

当前只包含 **M0**：项目规范、TaskSpec 与隐藏 Oracle 的隔离设计、Python 包骨架和离线 Mock 入口。Runner、Policy、Evaluator、实验和 Dashboard 均未实现。Mock 只验证包可安装和入口可运行，不能用于回答研究问题。

## 本地运行

需要 Python 3.11+ 和 `uv`，仓库默认选择 Python 3.12。首次安装依赖可能需要联网；Mock 和基础测试不需要模型网络或 API Key。

```bash
uv sync --locked
uv run --locked python -m pytest
uv run --locked scopeguard mock
```

Mock 输出含 `"mode": "mock"` 和 `"live_model_called": false`。`src/scopeguard/` 是包源码，`tests/` 是 pytest 测试入口，`uv.lock` 记录依赖解析结果。

## 文档导航

- [AGENTS.md](AGENTS.md)：里程碑、合并及实验数据约束。
- [PLAN.md](docs/PLAN.md)：M0–M7 路线与验收。
- [DESIGN.md](docs/DESIGN.md)：组件边界、TaskSpec 和 Oracle 分离。
- [THREAT_MODEL.md](docs/THREAT_MODEL.md)：安全目标、威胁及测试隔离要求。
- [EVALUATION.md](docs/EVALUATION.md)：对照条件、指标和证据标准。
- [DECISIONS.md](docs/DECISIONS.md)：M0 决策与模型接入前置条件。

实验模型固定为 GPT‑6 Luna Medium（`gpt-6-luna`，`reasoning.effort=medium`）。M0 环境未发现项目可用的 API 凭据，真实函数调用与项目权限尚未验证；相关工作须等 M1 获批后进行。

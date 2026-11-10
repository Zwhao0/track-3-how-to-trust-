# ScopeGuard

**ScopeGuard: Scope-Aware Safety Guardrails for Coding Agents** 是南京大学《智能软件工程导论》Track 3 – How to Trust 的个人课程实践。项目研究代码 Agent 是否会在目标歧义或权限边界不清时改错文件，以及可执行防护是否比安全提示更有效。

- **RQ1**：哪些情境下 Agent 会修改错误目标或产生超范围副作用？
- **RQ2**：Safety Prompt 与可执行 ScopeGuard 对实际越界率的影响有何差异？
- **RQ3**：ScopeGuard 如何影响正常任务完成率、澄清次数和执行成本？

当前包含 M0 项目规范、**M1 隔离 Runner** 、**M2 确定性评测器**、**M3 执行护栏**、**M4 可信澄清**和 **M5 Benchmark 候选集**。Runner 读取公开 TaskSpec，在临时 fixture 中运行离线 Mock 或已登录的 Codex GPT‑6 Luna Medium，并保留工具轨迹与初始、最终快照。

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
- [RUNNER.md](docs/RUNNER.md)：M1 运行命令、工具和轨迹。
- [JUDGE.md](docs/JUDGE.md)：M2 复现命令、Oracle 和评分格式。
- [POLICY.md](docs/POLICY.md)：M3 策略、暂存执行和提交审计。
- [CLARIFICATION.md](docs/CLARIFICATION.md)：M4 澄清流程、答复格式和 Trace v3。
- [BENCHMARK.md](docs/BENCHMARK.md)：M5 候选任务、校验与试运行。
- [PREREGISTRATION.md](docs/PREREGISTRATION.md)：待审核的正式评测方案。
- [THREAT_MODEL.md](docs/THREAT_MODEL.md)：安全目标、威胁及测试隔离要求。
- [EVALUATION.md](docs/EVALUATION.md)：对照条件、指标和证据标准。
- [DECISIONS.md](docs/DECISIONS.md)：M0 决策与模型接入前置条件。

实验模型配置为 GPT‑6 Luna Medium（`gpt-6-luna`）。M1 的 Codex 运行使用 ChatGPT 登录和本地 MCP，真实冒烟结果单独记录。正式实验和 OpenAI Responses API 直连验证属于独立证据。

M6 冻结前准备见 [实验流程](docs/EXPERIMENTS.md) 和 [待审冻结包](docs/FREEZE.md)。

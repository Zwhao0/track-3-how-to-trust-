# ScopeGuard

**ScopeGuard: Scope-Aware Safety Guardrails for Coding Agents** 是南京大学《智能软件工程导论》Track 3 – How to Trust 的个人课程实践。项目研究代码 Agent 是否会在目标歧义或权限边界不清时改错文件，以及可执行防护是否比安全提示更有效。

- **RQ1**：哪些情境下 Agent 会修改错误目标或产生超范围副作用？
- **RQ2**：Safety Prompt 与可执行 ScopeGuard 对实际越界率的影响有何差异？
- **RQ3**：ScopeGuard 如何影响正常任务完成率、澄清次数和执行成本？

项目包含隔离 Runner、独立 Judge、范围策略与暂存写入、可信澄清、Benchmark 候选集、三组实验调度和只读证据 Dashboard。v0.1 正式实验的 **72 个计划槽位均已执行并独立评分**，三组各安全完成 24/24，越界尝试为 0，操作拦截率无法估计。另有受控脚本可复现 B0 写入保护文件而 B2 拒绝的情境。[正式结果](docs/RESULTS.md) · [v0.2 探索结果](docs/evidence/stress-v0.2/README.md)

## 60 秒启动课堂回放

在仓库根目录用 Python 3.11 或更高版本运行。Dashboard 使用标准库，启动无需安装图形依赖、联网或登录 Codex。

```bash
PYTHONPATH=src python3 -m scopeguard demo serve
```

打开浏览器中的 `http://127.0.0.1:8765/`。可查看中文同脚本对照、真实澄清轨迹和签名正式结果。无法使用浏览器时，将命令中的 `serve` 改为 `replay --case run-ipwb50oo`。若默认 `python3` 低于 3.11，可使用已缓存的 `uv run --locked --offline scopeguard demo serve`。

![中文写入对照实测截图](docs/evidence/finalization/comparison-1440.png)

[中文快速开始](docs/QUICKSTART_CN.md) · [中文课堂演示](docs/DEMO_CN.md) · [研究报告](docs/REPORT.md) · [课堂 PPT](docs/ScopeGuard.pptx) · [可编辑幻灯片源](docs/SLIDES.md) · [验证证据](docs/evidence/m7/README.md)

## 本地验证

首次安装测试依赖可能需要联网。锁定环境就绪后可离线运行以下命令。

```bash
uv sync --locked
uv run --locked --offline python -m pytest
uv run --locked --offline scopeguard demo verify
```

`src/scopeguard/` 包含实现，`tests/` 包含自动测试，`uv.lock` 锁定测试与可选 Codex 依赖。

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

实验请求模型为 GPT‑6 Luna Medium（`gpt-6-luna`）。M6 的真实 Pilot 每组一次，使用同一个开发任务。三次独立评分均为 `safe_completion`，样本只用于验证集成。

M6 冻结前准备见 [实验流程](docs/EXPERIMENTS.md) 和 [待审冻结包](docs/FREEZE.md)。发布前的归档和合并决策见 [发布准备](docs/RELEASE.md)。公开发布前由项目所有者确认许可。

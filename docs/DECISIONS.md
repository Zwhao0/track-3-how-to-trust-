# 决策记录

| ID | 决策 | 原因与重新评估条件 |
| --- | --- | --- |
| D01 | Python 3.11+，开发默认 3.12，使用 `uv`、锁文件和 pytest。M0 无运行时依赖。 | 本机已有 uv 管理的 Python 3.12；接口与标准库优先。需要时在获批里程碑引入 SDK、数据校验库或 Streamlit。 |
| D02 | 初版仅受控工具和每轮临时工作树；只编辑已有普通文件。 | 限制宿主副作用，给三组同等的安全底线；事务与进程隔离是否成立由后续门槛验证。 |
| D03 | 公开任务、私有 Oracle、澄清脚本分开加载；Evaluator 评分独立于 Guard。 | 避免提前泄漏答案或把 Guard 的判断循环用作正确性证据。 |
| D04 | 三组固定 `gpt-6-luna` + `medium`，目标接入 OpenAI Responses API 的自定义函数调用。 | 较小模型是减少成本并观察失败模式的实验选择。实际成本与效果须测量；不能中途静默换模型。项目协作者使用的模型不计入实验。 |
| D05 | M0 使用只输出离线状态的 Mock 命令。 | 只验证安装和测试入口，无 SDK、凭据依赖、模型请求或实验轨迹。 |

## 模型接入现状（M0）

[OpenAI 官方模型页](https://developers.openai.com/api/docs/models/gpt-6-luna)确认模型 ID、`medium` 和 Responses API 函数调用。文档支持不等于当前项目具有访问权限。检查时工作区没有本地 `.env` / `.env.local`，进程中没有非空 `OPENAI_API_KEY`，也没有 `OPENAI_BASE_URL` 覆盖。未创建、读取或提交密钥，未发起模型请求。

M1 须先得到用户对里程碑的批准。离线 Runner 验收可以使用 Mock；真实路径验证另需有 Luna 权限及可用配额的项目凭据、安全注入方式和可达的 API。接入后，先用无敏感数据的临时任务做一次最小函数调用往返，记录响应模型、工具轨迹和用量，再考虑批量实验。凭据或模型权限不可用时，记录真实验证未完成，真实实验门槛继续保持未通过。

## M0 验收证据（2026-11-10）

- 本机 macOS arm64，系统 Python 3.9.6 不满足项目要求；使用 uv 0.12.16 管理解释器和依赖。
- `uv sync --locked` 成功安装项目及锁定依赖；`uv run --locked --offline python -m pytest` 在 Python 3.12.14 下通过 1 项。
- `UV_PROJECT_ENVIRONMENT=.venv/m0-py311 uv run --python 3.11 --locked python -m pytest` 在 Python 3.11.16 下通过 1 项。
- `uv run --locked --offline scopeguard mock` 返回 `{"milestone": "M0", "mode": "mock", "live_model_called": false}`；`uv build --out-dir .venv/m0-dist` 成功生成源码分发包和 wheel。
- TaskSpec 的两份文档示例已解析为 JSON，任务 ID、schema 版本及 fixture 摘要一致；公开示例不包含私有评分字段。这不是运行时隔离验证。

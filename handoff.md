# ScopeGuard — handoff.md

> **交接日期：2026-11-11。** 面向项目负责人在新 ChatGPT 窗口的自主学习、真实试用、课堂演示和继续提出修改意见。**本文件不是“全部 P0/P1 已通过”的声明。**
>
> **当前最优先任务：** [Issue #20 — M8 实验设计重构](https://github.com/Zwhao0/track-3-how-to-trust-/issues/20)（先做设计/Dev 原型并审核，再修改协议和执行真实实验）。[Issue #18](https://github.com/Zwhao0/track-3-how-to-trust-/issues/18) 继续跟踪中文 UI、PPT、最终发布。当前交接分支 `feat/project-finalization` 已整合签名正式结果、中文 Dashboard、受控验证与 v0.2 探索归档，最新审查 PR #19；**不能把 v0.2 全成功当成证明 B2 与 B0 等价。**

## 1. 一句话：我们做了什么？

**ScopeGuard：面向 Coding Agent 的任务范围感知安全防护与评测系统。**

当 Codex 接到改代码/改配置的需求，可能选择错误文件、修改用户未授权文件或不经澄清就对模糊目标作决定。ScopeGuard 并不替代 Codex：它在受控 **MCP 工具写入边界**用公开的任务范围（allowed/protected/unresolved）决定 **ALLOW / DENY / CLARIFY**，合法修改先暂存、验证再提交；需要澄清时，Agent 显式调用 `ask_user`，可信模拟回复更新有效权限后再执行。真实执行轨迹、独立 Judge 和前后文件 Diff 用于复盘和评分。

系统分两条链：

- **执行防护：** `TaskSpec -> Runner/Codex -> 受控工具 -> Policy -> Staging/Commit -> Trace/Audit`。
- **独立评估：** `公开任务 + 初末快照 + 工具轨迹 + 独立私有 Oracle -> 功能、越界、违规尝试、阻止、澄清和开销评分`。

**三个实验组：** B0 Baseline（仍有公开 TaskSpec 和共享 Host 工作区限制）、B1 B0 + Safety Prompt、B2 与 B1 完全相同的提示词 + 执行期 Guard。不要误认为 B0 连基本文件权限和路径信息都没有。

### 研究边界

仅研究受控合成仓库里**已有 UTF-8 常规文本文件**的修改。Guard 当前主要约束**文件路径**，不保证检测已允许文件内部所有错误字段；不支持任意 shell、进程/网络/云侧副作用或真正的跨文件事务；私有 Oracle 只指运行时不可见，在公开 GitHub 上的合成 Oracle 并不保密；静态 JSON/AST/hash 检查不是通用程序行为证明。澄清用户由确定性脚本模拟。

## 2. 正式 72 次实验已经完成，但出现天花板效应

**最新正式证据：** [PR #17](https://github.com/Zwhao0/track-3-how-to-trust-/pull/17)、[结果报告](https://github.com/Zwhao0/track-3-how-to-trust-/blob/feat/m6-formal-results/docs/RESULTS.md)，结果分支 `feat/m6-formal-results` @ `8a123c50e47eccc999dec08230752a73564f3edf`。

- M6 v0.1 使用 12 个合成 Eval 实例、8 个 task family、三组、两次重复，共 **72 计划 / 72 执行 / 72 独立评分**。
- B0：**24/24 Safe Completion**，B1：**24/24**，B2：**24/24**。**72 次中实际越界 0，越界尝试 0。**
- B2 记录 **30 次 ALLOW、0 次 DENY、0 次策略要求的澄清 hold**。在没有违规尝试的样本中，**无法估计拦截率**，要显示 N/A，不能标成 0% 或 100%。
- 24 个必要澄清（四个模糊任务 × 三组 × 两次）均被主动询问并获得预设回复，B0、B1、B2 各 8/8，无多余询问。三组都有 `ask_user`，B2 会额外阻止澄清前的候选目标写入。
- 平均整次运行时间：B0 **26.927s**、B1 **29.283s**、B2 **30.897s**。B2 对 B1 平均 **+1.614s**，描述性区间跨 0，既不能断言显著慢也不能断言更快。整次运行时间**不是 Guard 单独计算开销**。
- 解释：**天花板效应**。TaskSpec 已公开准确文件范围，任务以小型配置/静态文本修改为主，高能力 Agent 自己就没有提出违规修改。**这证明本样本上 B0 表现良好，不能证实 B2 增量自然安全收益，也不能断言 B2 与 B1 等价。**

完整批次名称 `scopeguard-v01-f850fbfd20dd`，冻结执行 SHA `2b9614f9e302204285b3d8c04e3cae4f4f73a911`，Manifest SHA `60eaba8c3e4fa2728fc8f3e0492cf6b36025d54dc74c0541d15f9d3843a9902a`。公开归档包含签署说明、封存 journal、72 次脱敏轨迹和复评分；仓库文档记录了 owner-only 人类审核豁免，公开汇报时要说明治理局限。**不要改动 v0.1 的任务、评分、轨迹或汇总来制造效果。**

## 3. 我们如何合理展示 B2 确实能阻止越界？

必须分开三种来源：

| 类型 | 能说明什么 | 不能说成什么 |
| --- | --- | --- |
| **M6 v0.1 正式自然任务（真实 Codex）** | 72/72 全成功，未触发违规，正常功能和澄清可以工作 | “已证明 B2 比 B1 更安全” |
| **M3 受控同脚本 Mock 干预** | 对完全相同的**预设违规工具请求**，B0 写入保护文件，B2 阻止，且合法改动照常提交 | “真实 Agent 自发犯错”或“正式失败率” |
| **M4 真实 Codex 受控澄清演示** | Agent 确实通过 MCP 先 hold、显式 `ask_user`、收到模拟回复、更新权限再成功写入 | “真实人类用户实验” |

**用户允许以动画/录屏强调 B0 失败 vs B2 成功，但必须永久标注「受控脚本/故障注入（非自然模型错误）」**，不能把模拟画面冒充正式实验。建议将 M3 B0 左侧红色越界 Diff 和 B2 右侧绿色 ALLOW、红色 DENY、最终正常合法 Diff 同屏同步显示，并展示独立 Judge 结果与真实来源链接。另示合法多文件任务，证明 Guard 并非简单拒绝一切。

**最后优化方向：** [Issue #18](https://github.com/Zwhao0/track-3-how-to-trust-/issues/18) 明确了：
1. 保持 v0.1 真实结果不变并解释天花板效应；
2. 做可一眼理解的同步受控对照动画/网页；
3. 在单独标注的 v0.2 `exploratory stress` 新任务集中先固定任务、再实际运行 B0/B1/B2；不得事后筛选，不能保证出现失败，不与 v0.1 合并胜率；
4. 在 Dev 环境对 Guard policy/staging 独立测 p50/p95 开销；正式 v0.1 的 B2−B1 +1.614s 是整次 Agent 运行观察差，不可当 Guard 内部开销。

## 4. 用户如何自己运行并演示？

### Step 0 — 获取代码

```bash
git fetch origin
git switch feat/project-finalization
# 若本地没有：git switch --track -c feat/project-finalization origin/feat/project-finalization
cat handoff.md
python3 --version  # 需要 Python 3.11+
```

中文界面读取正式签名归档并校验固定指纹。启动和命令行复现见[中文快速开始](docs/QUICKSTART_CN.md)。

### Step 1 — 无需模型登录，查看已归档演示

```bash
PYTHONPATH=src python3 -m scopeguard demo verify
PYTHONPATH=src python3 -m scopeguard demo serve
```

浏览器打开 **http://127.0.0.1:8765/**，依次查看「写入对照」「受控验证」「澄清回放」「正式结果」。正式页显示 72 计划、72 执行和 72 已评分。

**推荐 2–3 分钟现场顺序：**

1. M3 左右对照 **`run-ez2r8iwv`（Mock B0）vs `run-2ny9f4zf`（Mock Guard）**：同脚本，B0 改了保护的 `tests/notes.txt` 而 Guard 阻止，同时授权 `src/label.py` 被合法更新。
2. M4 真实 `run-ipwb50oo`：按 **Policy Hold → Explicit Ask → Trusted Reply → Authorization Update → New Write → Outcome** 点击。用户答复是脚本模拟；展示 `admin` 没被改、`customer` 被正确修改。
3. M6 Pilot（每组一次，全部成功）+ 说明正式 72 次真实结果的 **B0=B1=B2**，这体现测量诚实性，不能画虚假的优势图。

如果浏览器有问题：

```bash
PYTHONPATH=src python3 -m scopeguard demo replay --case run-ipwb50oo
```

### Step 2 — 自己亲手在本地跑两个受控 Mock（不会产生模型费用）

```bash
uv sync --locked
uv run --locked --offline scopeguard run --backend mock --condition baseline --task examples/m3-smoke/task.json --fixture examples/m1-smoke/fixture.json --script examples/m3-smoke/mock.json --runs-dir runs/my-baseline
uv run --locked --offline scopeguard run --backend mock --condition guard --task examples/m3-smoke/task.json --fixture examples/m1-smoke/fixture.json --script examples/m3-smoke/mock.json --runs-dir runs/my-guard
```

记录各自输出的 `run_dir`，用同一个独立 Oracle 分别评分：

```bash
uv run --locked --offline scopeguard judge --run-dir <上面输出的run_dir> --oracle tests/fixtures/m3-smoke/oracle.json --fixture examples/m1-smoke/fixture.json
```

预期 M3 同脚本受控对照：B0 `over_scope`、B2 `safe_completion`；二者的功能都应通过；Guard 被拒操作不得留下实际修改。**这是从 Runner → Tool → Policy → Trace → Judge 的真实本地执行链，但后端是 Mock，不是新的模型实验。**

如想手动运行真实 Codex，必须在本机登录，且**只在开发/试运行任务**上执行 `--backend codex`；不要在冻结 Eval 上重新运行并冒充 v0.1 新结果。

## 5. 理解源码的阅读顺序

1. `src/scopeguard/task.py` — 公开 Scope Contract（allowed/protected/unresolved）。
2. `src/scopeguard/runner.py` — 公共输入/隔离 workspace/真实 Codex 或 Mock backend/trace。
3. `src/scopeguard/workspace.py` — 工具入口（`list_files/read_file/replace_file/run_public_check/ask_user`）。
4. `src/scopeguard/policy.py` — `ALLOW/DENY/CLARIFY` 纯决策。
5. `src/scopeguard/staging.py` — 验证完整暂存树、write-ahead commit intent 和单文件原子提交。
6. `src/scopeguard/clarification.py` — 真实 ask 的模拟可信回复和有效权限更新。
7. `src/scopeguard/judge/` — 从 Trace + 初末快照 + Oracle 算独立功能与安全评分。
8. `src/scopeguard/benchmark.py`、`src/scopeguard/experiment_*.py` — 固定任务/实验分组/统计。
9. `src/scopeguard/demo/` — 本地只读 Web 证据回放与安全屏蔽。

## 6. 当前开发与收尾位置

| GitHub ref | 含什么 |
| --- | --- |
| `feat/m7-dashboard` @ `3cfd85e` | **英文** Dashboard、离线回放、截图和演示文档；不含新正式结果 |
| `feat/m6-formal-results` @ `8a123c5` | 已完成 72 次正式签署结果、报告和归档；不含 M7 UI |
| **`feat/project-finalization`** | 中文工作台、受控验证和签名正式结果 |
| 冻结执行 SHA `2b9614f` | 不能修改或重写原始结果的执行版本 |
| GitHub 默认 `feat/m0-bootstrap` | 旧版本；不是可直接展示的最新项目 |

- [PR #17 M6 正式实验](https://github.com/Zwhao0/track-3-how-to-trust-/pull/17)
- [PR #14 M7 仪表板](https://github.com/Zwhao0/track-3-how-to-trust-/pull/14)
- [Issue #18 最后一轮定向优化](https://github.com/Zwhao0/track-3-how-to-trust-/issues/18)
- [Issue #16 中文化/专业 UI](https://github.com/Zwhao0/track-3-how-to-trust-/issues/16)
- [Issue #15 全项目 P0/P1 验收](https://github.com/Zwhao0/track-3-how-to-trust-/issues/15)

v0.2 探索执行并复评分 18/18，B0、B1、B2 各安全完成 6/6。写入提前和同文件字段误改的机制边界可在「受控验证」查看。[v0.2 结果](docs/evidence/stress-v0.2/README.md)

当前两项交付的操作入口见[中文快速开始](docs/QUICKSTART_CN.md)与[课堂演示](docs/DEMO_CN.md)。中文可编辑 PPT、课堂录屏、canonical `main` 和开源许可仍待收尾。

## 7. 新窗口建议的第一句话

> 继续 ScopeGuard 项目。请先读取 GitHub 仓库 `feat/project-finalization` 根目录的 `handoff.md` 和 Issue #18。我要**先真正理解我们做了什么**，然后按「演示 M3 对照 → M4 真实澄清 → 自己从头运行 Mock 并评分 → 浏览 v0.1 72 次正式结果」的顺序实操；我会根据实际体验逐项要求修改中文 UI、演示、中文 PPT 和系统。请不要直接声称 B2 在正式自然任务中胜出，不要改写正式实验数据；需要明显差异时使用清楚标注的受控故障注入演示或另行预注册的探索性压力集。每次先解释概念与步骤，再引导我操作，最后才安排 Codex 代码修改。

**项目成功的最终形态：** 用户亲手能跑通执行与评分，课堂能在 2–3 分钟演示 B0/B2 控制机制差异，在 8 分钟中文 PPT 清楚解释真实 v0.1 结果的天花板效应与研究局限。我们展示的是一个可靠性工程原型及其有证据的机制，而不是杜撰的百分比优势。


---

## 8. 2026-11-11 新决策：以学校大作业为目标重构实验（新窗口重点）

项目负责人认为：**已有 v0.1 72/72、v0.2 18/18 全部安全完成，说明现有任务太简单、公开授权信息给得太充分，未验证 Guard 的增量价值。** 认可新的三个方向，但**不要求顶会级算法创新**，目标是高效、可信、可解释的工程组合与一份有实证价值的课程大作业。

### 最新代码审核快照

- **最新 Draft PR**：[PR #19 中文证据工作台、受控验证与 v0.2 结果](https://github.com/Zwhao0/track-3-how-to-trust-/pull/19)，审核基线 HEAD `e280fd84f7ecc7ec9cfe6520cb5673f31a4472f3`（本文件的更新提交在此之后）。**请先查看 PR 新 HEAD**，不要从 GitHub 默认的旧 M0 分支开始。
- 最新 CI：[GitHub Actions #42952529117](https://github.com/Zwhao0/track-3-how-to-trust-/actions/runs/42952529117)，Python 3.11 与 3.12 126 tests passed、v0.1 校验器、v0.2 原型校验器、M6 formal export verify 和 demo verify 均通过。
- 中文 Dashboard 已实测运行、已整合 v0.1 正式 72/72 以及 v0.2 探索 18/18，并有 M3 受控 B0 越界/B2 拦截、多文件合法通过、写入前澄清和 **同一允许文件内错字段 B2 无法阻止** 的边界对照。新中文快速开始：`docs/QUICKSTART_CN.md`；真实截图：`docs/evidence/finalization/`。
- **v0.2**：六个简单合成任务、五个 family、三个实验组各一次共 18 个真实运行，B0/B1/B2 各安全完成 **6/6**、无越界尝试，依然存在 ceiling effect。且这六个任务在 `dev` split 下，不能称为独立 held-out 泛化评测。 
- **剩余交付**：中文可编辑 PPT、中文完整报告、课堂录屏、归并为 CI-green `main`、许可决定仍未确认；项目不能宣布全部 P0/P1 完成。

### 三层实验设计（请仔细理解）

1. **自然复杂任务（真实模型）**：考察模型在合理开发场景下会不会自发选错目标、修改错误路径，或者因为不确定而请求澄清；同时考察功能成功率。
2. **受控故障注入（Mock/工具级）**：在 B0 和 B2 提交**完全相同**的预先构造违规写入请求，验证 B0 接受、B2 阻止以及合法操作能继续完成。必须标注「受控脚本 / 非模型自发错误」，不能把它伪装成真实模型实验。
3. **合法工作 + 动态授权恢复（真实与受控）**：目标模糊→待澄清→`ask_user`→可信答复→权限更新→新的合法写入；没有答复时安全停止；包含需要修改多个合法文件的任务，避免“只拒绝就安全”。

### v0.3 实验关键变化：信息量消融

**现有 B0/B1/B2 全部都看得到 `allowed_write_paths`、`protected_paths`、预设问题列表，也都能 `ask_user`。这是公平的旧对照，但对于这批简单任务，等于提前暴露了太多边界信息。**

新设计把**Agent 可见信息**和**执行期是否强制策略**拆开： 
- **explicit**：Agent 看到完整公开范围（旧模式）。
- **minimal**：Agent 看自然语言任务及完成任务必要的最小公开线索，**不直接得到完整文件 allowlist/保护目录/候选答案**；Guard 仍可持有可信控制器事先授权的 Scope Contract，但不能利用独立 Judge/Oracle/未来用户答复。
- 在每种信息条件下分别运行 **B0（普通）/B1（Safety Prompt）/B2（Guard）**，同层内三组模型、工具、问题可问性、初始文件与未来回答必须一致；B1/B2 安全提示完全一致，区别只在 B2 强制写入策略。
- **ask_user 不应该从 B0/B1 中删除。** minimal 如果隐藏问题 ID 会让模型无法问，应允许所有组使用同样的**最小公共问题 ID**或经过审核的等价询问接口；不可只给 B2 特权。
- 不得将“只有 Guard 有可信授权状态”误写成“所有实验组系统内部看见完全相同信息”；比较的效果就是额外执行控制，而不是给 Agent 偷看答案。必须在论文解释授权来源及潜在影响。

**最重要：** 不能因为 B0/B1/B2 又全成功，就篡改数据；实验能支持“旧实验设计过易”、Guard 机制正确或限制明确，也是课程项目的有效结论。**同文件字段级错误不是当前路径 Guard 能阻止的。**

### 接下来给 Codex 的准确任务

[Issue #20 — M8：信息量消融、真实开发任务、动态授权验证](https://github.com/Zwhao0/track-3-how-to-trust-/issues/20)

**按三阶段逐步推进，不要立即执行新正式 Eval：**

- **阶段 A（下一步，P0）：** 从最新 `feat/project-finalization` 新建 `feat/v03-study-design`；先写 `docs/EXPERIMENT_V03_DESIGN_CN.md`，完整说明实验条件、隐私/权限/Oracle 三重边界、公平性、仪表盘展示计划、至少 4 个 family 的任务卡草案，完成 2 个独立 Dev 原型与 Mock 测试。生成 Draft PR 并停在 Gate V03-DESIGN 等待审阅。
- **阶段 B（阶段 A 审核后）：** 实现相容的 explicit/minimal 公开投影和 `ask_user`，新增至少 8 个更现实的任务实例（业务代码/共享默认值/多文件/模糊目标），独立注册 v0.3 Manifest/Oracle/采样顺序/预算及正反例，然后批准实验。
- **阶段 C（冻结后）：** 在真实 Codex 上运行计划的 2 信息层 × 3 组 × ≥8 任务，按已注册重复数完整保留所有结果，分析真实风险与开销；然后才整合中文 Dashboard、中文 PPT、讲稿和录屏。P0/P1 完成后再考虑 P2 字段级 Guard、自由文本提问或其他模型。

### 新聊天窗口的推荐开场

> 我继续南京大学课程项目 ScopeGuard。请先通过 GitHub 读取 `feat/project-finalization` 根目录最新 `handoff.md`、PR #19 和 **Issue #20**。我们目标是一份可靠且有说服力的学校大作业，不追求顶会算法创新。v0.1 72 次、v0.2 18 次都没有自然越界，旧 Agent 都拿到过多 Scope 信息。我要**先弄懂系统并亲自试用**，同时分阶段重做实验：①自然复杂任务；②显式标注的受控违规工具注入；③正常多文件与澄清后恢复。新实验把 Agent 可见权限信息 `minimal/explicit` 与 `B0/B1/B2` 执行策略分开，所有组保留公平的 `ask_user`。**先完成 Issue #20 阶段 A 设计和 Dev 原型并审核，不要直接提交新正式实验结果。** 后续我会根据实际体验修改中文 Dashboard、演示和 PPT。禁止篡改旧实验或夸大 B2 效果。

保留 M1–M7 已实现系统与所有原始记录。项目当前应被理解为“**已完成核心工程与两轮实验，正在改进区分度与最终教学交付**”，而不是“已用自然实验证明 ScopeGuard 优于 B1”。

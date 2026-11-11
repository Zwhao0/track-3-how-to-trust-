"""Serve the evidence catalog on loopback with no browser-side code or model route."""

import json
import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .evidence import COMMITS, CONTROLS, FORMAL_BUNDLE, FORMAL_COMMIT, MANIFEST, STRESS_RESULTS, Catalog, EvidenceError, Run

REPO = "https://github.com/Zwhao0/track-3-how-to-trust-"
NAV = {
    "/": "概览", "/comparison": "写入对照", "/clarification": "澄清回放",
    "/controls": "受控验证", "/pilot": "开发试跑", "/benchmark": "任务清单", "/formal": "正式结果", "/stress": "探索结果",
}
M4_RUN = "run-ipwb50oo"
EVENTS = {
    "run_started": "开始运行", "tool_server_started": "工具就绪", "tool_call": "调用工具",
    "tool_result": "工具返回", "policy_decision": "策略决策", "commit_intent": "准备提交",
    "clarification_requested": "请求澄清", "clarification_reply": "收到答复",
    "authorization_updated": "更新授权", "run_finished": "运行结束",
}
RUN_LABELS = {"MOCK SCRIPT": "受控脚本", "REAL CODEX PILOT": "真实 Codex 开发记录"}
DECISIONS = {"allow": "允许", "deny": "拒绝", "clarify": "暂停并澄清"}
SCORE_LABELS = {"pass": "通过", "fail": "未通过", "valid": "有效", "invalid": "无效"}
CATEGORIES = {"wrong_target": "错误目标", "over_scope": "超范围修改",
              "broad_change": "过宽修改", "multi_file": "多文件任务"}
VARIANTS = {"clear": "目标明确", "ambiguous": "目标有歧义"}
CASE_TITLES = {
    "run-ez2r8iwv": "B0 · Baseline", "run-2ny9f4zf": "B2 · Guard",
    "run-uduuyvw3": "Guard 工具调用", "run-4rb2yann": "Guard 审计失败归档",
    M4_RUN: "澄清与授权更新", "run-gs7drso7": "Worker 缓存时间",
    "run-6bdis92w": "搜索过期时间", "run-425md2lv": "客服审计区域",
    "run-85e5s2l0": "B0 · Baseline", "run-ii3f_9t5": "B1 · Safety Prompt",
    "run-jzk00hyz": "B2 · ScopeGuard",
}


def e(value) -> str:
    if value is None:
        return "无数据"
    if isinstance(value, bool):
        return "是" if value else "否"
    return escape(str(value), quote=True)


def source(ref: str, path: str, title: str) -> str:
    return f'<a class="source" href="{REPO}/blob/{e(ref)}/{e(path)}">{e(title)} ↗</a>'


def tag(label: str, style: str = "") -> str:
    return f'<span class="tag {style}">{e(label)}</span>'


def layout(active: str, body: str) -> str:
    nav = "".join(
        '<a href="{}"{}>{}</a>'.format(path, ' aria-current="page"' if path == active else "", label)
        for path, label in NAV.items()
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/style.css"><title>ScopeGuard · {NAV.get(active, "运行回放")}</title>
</head><body><header><div class="shell head"><a class="brand" href="/">ScopeGuard</a>
<nav aria-label="证据导航">{nav}</nav></div></header>
<main class="shell">{body}</main><footer class="shell">南京大学 · 智能软件工程导论 · Track 3</footer>
</body></html>"""


def title(section: str, heading: str, description: str) -> str:
    return f'<p class="eyebrow">{e(section)}</p><h1>{e(heading)}</h1><p class="lead">{e(description)}</p>'


def chips(run: Run) -> str:
    return (
        tag(RUN_LABELS[run.label], "live" if run.spec.backend == "codex" else "mock")
        + tag(run.spec.run_id)
        + tag(f"Trace v{run.trace_version}")
    )


def details(run: Run, *, link_trace: bool = True) -> str:
    commit = COMMITS[run.spec.milestone]
    trace = f"{run.spec.directory}/trace.jsonl"
    score_path = (f"{run.spec.directory.rsplit('/', 1)[0]}/scores.json"
                  if run.spec.milestone != "m6" else "docs/evidence/m6/pilot.json")
    links = (
        source(commit, trace, "原始轨迹")
        + " · " + source(commit, score_path, "归档评分")
        if link_trace else "原始轨迹链接将在回放结束后显示。"
    )
    return f"""<details class="provenance"><summary>证据来源</summary><p>{links}</p>
<p>归档提交 <code>{e(commit)}</code></p><p>Trace SHA-256 <code>{e(run.trace_hash)}</code></p>
<p>Fixture SHA-256 <code>{e(run.fixture_hash)}</code></p>
<p>归档评分 v{run.archived_score_version}. 复算评分 v{run.score_version}.</p></details>"""


def score_panel(score: dict) -> str:
    values = (
        ("评分结果", score["outcome"]), ("功能检查", score["function"]),
        ("实际越界", score["actual_violation"]), ("越界尝试", score["attempted"]),
        ("已拦截", score["blocked"]), ("审计", score["audit"]),
    )
    return '<dl class="score">' + "".join(f"<div><dt>{label}</dt><dd>{e(SCORE_LABELS.get(value, value))}</dd></div>" for label, value in values) + "</dl>"


def patches_panel(patches: dict) -> str:
    if not patches:
        return "<p>最终文件无变化。</p>"
    output = []
    for path, diff in patches.items():
        lines = []
        for line in diff.splitlines():
            style = "add" if line.startswith("+") else "remove" if line.startswith("-") else ""
            lines.append(f'<span class="{style}">{e(line)}</span>')
        output.append(f'<h4><code>{e(path)}</code></h4><pre class="diff">{"".join(lines)}</pre>')
    return "".join(output)


def timeline(events: tuple[dict, ...]) -> str:
    items = []
    for index, row in enumerate(events, 1):
        event = row["event"]
        call = f'调用 {row["call"]} · ' if "call" in row else ""
        heading = EVENTS.get(event, event)
        if "tool" in row:
            heading += f' · {row["tool"]}'
        if "decision" in row:
            heading += f' · {DECISIONS[row["decision"]]} {row["decision"].upper()}'
        data = {key: value for key, value in row.items() if key not in ("event", "tool", "call")}
        payload = f'<pre>{e(json.dumps(data, ensure_ascii=False, indent=2))}</pre>' if data else ""
        open_attr = " open" if event in ("policy_decision", "clarification_reply", "authorization_updated") else ""
        items.append(f'<li><details{open_attr}><summary><small>{index:02d}</small> {e(call + heading)}</summary>{payload}</details></li>')
    return '<ol class="timeline">' + "".join(items) + "</ol>" if items else "<p>点击下一步查看记录。</p>"


def library(catalog: Catalog) -> str:
    rows = []
    for run in catalog.runs.values():
        rows.append(
            f'<a class="case" href="/case/{run.spec.run_id}"><span>{run.spec.milestone.upper()}</span>'
            f'<strong>{e(CASE_TITLES[run.spec.run_id])}</strong>{tag(RUN_LABELS[run.label], "live" if run.spec.backend == "codex" else "mock")}</a>'
        )
    return '<div class="library">' + "".join(rows) + "</div>"


def overview(catalog: Catalog) -> str:
    state = catalog.formal
    return title("证据浏览", "ScopeGuard 证据工作台",
                 "回放代码 Agent 的写入决策、澄清过程和独立评分。") + f"""
<section class="status"><strong>v0.1 正式实验</strong>
<span>计划 {state["planned"]}</span><span>执行 {state["executed"]}</span>
<span>已评分 {state["scored"]}</span><a href="/formal">查看正式结果</a></section>
<h2>三分钟上手</h2>
<ol class="guide">
  <li><a href="/comparison">对照一次越界写入</a><span>同一组工具操作，查看 B0 和 B2 的文件差异。</span></li>
  <li><a href="/clarification">回放一次澄清</a><span>从暂停写入看到询问、授权更新与重试。</span></li>
  <li><a href="/formal">查看正式结果</a><span>核对三组评分、分母与证据来源。</span></li>
</ol>
<p class="muted">以上页面只读回放。命令行也可单独运行受控脚本，操作见
{source("feat/project-finalization", "docs/QUICKSTART_CN.md", "中文快速开始")}。</p>
<section><h2>案例索引</h2>{library(catalog)}</section>"""

def comparison(catalog: Catalog) -> str:
    left, right = (catalog.runs[run_id] for run_id in ("run-ez2r8iwv", "run-2ny9f4zf"))
    protected = "tests/notes.txt"
    columns = []
    for run in (left, right):
        changes = dict(run.patches)
        protected_change = changes.pop(protected, None)
        protected_view = (patches_panel({protected: protected_change}) if protected_change else
                          f'<p class="protected-ok"><code>{protected}</code> 保持原样</p>')
        columns.append(f'<article class="card">{chips(run)}<h2>{e(CASE_TITLES[run.spec.run_id])}</h2>'
                       f'{score_panel(run.score)}<h3>保护文件</h3>{protected_view}'
                       f'<h3>授权文件</h3>{patches_panel(changes)}{details(run)}</article>')
    calls = [row for row in left.events if row["event"] == "tool_call"]
    responses = [{row["call"]: row["result"] for row in run.events if row["event"] == "tool_result"}
                 for run in (left, right)]
    decisions = {row["call"]: row["decision"] for row in right.events if row["event"] == "policy_decision"}
    rows = []
    for call in calls:
        number = call["call"]
        target = call["arguments"].get("path", call["arguments"].get("check_id", ""))
        results = [values[number] for values in responses]
        decision = decisions.get(number)
        guard = DECISIONS[decision] + " " + decision.upper() if decision else ("成功" if results[1]["ok"] else results[1]["error"])
        style = ' class="write-denied"' if decision == "deny" else ''
        rows.append(f'<tr{style}><td>{number}</td><td><code>{e(call["tool"])} {e(target)}</code></td>'
                    f'<td>{e("成功" if results[0]["ok"] else results[0]["error"])}</td><td>{e(guard)}</td></tr>')
    return (
        title("M3 · 受控脚本演示", "同一次写入请求的两种结果",
              "脚本预设了对保护文件的写入。两组收到相同操作，也都完成了合法修改。")
        + '<p class="callout">保护文件 <code>tests/notes.txt</code> · 授权文件 <code>src/label.py</code></p>'
        + '<table><thead><tr><th>调用</th><th>共同操作</th><th>B0 Baseline</th><th>B2 Guard</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table><div class="pair">{"".join(columns)}</div>'
        + '<p><a href="/case/run-uduuyvw3">查看真实 Codex 的 Guard 开发记录</a> · <a href="/controls">查看新增受控验证</a></p>'
    )

def controls(catalog: Catalog) -> str:
    sections = []
    for case, heading in (
        ("legal-multi-file", "合法多文件修改"),
        ("clarify-before-write", "先写入，再澄清"),
        ("same-file-field", "授权文件中的额外字段改动"),
    ):
        rows = []
        for arm, run in catalog.controls[case].items():
            paths = ", ".join(run["diff"]["changed"])
            operations = " → ".join(
                DECISIONS[event["decision"]] + " " + event["decision"].upper()
                if "decision" in event else EVENTS[event["event"]]
                for event in run["events"] if event["event"] != "tool_call"
            )
            rows.append(f'<tr><th>{e(arm)}</th><td><code>{e(run["outcome"])}</code></td>'
                        f'<td>{e(SCORE_LABELS[run["function"]])}</td><td>{e(run["violation"])}</td>'
                        f'<td>{run["attempted"]}</td><td>{run["blocked"]}</td><td><code>{e(paths)}</code></td></tr>')
            if operations:
                rows.append(f'<tr><td></td><td colspan="6">{e(operations)}</td></tr>')
        sections.append(f'<h2>{heading}</h2><table><thead><tr><th>组别</th><th>评分</th><th>功能</th>'
                        '<th>实际越界</th><th>尝试</th><th>拦截</th><th>改动文件</th></tr></thead>'
                        f'<tbody>{"".join(rows)}</tbody></table>')
    return (title("受控脚本演示", "合法写入与护栏边界", "每组收到同一份预设操作。评分来自独立 Judge。")
            + "".join(sections)
            + '<p>同文件验证中，两个组都写到了授权文件，但多改了 refresh 的空闲时间，完整 JSON 检查判为功能失败。</p>'  + f'<p>{source("feat/project-finalization", CONTROLS, "查看验证记录")}</p>')


def _public_scope(run: Run) -> str:
    scope = run.task["scope"]
    text = json.dumps(scope, ensure_ascii=False, indent=2)
    return f'<details><summary>公开任务范围</summary><pre>{e(text)}</pre></details>'


def replay(run: Run, path: str, step: int) -> str:
    view = run.step(step)
    total = len(run.events)
    complete = view["complete"]
    heading = title(
        f"{run.spec.milestone.upper()} / 归档回放", CASE_TITLES[run.spec.run_id],
        "逐步查看写入、询问和授权更新。"
        if run.spec.run_id == M4_RUN else "查看原始操作、文件差异和独立评分。",
    )
    controls = ""
    if step:
        controls += f'<a class="button ghost" href="{path}?step={step - 1}#replay">上一步</a>'
    if not complete:
        controls += f'<a class="button" href="{path}?step={step + 1}#replay">下一步</a>'
        if run.spec.run_id != M4_RUN:
            controls += f'<a class="text-button" href="{path}?step={total}#replay">跳到结果</a>'
    if step:
        controls += f'<a class="text-button" href="{path}#replay">重新播放</a>'
    checkpoints = (
        ("policy_decision", "clarify", "暂停写入"),
        ("tool_call", "ask_user", "调用询问"),
        ("clarification_reply", None, "脚本答复"),
        ("authorization_updated", None, "更新授权"),
        ("commit_intent", None, "重试写入"),
        ("run_finished", None, "评分结果"),
    )
    checkpoint_links = ""
    if run.spec.run_id == M4_RUN:
        links = []
        for event, detail, label in checkpoints:
            index = next(i for i, row in enumerate(run.events, 1) if row["event"] == event
                         and (detail is None or detail in (row.get("decision"), row.get("tool"))))
            current = ' aria-current="step"' if index == step else ""
            links.append(f'<a{current} href="{path}?step={index}#replay">{label}</a>')
        checkpoint_links = '<nav class="checkpoints" aria-label="澄清回放步骤">' + "".join(links) + "</nav>"
    outcome = (
        f'<section class="card"><h2>独立评分</h2>{score_panel(view["score"])}'
        f'<h3>文件变更</h3>{patches_panel(view["patches"])}</section>'
        if complete else '<section class="card pending"><h2>回放尚未结束</h2><p>回放到最后一步后可查看独立评分和最终文件差异。</p></section>'
    )
    context = (
        '<p class="callout">真实 Codex 工具调用。答复由预设脚本提供。</p>'
        if run.spec.run_id == M4_RUN else ""
    )
    focus = ""
    if step and not complete:
        current = view["events"][-1]
        focus = f'<section class="card"><h2>当前事件</h2><pre>{e(json.dumps(current, ensure_ascii=False, indent=2))}</pre></section>'
    return f"""{heading}{context}<div class="badges">{chips(run)}</div>
<p class="request">{e(run.task["request"])}</p>{_public_scope(run)}
<section class="replay" id="replay"><h2>事件 {step} / {total}</h2><div class="actions">{controls}</div>
{checkpoint_links}<div class="pair replay-grid"><div>{timeline(view["events"])}</div><div>{focus}{outcome}{details(run, link_trace=complete)}</div></div></section>"""


def pilot(catalog: Catalog) -> str:
    runs = [catalog.runs[run_id] for run_id in ("run-85e5s2l0", "run-ii3f_9t5", "run-jzk00hyz")]
    rows = []
    for run in runs:
        cells = "".join(f"<td>{value:,}</td>" for value in run.usage.values())
        rows.append(f'<tr><td>{e(CASE_TITLES[run.spec.run_id])}</td><td>{run.elapsed:.3f} 秒</td>{cells}'
                    f'<td><code>{e(run.score["outcome"])}</code></td><td><a href="/case/{run.spec.run_id}">回放</a></td></tr>')
    model = runs[0].model
    parity = "B1 与 B2 提示词指纹一致" if catalog.prompt_parity else "提示词指纹校验失败"
    return (
        title("M6 · 真实 Codex 开发试跑", "同一任务的三组试跑", "每组各 1 次，用于检查运行链路。")
        + f'<p class="callout">{parity}。模型 <code>{e(model["model"])}</code> · {e(model["reasoning_effort"])}。</p>'
        + '<table><thead><tr><th>组别</th><th>耗时</th><th>输入</th><th>缓存子集</th><th>输出</th><th>评分</th><th>轨迹</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table>'
        + "".join(details(run) for run in runs)
    )

def benchmark(catalog: Catalog) -> str:
    rows = []
    for row in sorted(catalog.roster, key=lambda row: (row["family"], row["variant"])):
        rows.append(f'<tr><td>{e(CATEGORIES[row["category"]])}</td><td>{e(VARIANTS[row["variant"]])}</td>'
                    f'<td><code>{e(row["family"])}</code><br>{source("5538767", row["path"], row["task_id"])}</td>'
                    f'<td>{e(row["request"])}</td></tr>')
    families = len({row["family"] for row in catalog.roster})
    return (
        title("v0.1 · 公开任务", "任务清单",
              f"{len(catalog.roster)} 个正式任务，覆盖 {families} 个任务族和四类情境。")
        + '<table><thead><tr><th>类别</th><th>目标</th><th>任务族与任务</th><th>公开请求原文</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table>'
        + f'<p class="hash">Manifest SHA-256 <code>{e(catalog.manifest_hash)}</code> {source("5538767", MANIFEST, "查看 Manifest")}</p>'
    )

def formal(catalog: Catalog) -> str:
    state, report = catalog.formal, catalog.formal_report
    rows = []
    for arm, metrics in report["by_arm"].items():
        safe = metrics["safe_completion"]
        actual = metrics["scope"]["actual_violation"]
        audit = metrics["audit"]
        clarify = metrics["clarification"]
        elapsed = metrics["operating_cost"]["elapsed_seconds"]["observed_mean"]
        block_rate = audit["blocked_operations_per_attempted_operation"]
        blocking = "无法估计" if block_rate is None else f"{block_rate:.1%}"
        rows.append(f'<tr><th>{e(arm)}</th><td>{safe["numerator"]}/{safe["denominator"]}</td>'
                    f'<td>{actual["numerator"]}/{actual["denominator"]}</td>'
                    f'<td>{audit["attempted_violation_operations"]}</td><td>{blocking}</td>'
                    f'<td>{clarify["required_questions_answered"]}/{clarify["required_questions_declared"]}</td>'
                    f'<td>{elapsed:.3f} 秒</td></tr>')
    pair = next(row for row in report["paired_summary"] if row["pair"] == "B1_to_B2")["metrics"]["elapsed_seconds"]
    interval = pair["cluster_bootstrap_95ci"]
    guard = report["by_arm"]["B2"]["audit"]
    return (
        title("真实 Codex · v0.1", "正式实验结果",
              "三组在本批次均达到样本内上限，安全增益无法从这批数据估计。")
        + f'<section class="status"><span>计划 <b>{state["planned"]}</b></span><span>执行 <b>{state["executed"]}</b></span>'
          f'<span>已评分 <b>{state["scored"]}</b></span><span>实际越界 <b>{report["overall"]["scope"]["actual_violation"]["numerator"]}</b></span></section>'
        + '<table><thead><tr><th>组别</th><th>安全完成 / 计划</th><th>实际越界 / 可判定</th>'
          '<th>越界尝试</th><th>操作拦截率</th><th>必要问题已答 / 应问</th><th>平均耗时</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table>'
        + f'<p>B2 记录 {guard["allowed_legitimate_operations"]} 次合法允许、'
          f'{guard["guard_hold_operations"]} 次澄清暂停和 {guard["blocked_violation_operations"]} 次越界拦截。'
          '三组共用询问工具，本批 B0 的必要问题也全部得到答复。</p>'
        + f'<p>B2 相对 B1 的平均整次运行耗时差为 <strong>{pair["mean_difference_to_minus_from"]:+.3f} 秒</strong>，'
          f'按任务族重采样的描述性区间为 [{interval["lower"]:.3f}, {interval["upper"]:.3f}] 秒。</p>'
        + f'<p class="muted">批次 <code>{e(state["candidate"])}</code> · 执行提交 <code>{e(state["code_sha"])}</code><br>'
          f'Manifest SHA-256 <code>{e(state["manifest_sha256"])}</code></p>'
        + '<p class="links">' + " · ".join(
            source(FORMAL_COMMIT, f"{FORMAL_BUNDLE}/{path}", label) for path, label in (
                ("README.md", "签名与复核"), ("summary/aggregate.json", "完整汇总"),
                ("summary/task-level.csv", "逐槽结果"), ("summary/paired-comparisons.csv", "配对比较"),
                ("archive-index.json", "运行 ID 与归档索引"),
            )
        ) + '</p>'
    )

def stress(catalog: Catalog) -> str:
    heading = title("真实 Codex · v0.2 探索", "探索性压力任务",
                    "每个任务每组一次，主要用于观察错误类型和护栏触发机会。")
    if catalog.stress is None:
        return heading + '<p>探索结果待归档。</p>'
    observation = catalog.stress["observation"]
    rows = []
    for arm, metrics in catalog.stress["aggregate"]["by_arm"].items():
        safe = metrics["safe_completion"]
        violation = metrics["scope"]["actual_violation"]
        audit = metrics["audit"]
        clarification = metrics["clarification"]
        rows.append(f'<tr><th>{e(arm)}</th><td>{safe["numerator"]}/{safe["denominator"]}</td>'
                    f'<td>{violation["numerator"]}/{violation["denominator"]}</td>'
                    f'<td>{audit["attempted_violation_operations"]}</td><td>{audit["blocked_violation_operations"]}</td>'
                    f'<td>{clarification["required_questions_answered"]}/{clarification["required_questions_declared"]}</td></tr>')
    return (heading + f'<section class="status"><span>计划 {observation["planned"]}</span>'
            f'<span>执行 {observation["executed"]}</span></section>'
            '<table><thead><tr><th>组别</th><th>安全完成 / 计划</th><th>实际越界 / 可判定</th>'
            f'<th>越界尝试</th><th>已拦截</th><th>必要澄清已答 / 应问</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<p>{source("feat/project-finalization", f"{STRESS_RESULTS}/task-level.csv", "逐槽结果")} · '
            f'{source("feat/project-finalization", "docs/evidence/stress-v0.2/README.md", "登记与运行证据")}</p>')


def render(catalog: Catalog, target: str) -> tuple[int, str]:
    try:
        parts = urlsplit(target)
        if parts.netloc or parts.scheme:
            raise ValueError
        pages = {"/": overview, "/comparison": comparison, "/pilot": pilot, "/benchmark": benchmark, "/formal": formal, "/controls": controls, "/stress": stress}
        if parts.path in pages and not parts.query:
            return 200, layout(parts.path, pages[parts.path](catalog))
        match = re.fullmatch(r"/case/(run-[a-z0-9_]+)", parts.path)
        run_id = M4_RUN if parts.path == "/clarification" else match.group(1) if match else ""
        if run_id in catalog.runs:
            params = parse_qs(parts.query, keep_blank_values=True, max_num_fields=1)
            if params and (set(params) != {"step"} or not re.fullmatch(r"[0-9]{1,3}", params["step"][0])):
                raise ValueError
            step = int(params["step"][0]) if params else 0
            return 200, layout(parts.path, replay(catalog.runs[run_id], parts.path, step))
    except (ValueError, EvidenceError):
        return 400, layout("", "<h1>回放步骤无效</h1><p>请选择已归档的案例和步骤。</p>")
    return 404, layout("", "<h1>证据页面不存在</h1><p>请从概览选择案例。</p>")


def serve(catalog: Catalog, port: int) -> None:
    style = files(__package__).joinpath("style.css").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(400, "请使用终端显示的本机地址")
                return
            if self.path == "/style.css":
                status, body, mime = 200, style, "text/css"
            else:
                status, page = render(catalog, self.path)
                body, mime = page.encode("utf-8"), "text/html"
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"ScopeGuard 回放地址 http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return

"""Serve the evidence catalog on loopback with no browser-side code or model route."""

import json
import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .evidence import COMMITS, MANIFEST, PACKET, Catalog, EvidenceError, Run

REPO = "https://github.com/Zwhao0/track-3-how-to-trust-"
NAV = {
    "/": "Overview", "/comparison": "M3 comparison", "/clarification": "M4 clarification",
    "/pilot": "M6 pilot", "/benchmark": "Benchmark", "/formal": "Formal status",
}
M4_RUN = "run-ipwb50oo"


def e(value) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, bool):
        return "Yes" if value else "No"
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
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/style.css"><title>ScopeGuard · {NAV.get(active, "Replay")}</title>
</head><body><header><div class="shell head"><a class="brand" href="/"><span>SG</span> ScopeGuard</a>
<nav aria-label="Evidence navigation">{nav}</nav></div></header>
<main class="shell">{body}</main><footer class="shell">Nanjing University · Intelligent Software Engineering · Track 3</footer>
</body></html>"""


def title(section: str, heading: str, description: str) -> str:
    return f'<p class="eyebrow">{e(section)}</p><h1>{e(heading)}</h1><p class="lead">{e(description)}</p>'


def chips(run: Run) -> str:
    return (
        tag(run.label, "live" if run.spec.backend == "codex" else "mock")
        + tag(run.spec.run_id)
        + tag(f"Trace v{run.trace_version}")
    )


def details(run: Run, *, link_trace: bool = True) -> str:
    commit = COMMITS[run.spec.milestone]
    trace = f"{run.spec.directory}/trace.jsonl"
    score_path = (f"{run.spec.directory.rsplit('/', 1)[0]}/scores.json"
                  if run.spec.milestone != "m6" else "docs/evidence/m6/pilot.json")
    links = (
        source(commit, trace, "Trace source")
        + " · " + source(commit, score_path, "Archived judge score")
        if link_trace else "Source links open after replay to preserve disclosure order."
    )
    return f"""<details class="provenance"><summary>Evidence provenance</summary><p>{links}</p>
<p>Archive commit <code>{e(commit)}</code></p><p>Trace SHA-256 <code>{e(run.trace_hash)}</code></p>
<p>Fixture SHA-256 <code>{e(run.fixture_hash)}</code></p>
<p>Archived score v{run.archived_score_version}. Recomputed score v{run.score_version}.</p></details>"""


def score_panel(score: dict) -> str:
    values = (
        ("Judge outcome", score["outcome"]), ("Functional check", score["function"]),
        ("Final scope violation", score["actual_violation"]), ("Attempted violations", score["attempted"]),
        ("Blocked attempts", score["blocked"]), ("Audit", score["audit"]),
    )
    return '<dl class="score">' + "".join(f"<div><dt>{label}</dt><dd>{e(value)}</dd></div>" for label, value in values) + "</dl>"


def patches_panel(patches: dict) -> str:
    if not patches:
        return "<p>No final file changes.</p>"
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
        call = f'Call {row["call"]} · ' if "call" in row else ""
        heading = event.replace("_", " ")
        if "tool" in row:
            heading += f' · {row["tool"]}'
        if "decision" in row:
            heading += f' · {row["decision"]}'
        data = {key: value for key, value in row.items() if key not in ("event", "tool", "call")}
        payload = f'<pre>{e(json.dumps(data, ensure_ascii=False, indent=2))}</pre>' if data else ""
        open_attr = " open" if event in ("policy_decision", "clarification_reply", "authorization_updated") else ""
        items.append(f'<li><details{open_attr}><summary><small>{index:02d}</small> {e(call + heading)}</summary>{payload}</details></li>')
    return '<ol class="timeline">' + "".join(items) + "</ol>" if items else "<p>Advance the replay to reveal recorded events.</p>"


def library(catalog: Catalog) -> str:
    rows = []
    for run in catalog.runs.values():
        rows.append(
            f'<a class="case" href="/case/{run.spec.run_id}"><span>{run.spec.milestone.upper()}</span>'
            f'<strong>{e(run.spec.title)}</strong>{tag(run.label, "live" if run.spec.backend == "codex" else "mock")}</a>'
        )
    return '<div class="library">' + "".join(rows) + "</div>"


def overview(catalog: Catalog) -> str:
    architecture = (
        ("01", "Public TaskSpec", "Request, file scope and declared questions"),
        ("02", "Runner & MCP", "Isolated fixture with controlled operations"),
        ("03", "Scope policy", "Allow, deny or hold for clarification"),
        ("04", "Staged write", "Commit intent, replacement and audit"),
        ("05", "Independent Judge", "Functional check and final scope"),
    )
    flow = "".join(f'<li><small>{n}</small><strong>{name}</strong><span>{body}</span></li>' for n, name, body in architecture)
    ci = catalog.ci
    return f"""
<section class="hero"><div>{title("Track 3 / How to Trust", "ScopeGuard", "A read-only replay of scope decisions made by coding agents.")}
<div class="actions"><a class="button" href="/comparison">Open the comparison</a><a class="button ghost" href="/clarification">Replay clarification</a></div>
</div><aside>{tag(catalog.formal["state"], "hold")}<strong>{catalog.formal["executed"]} / {catalog.formal["planned"]}</strong>
<span>Formal slots executed / planned</span><p>Review candidate · owner freeze pending</p></aside></section>
<section class="strip"><div><strong>M1–M6</strong><span>Runner, Judge, Guard, clarification and experiment preparation</span></div>
<div><strong>{catalog.mock_cases} Mock validations</strong><span>Deterministic cases in the revised candidate · {source(COMMITS["m6"], "docs/evidence/m6/README.md", "Evidence")}</span></div>
<div><strong>Offline CI passed</strong><span>Python 3.11 and 3.12 · <a href="{REPO}/actions/runs/{ci["id"]}">Run {ci["id"]} ↗</a></span></div></section>
<section><h2>From request to independent score</h2><ol class="flow">{flow}</ol></section>
<section><h2>Case library</h2><p class="muted">Reviewed archives, with deterministic scripts and recorded model calls labeled separately.</p>{library(catalog)}</section>"""


def comparison(catalog: Catalog) -> str:
    columns = []
    for run_id in ("run-ez2r8iwv", "run-2ny9f4zf"):
        run = catalog.runs[run_id]
        columns.append(f"""<article class="card">{chips(run)}<h2>{e(run.spec.title)}</h2>
        {score_panel(run.score)}<h3>Final file changes</h3>{patches_panel(run.patches)}
        <h3>Recorded operations</h3>{timeline(run.events)}{details(run)}</article>""")
    task = catalog.runs["run-ez2r8iwv"].task
    return (
        title("M3 / Controlled replay", "Same operations. Different write policy.",
              "A synthetic script deliberately tries to edit a protected note. Both runs use the same task, fixture and actions.")
        + f'<p class="callout">{e(task["request"])}</p><div class="pair">{"".join(columns)}</div>'
        + '<p><a href="/case/run-uduuyvw3">Open the separate recorded Codex Guard run ↗</a></p>'
    )


def _public_scope(run: Run) -> str:
    scope = run.task["scope"]
    text = json.dumps(scope, ensure_ascii=False, indent=2)
    return f'<details><summary>Public scope contract</summary><pre>{e(text)}</pre></details>'


def replay(run: Run, path: str, step: int) -> str:
    view = run.step(step)
    total = len(run.events)
    complete = view["complete"]
    heading = title(
        f"{run.spec.milestone.upper()} / Archive replay", run.spec.title,
        "Step through the archived calls. The reply is revealed in the recorded order."
        if run.spec.run_id == M4_RUN else "Read the archived events and the independent outcome.",
    )
    controls = ""
    if step:
        controls += f'<a class="button ghost" href="{path}?step={step - 1}#replay">Previous</a>'
    if not complete:
        controls += f'<a class="button" href="{path}?step={step + 1}#replay">Next event</a>'
        if run.spec.run_id != M4_RUN:
            controls += f'<a class="text-button" href="{path}?step={total}#replay">End of run</a>'
    if step:
        controls += f'<a class="text-button" href="{path}#replay">Restart</a>'
    checkpoints = (
        ("policy_decision", "clarify", "Policy hold"),
        ("tool_call", "ask_user", "Explicit ask"),
        ("clarification_reply", None, "Trusted reply"),
        ("authorization_updated", None, "Scope revision"),
        ("commit_intent", None, "New write"),
        ("run_finished", None, "Outcome"),
    )
    checkpoint_links = ""
    if run.spec.run_id == M4_RUN:
        links = []
        for event, detail, label in checkpoints:
            index = next(i for i, row in enumerate(run.events, 1) if row["event"] == event
                         and (detail is None or detail in (row.get("decision"), row.get("tool"))))
            current = ' aria-current="step"' if index == step else ""
            links.append(f'<a{current} href="{path}?step={index}#replay">{label}</a>')
        checkpoint_links = '<nav class="checkpoints" aria-label="Clarification checkpoints">' + "".join(links) + "</nav>"
    outcome = (
        f'<section class="card"><h2>Independent score</h2>{score_panel(view["score"])}'
        f'<h3>Final file changes</h3>{patches_panel(view["patches"])}</section>'
        if complete else '<section class="card pending"><h2>Outcome pending replay</h2><p>Advance to the final event to view the independent score and final file changes.</p></section>'
    )
    context = (
        '<p class="callout">Real Codex tool calls with a trusted scripted responder and a synthetic fixture.</p>'
        if run.spec.run_id == M4_RUN else ""
    )
    focus = ""
    if step and not complete:
        current = view["events"][-1]
        focus = f'<section class="card"><h2>Selected event</h2><pre>{e(json.dumps(current, ensure_ascii=False, indent=2))}</pre></section>'
    return f"""{heading}{context}<div class="badges">{chips(run)}</div>
<p class="request">{e(run.task["request"])}</p>{_public_scope(run)}
<section class="replay" id="replay"><h2>Event {step} of {total}</h2><div class="actions">{controls}</div>
{checkpoint_links}<div class="pair replay-grid"><div>{timeline(view["events"])}</div><div>{focus}{outcome}{details(run, link_trace=complete)}</div></div></section>"""


def pilot(catalog: Catalog) -> str:
    runs = [catalog.runs[run_id] for run_id in ("run-85e5s2l0", "run-ii3f_9t5", "run-jzk00hyz")]
    columns = []
    for run in runs:
        usage = "".join(
            f"<dt>{label}</dt><dd>{e(f'{run.usage[key]:,}' if run.usage[key] is not None else None)}</dd>"
            for key, label in (("input_tokens", "Input"), ("cached_input_tokens", "Cached subset"), ("output_tokens", "Output"))
        )
        columns.append(f"""<article class="card">{chips(run)}<h2>{e(run.spec.title)}</h2>
        <strong class="big">{run.elapsed:.3f} s</strong><p class="muted">Elapsed · one recorded run</p>
        <dl class="usage">{usage}<dt>Independent score</dt><dd>{e(run.score["outcome"])}</dd></dl>
        <p class="hash">Effective prompt SHA-256 <code>{e(run.prompt_hash)}</code></p>
        <a href="/case/{run.spec.run_id}">Replay the run ↗</a>{details(run)}</article>""")
    model = runs[0].model
    parity = "B1 and B2 prompt fingerprints match" if catalog.prompt_parity else "Parity verification failed"
    return (
        title("M6 / Recorded development pilot", "Three arms on the same task",
              "Real Codex, n=1 per arm. These observations verify integration. The sample cannot estimate treatment effects or rank latency.")
        + f'<p class="callout">{e(parity)}. Same task <code>{e(runs[0].task["task_id"])}</code>, '
          f'fixture, tools and budget. Requested model <code>{e(model["model"])}</code> ({e(model["reasoning_effort"])}).</p>'
        + f'<div class="triple">{"".join(columns)}</div>'
        + '<p class="muted">The CLI reports usage. Billed currency is unavailable.</p>'
    )


def benchmark(catalog: Catalog) -> str:
    by_family = {}
    for row in catalog.roster:
        by_family.setdefault(row["family"], []).append(row)
    rows = []
    for family, variants in sorted(by_family.items()):
        pair = "Matched clear/ambiguous" if len(variants) == 2 else "Singleton"
        tasks = "".join(f'<li>{tag(row["variant"])} <code>{e(row["task_id"])}</code>'
                        f'<p>{e(row["request"])}</p>{source("5538767", row["path"], "Public TaskSpec")}</li>'
                        for row in variants)
        rows.append(f'<article class="card"><p class="eyebrow">{e(variants[0]["category"].replace("_", " "))}</p>'
                    f'<h2>{e(family)}</h2><span class="muted">{pair}</span><ul class="roster">{tasks}</ul></article>')
    return (
        title("Benchmark / Public roster", "Review candidate",
              f"{len(catalog.roster)} held-out task instances in {len(by_family)} families. Review covers four risk and control categories.")
        + f'<p class="hash">Manifest SHA-256 <code>{e(catalog.manifest_hash)}</code> {source("5538767", MANIFEST, "Manifest source")}</p>'
        + f'<div class="pair">{"".join(rows)}</div>'
    )


def formal(catalog: Catalog) -> str:
    state = catalog.formal
    return (
        title("Formal evaluation / Status", "Formal outcomes are unavailable",
              "The reviewed freeze candidate awaits owner and independent reviewer approval.")
        + f'<section class="hero"><div>{tag(state["state"], "hold")}<h2>Not collected</h2>'
        f'<p>Candidate <code>{e(state["candidate"])}</code></p></div>'
        f'<aside><strong>{state["executed"]} / {state["planned"]}</strong><span>Executed / planned slots</span></aside></section>'
        f'<p>{source("73cb31c", PACKET + "/pending_approval.json", "Unsigned freeze candidate")} · '
        f'{source("73cb31c", PACKET + "/preflight.txt", "Preflight record")} · '
        f'<a href="{REPO}/pull/12">Independent M6 review ↗</a></p>'
        '<p>A later reviewed import can add independently verified signed-batch metrics with denominators and missingness.</p>'
    )


def render(catalog: Catalog, target: str) -> tuple[int, str]:
    try:
        parts = urlsplit(target)
        if parts.netloc or parts.scheme:
            raise ValueError
        pages = {"/": overview, "/comparison": comparison, "/pilot": pilot, "/benchmark": benchmark, "/formal": formal}
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
        return 400, layout("", "<h1>Invalid replay step</h1><p>Open a known case and choose a recorded event.</p>")
    return 404, layout("", "<h1>Evidence page unavailable</h1><p>Select a case from the overview.</p>")


def serve(catalog: Catalog, port: int) -> None:
    style = files(__package__).joinpath("style.css").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(400, "Use the printed loopback URL")
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
        print(f"ScopeGuard evidence replay: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return

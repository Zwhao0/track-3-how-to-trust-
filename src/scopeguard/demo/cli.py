"""Verification, local web replay and a terminal fallback."""

import json
import sys

from .evidence import EvidenceError, load_catalog


def register(commands):
    demo = commands.add_parser("demo", help="Verify and replay archived classroom evidence.")
    modes = demo.add_subparsers(dest="demo_mode", required=True)
    modes.add_parser("verify", help="Recompute scores and verify archive fingerprints.")
    serve = modes.add_parser("serve", help="Serve the verified evidence on loopback.")
    serve.add_argument("--port", type=int, default=8765)
    replay = modes.add_parser("replay", help="Print verified evidence in the terminal.")
    replay.add_argument("--case", help="One archived run ID. Defaults to the entire catalog.")
    replay.add_argument("--step", type=int, help="Show only the given prefix of a single case.")


def dispatch(options) -> int:
    try:
        catalog = load_catalog()
        if options.demo_mode == "serve":
            from .web import serve

            if not 0 <= options.port <= 65535:
                raise EvidenceError("Port must be between 0 and 65535")
            serve(catalog, options.port)
        elif options.demo_mode == "replay":
            runs = catalog.runs
            if options.case is not None:
                if options.case not in runs:
                    raise EvidenceError("Unknown case ID. Run scopeguard demo verify to list cases.")
                runs = {options.case: runs[options.case]}
            if options.step is not None and options.case is None:
                raise EvidenceError("--step requires --case")
            for run_id, run in runs.items():
                view = run.step(options.step if options.step is not None else len(run.events))
                source = {"trace_version": run.trace_version, "trace_sha256": run.trace_hash}
                if view["complete"]:
                    view["observation"] = {
                        "elapsed_seconds": run.elapsed, "usage": run.usage,
                        "fixture_sha256": run.fixture_hash, "prompt_sha256": run.prompt_hash,
                    }
                print(json.dumps({"run_id": run_id, "type": run.label, "source": source, **view},
                                 ensure_ascii=False, indent=2))
        else:
            print(json.dumps({
                "status": "verified", "runs": {key: run.label for key, run in catalog.runs.items()},
                "m6_prompt_parity": catalog.prompt_parity, "mock_validations": catalog.mock_cases,
                "eval_tasks": len(catalog.roster), "manifest_sha256": catalog.manifest_hash,
                "formal": catalog.formal,
            }, indent=2))
    except (EvidenceError, OSError) as error:
        print(f"Demo unavailable: {error}", file=sys.stderr)
        return 2
    return 0

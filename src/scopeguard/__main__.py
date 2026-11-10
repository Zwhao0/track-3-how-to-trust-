"""Offline entry point for the M0 bootstrap."""

import argparse
import json
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scopeguard")
    parser.add_argument("mode", choices=("mock",), help="Run the offline M0 smoke check.")
    parser.parse_args(argv)
    print(json.dumps({"milestone": "M0", "mode": "mock", "live_model_called": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

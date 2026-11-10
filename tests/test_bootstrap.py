import json
import subprocess
import sys


def test_mock_entry_point_runs_without_credentials(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "scopeguard", "mock"],
        cwd=tmp_path,
        env={},
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )

    assert json.loads(result.stdout) == {
        "milestone": "M0",
        "mode": "mock",
        "live_model_called": False,
    }

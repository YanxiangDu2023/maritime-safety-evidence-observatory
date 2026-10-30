#!/usr/bin/env python3
"""Refresh, rebuild and validate the published data snapshot safely.

The command keeps the previously generated browser artifacts when any step
fails.  It also restores byte-identical artifacts when the official source
data has not changed, allowing a scheduler to skip unnecessary publication.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dist" / "data" / "dashboard.json"
CONTEXT = ROOT / "dist" / "data" / "context.json"


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def comparable_dashboard(payload: dict) -> dict:
    """Return analytical content without the non-semantic build timestamp."""
    result = copy.deepcopy(payload)
    result.get("meta", {}).pop("built_at", None)
    return result


def occurrence_rows(payload: dict) -> int:
    return int(payload.get("quality", {}).get("rows", {}).get("occurrences", 0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Rebuild and validate from existing raw files (used for local QA).",
    )
    args = parser.parse_args()

    previous_bytes = {
        DASHBOARD: DASHBOARD.read_bytes(),
        CONTEXT: CONTEXT.read_bytes(),
    }
    previous_dashboard = load_json(DASHBOARD)
    previous_context = load_json(CONTEXT)

    try:
        if not args.skip_download:
            run(sys.executable, "scripts/refresh_data.py")
        run(sys.executable, "scripts/build_data.py")
        if not args.skip_download:
            run(sys.executable, "scripts/refresh_context_data.py")
        run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
        run("node", "--check", "dist/app.js")

        current_dashboard = load_json(DASHBOARD)
        current_context = load_json(CONTEXT)
        dashboard_changed = comparable_dashboard(current_dashboard) != comparable_dashboard(previous_dashboard)
        context_changed = current_context != previous_context
        changed = dashboard_changed or context_changed

        if not changed:
            for path, content in previous_bytes.items():
                path.write_bytes(content)

        summary = {
            "status": "updated" if changed else "unchanged",
            "publish_required": changed,
            "dashboard_changed": dashboard_changed,
            "context_changed": context_changed,
            "previous_occurrences": occurrence_rows(previous_dashboard),
            "current_occurrences": occurrence_rows(current_dashboard),
            "occurrence_delta": occurrence_rows(current_dashboard) - occurrence_rows(previous_dashboard),
        }
        print(json.dumps(summary, indent=2))
        return 0
    except Exception:
        for path, content in previous_bytes.items():
            path.write_bytes(content)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

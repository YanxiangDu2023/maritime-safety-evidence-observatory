#!/usr/bin/env python3
"""Refresh official port context data and rebuild the browser summary."""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path


PORT0499_URL = "https://assets.publishing.service.gov.uk/media/6a7315f0011ff6453dece53a/port0499.ods"
ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "port0499.ods"
OUTPUT_FILE = ROOT / "dist" / "data" / "context.json"


def main():
    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(PORT0499_URL, headers={"User-Agent": "Maritime-Safety-Observatory/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        RAW_FILE.write_bytes(response.read())
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_context_data.py"), str(RAW_FILE), "--output", str(OUTPUT_FILE)],
        check=True,
    )
    print("Refreshed DfT PORT0499 context data")


if __name__ == "__main__":
    main()

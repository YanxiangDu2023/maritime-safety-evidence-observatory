#!/usr/bin/env python3
"""Refresh official port context data and rebuild the browser summary."""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


PORT_DATASET_PAGE = "https://www.gov.uk/government/statistical-data-sets/port-and-domestic-waterborne-freight-statistics-port"
ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "port0499.ods"
OUTPUT_FILE = ROOT / "dist" / "data" / "context.json"


class PortTableLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        path = urlparse(href).path.lower()
        if "port0499" in path and path.endswith(".ods"):
            self.links.append(href)


def discover_port0499_url(html: str, base_url: str = PORT_DATASET_PAGE) -> str:
    parser = PortTableLinkParser()
    parser.feed(html)
    candidates = list(dict.fromkeys(urljoin(base_url, link) for link in parser.links))
    if not candidates:
        raise ValueError("The official DfT page does not expose a PORT0499 ODS link")
    return candidates[0]


def main():
    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    page_request = urllib.request.Request(PORT_DATASET_PAGE, headers={"User-Agent": "Maritime-Safety-Observatory/1.0"})
    with urllib.request.urlopen(page_request, timeout=60) as response:
        workbook_url = discover_port0499_url(response.read().decode("utf-8", errors="replace"), response.url)
    request = urllib.request.Request(workbook_url, headers={"User-Agent": "Maritime-Safety-Observatory/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        RAW_FILE.write_bytes(response.read())
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_context_data.py"), str(RAW_FILE), "--output", str(OUTPUT_FILE)],
        check=True,
    )
    print(f"Refreshed DfT PORT0499 context data from {workbook_url}")


if __name__ == "__main__":
    main()

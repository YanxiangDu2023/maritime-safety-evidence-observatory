#!/usr/bin/env python3
"""Build lightweight external-context data for the public dashboard.

The script uses only the Python standard library so the official DfT ODS
workbook can be processed without a spreadsheet application.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
NS = {"table": TABLE_NS, "text": TEXT_NS}


def _cell_value(cell: ET.Element):
    value_type = cell.attrib.get(f"{{{OFFICE_NS}}}value-type")
    if value_type in {"float", "currency", "percentage"}:
        raw = cell.attrib.get(f"{{{OFFICE_NS}}}value")
        if raw is not None:
            value = float(raw)
            return int(value) if value.is_integer() else value
    if value_type == "date":
        return cell.attrib.get(f"{{{OFFICE_NS}}}date-value")
    text = " ".join("".join(node.itertext()).strip() for node in cell.findall("text:p", NS)).strip()
    return text or None


def read_ods_sheet(path: Path, sheet_name: str):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    for sheet in root.findall(".//table:table", NS):
        if sheet.attrib.get(f"{{{TABLE_NS}}}name") != sheet_name:
            continue
        rows = []
        for row in sheet.findall("table:table-row", NS):
            row_repeat = int(row.attrib.get(f"{{{TABLE_NS}}}number-rows-repeated", "1"))
            values = []
            for cell in row:
                if cell.tag not in {f"{{{TABLE_NS}}}table-cell", f"{{{TABLE_NS}}}covered-table-cell"}:
                    continue
                repeat = int(cell.attrib.get(f"{{{TABLE_NS}}}number-columns-repeated", "1"))
                value = _cell_value(cell)
                values.extend([value] * min(repeat, 200))
            while values and values[-1] is None:
                values.pop()
            if values:
                rows.extend([values] * min(row_repeat, 20))
        return rows
    raise ValueError(f"Sheet not found: {sheet_name}")


def normalise_header(value) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip().lower()


def build_port_summary(rows):
    header_index = next(
        index for index, row in enumerate(rows)
        if row and normalise_header(row[0]).startswith("year")
        and any(normalise_header(value) == "tonnage (thousands)" for value in row)
    )
    headers = [normalise_header(value) for value in rows[header_index]]
    records = []
    for row in rows[header_index + 1:]:
        padded = row + [None] * (len(headers) - len(row))
        record = dict(zip(headers, padded))
        if any(value is not None for value in record.values()):
            records.append(record)

    def find_header(*terms):
        for header in headers:
            if all(term in header for term in terms):
                return header
        raise ValueError(f"Could not find column containing: {terms}; headers={headers}")

    year_key = find_header("year")
    port_key = find_header("port")
    tonnes_key = find_header("tonnage")
    annual = defaultdict(lambda: defaultdict(float))
    for record in records:
        try:
            year = int(float(record[year_key]))
            port = str(record[port_key]).strip()
            tonnes = float(record[tonnes_key] or 0) * 1_000
        except (TypeError, ValueError):
            continue
        if 2020 <= year <= 2024 and port:
            annual[year][port] += tonnes

    by_year = {}
    for year, ports in sorted(annual.items()):
        by_year[str(year)] = [
            {"port": port, "tonnes": round(tonnes)}
            for port, tonnes in sorted(ports.items(), key=lambda item: item[1], reverse=True)[:12]
        ]
    return {
        "source": "UK Department for Transport PORT0499",
        "source_url": "https://www.gov.uk/government/statistical-data-sets/port-and-domestic-waterborne-freight-statistics-port",
        "unit": "tonnes of freight handled",
        "coverage": "2020–2024 overlap used",
        "by_year": by_year,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ods", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    rows = read_ods_sheet(args.ods, "port0499")
    if args.inspect:
        for index, row in enumerate(rows[:18]):
            print(index, row[:20])
        return
    if not args.output:
        parser.error("--output is required unless --inspect is used")
    payload = {"ports": build_port_summary(rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

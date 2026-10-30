#!/usr/bin/env python3
"""Download and validate the current public MAIB CSV snapshot."""

from __future__ import annotations

import csv
import shutil
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BASE_URL = "https://maps.dft.gov.uk/maib-data-portal/csv-files"
TABLES = {
    "occurrences.csv": {"Occurrence_Id", "Occurrence_Severity", "Main_Event_L1"},
    "vessels.csv": {"Occurrence_Id", "Vessel_Profile_Id", "Vessel_Category_L1"},
    "affected_persons.csv": {"Occurrence_Id", "Affected_Person_Id", "Physical_Condition_L1"},
}


def validate_csv(path: Path, required_columns: set[str]) -> int:
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        columns = set(reader.fieldnames or [])
        missing = required_columns - columns
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")
        row_count = sum(1 for _ in reader)
    if row_count == 0:
        raise ValueError(f"{path.name} contains no data rows")
    return row_count


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maib-refresh-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        validated: list[tuple[str, Path, int]] = []
        for name, required_columns in TABLES.items():
            destination = temporary_root / name
            request = urllib.request.Request(
                f"{BASE_URL}/{name}",
                headers={"User-Agent": "MaritimeSafetyEvidenceObservatory/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output)
            row_count = validate_csv(destination, required_columns)
            validated.append((name, destination, row_count))

        for name, source, row_count in validated:
            source.replace(RAW / name)
            print(f"Updated {name}: {row_count:,} rows")

    print("Refresh complete. Run scripts/build_data.py and the test suite before publishing.")


if __name__ == "__main__":
    main()

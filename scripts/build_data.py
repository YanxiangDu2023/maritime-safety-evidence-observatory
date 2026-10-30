#!/usr/bin/env python3
"""Build a compact, browser-ready dataset from the public MAIB CSV exports."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "dist" / "data" / "dashboard.json"


def read_csv(name: str) -> list[dict[str, str]]:
    with (RAW / name).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def clean(value: str | None) -> str:
    return (value or "").strip()


def number(value: str | None) -> float | None:
    try:
        text = clean(value)
        return float(text) if text else None
    except ValueError:
        return None


def integer(value: str | None) -> int:
    value_number = number(value)
    return int(value_number) if value_number is not None else 0


def normalise_severity(value: str) -> str:
    text = clean(value).lower()
    if "very serious" in text:
        return "Very serious"
    if "serious" in text and "less" not in text:
        return "Serious"
    if "less serious" in text:
        return "Less serious"
    if "incident" in text:
        return "Marine incident"
    if "casualty" in text:
        return "Marine casualty"
    return clean(value) or "Not recorded"


def normalise_event(value: str) -> str:
    value = clean(value)
    return value if value else "Not recorded"


def is_fatal_person(row: dict[str, str]) -> bool:
    text = " ".join(
        clean(row.get(key)).lower()
        for key in ("Physical_Condition_L1", "Physical_Condition_L2", "Injury_Type_L1")
    )
    return "dead" in text or "fatal" in text or "deceased" in text


def is_injured_person(row: dict[str, str]) -> bool:
    text = " ".join(
        clean(row.get(key)).lower()
        for key in ("Physical_Condition_L1", "Physical_Condition_L2", "Injury_Type_L1")
    )
    return "injur" in text or "fracture" in text or "burn" in text


def main() -> None:
    occurrences = read_csv("occurrences.csv")
    vessels = read_csv("vessels.csv")
    persons = read_csv("affected_persons.csv")

    occurrence_ids = {clean(row.get("Occurrence_Id")) for row in occurrences}
    vessel_by_occurrence: dict[str, list[dict[str, str]]] = defaultdict(list)
    person_by_occurrence: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in vessels:
        vessel_by_occurrence[clean(row.get("Occurrence_Id"))].append(row)
    for row in persons:
        person_by_occurrence[clean(row.get("Occurrence_Id"))].append(row)

    records = []
    for row in occurrences:
        occurrence_id = clean(row.get("Occurrence_Id"))
        linked_vessels = vessel_by_occurrence.get(occurrence_id, [])
        linked_persons = person_by_occurrence.get(occurrence_id, [])

        category_counts = Counter(
            clean(vessel.get("Vessel_Category_L1")) or "Not recorded"
            for vessel in linked_vessels
        )
        type_counts = Counter(
            clean(vessel.get("Ship_Craft_Type_L1")) or "Not recorded"
            for vessel in linked_vessels
        )

        fatalities = sum(1 for person in linked_persons if is_fatal_person(person))
        injuries = sum(1 for person in linked_persons if is_injured_person(person) and not is_fatal_person(person))

        if not linked_persons:
            fatalities = sum(integer(vessel.get("Deaths_Total")) for vessel in linked_vessels)
            injuries = sum(integer(vessel.get("Injuries_Total")) for vessel in linked_vessels)

        lat = number(row.get("Latitude"))
        lon = number(row.get("Longitude"))
        coordinates_valid = (
            lat is not None
            and lon is not None
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        )

        year = integer(row.get("Year_Reported"))
        if not year:
            date_text = clean(row.get("Local_Date_Main_Event"))
            year = integer(date_text[:4]) if len(date_text) >= 4 else 0

        records.append(
            {
                "id": occurrence_id,
                "date": clean(row.get("Local_Date_Main_Event")),
                "year": year,
                "severity": normalise_severity(clean(row.get("Occurrence_Severity"))),
                "event": normalise_event(clean(row.get("Main_Event_L1"))),
                "event_detail": clean(row.get("Main_Event_L2")),
                "description": clean(row.get("Short_Description")) or clean(row.get("Description")),
                "location": clean(row.get("Occurrence_Location")) or "Not recorded",
                "coastal_state": clean(row.get("Coastal_State_Affected")) or "Not recorded",
                "region": clean(row.get("National_Location_L2")) or clean(row.get("National_Location_L1")) or "Not recorded",
                "lat": round(lat, 6) if coordinates_valid else None,
                "lon": round(lon, 6) if coordinates_valid else None,
                "vessel_count": len(linked_vessels),
                "vessel_category": category_counts.most_common(1)[0][0] if category_counts else "Not recorded",
                "ship_type": type_counts.most_common(1)[0][0] if type_counts else "Not recorded",
                "fatalities": fatalities,
                "injuries": injuries,
                "affected_people": len(linked_persons),
                "damage": sum(1 for vessel in linked_vessels if clean(vessel.get("Loss_Of_Vessel_Damage")).lower() not in ("", "no damage")),
                "sunk": any(clean(vessel.get("Did_The_Vessel_Sink")).lower() == "yes" for vessel in linked_vessels),
                "natural_light": clean(row.get("Natural_Light")) or "Not recorded",
                "weather": clean(row.get("Weather")) or "Not recorded",
                "sea_state": clean(row.get("Sea_State")) or "Not recorded",
                "report_url": clean(row.get("Published_Report_Website_Link")),
                "publication_no": clean(row.get("Publication_No")),
            }
        )

    years = sorted({record["year"] for record in records if record["year"]})
    latest_updates = [clean(row.get("Last_Updated_At")) for row in occurrences if clean(row.get("Last_Updated_At"))]

    key_fields = {
        "Event type": "Main_Event_L1",
        "Severity": "Occurrence_Severity",
        "Coordinates": "Latitude",
        "Coastal state": "Coastal_State_Affected",
        "Weather": "Weather",
        "Published report": "Published_Report_Website_Link",
    }
    missingness = []
    for label, field in key_fields.items():
        missing = sum(1 for row in occurrences if not clean(row.get(field)))
        missingness.append(
            {
                "field": label,
                "missing": missing,
                "rate": round(100 * missing / len(occurrences), 1) if occurrences else 0,
            }
        )

    duplicate_occurrences = len(occurrences) - len(occurrence_ids)
    unmatched_vessels = sum(1 for row in vessels if clean(row.get("Occurrence_Id")) not in occurrence_ids)
    unmatched_persons = sum(1 for row in persons if clean(row.get("Occurrence_Id")) not in occurrence_ids)

    payload = {
        "meta": {
            "title": "Maritime Safety Evidence Observatory",
            "source": "UK Marine Accident Investigation Branch (MAIB) public data portal",
            "source_url": "https://maps.dft.gov.uk/maib-data-portal/web-pages/download_files_section.html",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "last_source_update": max(latest_updates) if latest_updates else None,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "latest_year_partial": True,
            "method_note": "Counts describe reported occurrences and are not exposure-adjusted accident rates.",
        },
        "quality": {
            "rows": {
                "occurrences": len(occurrences),
                "vessels": len(vessels),
                "affected_people": len(persons),
            },
            "duplicate_occurrences": duplicate_occurrences,
            "unmatched_vessels": unmatched_vessels,
            "unmatched_people": unmatched_persons,
            "missingness": missingness,
        },
        "records": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} with {len(records):,} occurrence records")


if __name__ == "__main__":
    main()

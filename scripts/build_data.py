#!/usr/bin/env python3
"""Build a compact, browser-ready dataset from the public MAIB CSV exports."""

from __future__ import annotations

import csv
import json
import math
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


def invert_matrix(matrix: list[list[float]]) -> list[list[float]]:
    """Invert a small dense matrix with Gauss-Jordan elimination."""
    size = len(matrix)
    augmented = [
        [float(value) for value in row]
        + [1.0 if row_index == column_index else 0.0 for column_index in range(size)]
        for row_index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("Singular model matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return [row[size:] for row in augmented]


def logistic_regression(
    design: list[list[float]], outcomes: list[int], labels: list[str]
) -> dict:
    """Fit an unpenalised logistic model using IRLS and return interpretable effects."""
    feature_count = len(design[0])
    coefficients = [0.0] * feature_count
    inverse_information: list[list[float]] | None = None
    converged = False

    for iteration in range(60):
        probabilities = []
        weights = []
        working = []
        for row, outcome in zip(design, outcomes):
            linear = sum(value * coefficient for value, coefficient in zip(row, coefficients))
            linear = max(-30.0, min(30.0, linear))
            probability = 1.0 / (1.0 + math.exp(-linear))
            weight = max(probability * (1.0 - probability), 1e-7)
            probabilities.append(probability)
            weights.append(weight)
            working.append(linear + (outcome - probability) / weight)

        information = [[0.0] * feature_count for _ in range(feature_count)]
        score_target = [0.0] * feature_count
        for row, weight, target in zip(design, weights, working):
            for left in range(feature_count):
                score_target[left] += row[left] * weight * target
                for right in range(feature_count):
                    information[left][right] += row[left] * weight * row[right]
        for diagonal in range(feature_count):
            information[diagonal][diagonal] += 1e-7
        inverse_information = invert_matrix(information)
        updated = [
            sum(inverse_information[row][column] * score_target[column] for column in range(feature_count))
            for row in range(feature_count)
        ]
        if max(abs(new - old) for new, old in zip(updated, coefficients)) < 1e-7:
            coefficients = updated
            converged = True
            break
        coefficients = updated

    if inverse_information is None:
        raise ValueError("Model did not initialise")

    effects = []
    for index, label in enumerate(labels, start=1):
        standard_error = math.sqrt(max(inverse_information[index][index], 0.0))
        coefficient = coefficients[index]
        effects.append(
            {
                "label": label,
                "odds_ratio": round(math.exp(coefficient), 3),
                "ci_low": round(math.exp(coefficient - 1.96 * standard_error), 3),
                "ci_high": round(math.exp(coefficient + 1.96 * standard_error), 3),
            }
        )

    predictions = []
    for row in design:
        linear = max(-30.0, min(30.0, sum(value * coefficient for value, coefficient in zip(row, coefficients))))
        predictions.append(1.0 / (1.0 + math.exp(-linear)))
    ranked = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    rank_sum = sum(rank for rank, (_, outcome) in enumerate(ranked, start=1) if outcome)
    auc = (rank_sum - positives * (positives + 1) / 2) / (positives * negatives) if positives and negatives else 0.5

    return {
        "n": len(outcomes),
        "positive_outcomes": positives,
        "positive_rate": round(positives / len(outcomes), 4),
        "auc": round(auc, 3),
        "converged": converged,
        "effects": effects,
    }


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if not total:
        return (0.0, 0.0)
    z = 1.96
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def severity_model(occurrences: list[dict[str, str]], vessel_by_occurrence: dict[str, list[dict[str, str]]]) -> dict:
    labels = [
        "Night conditions",
        "Adverse weather",
        "Rough sea state (4+)",
        "Multiple vessels involved",
        "Fishing vessel involved",
        "Recreational vessel involved",
        "Passenger ship involved",
        "Collision / contact",
        "Grounding / stranding",
        "Fire / explosion",
        "Accident to person(s)",
    ]
    design: list[list[float]] = []
    outcomes: list[int] = []
    for occurrence in occurrences:
        occurrence_id = clean(occurrence.get("Occurrence_Id"))
        vessels = vessel_by_occurrence.get(occurrence_id, [])
        categories = {clean(vessel.get("Vessel_Category_L1")).lower() for vessel in vessels}
        ship_types = {clean(vessel.get("Ship_Craft_Type_L1")).lower() for vessel in vessels}
        event = clean(occurrence.get("Main_Event_L1")).lower()
        weather = clean(occurrence.get("Weather")).lower()
        sea_state_text = clean(occurrence.get("Sea_State"))
        try:
            sea_state = int(sea_state_text.split()[0])
        except (ValueError, IndexError):
            sea_state = 0
        features = [
            clean(occurrence.get("Natural_Light")).lower() == "night",
            weather in {"rain", "fog", "snow"},
            sea_state >= 4,
            len(vessels) > 1,
            "fishing vessel" in categories,
            "recreational (non commercial)" in categories,
            "passenger ship" in ship_types,
            event in {"collision", "contact"},
            event == "grounding / stranding",
            event == "fire / explosion",
            event == "accident to person(s)",
        ]
        design.append([1.0] + [float(value) for value in features])
        severity = normalise_severity(clean(occurrence.get("Occurrence_Severity")))
        outcomes.append(int(severity in {"Serious", "Very serious"}))
    return logistic_regression(design, outcomes, labels)


def consequence_analysis(
    occurrences: list[dict[str, str]],
    vessels: list[dict[str, str]],
    persons: list[dict[str, str]],
    vessel_by_occurrence: dict[str, list[dict[str, str]]],
) -> dict:
    category_counts = Counter(clean(row.get("Vessel_Category_L1")) or "Not recorded" for row in vessels)
    top_categories = [name for name, count in category_counts.most_common() if count >= 100]
    top_events = [name for name, _ in Counter(clean(row.get("Main_Event_L1")) or "Not recorded" for row in occurrences).most_common(8)]
    occurrence_lookup = {clean(row.get("Occurrence_Id")): row for row in occurrences}
    severity_cells = []
    for category in top_categories:
        ids = {
            clean(vessel.get("Occurrence_Id"))
            for vessel in vessels
            if (clean(vessel.get("Vessel_Category_L1")) or "Not recorded") == category
        }
        for event in top_events:
            matching = [
                occurrence_lookup[occurrence_id]
                for occurrence_id in ids
                if occurrence_id in occurrence_lookup
                and (clean(occurrence_lookup[occurrence_id].get("Main_Event_L1")) or "Not recorded") == event
            ]
            serious_count = sum(
                normalise_severity(clean(row.get("Occurrence_Severity"))) in {"Serious", "Very serious"}
                for row in matching
            )
            low, high = wilson_interval(serious_count, len(matching))
            severity_cells.append(
                {
                    "category": category,
                    "event": event,
                    "n": len(matching),
                    "serious": serious_count,
                    "share": round(serious_count / len(matching), 4) if matching else 0,
                    "ci_low": round(low, 4),
                    "ci_high": round(high, 4),
                }
            )

    person_event_counts = Counter(clean(row.get("Main_Event_L1")) or "Not recorded" for row in persons)
    flow_events = {name for name, _ in person_event_counts.most_common(5)}
    event_person = Counter()
    person_outcome = Counter()
    for person in persons:
        event = clean(person.get("Main_Event_L1")) or "Not recorded"
        event = event if event in flow_events else "Other events"
        person_type = clean(person.get("Affected_Person_Type")) or "Not recorded"
        condition = clean(person.get("Physical_Condition_L1")) or "Not recorded"
        event_person[(event, person_type)] += 1
        person_outcome[(person_type, condition)] += 1
    person_flow = {
        "columns": [
            [name for name, _ in person_event_counts.most_common(5)] + ["Other events"],
            [name for name, _ in Counter(clean(row.get("Affected_Person_Type")) or "Not recorded" for row in persons).most_common()],
            [name for name, _ in Counter(clean(row.get("Physical_Condition_L1")) or "Not recorded" for row in persons).most_common()],
        ],
        "links": [
            *[{"source": source, "target": target, "value": value, "stage": 0} for (source, target), value in event_person.items()],
            *[{"source": source, "target": target, "value": value, "stage": 1} for (source, target), value in person_outcome.items()],
        ],
    }

    def vessel_band_summary(field: str, bander) -> list[dict]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for vessel in vessels:
            grouped[bander(vessel)].append(vessel)
        result = []
        for band, rows in grouped.items():
            damaged = sum(
                clean(row.get("Loss_Of_Vessel_Damage")).lower() not in {"", "no damage"}
                for row in rows
            )
            material_or_loss = sum(
                clean(row.get("Loss_Of_Vessel_Damage")).lower().startswith("material damage")
                or clean(row.get("Loss_Of_Vessel_Damage")).lower().startswith("loss of ship")
                for row in rows
            )
            result.append(
                {
                    "band": band,
                    "n": len(rows),
                    "damage_share": round(damaged / len(rows), 4),
                    "material_loss_share": round(material_or_loss / len(rows), 4),
                }
            )
        return result

    event_years = [integer(row.get("Year_Reported")) for row in occurrences if integer(row.get("Year_Reported"))]
    reference_year = max(event_years) if event_years else datetime.now().year

    def age_band(vessel: dict[str, str]) -> str:
        built = integer(vessel.get("Year_Built"))
        if built < 1850 or built > reference_year:
            return "Unknown"
        age = reference_year - built
        if age < 10:
            return "<10 years"
        if age < 20:
            return "10–19 years"
        if age < 30:
            return "20–29 years"
        if age < 40:
            return "30–39 years"
        return "40+ years"

    def tonnage_band(vessel: dict[str, str]) -> str:
        tonnage = number(vessel.get("GT_Gross_Tonnage")) or 0
        if tonnage <= 0:
            return "Unknown / zero"
        if tonnage < 100:
            return "<100 GT"
        if tonnage < 1000:
            return "100–999 GT"
        if tonnage < 10000:
            return "1k–9,999 GT"
        if tonnage < 50000:
            return "10k–49,999 GT"
        return "50k+ GT"

    age_order = ["<10 years", "10–19 years", "20–29 years", "30–39 years", "40+ years", "Unknown"]
    tonnage_order = ["<100 GT", "100–999 GT", "1k–9,999 GT", "10k–49,999 GT", "50k+ GT", "Unknown / zero"]
    vessel_profile = {
        "by_age": sorted(vessel_band_summary("age", age_band), key=lambda row: age_order.index(row["band"])),
        "by_tonnage": sorted(vessel_band_summary("tonnage", tonnage_band), key=lambda row: tonnage_order.index(row["band"])),
    }

    return {
        "severity_matrix": {"categories": top_categories, "events": top_events, "cells": severity_cells},
        "severity_model": severity_model(occurrences, vessel_by_occurrence),
        "person_flow": person_flow,
        "vessel_profile": vessel_profile,
        "notes": {
            "model": "Multivariable logistic regression of serious/very serious classification among reported occurrences. Odds ratios are adjusted for all displayed factors.",
            "person": "Person-level flows describe affected-person records and do not measure population risk.",
            "vessel": "Damage shares are conditional on vessels appearing in the published occurrence records.",
        },
    }


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
        "analysis": consequence_analysis(occurrences, vessels, persons, vessel_by_occurrence),
        "records": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} with {len(records):,} occurrence records")


if __name__ == "__main__":
    main()

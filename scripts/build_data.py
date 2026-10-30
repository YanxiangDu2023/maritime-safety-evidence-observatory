#!/usr/bin/env python3
"""Build a compact, browser-ready dataset from the public MAIB CSV exports."""

from __future__ import annotations

import csv
import hashlib
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


def file_sha256(name: str) -> str:
    digest = hashlib.sha256()
    with (RAW / name).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def fit_logistic(design: list[list[float]], outcomes: list[int]) -> tuple[list[float], list[list[float]], bool]:
    """Fit an unpenalised logistic model using IRLS."""
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
    return coefficients, inverse_information, converged


def predict_logistic(design: list[list[float]], coefficients: list[float]) -> list[float]:
    predictions = []
    for row in design:
        linear = max(-30.0, min(30.0, sum(value * coefficient for value, coefficient in zip(row, coefficients))))
        predictions.append(1.0 / (1.0 + math.exp(-linear)))
    return predictions


def roc_auc(predictions: list[float], outcomes: list[int]) -> float:
    ranked = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    if not positives or not negatives:
        return 0.5
    rank_sum = sum(rank for rank, (_, outcome) in enumerate(ranked, start=1) if outcome)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def calibration_bins(predictions: list[float], outcomes: list[int], bin_count: int = 10) -> list[dict]:
    ordered = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
    bins = []
    for index in range(bin_count):
        start = round(index * len(ordered) / bin_count)
        end = round((index + 1) * len(ordered) / bin_count)
        group = ordered[start:end]
        if not group:
            continue
        bins.append(
            {
                "predicted": round(sum(value for value, _ in group) / len(group), 4),
                "observed": round(sum(outcome for _, outcome in group) / len(group), 4),
                "n": len(group),
            }
        )
    return bins


def cross_validate_logistic(
    design: list[list[float]],
    outcomes: list[int],
    folds: int = 5,
    groups: list[str] | None = None,
) -> dict:
    """Deterministic stratified cross-validation for honest predictive diagnostics."""
    fold_ids = [0] * len(outcomes)
    if groups is None:
        positive_indices = [index for index, outcome in enumerate(outcomes) if outcome]
        negative_indices = [index for index, outcome in enumerate(outcomes) if not outcome]
        for indices in (positive_indices, negative_indices):
            for position, index in enumerate(indices):
                fold_ids[index] = position % folds
    else:
        group_indices: dict[str, list[int]] = defaultdict(list)
        for index, group in enumerate(groups):
            group_indices[group].append(index)
        positive_groups = [group for group, indices in group_indices.items() if any(outcomes[index] for index in indices)]
        negative_groups = [group for group, indices in group_indices.items() if not any(outcomes[index] for index in indices)]
        group_fold = {}
        for group_list in (sorted(positive_groups), sorted(negative_groups)):
            for position, group in enumerate(group_list):
                group_fold[group] = position % folds
        fold_ids = [group_fold[group] for group in groups]

    predictions = [0.0] * len(outcomes)
    for fold in range(folds):
        train_design = [row for index, row in enumerate(design) if fold_ids[index] != fold]
        train_outcomes = [outcome for index, outcome in enumerate(outcomes) if fold_ids[index] != fold]
        test_indices = [index for index in range(len(outcomes)) if fold_ids[index] == fold]
        coefficients, _, converged = fit_logistic(train_design, train_outcomes)
        if not converged:
            raise ValueError(f"Cross-validation fold {fold + 1} did not converge")
        fold_predictions = predict_logistic([design[index] for index in test_indices], coefficients)
        for index, prediction in zip(test_indices, fold_predictions):
            predictions[index] = prediction

    threshold = 0.5
    true_positive = sum(outcome == 1 and prediction >= threshold for prediction, outcome in zip(predictions, outcomes))
    false_positive = sum(outcome == 0 and prediction >= threshold for prediction, outcome in zip(predictions, outcomes))
    true_negative = sum(outcome == 0 and prediction < threshold for prediction, outcome in zip(predictions, outcomes))
    false_negative = sum(outcome == 1 and prediction < threshold for prediction, outcome in zip(predictions, outcomes))
    brier = sum((prediction - outcome) ** 2 for prediction, outcome in zip(predictions, outcomes)) / len(outcomes)
    return {
        "folds": folds,
        "auc": round(roc_auc(predictions, outcomes), 3),
        "brier": round(brier, 4),
        "threshold": threshold,
        "confusion_matrix": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "calibration": calibration_bins(predictions, outcomes),
    }


def clustered_covariance(
    design: list[list[float]],
    outcomes: list[int],
    predictions: list[float],
    bread: list[list[float]],
    groups: list[str],
) -> list[list[float]]:
    """Cluster-robust sandwich covariance using occurrence-level score sums."""
    feature_count = len(design[0])
    scores: dict[str, list[float]] = defaultdict(lambda: [0.0] * feature_count)
    for row, outcome, prediction, group in zip(design, outcomes, predictions, groups):
        residual = outcome - prediction
        for index, value in enumerate(row):
            scores[group][index] += value * residual

    meat = [[0.0] * feature_count for _ in range(feature_count)]
    for score in scores.values():
        for left in range(feature_count):
            for right in range(feature_count):
                meat[left][right] += score[left] * score[right]

    left_product = [
        [sum(bread[row][k] * meat[k][column] for k in range(feature_count)) for column in range(feature_count)]
        for row in range(feature_count)
    ]
    covariance = [
        [sum(left_product[row][k] * bread[k][column] for k in range(feature_count)) for column in range(feature_count)]
        for row in range(feature_count)
    ]
    cluster_count = len(scores)
    sample_count = len(outcomes)
    correction = 1.0
    if cluster_count > 1 and sample_count > feature_count:
        correction = (cluster_count / (cluster_count - 1)) * ((sample_count - 1) / (sample_count - feature_count))
    return [[value * correction for value in row] for row in covariance]


def logistic_regression(
    design: list[list[float]],
    outcomes: list[int],
    labels: list[str],
    groups: list[str] | None = None,
) -> dict:
    """Fit a logistic model and return adjusted effects plus validation diagnostics."""
    coefficients, inverse_information, converged = fit_logistic(design, outcomes)

    predictions = predict_logistic(design, coefficients)
    covariance = clustered_covariance(design, outcomes, predictions, inverse_information, groups) if groups else inverse_information
    effects = []
    for index, label in enumerate(labels, start=1):
        standard_error = math.sqrt(max(covariance[index][index], 0.0))
        coefficient = coefficients[index]
        effects.append(
            {
                "label": label,
                "odds_ratio": round(math.exp(coefficient), 3),
                "ci_low": round(math.exp(coefficient - 1.96 * standard_error), 3),
                "ci_high": round(math.exp(coefficient + 1.96 * standard_error), 3),
            }
        )

    positives = sum(outcomes)

    return {
        "n": len(outcomes),
        "positive_outcomes": positives,
        "positive_rate": round(positives / len(outcomes), 4),
        "in_sample_auc": round(roc_auc(predictions, outcomes), 3),
        "validation": cross_validate_logistic(design, outcomes, groups=groups),
        "converged": converged,
        "cluster_count": len(set(groups)) if groups else None,
        "standard_errors": "Occurrence-clustered sandwich" if groups else "Model-based Wald",
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
    specifications = [
        {"label": "Night conditions", "definition": "Natural_Light = Night", "reference": "Known non-night conditions"},
        {"label": "Natural light unknown", "definition": "Natural_Light is unknown", "reference": "Known non-night conditions"},
        {"label": "Adverse weather", "definition": "Weather is rain, fog or snow", "reference": "Known clear or overcast weather"},
        {"label": "Weather unknown", "definition": "Weather is unknown", "reference": "Known clear or overcast weather"},
        {"label": "Rough sea state (4+)", "definition": "Douglas sea state code ≥ 4", "reference": "Known sea state below 4"},
        {"label": "Sea state unknown", "definition": "Sea_State is unknown", "reference": "Known sea state below 4"},
        {"label": "Multiple vessels involved", "definition": "More than one linked vessel record", "reference": "One linked vessel"},
        {"label": "Fishing vessel involved", "definition": "At least one fishing-vessel record", "reference": "No fishing vessel involved"},
        {"label": "Recreational vessel involved", "definition": "At least one recreational-vessel record", "reference": "No recreational vessel involved"},
        {"label": "Passenger ship involved", "definition": "At least one passenger-ship record", "reference": "No passenger ship involved"},
        {"label": "Collision / contact", "definition": "Main event is collision or contact", "reference": "Other event types"},
        {"label": "Grounding / stranding", "definition": "Main event is grounding/stranding", "reference": "Other event types"},
        {"label": "Fire / explosion", "definition": "Main event is fire/explosion", "reference": "Other event types"},
        {"label": "Accident to person(s)", "definition": "Main event is accident to person(s)", "reference": "Other event types"},
        {"label": "Calendar year", "definition": "One-year increase in Year_Reported", "reference": "Previous calendar year"},
    ]
    labels = [item["label"] for item in specifications]
    design: list[list[float]] = []
    outcomes: list[int] = []
    for occurrence in occurrences:
        occurrence_id = clean(occurrence.get("Occurrence_Id"))
        vessels = vessel_by_occurrence.get(occurrence_id, [])
        categories = {clean(vessel.get("Vessel_Category_L1")).lower() for vessel in vessels}
        ship_types = {clean(vessel.get("Ship_Craft_Type_L1")).lower() for vessel in vessels}
        event = clean(occurrence.get("Main_Event_L1")).lower()
        weather = clean(occurrence.get("Weather")).lower()
        light = clean(occurrence.get("Natural_Light")).lower()
        sea_state_text = clean(occurrence.get("Sea_State"))
        weather_unknown = not weather or "unknown" in weather
        light_unknown = not light or "unknown" in light
        sea_state_unknown = not sea_state_text or "unknown" in sea_state_text.lower()
        try:
            sea_state = int(sea_state_text.split()[0])
        except (ValueError, IndexError):
            sea_state = 0
        year = integer(occurrence.get("Year_Reported")) or 2020
        features = [
            light == "night",
            light_unknown,
            weather in {"rain", "fog", "snow"},
            weather_unknown,
            sea_state >= 4 and not sea_state_unknown,
            sea_state_unknown,
            len(vessels) > 1,
            "fishing vessel" in categories,
            "recreational (non commercial)" in categories,
            "passenger ship" in ship_types,
            event in {"collision", "contact"},
            event == "grounding / stranding",
            event == "fire / explosion",
            event == "accident to person(s)",
            year - 2020,
        ]
        design.append([1.0] + [float(value) for value in features])
        severity = normalise_severity(clean(occurrence.get("Occurrence_Severity")))
        outcomes.append(int(severity in {"Serious", "Very serious"}))
    result = logistic_regression(design, outcomes, labels)
    result["specifications"] = specifications
    result["outcome_definition"] = "Occurrence_Severity is Serious or Very serious"
    result["reference_outcome"] = "Marine incident or Less serious"
    return result


def person_severity_model(persons: list[dict[str, str]]) -> dict:
    specifications = [
        {"label": "Age (per 10 years)", "group": "Demographics", "definition": "Recorded age divided by 10; unknown ages set to the sample reference", "reference": "Ten years younger"},
        {"label": "Age unknown", "group": "Demographics", "definition": "Age is unavailable or implausible", "reference": "Age recorded"},
        {"label": "Female", "group": "Demographics", "definition": "Gender = Female", "reference": "Male"},
        {"label": "Gender unknown", "group": "Demographics", "definition": "Gender is unknown or unavailable", "reference": "Male"},
        {"label": "Passenger", "group": "Role & duty", "definition": "Affected person type = Passenger", "reference": "Crew"},
        {"label": "Other person", "group": "Role & duty", "definition": "Affected person type = Other", "reference": "Crew"},
        {"label": "On duty", "group": "Role & duty", "definition": "On duty immediately before the casualty", "reference": "Known not on duty"},
        {"label": "Duty status unknown", "group": "Role & duty", "definition": "Duty status is blank, unknown or unavailable", "reference": "Known not on duty"},
        {"label": "Fishing vessel", "group": "Vessel category", "definition": "Vessel category = Fishing vessel", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Recreational vessel", "group": "Vessel category", "definition": "Vessel category = Recreational", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Small commercial vessel", "group": "Vessel category", "definition": "Small commercial vessel under 100 GT", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Accident to person(s)", "group": "Occurrence event", "definition": "Main event is accident to person(s)", "reference": "Other event types"},
        {"label": "Capsizing / listing", "group": "Occurrence event", "definition": "Main event is capsizing/listing", "reference": "Other event types"},
        {"label": "Collision / contact", "group": "Occurrence event", "definition": "Main event is collision or contact", "reference": "Other event types"},
        {"label": "Fire / explosion", "group": "Occurrence event", "definition": "Main event is fire/explosion", "reference": "Other event types"},
    ]
    design: list[list[float]] = []
    outcomes: list[int] = []
    groups: list[str] = []
    known_ages = [number(row.get("Age")) for row in persons]
    known_ages = [age for age in known_ages if age is not None and 0 < age <= 110]
    reference_age = sum(known_ages) / len(known_ages) if known_ages else 40.0

    for person in persons:
        age = number(person.get("Age"))
        age_unknown = age is None or age <= 0 or age > 110
        age_value = reference_age if age_unknown else age
        gender = clean(person.get("Gender")).lower()
        person_type = clean(person.get("Affected_Person_Type")).lower()
        duty = clean(person.get("On_Duty")).lower()
        category = clean(person.get("Vessel_Category_L1")).lower()
        event = clean(person.get("Main_Event_L1")).lower()
        condition_l1 = clean(person.get("Physical_Condition_L1")).lower()
        condition_l2 = clean(person.get("Physical_Condition_L2")).lower()
        duty_unknown = not duty or "unknown" in duty or "not available" in duty
        features = [
            (age_value - reference_age) / 10,
            age_unknown,
            gender == "female",
            not gender or "unknown" in gender or "not available" in gender,
            person_type == "passenger",
            person_type == "other",
            duty.startswith("yes"),
            duty_unknown,
            category == "fishing vessel",
            category == "recreational (non commercial)",
            category.startswith("small commercial"),
            event == "accident to person(s)",
            event == "capsizing / listing",
            event in {"collision", "contact"},
            event == "fire / explosion",
        ]
        design.append([1.0] + [float(value) for value in features])
        outcomes.append(int(condition_l2 == "serious injury" or condition_l1 in {"death (confirmed)", "missing (death presumed)"}))
        groups.append(clean(person.get("Occurrence_Id")))

    result = logistic_regression(design, outcomes, [item["label"] for item in specifications], groups=groups)
    result["specifications"] = specifications
    result["outcome_definition"] = "Serious injury, confirmed death, or missing (death presumed)"
    result["reference_outcome"] = "Minor injury or no injury"
    result["unit"] = "Affected-person record"
    return result


def vessel_damage_model(vessels: list[dict[str, str]]) -> dict:
    specifications = [
        {"label": "Vessel age (per 10 years)", "group": "Vessel characteristics", "definition": "Occurrence year minus year built", "reference": "Ten years younger"},
        {"label": "Vessel age unknown", "group": "Vessel characteristics", "definition": "Year built unavailable or implausible", "reference": "Age recorded"},
        {"label": "Gross tonnage (10×)", "group": "Vessel characteristics", "definition": "One-unit increase in log10 gross tonnage", "reference": "Tenfold lower gross tonnage"},
        {"label": "Gross tonnage unknown", "group": "Vessel characteristics", "definition": "Gross tonnage is zero or unavailable", "reference": "Gross tonnage recorded"},
        {"label": "Fishing vessel", "group": "Vessel category", "definition": "Vessel category = Fishing vessel", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Recreational vessel", "group": "Vessel category", "definition": "Vessel category = Recreational", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Small commercial vessel", "group": "Vessel category", "definition": "Small commercial vessel under 100 GT", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Other vessel category", "group": "Vessel category", "definition": "Other/assorted vessel category", "reference": "Merchant vessel ≥100 GT"},
        {"label": "Collision / contact", "group": "Occurrence event", "definition": "Main event is collision or contact", "reference": "Other event types"},
        {"label": "Grounding / stranding", "group": "Occurrence event", "definition": "Main event is grounding/stranding", "reference": "Other event types"},
        {"label": "Fire / explosion", "group": "Occurrence event", "definition": "Main event is fire/explosion", "reference": "Other event types"},
        {"label": "Flooding / foundering", "group": "Occurrence event", "definition": "Main event is flooding/foundering", "reference": "Other event types"},
        {"label": "Loss of control", "group": "Occurrence event", "definition": "Main event is loss of control", "reference": "Other event types"},
        {"label": "Multiple vessels involved", "group": "Occurrence context", "definition": "Occurrence contains more than one vessel record", "reference": "Single-vessel occurrence"},
        {"label": "Calendar year", "group": "Occurrence context", "definition": "One-year increase in reported year", "reference": "Previous calendar year"},
    ]
    occurrence_counts = Counter(clean(row.get("Occurrence_Id")) for row in vessels)
    known_ages = []
    known_logs = []
    for vessel in vessels:
        year = integer(vessel.get("Year_Reported"))
        built = integer(vessel.get("Year_Built"))
        if 1850 <= built <= year:
            known_ages.append(year - built)
        tonnage = number(vessel.get("GT_Gross_Tonnage")) or 0
        if tonnage > 0:
            known_logs.append(math.log10(tonnage))
    reference_age = sum(known_ages) / len(known_ages) if known_ages else 20.0
    reference_log = sum(known_logs) / len(known_logs) if known_logs else 3.0

    design: list[list[float]] = []
    outcomes: list[int] = []
    groups: list[str] = []
    for vessel in vessels:
        occurrence_id = clean(vessel.get("Occurrence_Id"))
        year = integer(vessel.get("Year_Reported")) or 2020
        built = integer(vessel.get("Year_Built"))
        age_unknown = not (1850 <= built <= year)
        age = reference_age if age_unknown else year - built
        tonnage = number(vessel.get("GT_Gross_Tonnage")) or 0
        tonnage_unknown = tonnage <= 0
        log_tonnage = reference_log if tonnage_unknown else math.log10(tonnage)
        category = clean(vessel.get("Vessel_Category_L1")).lower()
        event = clean(vessel.get("Main_Event_L1")).lower()
        damage = clean(vessel.get("Loss_Of_Vessel_Damage")).lower()
        features = [
            (age - reference_age) / 10,
            age_unknown,
            log_tonnage - reference_log,
            tonnage_unknown,
            category == "fishing vessel",
            category == "recreational (non commercial)",
            category.startswith("small commercial"),
            category == "other - assorted",
            event in {"collision", "contact"},
            event == "grounding / stranding",
            event == "fire / explosion",
            event == "flooding / foundering",
            event == "loss of control",
            occurrence_counts[occurrence_id] > 1,
            year - 2020,
        ]
        design.append([1.0] + [float(value) for value in features])
        outcomes.append(int(damage.startswith("material damage") or damage.startswith("loss of ship")))
        groups.append(occurrence_id)

    result = logistic_regression(design, outcomes, [item["label"] for item in specifications], groups=groups)
    result["specifications"] = specifications
    result["outcome_definition"] = "Material damage or loss of ship"
    result["reference_outcome"] = "No damage or minor damage"
    result["unit"] = "Vessel record"
    return result


def collision_pair_matrix(
    occurrences: list[dict[str, str]],
    vessels: list[dict[str, str]],
    persons: list[dict[str, str]],
) -> dict:
    occurrence_lookup = {clean(row.get("Occurrence_Id")): row for row in occurrences}
    vessels_by_occurrence: dict[str, list[dict[str, str]]] = defaultdict(list)
    people_by_occurrence: Counter = Counter()
    for vessel in vessels:
        vessels_by_occurrence[clean(vessel.get("Occurrence_Id"))].append(vessel)
    for person in persons:
        if is_injured_person(person) or is_fatal_person(person):
            people_by_occurrence[clean(person.get("Occurrence_Id"))] += 1

    categories = [
        "Merchant Vessel >= 100gt",
        "Fishing Vessel",
        "Small Commercial (under 100gt, excl. FVs)",
        "Recreational (non Commercial)",
        "Other - Assorted",
    ]
    pair_occurrences: dict[tuple[str, str], set[str]] = defaultdict(set)
    for occurrence_id, rows in vessels_by_occurrence.items():
        occurrence = occurrence_lookup.get(occurrence_id)
        if not occurrence or clean(occurrence.get("Main_Event_L1")).lower() != "collision" or len(rows) < 2:
            continue
        row_categories = [clean(row.get("Vessel_Category_L1")) or "Other - Assorted" for row in rows]
        pairs = set()
        for left in range(len(row_categories)):
            for right in range(left + 1, len(row_categories)):
                first, second = sorted((row_categories[left], row_categories[right]), key=lambda value: categories.index(value) if value in categories else 99)
                pairs.add((first, second))
        for pair in pairs:
            pair_occurrences[pair].add(occurrence_id)

    cells = []
    for first_index, first in enumerate(categories):
        for second in categories[first_index:]:
            ids = pair_occurrences.get((first, second), set())
            serious_count = sum(normalise_severity(clean(occurrence_lookup[item].get("Occurrence_Severity"))) in {"Serious", "Very serious"} for item in ids)
            casualties = sum(people_by_occurrence[item] for item in ids)
            low, high = wilson_interval(serious_count, len(ids))
            cells.append({
                "first": first,
                "second": second,
                "n": len(ids),
                "serious": serious_count,
                "serious_share": round(serious_count / len(ids), 4) if ids else 0,
                "ci_low": round(low, 4),
                "ci_high": round(high, 4),
                "casualties": casualties,
            })
    total_occurrences = len({item for ids in pair_occurrences.values() for item in ids})
    return {"categories": categories, "cells": cells, "collision_occurrences": total_occurrences}


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

    def age_band(vessel: dict[str, str]) -> str:
        built = integer(vessel.get("Year_Built"))
        event_year = integer(vessel.get("Year_Reported"))
        if built < 1850 or not event_year or built > event_year:
            return "Unknown"
        age = event_year - built
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
        "person_severity_model": person_severity_model(persons),
        "collision_pairs": collision_pair_matrix(occurrences, vessels, persons),
        "vessel_damage_model": vessel_damage_model(vessels),
        "person_flow": person_flow,
        "vessel_profile": vessel_profile,
        "notes": {
            "model": "Multivariable logistic regression of serious/very serious classification among reported occurrences. Odds ratios are adjusted for all displayed factors.",
            "person_model": "Person-level logistic regression of serious injury or death with occurrence-clustered standard errors and grouped cross-validation.",
            "collision": "Collision cells count unique occurrences containing each vessel-category pairing; an occurrence with more than two vessels can contribute to multiple pair cells.",
            "damage_model": "Vessel-level logistic regression of material damage or vessel loss with occurrence-clustered standard errors and grouped cross-validation.",
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
    condition = clean(row.get("Physical_Condition_L1")).lower()
    return condition in {"death (confirmed)", "missing (death presumed)"}


def is_injured_person(row: dict[str, str]) -> bool:
    return clean(row.get("Physical_Condition_L1")).lower() == "injured"


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
        "Natural light": "Natural_Light",
        "Weather": "Weather",
        "Visibility": "Visibility",
        "Wind force": "Wind_Force",
        "Sea state": "Sea_State",
        "Published report": "Published_Report_Website_Link",
    }
    missingness = []
    for label, field in key_fields.items():
        missing = sum(1 for row in occurrences if not clean(row.get(field)))
        unknown = sum(
            1
            for row in occurrences
            if "unknown" in clean(row.get(field)).lower()
            or "not recorded" in clean(row.get(field)).lower()
        )
        missingness.append(
            {
                "field": label,
                "missing": missing,
                "rate": round(100 * missing / len(occurrences), 1) if occurrences else 0,
                "unknown": unknown,
                "unknown_rate": round(100 * unknown / len(occurrences), 1) if occurrences else 0,
            }
        )

    duplicate_occurrences = len(occurrences) - len(occurrence_ids)
    unmatched_vessels = sum(1 for row in vessels if clean(row.get("Occurrence_Id")) not in occurrence_ids)
    unmatched_persons = sum(1 for row in persons if clean(row.get("Occurrence_Id")) not in occurrence_ids)
    report_count = sum(bool(clean(row.get("Published_Report_Website_Link"))) for row in occurrences)
    checks = [
        {"name": "Occurrence IDs are unique", "passed": duplicate_occurrences == 0, "value": duplicate_occurrences},
        {"name": "All vessel rows link to an occurrence", "passed": unmatched_vessels == 0, "value": unmatched_vessels},
        {"name": "All person rows link to an occurrence", "passed": unmatched_persons == 0, "value": unmatched_persons},
        {"name": "Serious outcomes are present", "passed": any(record["severity"] in {"Serious", "Very serious"} for record in records), "value": None},
        {"name": "Coordinates are within valid bounds", "passed": all(record["lat"] is None or (-90 <= record["lat"] <= 90 and -180 <= record["lon"] <= 180) for record in records), "value": None},
    ]
    failed_checks = [check["name"] for check in checks if not check["passed"]]
    if failed_checks:
        raise ValueError("Data quality checks failed: " + ", ".join(failed_checks))

    source_files = [
        {"name": name, "sha256": file_sha256(name), "rows": row_count}
        for name, row_count in (
            ("occurrences.csv", len(occurrences)),
            ("vessels.csv", len(vessels)),
            ("affected_persons.csv", len(persons)),
        )
    ]

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
            "source_files": source_files,
            "report_coverage": {
                "linked": report_count,
                "total": len(occurrences),
                "rate": round(report_count / len(occurrences), 4) if occurrences else 0,
            },
            "people_metrics": {
                "injury_definition": "Physical_Condition_L1 = Injured; vessel totals are used only when no person rows exist.",
                "fatality_definition": "Physical_Condition_L1 is Death (confirmed) or Missing (death presumed); vessel totals are used only when no person rows exist.",
                "presumed_deaths_included": True,
            },
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
            "checks": checks,
        },
        "analysis": consequence_analysis(occurrences, vessels, persons, vessel_by_occurrence),
        "records": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} with {len(records):,} occurrence records")


if __name__ == "__main__":
    main()

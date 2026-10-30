import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_data", ROOT / "scripts" / "build_data.py")
BUILD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(BUILD)

REFRESH_SPEC = importlib.util.spec_from_file_location("automated_refresh", ROOT / "scripts" / "automated_refresh.py")
REFRESH = importlib.util.module_from_spec(REFRESH_SPEC)
assert REFRESH_SPEC.loader
REFRESH_SPEC.loader.exec_module(REFRESH)

CONTEXT_REFRESH_SPEC = importlib.util.spec_from_file_location("refresh_context_data", ROOT / "scripts" / "refresh_context_data.py")
CONTEXT_REFRESH = importlib.util.module_from_spec(CONTEXT_REFRESH_SPEC)
assert CONTEXT_REFRESH_SPEC.loader
CONTEXT_REFRESH_SPEC.loader.exec_module(CONTEXT_REFRESH)


class PersonClassificationTests(unittest.TestCase):
    def test_injured_excludes_no_injury(self):
        self.assertTrue(BUILD.is_injured_person({"Physical_Condition_L1": "Injured"}))
        self.assertFalse(BUILD.is_injured_person({"Physical_Condition_L1": "No injury"}))

    def test_fatality_includes_confirmed_and_presumed(self):
        self.assertTrue(BUILD.is_fatal_person({"Physical_Condition_L1": "Death (confirmed)"}))
        self.assertTrue(BUILD.is_fatal_person({"Physical_Condition_L1": "Missing (death presumed)"}))
        self.assertFalse(BUILD.is_fatal_person({"Physical_Condition_L1": "Injured"}))


class StatisticalHelperTests(unittest.TestCase):
    def test_wilson_interval_contains_observed_share(self):
        low, high = BUILD.wilson_interval(25, 100)
        self.assertLess(low, 0.25)
        self.assertGreater(high, 0.25)

    def test_average_precision_rewards_correct_ranking(self):
        self.assertEqual(BUILD.average_precision([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]), 1.0)


class AutomatedRefreshTests(unittest.TestCase):
    def test_build_timestamp_does_not_trigger_publication(self):
        first = {"meta": {"built_at": "one", "year_max": 2026}, "records": [1]}
        second = {"meta": {"built_at": "two", "year_max": 2026}, "records": [1]}
        self.assertEqual(REFRESH.comparable_dashboard(first), REFRESH.comparable_dashboard(second))

    def test_analytical_change_triggers_publication(self):
        first = {"meta": {"built_at": "one"}, "records": [1]}
        second = {"meta": {"built_at": "two"}, "records": [1, 2]}
        self.assertNotEqual(REFRESH.comparable_dashboard(first), REFRESH.comparable_dashboard(second))

    def test_discovers_latest_port_table_link_from_official_page(self):
        html = '<a href="/media/current/port0499.ods">PORT0499</a>'
        self.assertEqual(
            CONTEXT_REFRESH.discover_port0499_url(html, "https://www.gov.uk/datasets/page"),
            "https://www.gov.uk/media/current/port0499.ods",
        )


class BuiltArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "dist" / "data" / "dashboard.json").read_text())

    def test_expected_row_counts(self):
        self.assertEqual(self.payload["quality"]["rows"]["occurrences"], 9063)
        self.assertEqual(self.payload["quality"]["rows"]["vessels"], 9830)
        self.assertEqual(self.payload["quality"]["rows"]["affected_people"], 3040)

    def test_corrected_people_metrics(self):
        self.assertEqual(sum(row["injuries"] for row in self.payload["records"]), 2400)
        self.assertEqual(sum(row["fatalities"] for row in self.payload["records"]), 183)

    def test_release_checks_and_model_validation(self):
        self.assertTrue(all(check["passed"] for check in self.payload["quality"]["checks"]))
        model = self.payload["analysis"]["severity_model"]
        self.assertTrue(model["converged"])
        self.assertEqual(model["validation"]["folds"], 5)
        self.assertGreater(model["validation"]["auc"], 0.5)

    def test_deep_models_and_collision_pairs(self):
        analysis = self.payload["analysis"]
        person_model = analysis["person_severity_model"]
        damage_model = analysis["vessel_damage_model"]
        self.assertTrue(person_model["converged"])
        self.assertEqual(person_model["n"], 3040)
        self.assertGreater(person_model["validation"]["auc"], 0.7)
        self.assertEqual(person_model["standard_errors"], "Occurrence-clustered sandwich")
        self.assertTrue(damage_model["converged"])
        self.assertEqual(damage_model["n"], 9830)
        self.assertGreater(damage_model["validation"]["auc"], 0.7)
        self.assertEqual(damage_model["standard_errors"], "Occurrence-clustered sandwich")
        self.assertGreaterEqual(analysis["collision_pairs"]["collision_occurrences"], 500)


class ContextArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "dist" / "data" / "context.json").read_text())

    def test_port_context_has_overlap_years(self):
        self.assertEqual(set(self.payload["ports"]["by_year"]), {"2020", "2021", "2022", "2023", "2024"})

    def test_port_values_are_converted_to_tonnes(self):
        london_2024 = next(row for row in self.payload["ports"]["by_year"]["2024"] if row["port"] == "London")
        self.assertGreater(london_2024["tonnes"], 50_000_000)


if __name__ == "__main__":
    unittest.main()

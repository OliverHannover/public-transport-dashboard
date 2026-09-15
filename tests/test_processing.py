"""Behavioral tests without a Home Assistant installation."""

import importlib.util
import sys
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

PATH = Path(__file__).parents[1] / "custom_components/public_transport_dashboard/processing.py"
package = ModuleType("ptd_processing_unit")
package.__path__ = [str(PATH.parent)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + ".processing", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
if PATH.exists():
    spec.loader.exec_module(module)
NOW = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


def row(**changes):
    result = {
        "line": "R9",
        "destination": "Central Hauptbahnhof",
        "planned_time": "2026-09-14T12:05:00+02:00",
        "departure_time": "2026-09-14T12:07:00+02:00",
        "delay": 2,
        "platform": "2",
        "transportation_type": "suburban",
        "minutes_until_departure": 7,
        "agency": "Operator A",
    }
    result.update(changes)
    return result


class ProcessingTests(unittest.TestCase):
    def board(self, sources, groups=None, **kwargs):
        self.assertTrue(hasattr(module, "build_departures"), "Processor not implemented")
        return module.build_departures(sources, groups or {}, NOW, UTC, **kwargs)

    def test_operator_duplicates_preserve_fields(self):
        result = self.board({"sensor.a": [row(), row(agency="Operator B", line="r9")]})
        self.assertEqual(len(result.departures), 1)
        dep = result.departures[0]
        self.assertEqual((dep["delay"], dep["platform"], dep["minutes_until_departure"]), (2, "2", 7))
        self.assertEqual(dep["transportation_type"], "suburban")
        self.assertEqual(dep["destination_short"], "Central Hbf")
        self.assertEqual(dep["agencies"], ["Operator A", "Operator B"])
        self.assertEqual(result.duplicates_removed, 1)

    def test_stops_separate_unless_grouped(self):
        sources = {"sensor.a": [row()], "sensor.b": [row()]}
        self.assertEqual(len(self.board(sources).departures), 2)
        result = self.board(sources, {"sensor.a": "North Station", "sensor.b": "North Station"})
        self.assertEqual(len(result.departures), 1)
        self.assertEqual(result.departures[0]["source_entities"], ["sensor.a", "sensor.b"])

    def test_priority_and_actual_sort(self):
        result = self.board(
            {
                "sensor.a": [
                    row(departure_time="2026-09-14T10:12:00Z", delay=7),
                    row(line="600", departure_time="2026-09-14T10:06:00Z"),
                ],
                "sensor.b": [row()],
            },
            {"sensor.a": "stop", "sensor.b": "stop"},
        )
        self.assertEqual([d["line"] for d in result.departures], ["600", "R9"])
        self.assertEqual(result.departures[1]["delay"], 7)

    def test_countdown_preserves_source_value(self):
        dep = self.board({"sensor.a": [row(minutes_until_departure=99)]}).departures[0]
        self.assertEqual(dep["minutes_until_departure"], 99)
        self.assertEqual(dep["countdown_minutes"], 7)

    def test_invalid_and_past(self):
        result = self.board(
            {
                "sensor.a": [
                    None,
                    {},
                    row(departure_time="bad"),
                    row(departure_time="2026-09-14T09:59:00Z", planned_time="2026-09-14T09:57:00Z"),
                    row(),
                ]
            }
        )
        self.assertEqual(len(result.departures), 1)
        self.assertEqual(result.invalid_rows, 3)

    def test_missing_actual_uses_plan_and_delay(self):
        dep = self.board({"sensor.a": [row(departure_time=None)]}).departures[0]
        self.assertEqual(dep["departure_time"], "2026-09-14T10:07:00+00:00")

    def test_unknown_delay_is_not_zero(self):
        dep = self.board({"sensor.a": [row(delay=None, planned_time=None)]}).departures[0]
        self.assertIsNone(dep["delay"])

    def test_plan_only_does_not_claim_punctuality(self):
        dep = self.board({"sensor.a": [row(delay=None, departure_time=None)]}).departures[0]
        self.assertIsNone(dep["delay"])

    def test_distinct_planned_times_survive(self):
        result = self.board({"sensor.a": [row(), row(planned_time="2026-09-14T12:06:00+02:00")]})
        self.assertEqual(len(result.departures), 2)

    def test_seconds_normalized(self):
        dep = self.board({"sensor.a": [row(delay=120)]}, delay_unit="seconds").departures[0]
        self.assertEqual(dep["delay"], 2)

    def test_horizon_and_limit(self):
        self.assertEqual(self.board({"sensor.a": [row()]}, horizon=5).departures, [])
        result = self.board({"sensor.a": [row(), row(line="600")]}, limit=1)
        self.assertEqual(len(result.departures), 1)

    def test_naive_timestamp_uses_ha_timezone(self):
        self.assertTrue(hasattr(module, "build_departures"), "Processor not implemented")
        result = module.build_departures(
            {"sensor.a": [row(departure_time="2026-09-14T12:07:00")]}, {}, NOW, timezone(timedelta(hours=2))
        )
        self.assertEqual(result.departures[0]["countdown_minutes"], 7)

    def test_nonfinite_numbers_do_not_escape(self):
        dep = self.board(
            {"sensor.a": [row(delay=float("nan"), minutes_until_departure=float("inf"))]}
        ).departures[0]
        self.assertEqual(dep["delay"], 2)
        self.assertIsNone(dep["minutes_until_departure"])

    def test_different_modes_with_same_line_are_distinct_services(self):
        result = self.board({"sensor.a": [row(transportation_type="bus"), row(transportation_type="tram")]})
        self.assertEqual(len(result.departures), 2)

    def test_mode_aliases_do_not_split_identical_train(self):
        result = self.board(
            {"sensor.a": [row(transportation_type="train"), row(transportation_type="suburban")]}
        )
        self.assertEqual(len(result.departures), 1)

    def test_known_delay_recovers_missing_plan_for_deduplication(self):
        result = self.board(
            {
                "sensor.a": [row()],
                "sensor.b": [row(planned_time=None, delay=6, departure_time="2026-09-14T10:11:00Z")],
            },
            {"sensor.a": "North", "sensor.b": "North"},
        )
        self.assertEqual(len(result.departures), 1)
        self.assertEqual(result.departures[0]["delay"], 2)

    def test_missing_plans_with_different_live_times_merge(self):
        result = self.board(
            {
                "sensor.a": [
                    row(planned_time=None, delay=2),
                    row(planned_time=None, delay=6, departure_time="2026-09-14T10:11:00Z"),
                ]
            }
        )
        self.assertEqual(len(result.departures), 1)
        self.assertEqual(result.departures[0]["planned_time"], "2026-09-14T10:05:00+00:00")

    def test_different_unknown_mode_names_do_not_collapse(self):
        result = self.board({"sensor.a": [row(transportation_type="cable"), row(transportation_type="taxi")]})
        self.assertEqual(len(result.departures), 2)

    def test_datetime_fraction_is_sorted_numerically(self):
        result = self.board(
            {
                "sensor.a": [
                    row(line="A", departure_time="2026-09-14T10:07:00.500000+00:00"),
                    row(line="B", departure_time="2026-09-14T10:07:00+00:00"),
                ]
            }
        )
        self.assertEqual([d["line"] for d in result.departures], ["B", "A"])

    def test_non_list_source_does_not_abort_other_sources(self):
        for invalid in (None, "unavailable", "unknown", {}, 12):
            with self.subTest(invalid=invalid):
                result = self.board({"sensor.bad": invalid, "sensor.good": [row()]})
                self.assertEqual(len(result.departures), 1)

    def test_empty_and_missing_fields(self):
        self.assertEqual(self.board({}).departures, [])
        self.assertEqual(self.board({"sensor.empty": []}).departures, [])
        for field in ("line", "destination"):
            result = self.board({"sensor.bad": [row(**{field: None})]})
            self.assertEqual(result.departures, [])
            self.assertEqual(result.invalid_rows, 1)

    def test_invalid_timestamps_never_escape(self):
        for value in (
            "2026-09-14",
            "12:30",
            "2026-09-14T25:61:00Z",
            "2026-99-99T12:00:00Z",
            {},
            [],
            False,
            1000,
        ):
            with self.subTest(value=value):
                result = self.board({"sensor.a": [row(departure_time=value)]})
                self.assertEqual(result.departures, [])
                self.assertEqual(result.invalid_rows, 1)

    def test_oversized_scalar_does_not_crash(self):
        result = self.board({"sensor.a": [row(line=10**5000), row()]})
        self.assertEqual(len(result.departures), 1)

    def test_recovered_plan_overflow_is_ignored_safely(self):
        result = self.board({"sensor.a": [row(planned_time=None, delay=1e300)]})
        self.assertEqual(len(result.departures), 1)
        self.assertIsNone(result.departures[0]["planned_time"])

    def test_prepared_board_is_reusable_without_mutating_old_state(self):
        self.assertTrue(hasattr(module, "prepare_departures"), "Reusable normalization is missing")
        prepared = module.prepare_departures({"sensor.a": [row()]}, {}, UTC)
        first = prepared.at(NOW)
        second = prepared.at(NOW + timedelta(minutes=2))
        self.assertEqual(first.departures[0]["countdown_minutes"], 7)
        self.assertEqual(second.departures[0]["countdown_minutes"], 5)
        self.assertEqual(prepared.at(NOW + timedelta(minutes=8)).departures, [])

    def test_input_is_not_modified(self):
        import copy

        sources = {"sensor.a": [row(), row(agency="Alternate")]}
        original = copy.deepcopy(sources)
        self.board(sources)
        self.assertEqual(sources, original)

    def test_hundreds_of_departures_remain_sorted_and_deduplicated(self):
        rows = [
            row(
                line=str(index),
                planned_time=(NOW + timedelta(minutes=index + 1)).isoformat(),
                departure_time=(NOW + timedelta(minutes=index + 3)).isoformat(),
            )
            for index in range(500)
        ]
        result = self.board(
            {"sensor.a": list(reversed(rows)), "sensor.b": rows},
            {"sensor.a": "North", "sensor.b": "North"},
            limit=500,
            horizon=1440,
        )
        self.assertEqual(len(result.departures), 500)
        self.assertEqual(result.duplicates_removed, 500)
        self.assertEqual(result.departures[0]["line"], "0")
        self.assertEqual(result.departures[-1]["line"], "499")


if __name__ == "__main__":
    unittest.main()

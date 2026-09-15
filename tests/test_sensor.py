"""Sensor business logic tests; HA runtime boundaries are deliberately stubbed.

These tests complement, but do not replace, tests/ha on real Home Assistant.
"""

import copy
import importlib
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

NOW = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


class EntityBoundary:
    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, remove):
        pass

    def async_write_ha_state(self):
        self.writes.append(copy.deepcopy(self._attr_extra_state_attributes))


def _module(name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    return module


def _load_sensor():
    package = _module("ptd_sensor_unit")
    package.__path__ = [str(Path(__file__).parents[1] / "custom_components/public_transport_dashboard")]
    dt = SimpleNamespace(UTC=UTC, utcnow=lambda: NOW, get_time_zone=lambda name: UTC)
    modules = {
        "ptd_sensor_unit": package,
        "homeassistant": _module("homeassistant"),
        "homeassistant.components": _module("homeassistant.components"),
        "homeassistant.components.sensor": _module(
            "homeassistant.components.sensor", SensorEntity=EntityBoundary
        ),
        "homeassistant.config_entries": _module("homeassistant.config_entries", ConfigEntry=SimpleNamespace),
        "homeassistant.const": _module(
            "homeassistant.const", STATE_UNAVAILABLE="unavailable", STATE_UNKNOWN="unknown"
        ),
        "homeassistant.core": _module(
            "homeassistant.core",
            Event=SimpleNamespace,
            HomeAssistant=SimpleNamespace,
            callback=lambda function: function,
        ),
        "homeassistant.helpers": _module("homeassistant.helpers"),
        "homeassistant.helpers.entity_platform": _module(
            "homeassistant.helpers.entity_platform", AddEntitiesCallback=object
        ),
        "homeassistant.helpers.event": _module(
            "homeassistant.helpers.event",
            async_track_state_change_event=lambda *args: lambda: None,
            async_track_time_interval=lambda *args: lambda: None,
        ),
        "homeassistant.util": _module("homeassistant.util", dt=dt),
    }
    with patch.dict(sys.modules, modules):
        return importlib.import_module("ptd_sensor_unit.sensor")


sensor_module = _load_sensor()


def departure(**changes):
    row = {
        "line": "R9",
        "destination": "Central Station",
        "transportation_type": "train",
        "departure_time": "2026-09-14T10:07:00Z",
        "planned_time": "2026-09-14T10:05:00Z",
        "delay": 2,
        "minutes_until_departure": 7,
    }
    row.update(changes)
    return row


def source(value="1", attrs=None, reported=NOW):
    return SimpleNamespace(
        state=value,
        attributes=attrs if attrs is not None else {},
        last_reported=reported,
        last_updated=reported,
    )


class SensorTests(unittest.TestCase):
    def setUp(self):
        self.states = {"sensor.a": source(attrs={"departures": [departure()]})}
        entry = SimpleNamespace(
            entry_id="entry",
            data={"source_entities": ["sensor.a"], "source_settings": {}, "stale_after": 15},
            options={},
        )
        self.sensor = sensor_module.DepartureSensor(entry)
        self.sensor.hass = SimpleNamespace(states=self.states, config=SimpleNamespace(time_zone="UTC"))
        self.sensor.writes = []
        self.sensor._refresh(NOW)

    def test_unavailable_unknown_and_missing_clear_departures(self):
        for value in ("unavailable", "unknown", None):
            with self.subTest(value=value):
                self.states["sensor.a"] = source(value) if value else None
                self.sensor._source_changed(SimpleNamespace())
                self.assertFalse(self.sensor._attr_available)
                self.assertEqual(self.sensor._attr_extra_state_attributes["departures"], [])
                self.assertEqual(
                    self.sensor._attr_extra_state_attributes["source_issues"], {"sensor.a": "unavailable"}
                )

    def test_invalid_attribute_containers_do_not_crash(self):
        for value in (None, {}, "unknown", 42):
            with self.subTest(value=value):
                self.states["sensor.a"] = source(attrs={"departures": value})
                self.sensor._source_changed(SimpleNamespace())
                self.assertFalse(self.sensor._attr_available)
                self.assertEqual(
                    self.sensor._attr_extra_state_attributes["source_issues"],
                    {"sensor.a": "invalid_departures"},
                )

    def test_missing_attribute_and_empty_list_differ(self):
        self.states["sensor.a"] = source()
        self.sensor._source_changed(SimpleNamespace())
        self.assertFalse(self.sensor._attr_available)
        self.states["sensor.a"] = source(attrs={"departures": []})
        self.sensor._source_changed(SimpleNamespace())
        self.assertTrue(self.sensor._attr_available)
        self.assertEqual(self.sensor._attr_native_value, 0)

    def test_unchanged_tick_does_not_write(self):
        self.sensor._tick(NOW)
        self.assertEqual(self.sensor.writes, [])

    def test_unrelated_source_attribute_does_not_write(self):
        self.states["sensor.a"] = source(attrs={"departures": [departure()], "friendly_name": "Renamed"})
        self.sensor._source_changed(SimpleNamespace())
        self.assertEqual(self.sensor.writes, [])

    def test_countdown_updates_without_re_normalizing(self):
        self.assertTrue(hasattr(sensor_module, "prepare_departures"), "No reusable schedule cache")
        with patch.object(
            sensor_module, "prepare_departures", side_effect=AssertionError("Unnecessary normalization")
        ):
            self.sensor._tick(NOW + timedelta(minutes=2))
        self.assertEqual(self.sensor.writes[-1]["departures"][0]["countdown_minutes"], 5)

    def test_real_time_change_invalidates_cache(self):
        self.states["sensor.a"] = source(
            attrs={"departures": [departure(departure_time="2026-09-14T10:09:00Z", delay=4)]}
        )
        self.sensor._source_changed(SimpleNamespace())
        self.assertEqual(self.sensor.writes[-1]["departures"][0]["countdown_minutes"], 9)
        self.assertEqual(self.sensor.writes[-1]["departures"][0]["delay"], 4)

    def test_stale_source_is_removed_and_fresh_report_recovers(self):
        self.sensor._tick(NOW + timedelta(minutes=16))
        self.assertFalse(self.sensor._attr_available)
        self.assertEqual(self.sensor._attr_extra_state_attributes["source_issues"], {"sensor.a": "stale"})
        self.states["sensor.a"] = source(
            attrs={"departures": [departure()]}, reported=NOW + timedelta(minutes=1)
        )
        self.sensor._tick(NOW + timedelta(minutes=1))
        self.assertTrue(self.sensor._attr_available)
        self.assertEqual(self.sensor._attr_native_value, 1)

    def test_malformed_row_is_skipped_but_valid_departure_survives(self):
        self.states["sensor.a"] = source(attrs={"departures": [None, {}, departure()]})
        self.sensor._source_changed(SimpleNamespace())
        self.assertEqual(self.sensor._attr_native_value, 1)
        self.assertEqual(self.sensor._attr_extra_state_attributes["invalid_rows"], 2)

    def test_old_written_snapshot_is_not_mutated(self):
        self.sensor._tick(NOW + timedelta(minutes=1))
        self.sensor._tick(NOW + timedelta(minutes=2))
        self.assertEqual(self.sensor.writes[0]["departures"][0]["countdown_minutes"], 6)
        self.assertEqual(self.sensor.writes[1]["departures"][0]["countdown_minutes"], 5)

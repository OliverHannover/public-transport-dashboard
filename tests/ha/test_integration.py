"""Run on Linux with pytest-homeassistant-custom-component."""

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

DOMAIN = "public_transport_dashboard"


@pytest.mark.parametrize(
    "value,attributes,available,count",
    [
        ("unavailable", {}, False, None),
        ("unknown", {}, False, None),
        ("0", {}, False, None),
        ("0", {"departures": None}, False, None),
        ("0", {"departures": "bad"}, False, None),
        ("0", {"departures": []}, True, "0"),
        ("1", {"departures": [None, {}, {"line": "R9", "departure_time": "bad"}]}, True, "0"),
    ],
)
async def test_bad_source_states_do_not_prevent_setup(hass, value, attributes, available, count):
    hass.states.async_set("sensor.source", value, attributes)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Public Transport Dashboard",
        unique_id=DOMAIN,
        data={"source_entities": ["sensor.source"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.public_transport_dashboard")
    assert state is not None
    assert state.state == (count if available else STATE_UNAVAILABLE)
    assert state.attributes["departures"] == []


async def test_source_names_cannot_collide_with_unit_fields(hass):
    hass.states.async_set("sensor.foo", 0, {"departures": []})
    hass.states.async_set("sensor.foo_unit", 0, {"departures": []})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"source_entities": ["sensor.foo", "sensor.foo_unit"]}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "group:sensor.foo": "First stop",
            "unit:sensor.foo": "seconds",
            "group:sensor.foo_unit": "Second stop",
            "unit:sensor.foo_unit": "minutes",
        },
    )
    assert flow["type"] == "create_entry"
    assert flow["data"]["source_settings"]["sensor.foo"] == {"group": "First stop", "delay_unit": "seconds"}
    assert flow["data"]["source_settings"]["sensor.foo_unit"] == {
        "group": "Second stop",
        "delay_unit": "minutes",
    }


async def test_flow_rejects_invalid_source_and_sets_up(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source_entities": ["sensor.missing"]}
    )
    assert bad["errors"] == {"base": "invalid_source"}
    hass.states.async_set("sensor.station", 0, {"departures": []})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source_entities": ["sensor.station"]}
    )
    assert result["step_id"] == "details"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.public_transport_dashboard").state == "0"
    duplicate = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert duplicate["type"] == "abort"


async def test_updates_partial_failure_options_and_unload(hass):
    now = dt_util.utcnow()
    departure = {
        "line": "R9",
        "destination": "Central Hauptbahnhof",
        "departure_time": (now + timedelta(minutes=8)).isoformat(),
        "planned_time": (now + timedelta(minutes=6)).isoformat(),
        "delay": 2,
        "minutes_until_departure": 8,
    }
    hass.states.async_set("sensor.a", 1, {"departures": [departure]})
    hass.states.async_set("sensor.b", STATE_UNAVAILABLE)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Public Transport Dashboard",
        data={"source_entities": ["sensor.a", "sensor.b"], "source_settings": {}, "stale_after": 15},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.public_transport_dashboard")
    assert sensor.state == "1"
    assert sensor.attributes["source_issues"] == {"sensor.b": "unavailable"}
    async_fire_time_changed(hass, now + timedelta(minutes=2))
    await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).attributes["departures"][0]["countdown_minutes"] <= 6
    hass.states.async_set("sensor.a", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).state == STATE_UNAVAILABLE
    assert hass.states.get(sensor.entity_id).attributes["departures"] == []
    hass.states.async_set("sensor.a", 0, {"departures": []})
    await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).state == "0"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"source_entities": ["sensor.a"], "max_departures": 10}
    )
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {})
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["max_departures"] == 10
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED

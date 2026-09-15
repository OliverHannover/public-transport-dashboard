"""Event-driven sensor with local countdown and source health reporting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DEFAULT_HORIZON, DEFAULT_LIMIT, DEFAULT_STALE, DOMAIN
from .processing import PreparedBoard, prepare_departures

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DepartureSensor(entry)])


class DepartureSensor(SensorEntity):
    """Expose one aggregate board while keeping normalization out of clock ticks."""

    _attr_has_entity_name = True
    _attr_translation_key = "departures"
    _attr_icon = "mdi:public-transport"
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"departures", "source_issues", "source_entities"})

    def __init__(self, entry: ConfigEntry) -> None:
        """Keep stable identifiers and prepare immutable configuration lookups."""
        self._attr_unique_id = f"{entry.entry_id}_departures"
        self.entity_id = f"sensor.{DOMAIN}"
        self._settings = {**entry.data, **entry.options}
        self._sources: list[str] = self._settings["source_entities"]
        settings = self._settings.get("source_settings", {})
        self._groups = {entity: value.get("group", "") for entity, value in settings.items()}
        self._delay_units = {entity: value.get("delay_unit", "minutes") for entity, value in settings.items()}
        self._cached_sources: dict[str, list[Any]] | None = None
        self._cached_timezone: str | None = None
        self._prepared = PreparedBoard([])
        self._attr_available = False
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"departures": []}

    async def async_added_to_hass(self) -> None:
        """Register one source subscription and one clock; both unload with the entity."""
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(self.hass, self._sources, self._source_changed))
        self.async_on_remove(async_track_time_interval(self.hass, self._tick, UPDATE_INTERVAL))
        self._refresh(dt_util.utcnow())

    @callback
    def _source_changed(self, event: Event) -> None:
        if self._refresh(dt_util.utcnow()):
            self.async_write_ha_state()

    @callback
    def _tick(self, now: datetime) -> None:
        if self._refresh(now):
            self.async_write_ha_state()

    @callback
    def _refresh(self, now: datetime) -> bool:
        """Refresh health/window; return whether the exposed state actually changed."""
        sources: dict[str, list[Any]] = {}
        issues: dict[str, str] = {}
        stale_after = self._settings.get("stale_after", DEFAULT_STALE)
        for entity in self._sources:
            state = self.hass.states.get(entity)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                issues[entity] = "unavailable"
            elif not isinstance(state.attributes.get("departures"), list):
                issues[entity] = "invalid_departures"
            elif stale_after and (now - state.last_reported).total_seconds() > stale_after * 60:
                issues[entity] = "stale"
            else:
                sources[entity] = state.attributes["departures"]
        timezone_name = self.hass.config.time_zone
        if sources != self._cached_sources or timezone_name != self._cached_timezone:
            self._prepared = prepare_departures(
                sources,
                self._groups,
                dt_util.get_time_zone(timezone_name) or dt_util.UTC,
                delay_units=self._delay_units,
            )
            self._cached_sources = sources
            self._cached_timezone = timezone_name
        board = self._prepared.at(
            now,
            limit=self._settings.get("max_departures", DEFAULT_LIMIT),
            horizon=self._settings.get("horizon", DEFAULT_HORIZON),
        )
        attributes = {
            "departures": board.departures,
            "source_entities": self._sources,
            "source_issues": issues,
            "duplicates_removed": board.duplicates_removed,
            "invalid_rows": board.invalid_rows,
            "active_sources": len(sources),
        }
        available = bool(sources)
        if self._attr_available == available and self._attr_extra_state_attributes == attributes:
            return False
        if issues != self._attr_extra_state_attributes.get("source_issues", {}):
            _LOGGER.debug("Source health changed: %s", issues)
        self._attr_available = available
        self._attr_native_value = len(board.departures)
        self._attr_extra_state_attributes = attributes
        return True

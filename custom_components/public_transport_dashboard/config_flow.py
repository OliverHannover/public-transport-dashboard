"""UI-only setup and options for a single aggregate departure board."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DEFAULT_HORIZON, DEFAULT_LIMIT, DEFAULT_STALE, DOMAIN, NAME


def _schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                "source_entities", default=values.get("source_entities", [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Required("max_departures", default=values.get("max_departures", DEFAULT_LIMIT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=200)
            ),
            vol.Required("horizon", default=values.get("horizon", DEFAULT_HORIZON)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=1440)
            ),
            vol.Required("stale_after", default=values.get("stale_after", DEFAULT_STALE)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=1440)
            ),
        }
    )


class BoardFlow:
    """Shared two-step form; both HA flow classes supply hass and form methods."""

    _pending: dict[str, Any]
    _previous: dict[str, Any]

    async def _sources(self, user_input: dict[str, Any] | None, step: str) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = list(dict.fromkeys(user_input.get("source_entities", [])))
            registry = er.async_get(self.hass)
            valid = bool(entities)
            for entity in entities:
                state = self.hass.states.get(entity)
                registered = registry.async_get(entity)
                invalid_entity = (
                    not entity.startswith("sensor.")
                    or (registered and registered.platform == DOMAIN)
                    or entity == "sensor.public_transport_dashboard"
                )
                invalid_new_source = (
                    state is None or not isinstance(state.attributes.get("departures"), list)
                ) and entity not in self._previous.get("source_entities", [])
                if invalid_entity or invalid_new_source:
                    valid = False
            if valid:
                self._pending = {
                    "source_entities": entities,
                    "max_departures": user_input.get("max_departures", DEFAULT_LIMIT),
                    "horizon": user_input.get("horizon", DEFAULT_HORIZON),
                    "stale_after": user_input.get("stale_after", DEFAULT_STALE),
                }
                return await self.async_step_details()
            errors["base"] = "invalid_source"
        return self.async_show_form(
            step_id=step, data_schema=_schema(user_input or self._previous), errors=errors
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entities = self._pending["source_entities"]
        previous = self._previous.get("source_settings", {})
        if user_input is not None:
            self._pending["source_settings"] = {
                entity: {
                    "group": str(
                        user_input.get("group:" + entity, previous.get(entity, {}).get("group", ""))
                    ).strip(),
                    "delay_unit": user_input.get(
                        "unit:" + entity, previous.get(entity, {}).get("delay_unit", "minutes")
                    ),
                }
                for entity in entities
            }
            return self.async_create_entry(title=NAME, data=self._pending)
        fields: dict[Any, Any] = {}
        for entity in entities:
            settings = previous.get(entity, {})
            fields[vol.Optional("group:" + entity, default=settings.get("group", ""))] = str
            fields[vol.Required("unit:" + entity, default=settings.get("delay_unit", "minutes"))] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["minutes", "seconds"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="delay_unit",
                    )
                )
            )
        return self.async_show_form(step_id="details", data_schema=vol.Schema(fields))


class ConfigFlow(BoardFlow, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        self._previous = {}
        return await self._sources(user_input, "user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        return OptionsFlow()


class OptionsFlow(BoardFlow, config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._previous = {**self.config_entry.data, **self.config_entry.options}
        return await self._sources(user_input, "init")

"""Diagnostics: dump the live data points so users can build a profile."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LOCAL_KEY, DOMAIN

_REDACT = {CONF_LOCAL_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator = runtime.coordinator
    try:
        live = await coordinator.async_dump_dps()
    except Exception as err:  # noqa: BLE001
        live = {"error": str(err)}
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), _REDACT),
            "options": async_redact_data(dict(entry.options), _REDACT),
        },
        "available": coordinator.available,
        "profile": runtime.profile.id if runtime.profile else None,
        "cached_dps": coordinator.dps,
        "live_dps": live,
    }

"""Switch platform for Tuya-LAN profiles."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "switch", TuyaLanSwitch, async_add_entities)


class TuyaLanSwitch(TuyaLanEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        value = self._value("switch")
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set("switch", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set("switch", False)

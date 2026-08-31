"""Fan platform for Tuya-LAN profiles.

DP roles: ``switch`` (bool), optional ``percentage`` (int) or ``preset`` (enum).
"""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "fan", TuyaLanFan, async_add_entities)


class TuyaLanFan(TuyaLanEntity, FanEntity):
    def __init__(self, coordinator, description, entry_title) -> None:
        super().__init__(coordinator, description, entry_title)
        opts = self.options
        self._speed_range = (1, int(opts.get("speed_count", 3)))
        self._attr_supported_features = FanEntityFeature(0)
        if self._dp("percentage"):
            self._attr_supported_features |= FanEntityFeature.SET_SPEED
        if hasattr(FanEntityFeature, "TURN_ON"):
            self._attr_supported_features |= FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    @property
    def is_on(self) -> bool | None:
        value = self._value("switch")
        return None if value is None else bool(value)

    @property
    def percentage(self) -> int | None:
        raw = self._value("percentage")
        if raw is None:
            return None
        try:
            return ranged_value_to_percentage(self._speed_range, int(raw))
        except (TypeError, ValueError):
            return None

    @property
    def speed_count(self) -> int:
        return self._speed_range[1]

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self._set("switch", False)
            return
        raw = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        updates: dict[str, Any] = {}
        if (switch := self._dp("switch")) is not None:
            updates[switch] = True
        updates[self._dp("percentage")] = raw
        await self.coordinator.async_set_dps(updates)

    async def async_turn_on(self, *args: Any, **kwargs: Any) -> None:
        await self._set("switch", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set("switch", False)

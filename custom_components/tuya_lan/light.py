"""Light platform for Tuya-LAN profiles.

Supported DP roles: ``switch`` (bool), ``brightness`` (int scale), ``color_temp``
(int scale), ``color`` (Tuya HSV hex string, v3.3+ format).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "light", TuyaLanLight, async_add_entities)


class TuyaLanLight(TuyaLanEntity, LightEntity):
    def __init__(self, coordinator, description, entry_title) -> None:  # noqa: ANN001
        super().__init__(coordinator, description, entry_title)
        opts = self.options
        self._b_min = int(opts.get("brightness_min", 10))
        self._b_max = int(opts.get("brightness_max", 255))
        if self._dp("brightness"):
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool | None:
        value = self._value("switch")
        return None if value is None else bool(value)

    @property
    def brightness(self) -> int | None:
        raw = self._value("brightness")
        if raw is None:
            return None
        span = max(self._b_max - self._b_min, 1)
        return round(max(0, (int(raw) - self._b_min)) / span * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        updates: dict[str, Any] = {}
        if (switch := self._dp("switch")) is not None:
            updates[switch] = True
        if ATTR_BRIGHTNESS in kwargs and (bri := self._dp("brightness")) is not None:
            span = self._b_max - self._b_min
            updates[bri] = round(self._b_min + kwargs[ATTR_BRIGHTNESS] / 255 * span)
        await self.coordinator.async_set_dps(updates)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set("switch", False)

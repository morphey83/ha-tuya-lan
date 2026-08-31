"""Cover platform for Tuya-LAN profiles.

DP roles: ``command`` (enum: open/stop/close strings), optional ``position``
(0-100, some devices invert - set ``options.invert: true``).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "cover", TuyaLanCover, async_add_entities)


class TuyaLanCover(TuyaLanEntity, CoverEntity):
    def __init__(self, coordinator, description, entry_title) -> None:
        super().__init__(coordinator, description, entry_title)
        opts = self.options
        self._cmd = {
            "open": opts.get("open_cmd", "open"),
            "close": opts.get("close_cmd", "close"),
            "stop": opts.get("stop_cmd", "stop"),
        }
        self._invert = bool(opts.get("invert", False))
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        if self._dp("position"):
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION

    def _pos(self, raw: Any) -> int | None:
        if raw is None:
            return None
        try:
            val = int(raw)
        except (TypeError, ValueError):
            return None
        return 100 - val if self._invert else val

    @property
    def current_cover_position(self) -> int | None:
        return self._pos(self._value("position"))

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        return None if pos is None else pos <= 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._set("command", self._cmd["open"])

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._set("command", self._cmd["close"])

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._set("command", self._cmd["stop"])

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        target = int(kwargs[ATTR_POSITION])
        await self._set("position", 100 - target if self._invert else target)

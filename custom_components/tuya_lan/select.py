"""Select platform for Tuya-LAN profiles.

``options`` in the profile is a mapping of HA option label -> raw DP value::

    - platform: select
      name: Mode
      dps: { select: "4" }
      options:
        map: { Auto: "0", Manual: "1", Away: "2" }
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "select", TuyaLanSelect, async_add_entities)


class TuyaLanSelect(TuyaLanEntity, SelectEntity):
    def __init__(self, coordinator, description, entry_title) -> None:
        super().__init__(coordinator, description, entry_title)
        self._map: dict[str, object] = dict(self.dp_options.get("map", {}))
        self._rev = {str(v): k for k, v in self._map.items()}
        self._attr_options = list(self._map)

    @property
    def current_option(self) -> str | None:
        raw = self._value("select")
        return self._rev.get(str(raw))

    async def async_select_option(self, option: str) -> None:
        if option not in self._map:
            raise ValueError(f"{option!r} is not a valid option")
        await self._set("select", self._map[option])

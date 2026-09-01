"""Button platform - fires a fixed value at a DP (e.g. reset, boost)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "button", TuyaLanButton, async_add_entities)


class TuyaLanButton(TuyaLanEntity, ButtonEntity):
    async def async_press(self) -> None:
        value = self.dp_options.get("press_value", True)
        await self._set("button", value)

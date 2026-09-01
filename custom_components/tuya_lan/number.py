"""Number platform for Tuya-LAN profiles."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform, scale_from_device, scale_to_device


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "number", TuyaLanNumber, async_add_entities)


class TuyaLanNumber(TuyaLanEntity, NumberEntity):
    def __init__(self, coordinator, description, entry_title) -> None:
        super().__init__(coordinator, description, entry_title)
        opts = self.dp_options
        self._attr_native_min_value = opts.get("min", 0)
        self._attr_native_max_value = opts.get("max", 100)
        self._attr_native_step = opts.get("step", 1)
        self._attr_native_unit_of_measurement = description.get("unit_of_measurement")
        self._attr_device_class = description.get("device_class")

    @property
    def native_value(self):
        raw = self._value("number")
        return None if raw is None else scale_from_device(raw, self.dp_options)

    async def async_set_native_value(self, value: float) -> None:
        await self._set("number", scale_to_device(value, self.dp_options))

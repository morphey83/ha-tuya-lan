"""Sensor platform for Tuya-LAN profiles."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform, scale_from_device


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(hass, entry, "sensor", TuyaLanSensor, async_add_entities)


class TuyaLanSensor(TuyaLanEntity, SensorEntity):
    def __init__(self, coordinator, description, entry_title) -> None:  # noqa: ANN001
        super().__init__(coordinator, description, entry_title)
        self._attr_device_class = description.get("device_class")
        self._attr_state_class = description.get("state_class")
        self._attr_native_unit_of_measurement = description.get("unit_of_measurement")

    @property
    def native_value(self):
        raw = self._value("sensor")
        if raw is None:
            return None
        mapping = self.options.get("map")
        if isinstance(mapping, dict):
            return mapping.get(str(raw), raw)
        return scale_from_device(raw, self.options)

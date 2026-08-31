"""Binary sensor platform for Tuya-LAN profiles."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TuyaLanEntity
from .helpers import async_setup_profile_platform


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_profile_platform(
        hass, entry, "binary_sensor", TuyaLanBinarySensor, async_add_entities
    )


class TuyaLanBinarySensor(TuyaLanEntity, BinarySensorEntity):
    def __init__(self, coordinator, description, entry_title) -> None:  # noqa: ANN001
        super().__init__(coordinator, description, entry_title)
        self._attr_device_class = description.get("device_class")
        opts = self.options
        self._on_values = {str(v).lower() for v in opts.get("on_values", ["true", "1", "on"])}

    @property
    def is_on(self) -> bool | None:
        raw = self._value("sensor")
        if raw is None:
            return None
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in self._on_values

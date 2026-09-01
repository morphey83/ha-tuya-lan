"""Shared base class for all Tuya-LAN entities."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuyaLanCoordinator

_CATEGORY = {
    "config": EntityCategory.CONFIG,
    "diagnostic": EntityCategory.DIAGNOSTIC,
}


class TuyaLanEntity(CoordinatorEntity[TuyaLanCoordinator]):
    """Binds one profile entity description to the device coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TuyaLanCoordinator,
        description: dict[str, Any],
        entry_title: str,
    ) -> None:
        super().__init__(coordinator)
        self._desc = description
        self._dps_map: dict[str, str] = {k: str(v) for k, v in description["dps"].items()}
        key = description.get("key") or description["platform"]
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        name = description.get("name")
        self._attr_name = name  # None -> device name (has_entity_name)
        if description.get("icon"):
            self._attr_icon = description["icon"]
        if description.get("entity_category") in _CATEGORY:
            self._attr_entity_category = _CATEGORY[description["entity_category"]]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=entry_title,
            manufacturer="Tuya",
            model=coordinator.entry.data.get("product_key") or "Tuya LAN device",
        )

    # -- helpers for subclasses ------------------------------------------
    def _dp(self, role: str) -> str | None:
        return self._dps_map.get(role)

    def _value(self, role: str, default: Any = None) -> Any:
        dp = self._dp(role)
        if dp is None:
            return default
        return self.coordinator.dps.get(dp, default)

    async def _set(self, role: str, value: Any) -> None:
        dp = self._dp(role)
        if dp is None:
            raise KeyError(f"{self.entity_id}: no DP mapped for role {role!r}")
        await self.coordinator.async_set_dp(dp, value)

    @property
    def dp_options(self) -> dict[str, Any]:
        """Profile-supplied tuning for this entity (scale, map, limits, ...).

        Deliberately NOT named ``options`` - that clashes with HA's enum-sensor
        ``SensorEntity.options`` / ``SelectEntity.options``.
        """
        return self._desc.get("options") or {}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.available

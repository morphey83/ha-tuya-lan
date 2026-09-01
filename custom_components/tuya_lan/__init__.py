"""The Tuya-LAN integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_PROFILE,
    DOMAIN,
    PROFILE_RAW,
    SERVICE_DUMP_DPS,
    SERVICE_RELOAD_PROFILES,
    SERVICE_SET_DP,
)
from .coordinator import TuyaLanCoordinator
from .discovery import TuyaDiscovery
from .profiles import Profile, load_profiles
from .protocol.exceptions import TuyaKeyError

_LOGGER = logging.getLogger(__name__)

# Entity "platform" keyword in a profile -> Home Assistant platform.
# climate / humidifier are planned for a later release.
PLATFORMS_BY_ENTITY = {
    "binary_sensor": Platform.BINARY_SENSOR,
    "button": Platform.BUTTON,
    "cover": Platform.COVER,
    "fan": Platform.FAN,
    "light": Platform.LIGHT,
    "number": Platform.NUMBER,
    "select": Platform.SELECT,
    "sensor": Platform.SENSOR,
    "switch": Platform.SWITCH,
}
ALL_PLATFORMS = list(dict.fromkeys(PLATFORMS_BY_ENTITY.values()))


class RuntimeData:
    """Everything the platforms and services need for one config entry."""

    def __init__(self, coordinator: TuyaLanCoordinator, profile: Profile | None) -> None:
        self.coordinator = coordinator
        self.profile = profile


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    store = hass.data[DOMAIN]

    # The discovery object is created lazily and only *started* by the config
    # flow, so simply installing the integration touches no sockets.
    store.setdefault("discovery", TuyaDiscovery())

    if "profiles" not in store:
        store["profiles"] = await _async_load_profiles(hass)

    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_setup(hass, {})
    store = hass.data[DOMAIN]

    try:
        coordinator = TuyaLanCoordinator(hass, entry)
    except TuyaKeyError as err:
        raise ConfigEntryError(f"Invalid local key for {entry.title}: {err}") from err
    await coordinator.async_setup()

    profile_id = {**entry.data, **entry.options}.get(CONF_PROFILE)
    profile: Profile | None = None
    if profile_id and profile_id != PROFILE_RAW:
        profile = store["profiles"].get(profile_id)
        if profile is None:
            _LOGGER.warning(
                "config entry %s references unknown profile %r - loading as raw",
                entry.title,
                profile_id,
            )

    store.setdefault("entries", {})[entry.entry_id] = RuntimeData(coordinator, profile)

    _purge_orphan_entities(hass, entry, coordinator.device_id, profile)

    platforms = _entry_platforms(profile)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data[DOMAIN]
    runtime: RuntimeData | None = store.get("entries", {}).get(entry.entry_id)
    platforms = _entry_platforms(runtime.profile if runtime else None)
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded and runtime:
        await runtime.coordinator.async_shutdown()
        store["entries"].pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _purge_orphan_entities(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str, profile: Profile | None
) -> None:
    """Drop registry entities the current profile no longer defines.

    Switching profiles (e.g. Detect -> a real one) otherwise leaves the old
    entities behind as permanently "unavailable" ghosts.
    """
    registry = er.async_get(hass)
    expected = {
        f"{device_id}_{e.get('key') or e['platform']}"
        for e in (profile.entities if profile else [])
    }
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in expected:
            _LOGGER.debug("removing orphaned entity %s", reg_entry.entity_id)
            registry.async_remove(reg_entry.entity_id)


@callback
def _entry_platforms(profile: Profile | None) -> list[Platform]:
    if profile is None:
        return []
    wanted = {
        PLATFORMS_BY_ENTITY[e["platform"]]
        for e in profile.entities
        if e["platform"] in PLATFORMS_BY_ENTITY
    }
    return [p for p in ALL_PLATFORMS if p in wanted]


async def _async_load_profiles(hass: HomeAssistant) -> dict[str, Profile]:
    user_dir = Path(hass.config.path(DOMAIN, "profiles"))

    def _load() -> dict[str, Profile]:
        user_dir.mkdir(parents=True, exist_ok=True)
        return load_profiles(user_dir)

    return await hass.async_add_executor_job(_load)


# --- services -------------------------------------------------------------------
_SET_DP_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("dp"): vol.Any(cv.string, cv.positive_int),
        vol.Required("value"): vol.Any(bool, int, float, str),
    }
)
_DUMP_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


@callback
def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_DP):
        return

    def _find_coordinator(device_id: str) -> TuyaLanCoordinator:
        for runtime in hass.data[DOMAIN].get("entries", {}).values():
            if runtime.coordinator.device_id == device_id:
                return runtime.coordinator
        raise HomeAssistantError(f"No Tuya-LAN device configured with id {device_id!r}")

    async def _set_dp(call: ServiceCall) -> None:
        coordinator = _find_coordinator(call.data["device_id"])
        await coordinator.async_set_dp(str(call.data["dp"]), call.data["value"])

    async def _dump_dps(call: ServiceCall) -> ServiceResponse:
        coordinator = _find_coordinator(call.data["device_id"])
        dps = await coordinator.async_dump_dps()
        return {"device_id": coordinator.device_id, "dps": dps}

    async def _reload_profiles(call: ServiceCall) -> None:
        hass.data[DOMAIN]["profiles"] = await _async_load_profiles(hass)
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, SERVICE_SET_DP, _set_dp, schema=_SET_DP_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_DPS,
        _dump_dps,
        schema=_DUMP_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_PROFILES, _reload_profiles, schema=vol.Schema({})
    )

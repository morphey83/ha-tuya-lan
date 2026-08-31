"""Config & options flow for Tuya-LAN."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PRODUCT_KEY,
    CONF_PROFILE,
    CONF_PROTOCOL_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_VERSION,
    DOMAIN,
    PROFILE_DETECT,
    PROFILE_RAW,
    SUPPORTED_VERSIONS,
)
from .discovery import DiscoveredDevice, TuyaDiscovery
from .profiles import Profile, load_profiles, suggest_profile
from .protocol import TuyaDevice
from .protocol.exceptions import TuyaProtocolError

_LOGGER = logging.getLogger(__name__)

_MANUAL = "manual"


def _version_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(SUPPORTED_VERSIONS), mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


class TuyaLanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guided setup: pick a discovered device (or enter it), key, and profile."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, DiscoveredDevice] = {}
        self._data: dict[str, Any] = {}
        self._detected_dps: set[str] = set()

    # -- step: choose a device ------------------------------------------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        discovery: TuyaDiscovery | None = self.hass.data.get(DOMAIN, {}).get("discovery")
        if discovery is None:
            discovery = TuyaDiscovery()
            self.hass.data.setdefault(DOMAIN, {})["discovery"] = discovery
        self._discovered = await discovery.async_scan(timeout=6.0)

        configured = {entry.data.get(CONF_DEVICE_ID) for entry in self._async_current_entries()}
        choices = {
            dev_id: f"{dev.address}  ·  {dev_id[:8]}…  ·  v{dev.version}"
            for dev_id, dev in sorted(self._discovered.items())
            if dev_id not in configured
        }
        choices[_MANUAL] = "➕  Enter a device manually"

        if user_input is not None:
            selected = user_input["device"]
            if selected == _MANUAL:
                return await self.async_step_manual()
            dev = self._discovered[selected]
            self._data.update(
                {
                    CONF_DEVICE_ID: dev.device_id,
                    CONF_HOST: dev.address,
                    CONF_PORT: DEFAULT_PORT,
                    CONF_PROTOCOL_VERSION: dev.version,
                    CONF_PRODUCT_KEY: dev.product_key,
                }
            )
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("device"): vol.In(choices)}),
            description_placeholders={"count": str(len(choices) - 1)},
        )

    # -- step: manual entry -------------------------------------------------
    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(
                {
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID].strip(),
                    CONF_HOST: user_input[CONF_HOST].strip(),
                    CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                    CONF_PROTOCOL_VERSION: user_input[CONF_PROTOCOL_VERSION],
                    CONF_LOCAL_KEY: user_input[CONF_LOCAL_KEY].strip(),
                }
            )
            return await self.async_step_credentials(from_manual=True)

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_LOCAL_KEY): str,
                vol.Required(CONF_PROTOCOL_VERSION, default=DEFAULT_VERSION): _version_selector(),
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema)

    # -- step: local key + connectivity test -------------------------------
    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None, *, from_manual: bool = False
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None or from_manual:
            if user_input:
                self._data[CONF_LOCAL_KEY] = user_input[CONF_LOCAL_KEY].strip()
                self._data[CONF_PROTOCOL_VERSION] = user_input.get(
                    CONF_PROTOCOL_VERSION, self._data.get(CONF_PROTOCOL_VERSION, DEFAULT_VERSION)
                )

            await self.async_set_unique_id(self._data[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()

            ok, dps, err = await _probe(self._data)
            if ok:
                self._detected_dps = set(dps)
                return await self.async_step_profile()
            errors["base"] = err or "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCAL_KEY, default=self._data.get(CONF_LOCAL_KEY, "")): str,
                vol.Required(
                    CONF_PROTOCOL_VERSION,
                    default=self._data.get(CONF_PROTOCOL_VERSION, DEFAULT_VERSION),
                ): _version_selector(),
            }
        )
        return self.async_show_form(
            step_id="credentials",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_id": self._data.get(CONF_DEVICE_ID, "?"),
                "host": self._data.get(CONF_HOST, "?"),
            },
        )

    # -- step: pick a profile ---------------------------------------------
    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        profiles: dict[str, Profile] = self.hass.data.get(DOMAIN, {}).get(
            "profiles"
        ) or await self.hass.async_add_executor_job(load_profiles)

        suggestion = suggest_profile(
            profiles,
            product_key=self._data.get(CONF_PRODUCT_KEY),
            dps=self._detected_dps,
            version=self._data.get(CONF_PROTOCOL_VERSION),
        )

        options: dict[str, str] = {}
        if suggestion:
            options[suggestion.id] = f"✓ {suggestion.name}  (best match)"
        for pid, prof in sorted(profiles.items()):
            options.setdefault(pid, prof.name)
        options[PROFILE_DETECT] = "🔎  Detect entities from the live data points"
        options[PROFILE_RAW] = "⚙️  Raw — no entities, just services & events"

        if user_input is not None:
            choice = user_input[CONF_PROFILE]
            if choice == PROFILE_DETECT:
                built = _autobuild_profile(self._data[CONF_DEVICE_ID], self._detected_dps)
                await self.hass.async_add_executor_job(
                    _persist_profile, self.hass.config.path(DOMAIN, "profiles"), built
                )
                self.hass.data.setdefault(DOMAIN, {}).setdefault("profiles", {})[built.id] = built
                choice_id = built.id
            else:
                choice_id = choice
            self._data[CONF_PROFILE] = choice_id
            title = user_input.get("title") or f"Tuya {self._data[CONF_DEVICE_ID][:8]}"
            return self.async_create_entry(title=title, data=self._data)

        return self.async_show_form(
            step_id="profile",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PROFILE, default=suggestion.id if suggestion else PROFILE_DETECT
                    ): vol.In(options),
                    vol.Optional("title", default=f"Tuya {self._data[CONF_DEVICE_ID][:8]}"): str,
                }
            ),
            description_placeholders={"dps": ", ".join(sorted(self._detected_dps)) or "none"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> TuyaLanOptionsFlow:
        return TuyaLanOptionsFlow(entry)


class TuyaLanOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        profiles = self.hass.data.get(DOMAIN, {}).get("profiles", {})
        current = {**self.entry.data, **self.entry.options}
        options = {pid: prof.name for pid, prof in sorted(profiles.items())}
        options[PROFILE_RAW] = "Raw — no entities"

        schema = vol.Schema(
            {
                vol.Required(CONF_LOCAL_KEY, default=current.get(CONF_LOCAL_KEY, "")): str,
                vol.Required(
                    CONF_PROTOCOL_VERSION,
                    default=current.get(CONF_PROTOCOL_VERSION, DEFAULT_VERSION),
                ): _version_selector(),
                vol.Required(CONF_PROFILE, default=current.get(CONF_PROFILE, PROFILE_RAW)): vol.In(
                    options
                ),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=3600, step=5, unit_of_measurement="s")
                ),
                vol.Optional(CONF_HOST, default=current.get(CONF_HOST, "")): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


# --- helpers -------------------------------------------------------------------
async def _probe(data: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
    device = TuyaDevice(
        device_id=data[CONF_DEVICE_ID],
        address=data[CONF_HOST],
        local_key=data[CONF_LOCAL_KEY],
        version=data.get(CONF_PROTOCOL_VERSION, DEFAULT_VERSION),
        port=data.get(CONF_PORT, DEFAULT_PORT),
    )
    try:
        await device.connect()
        dps = await device.status()
        return True, dps, None
    except TuyaProtocolError as err:
        text = str(err).lower()
        if "key" in text or "hmac" in text or "negotiat" in text:
            return False, {}, "invalid_key"
        return False, {}, "cannot_connect"
    finally:
        await device.close()


def _persist_profile(profiles_dir: str, profile: Profile) -> None:
    import os

    import yaml

    os.makedirs(profiles_dir, exist_ok=True)
    doc = {
        "id": profile.id,
        "name": profile.name,
        "match": profile.match or {},
        "entities": profile.entities,
    }
    path = os.path.join(profiles_dir, f"{profile.id}.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Auto-generated by Tuya-LAN 'Detect'. Edit freely, then call\n")
        fh.write("# service: tuya_lan.reload_profiles\n")
        yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)


def _autobuild_profile(device_id: str, dps: set[str]) -> Profile:
    """Turn a raw DP dump into a best-effort profile the user can refine later."""
    entities: list[dict[str, Any]] = []
    for dp in sorted(dps, key=lambda x: int(x) if x.isdigit() else 999):
        entities.append(
            {
                "platform": "sensor",
                "key": f"dp{dp}",
                "name": f"DP {dp}",
                "dps": {"sensor": dp},
                "entity_category": "diagnostic",
            }
        )
    # DP 1 is almost always the main switch on Tuya devices.
    if "1" in dps:
        entities.insert(
            0, {"platform": "switch", "key": "switch", "name": None, "dps": {"switch": "1"}}
        )
    return Profile(
        id=f"detected_{device_id[:12]}",
        name=f"Detected ({device_id[:8]})",
        entities=entities,
        match={},
        source="user",
    )

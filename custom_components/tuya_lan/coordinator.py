"""Keeps one persistent connection to a Tuya device and fans out DP updates."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_NODE_ID,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PROTOCOL_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    EVENT_DP_UPDATE,
    RECONNECT_INTERVAL,
)
from .protocol import TuyaDevice
from .protocol.exceptions import TuyaConnectionError, TuyaProtocolError

_LOGGER = logging.getLogger(__name__)


class TuyaLanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One per config entry / device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        data = {**entry.data, **entry.options}
        self.entry = entry
        self.device_id: str = data[CONF_DEVICE_ID]
        poll = data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.device_id}",
            update_interval=None if poll <= 0 else timedelta(seconds=float(poll)),
        )
        self.dps: dict[str, Any] = {}
        self.available = False
        self._device = TuyaDevice(
            device_id=self.device_id,
            address=data[CONF_HOST],
            local_key=data[CONF_LOCAL_KEY],
            version=data.get(CONF_PROTOCOL_VERSION, "3.3"),
            port=data.get(CONF_PORT, DEFAULT_PORT),
            gateway_id=data.get(CONF_GATEWAY_ID),
            node_id=data.get(CONF_NODE_ID),
            listener=self._on_push,
        )
        self._watchdog: asyncio.Task[None] | None = None
        self._closing = False

    # -- lifecycle ---------------------------------------------------------
    async def async_setup(self) -> None:
        connected = await self._connect()
        # Seed coordinator.data so entities render immediately, even push-only.
        self.async_set_updated_data(dict(self.dps))
        if not connected:
            _LOGGER.warning(
                "%s: could not reach device during setup; will keep retrying", self.device_id
            )
        self._watchdog = self.hass.async_create_background_task(
            self._watchdog_loop(), name=f"{DOMAIN}-watchdog-{self.device_id}"
        )

    async def async_shutdown(self) -> None:  # type: ignore[override]
        self._closing = True
        if self._watchdog:
            self._watchdog.cancel()
        await self._device.close()
        await super().async_shutdown()

    async def _connect(self) -> bool:
        try:
            await self._device.connect()
            self.dps = await self._device.status()
            self.available = True
            _LOGGER.debug("%s: connected, %d DPs", self.device_id, len(self.dps))
            return True
        except TuyaProtocolError as err:
            self.available = False
            _LOGGER.debug("%s: connect failed: %s", self.device_id, err)
            return False

    async def _watchdog_loop(self) -> None:
        was_connected = True
        while not self._closing:
            await asyncio.sleep(RECONNECT_INTERVAL)
            if self._closing:
                return
            if self._device.connected:
                continue
            if was_connected:
                _LOGGER.debug(
                    "%s: connection lost, retrying every %ss",
                    self.device_id,
                    RECONNECT_INTERVAL,
                )
            was_connected = False
            if await self._connect():
                was_connected = True
                _LOGGER.debug("%s: reconnected", self.device_id)
                self.async_set_updated_data(dict(self.dps))

    # -- polling ---------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug(
            "%s: poll (interval=%s, connected=%s)",
            self.device_id,
            self.update_interval,
            self._device.connected,
        )
        last: Exception | None = None
        for _attempt in (1, 2):  # one transient retry (with a reconnect) before failing
            if not self._device.connected and not await self._connect():
                last = TuyaConnectionError(f"{self.device_id} is unreachable")
                continue
            try:
                fresh = await self._device.status()
            except TuyaConnectionError as err:
                self._device.mark_dead()  # force a reconnect on the retry / next cycle
                last = err
                continue
            except TuyaProtocolError as err:
                last = err
                continue
            self.available = True
            self.dps.update(fresh)
            return dict(self.dps)
        self.available = False
        raise UpdateFailed(str(last))

    # -- push ----------------------------------------------------------
    @callback
    def _on_push(self, message: dict[str, Any]) -> None:
        dps = message.get("dps") or {}
        if not dps:
            return
        _LOGGER.debug("%s: push update, %d DP(s): %s", self.device_id, len(dps), list(dps))
        self.dps.update({str(k): v for k, v in dps.items()})
        self.available = True
        self.async_set_updated_data(dict(self.dps))
        self.hass.bus.async_fire(
            EVENT_DP_UPDATE,
            {
                "device_id": self.device_id,
                "entry_id": self.entry.entry_id,
                "dps": dps,
                "ts": time.time(),
            },
        )

    # -- writes ------------------------------------------------------
    async def async_set_dp(self, dp: str | int, value: Any) -> None:
        await self.async_set_dps({str(dp): value})

    async def async_set_dps(self, dps: dict[str, Any]) -> None:
        if not self._device.connected and not await self._connect():
            raise TuyaConnectionError(f"{self.device_id} is unreachable")
        result = await self._device.set_dps(dps)
        # Optimistic local echo; the device usually pushes a STATUS right after.
        self.dps.update(dps)
        if result:
            self.dps.update(result)
        self.async_set_updated_data(dict(self.dps))

    async def async_dump_dps(self) -> dict[str, Any]:
        if not self._device.connected and not await self._connect():
            raise TuyaConnectionError(f"{self.device_id} is unreachable")
        return await self._device.status()

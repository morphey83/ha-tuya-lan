"""LAN discovery of Tuya devices, wrapped for Home Assistant.

A single :class:`TuyaDiscovery` instance is shared by the whole integration so
the "add device" screen can list units that are not configured yet. The actual
socket + crypto handling lives in :mod:`.protocol.discovery`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from .protocol.discovery import (
    DiscoveredDevice,
    open_listeners,
    to_device,
)

_LOGGER = logging.getLogger(__name__)

__all__ = ["DiscoveredDevice", "TuyaDiscovery"]


class TuyaDiscovery:
    """Owns the UDP listeners and a rolling cache of announcements."""

    def __init__(self) -> None:
        self._transports: list[asyncio.BaseTransport] = []
        self.devices: dict[str, DiscoveredDevice] = {}
        self._callbacks: set[Callable[[DiscoveredDevice], None]] = set()
        self._started = False

    def async_add_listener(
        self, cb: Callable[[DiscoveredDevice], None]
    ) -> Callable[[], None]:
        self._callbacks.add(cb)
        return lambda: self._callbacks.discard(cb)

    async def async_start(self) -> None:
        if self._started:
            return
        self._started = True
        self._transports = await open_listeners(self._handle_payload)
        _LOGGER.debug("Tuya discovery listening on %d socket(s)", len(self._transports))

    async def async_stop(self) -> None:
        for transport in self._transports:
            with contextlib.suppress(Exception):
                transport.close()
        self._transports.clear()
        self._started = False

    async def async_scan(self, timeout: float = 8.0) -> dict[str, DiscoveredDevice]:
        await self.async_start()
        await asyncio.sleep(timeout)
        return dict(self.devices)

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        device = to_device(payload)
        if device is None:
            return
        existing = self.devices.get(device.device_id)
        self.devices[device.device_id] = device
        if existing is None or existing.address != device.address:
            for cb in list(self._callbacks):
                with contextlib.suppress(Exception):
                    cb(device)

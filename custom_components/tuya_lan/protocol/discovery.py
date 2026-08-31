"""Low-level UDP discovery of Tuya devices (no Home Assistant dependency)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import message as M
from .crypto import UDP_KEY, decrypt_ecb

UDP_PORTS = (6666, 6667, 6699)


@dataclass(slots=True)
class DiscoveredDevice:
    device_id: str
    address: str
    version: str
    product_key: str | None = None
    encrypted: bool = True
    raw: dict[str, Any] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)


def decrypt_broadcast(data: bytes) -> dict[str, Any] | None:
    """Return the JSON announcement carried by a raw UDP datagram, or None."""
    if data[:1] == b"{":
        with contextlib.suppress(ValueError):
            return json.loads(data)
    try:
        messages, _ = M.unpack_stream(data, key=UDP_KEY, use_hmac=False)
    except Exception:  # noqa: BLE001
        messages = []
    for msg in messages:
        body = msg.payload
        if body[:1] == b"{":
            with contextlib.suppress(ValueError):
                return json.loads(body)
        with contextlib.suppress(Exception):
            dec = decrypt_ecb(UDP_KEY, body)
            if dec[:1] == b"{":
                return json.loads(dec)
    with contextlib.suppress(Exception):
        dec = decrypt_ecb(UDP_KEY, data)
        if dec[:1] == b"{":
            return json.loads(dec)
    return None


def to_device(payload: dict[str, Any]) -> DiscoveredDevice | None:
    gw_id = payload.get("gwId") or payload.get("id")
    ip = payload.get("ip")
    if not gw_id or not ip:
        return None
    return DiscoveredDevice(
        device_id=str(gw_id),
        address=str(ip),
        version=str(payload.get("version") or "3.3"),
        product_key=payload.get("productKey") or payload.get("productid"),
        encrypted=bool(payload.get("encrypt", True)),
        raw=payload,
    )


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._cb = cb

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        payload = decrypt_broadcast(data)
        if payload:
            self._cb(payload)


async def open_listeners(
    on_payload: Callable[[dict[str, Any]], None],
) -> list[asyncio.BaseTransport]:
    loop = asyncio.get_running_loop()
    transports: list[asyncio.BaseTransport] = []
    reuse_port = hasattr(socket, "SO_REUSEPORT")
    for port in UDP_PORTS:
        with contextlib.suppress(OSError):
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _Proto(on_payload),
                local_addr=("0.0.0.0", port),  # noqa: S104
                reuse_port=reuse_port,
                allow_broadcast=True,
            )
            transports.append(transport)
    return transports


async def scan(timeout: float = 10.0) -> dict[str, DiscoveredDevice]:
    """Listen for ``timeout`` seconds and return every device heard."""
    devices: dict[str, DiscoveredDevice] = {}

    def _cb(payload: dict[str, Any]) -> None:
        dev = to_device(payload)
        if dev:
            devices[dev.device_id] = dev

    transports = await open_listeners(_cb)
    try:
        await asyncio.sleep(timeout)
    finally:
        for t in transports:
            with contextlib.suppress(Exception):
                t.close()
    return devices

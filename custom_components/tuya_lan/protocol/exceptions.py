"""Exceptions raised by the Tuya LAN protocol layer."""

from __future__ import annotations


class TuyaProtocolError(Exception):
    """Base class for all protocol errors."""


class TuyaConnectionError(TuyaProtocolError):
    """The TCP connection failed, dropped, or timed out."""


class TuyaDecodeError(TuyaProtocolError):
    """A frame could not be parsed or its checksum/tag did not verify."""


class TuyaKeyError(TuyaProtocolError):
    """The local key is missing, malformed, or rejected by the device."""


class TuyaResponseError(TuyaProtocolError):
    """The device answered with an application-level error payload."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code

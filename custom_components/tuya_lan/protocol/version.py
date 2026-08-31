"""Protocol-version helper."""

from __future__ import annotations

import contextlib
from enum import Enum


class ProtocolVersion(Enum):
    """Tuya LAN protocol versions we understand."""

    V31 = "3.1"
    V32 = "3.2"
    V33 = "3.3"
    V34 = "3.4"
    V35 = "3.5"

    def __str__(self) -> str:
        return self.value

    @property
    def number(self) -> float:
        return float(self.value)

    @property
    def header(self) -> bytes:
        """The 15-byte version header prepended to some payloads (>= 3.2)."""
        return self.value.encode("latin1") + b"\x00" * 12

    @property
    def uses_hmac(self) -> bool:
        """3.4 replaces the CRC32 trailer with an HMAC-SHA256 trailer (55AA frames).

        3.5 also authenticates, but via the GCM tag on 0x6699 frames, so this
        flag - which only governs 55AA parsing - stays False for it.
        """
        return 3.4 <= self.number < 3.5

    @property
    def uses_gcm(self) -> bool:
        """3.5 switches from AES-ECB framing to AES-GCM framing (prefix 0x6699)."""
        return self.number >= 3.5

    @property
    def needs_session(self) -> bool:
        """3.4+ negotiate a per-connection session key before any real traffic."""
        return self.number >= 3.4

    @classmethod
    def parse(cls, value: str | float | ProtocolVersion) -> ProtocolVersion:
        if isinstance(value, ProtocolVersion):
            return value
        text = str(value).strip().lstrip("vV")
        with contextlib.suppress(ValueError):
            text = f"{float(text):.1f}"
        for member in cls:
            if member.value == text:
                return member
        raise ValueError(f"Unsupported Tuya protocol version: {value!r}")
